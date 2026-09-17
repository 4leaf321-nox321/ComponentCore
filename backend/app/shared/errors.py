"""오류 규약 — 구조화 코드 + 반드시 로그를 남긴다.

**오류를 만드는 경로가 곧 로그를 남기는 경로다.** 핸들러를 거치지 않고 오류 응답을 만들
방법을 두지 않는다.

코드 형식: <PREFIX>-<MODULE>-<NNNN>  예) AJG-AUTH-0001
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.branding import ERROR_PREFIX
from app.shared.request_context import get_request_id

logger = logging.getLogger(__name__)


def code(module: str, number: int) -> str:
    """AJG-AUTH-0001 을 만든다. **문자열을 손으로 잇지 않는다.**"""
    return f"{ERROR_PREFIX}-{module.upper()}-{number:04d}"


_VALIDATION_MESSAGES = {
    "missing": "값이 빠졌습니다",
    "string_too_short": "값이 필요합니다",
    "string_too_long": "너무 깁니다",
    "string_pattern_mismatch": "쓸 수 없는 문자가 있습니다",
    "int_parsing": "정수여야 합니다",
    "float_parsing": "숫자여야 합니다",
    "bool_parsing": "예/아니오 값이어야 합니다",
    "value_error": "값이 올바르지 않습니다",
    "greater_than_equal": "너무 작습니다",
    "greater_than": "너무 작습니다",
    "less_than_equal": "너무 큽니다",
    "less_than": "너무 큽니다",
    "too_long": "너무 많습니다",
    "too_short": "개수가 모자랍니다",
}

_MAX_VALIDATION_ITEMS = 3


def describe_validation(errors: Sequence[Any]) -> str:
    """**어느 칸이 왜 틀렸는지 말한다.** 화면이 보여 주는 것은 message 하나다."""
    if not errors:
        return "요청 형식이 올바르지 않습니다."

    parts: list[str] = []
    for error in errors[:_MAX_VALIDATION_ITEMS]:
        location = [
            str(item) for item in error.get("loc", ()) if item not in ("body", "query")
        ]
        where = ""
        for index, item in enumerate(location):
            where += f"[{item}]" if item.isdigit() else (f".{item}" if index else item)

        kind = str(error.get("type"))
        message = str(error.get("msg", ""))
        reason = (
            message.removeprefix("Value error, ")
            if kind == "value_error" and message.startswith("Value error, ")
            else _VALIDATION_MESSAGES.get(kind, message)
        )
        parts.append(f"{where or '요청'} — {reason}")

    more = len(errors) - len(parts)
    summary = " / ".join(parts)
    return f"{summary} 외 {more}건" if more > 0 else summary


def _plain(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """검증 오류를 JSON 으로 낼 수 있는 형태로 — ctx 의 예외 객체가 직렬화에서 터지지 않게."""
    out: list[dict[str, Any]] = []
    for error in errors:
        item = dict(error)
        context = item.get("ctx")
        if isinstance(context, dict):
            item["ctx"] = {key: str(value) for key, value in context.items()}
        if "input" in item:
            try:
                json.dumps(item["input"])
            except (TypeError, ValueError):
                item["input"] = str(item["input"])
        out.append(item)
    return out


class AppError(Exception):
    """도메인 오류. status 는 HTTP 상태, code 는 사람이 검색할 수 있는 식별자."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


class NotFound(AppError):
    def __init__(self, code: str, message: str, **kw: Any) -> None:
        super().__init__(code, message, status=404, **kw)


class Conflict(AppError):
    def __init__(self, code: str, message: str, **kw: Any) -> None:
        super().__init__(code, message, status=409, **kw)


class Forbidden(AppError):
    def __init__(self, code: str, message: str, **kw: Any) -> None:
        super().__init__(code, message, status=403, **kw)


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(),
            "details": details or {},
        }
    }


_HTTP_MESSAGES = {
    405: "이 주소는 그 방식의 요청을 받지 않습니다. 서버가 옛 버전일 수 있습니다.",
    413: "파일이 너무 큽니다.",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        log = logger.warning if exc.status < 500 else logger.error
        log(
            "%s %s -> %s %s: %s",
            request.method,
            request.url.path,
            exc.status,
            exc.code,
            exc.message,
            extra={"details": exc.details},
        )
        return JSONResponse(
            status_code=exc.status, content=_body(exc.code, exc.message, exc.details)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = _plain(exc.errors())
        logger.warning("%s %s -> 422 validation: %s", request.method, request.url.path, errors)
        return JSONResponse(
            status_code=422,
            content=_body(
                code("COMMON", 422), describe_validation(errors), {"errors": errors}
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """프레임워크가 내는 오류도 **같은 봉투에 담는다.** 프론트의 오류 파서가 봉투를
        기대한다."""
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail else ""
        message = _HTTP_MESSAGES.get(exc.status_code) or detail or "요청을 처리할 수 없습니다."
        log = logger.warning if exc.status_code < 500 else logger.error
        log("%s %s -> %s http: %s", request.method, request.url.path, exc.status_code, message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(code("COMMON", exc.status_code), message),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("%s %s -> 500 unhandled", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_body(
                code("COMMON", 500),
                "서버 오류가 발생했습니다. 요청 ID를 관리자에게 알려주세요.",
            ),
        )
