"""요청 ID — 사용자 신고와 로그를 잇는 유일한 끈.

**순수 ASGI 미들웨어로 구현한다.** Starlette 의 BaseHTTPMiddleware 는 downstream 을 별도
태스크로 실행해서 ContextVar 가 엔드포인트와 예외 핸들러에 전파되지 않는다.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

HEADER = "X-Request-ID"
_HEADER_BYTES = HEADER.lower().encode()


def get_request_id() -> str:
    return _request_id.get()


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or {}).get(_HEADER_BYTES)
        rid = incoming.decode() if incoming else uuid.uuid4().hex[:12]
        token = _request_id.set(rid)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((_HEADER_BYTES, rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _request_id.reset(token)
