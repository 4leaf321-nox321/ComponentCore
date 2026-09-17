"""인증 의존성 — 모든 모듈이 쓰는 current_user.

app/modules/auth 가 아니라 shared 에 있는 이유: 모든 모듈이 현재 사용자를 필요로 하는데,
그때마다 auth 모듈을 직접 import 하면 모든 모듈이 auth 에 묶인다. 방향은 shared -> auth
한 쪽이다.
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.auth import security, services
from app.shared.access_log import USER_ID_SCOPE_KEY
from app.shared.errors import AppError, Forbidden, code

_UNAUTHENTICATED = "로그인이 필요합니다."


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        return None
    return header[7:].strip() or None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer(request)
    if token is None:
        raise AppError(code("AUTH", 100), _UNAUTHENTICATED, status=401)

    payload = security.decode_access_token(token)
    if payload is None:
        # 사유(만료·서명 불일치)는 응답에 싣지 않는다 — 공격자에게 힌트가 된다.
        raise AppError(code("AUTH", 102), "세션이 만료되었습니다.", status=401)

    signed_in = db.get(User, payload["sub"])
    if signed_in is None:
        raise Forbidden(code("AUTH", 2), "삭제된 계정입니다. 관리자에게 문의하세요.")
    services.ensure_can_sign_in(signed_in)
    request.scope[USER_ID_SCOPE_KEY] = signed_in.id
    return signed_in


def require_system_admin(user: User = Depends(current_user)) -> User:
    if not user.is_system_admin:
        raise Forbidden(code("AUTH", 103), "권한이 없습니다.")
    return user
