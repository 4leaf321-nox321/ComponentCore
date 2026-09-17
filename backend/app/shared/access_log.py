"""접근 로그 미들웨어 — 상태를 바꾸는 요청과 로그인만 남긴다.

기록은 요청 처리와 별개 세션에서 한다. 로그를 남기다 실패해도 사용자의 요청은 성공해야 한다.
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.database import SessionLocal
from app.modules.audit.models import AccessLog
from app.shared.request_context import get_request_id

logger = logging.getLogger(__name__)

#: 인증 의존성이 scope 에 남기는 키. 미들웨어는 인증보다 **바깥**에 있어서 스스로는 누가
#: 불렀는지 알 수 없다.
USER_ID_SCOPE_KEY = "app_user_id"

_RECORDED_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

#: 남기지 않을 경로. **폴링 경로를 만들면 여기에 더한다** — 안 더하면 표가 그 한 줄로 찬다.
_SKIP = ("/api/health",)


def _action(path: str) -> str:
    if path.endswith("/auth/login"):
        return "LOGIN"
    if path.endswith("/auth/logout"):
        return "LOGOUT"
    return "API"


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", ""))
        status_holder = {"status": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message["status"])
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if not path.startswith("/api/") or path in _SKIP or method not in _RECORDED_METHODS:
            return

        try:
            headers = dict(scope.get("headers") or {})
            client = scope.get("client")
            # 세션 공장을 app.state 에서 가져온다 — 테스트가 자기 DB 로 바꿔 끼운다.
            factory = getattr(scope["app"].state, "session_factory", SessionLocal)
            db = factory()
            try:
                db.add(
                    AccessLog(
                        user_id=scope.get(USER_ID_SCOPE_KEY),
                        action=_action(path),
                        path=path[:300],
                        method=method,
                        status_code=status_holder["status"],
                        request_id=get_request_id(),
                        client_ip=client[0] if client else None,
                        user_agent=(headers.get(b"user-agent") or b"").decode()[:300] or None,
                    )
                )
                db.commit()
            finally:
                db.close()
        except Exception:
            logger.exception("접근 로그 기록 실패 (%s %s)", method, path)
