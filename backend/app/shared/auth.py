"""인증 의존성 — 모든 모듈이 쓰는 current_user.

app/modules/auth 가 아니라 shared 에 있는 이유: 모든 모듈이 현재 사용자를 필요로 하는데,
그때마다 auth 모듈을 직접 import 하면 모든 모듈이 auth 에 묶인다. 방향은 shared -> auth
한 쪽이다.
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.auth import security, services
from app.shared import scopes
from app.shared.access_log import USER_ID_SCOPE_KEY
from app.shared.errors import AppError, Forbidden, code
from app.shared.request_context import set_actor_token, set_viewer

_UNAUTHENTICATED = "로그인이 필요합니다."

#: 포털 게이트웨이가 그 사람 대신 들고 온 토큰의 표시(`auth.sso`). 그 사람의 권한으로 일하되
#: **관리자 권한은 내려놓는다** — AI 가 채팅으로 계정 · 서버 설정 · 남의 작업에 손대지 않게.
PORTAL_SCOPE = "portal"


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        return None
    return header[7:].strip() or None


def _is_write(request: Request) -> bool:
    """쓰기인가. POST 지만 아무것도 안 바꾸는 경로(레시피 검증 · 미리보기 · 내보내기 ·
    SPARQL …)는 조립 지점(`main.register_platform`)이 `shared/scopes` 에 읽기로 등록한다 —
    읽기 토큰으로 되어야 AI 가 그려 보고 물어본다."""
    return not scopes.is_reading(request.method, request.url.path)


def _enforce_token_scope(request: Request, token_scopes: list[str]) -> None:
    """**기계 자격만 범위로 막는다** — 사람 세션에는 안 건다(그 사람의 권한이 이미 한계다).

    CompCore 의 `read` · `write` 는 그대로 전부를 열고, StandardPlatform 에서 들인 좁은 범위
    (`ontology:write` · `objects:write` · `core:read`)는 등록된 경로만 연다(`shared/scopes`,
    ADR 0008). 좁은 범위만 든 토큰(바깥 시스템의 `core:read`)은 그 자리 밖을 못 읽는다."""
    path = request.url.path
    if _is_write(request):
        needed = scopes.needed_scope(path)
        if "write" in token_scopes or (needed is not None and needed in token_scopes):
            return
        raise Forbidden(
            code("AUTH", 106),
            "이 토큰에는 write 범위가 없습니다."
            + (f" 이 경로는 {needed} 범위로도 고칠 수 있습니다." if needed else ""),
            details={"granted": token_scopes, "needed": needed},
        )
    if "write" in token_scopes or scopes.may_read(path, token_scopes):
        return
    raise Forbidden(
        code("AUTH", 104),
        "이 토큰에는 이 경로를 읽을 범위가 없습니다(read 또는 그 자리의 좁은 범위).",
        details={"path": path, "granted": token_scopes},
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer(request)
    if token is None:
        raise AppError(code("AUTH", 100), _UNAUTHENTICATED, status=401)

    if token.startswith(security.pat_prefix()):
        found = services.resolve_pat(db, token)
        if found is None:
            raise AppError(code("AUTH", 101), "토큰이 유효하지 않습니다.", status=401)
        user, pat = found
        _enforce_token_scope(request, list(pat.scopes or []))
        if PORTAL_SCOPE in (pat.scopes or []):
            _portal_limits(request, user)
        request.state.token_name = pat.name
        request.state.token_scopes = list(pat.scopes or [])
        # **감사에 토큰 이름을 남긴다**(StandardPlatform 과 같다) — 소유자만 남기면 사람이 넣은
        # 것과 기계가 넣은 것이 구별되지 않는다.
        set_actor_token(pat.name)
        set_viewer(user.id, admin=user.is_system_admin)
        request.scope[USER_ID_SCOPE_KEY] = user.id
        return user

    payload = security.decode_access_token(token)
    if payload is None:
        # 사유(만료·서명 불일치)는 응답에 싣지 않는다 — 공격자에게 힌트가 된다.
        raise AppError(code("AUTH", 102), "세션이 만료되었습니다.", status=401)

    signed_in = db.get(User, payload["sub"])
    if signed_in is None:
        raise Forbidden(code("AUTH", 2), "삭제된 계정입니다. 관리자에게 문의하십시오.")
    services.ensure_can_sign_in(signed_in)
    set_viewer(signed_in.id, admin=signed_in.is_system_admin)
    request.scope[USER_ID_SCOPE_KEY] = signed_in.id
    return signed_in


def _portal_limits(request: Request, user: User) -> None:
    """포털 위임 토큰 — 계정 설정(토큰 · 비밀번호 · 프로필)을 바꾸지 못하고, 관리자도 이
    요청에서는 일반 사용자로 본다. 토큰을 새로 만들 수 있으면 `portal` 없는 토큰으로 울타리를
    넘는다.

    관리자 표시는 **이 요청의 세션에서만** 내린다 — `set_committed_value` 는 바뀐 것으로 치지
    않아 커밋해도 DB 에 쓰이지 않는다. 관리자 검사가 여러 모듈에 흩어져 있어도 한 곳에서
    끝난다."""
    if request.url.path.startswith("/api/auth/") and _is_write(request):
        raise Forbidden(
            code("AUTH", 109), "포털 위임 토큰으로는 계정 설정을 변경할 수 없습니다."
        )
    if user.is_system_admin:
        set_committed_value(user, "is_system_admin", False)


def granted_scopes(request: Request) -> list[str]:
    """이 요청이 들고 온 **토큰의 범위.** 사람 세션이면 빈 목록이다.

    빈 목록을 「아무것도 못 한다」 로 읽으면 안 된다 — 사람 세션에는 범위를 걸지 않는다(그
    사람의 권한이 이미 한계다). 범위는 **기계 자격에만** 거는 울타리다."""
    return list(getattr(request.state, "token_scopes", []) or [])


def require_system_admin(request: Request, user: User = Depends(current_user)) -> User:
    if PORTAL_SCOPE in granted_scopes(request):
        raise Forbidden(
            code("AUTH", 104), "포털 위임 토큰으로는 관리자 기능을 사용할 수 없습니다."
        )
    if not user.is_system_admin:
        raise Forbidden(code("AUTH", 103), "권한이 없습니다.")
    return user
