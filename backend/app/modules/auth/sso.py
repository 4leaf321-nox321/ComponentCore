"""HWAX 포털 연계 — **포털 SSO(jwt-handoff)** 와 **MCP 게이트웨이의 사용자 위임 창구**.

포털에 붙은 다른 앱(ReportArchive · heax-hub …)과 **같은 계약**이다 — 포털 쪽은 설정 몇
줄이고 CompCore 전용 코드는 없다. 둘 다 **설정이 비면 꺼진다**(404) — 단독 설치는 아무것도
열지 않는다.

    POST /api/auth/portal-callback   타일 클릭 — 포털 화면이 폼(`token`)으로 자동 POST
    POST /api/auth/portal-exchange   주소로 바로 들어온 사람 — 포털 세션으로 받은 토큰 교환
    POST /api/auth/sso               게이트웨이 — 그 사람의 CompCore 토큰(없으면 계정 생성)
    POST /api/auth/sso/verify        게이트웨이 — 비밀만 확인(204)
    POST /api/auth/sso/revoke        게이트웨이 — 그 사람 · 그 client 의 위임 토큰 회수

**포털 SSO** — 포털이 90초짜리 launch 토큰(RS256, `kid`, `aud`, `iss`, `scope=launch`, `jti`
1회용)을 준다. 포털 JWKS 로 검증하고 사람을 찾아(없으면 만든다) **비밀번호 로그인과 같은
세션**(refresh 쿠키 + access 토큰)을 준다. 콜백은 쿠키만 심고 화면으로 보낸다 — 토큰을 URL 에
싣지 않는다(화면이 뜰 때 refresh 쿠키로 들어온다).

**위임 창구** — 포털 게이트웨이는 브라우저 없이 서버끼리 부른다. 공유 비밀 + 포털이 확인한
이메일로 **그 사람 이름의 개인 토큰**(2일, client 마다 하나, 다시 받으면 직전 것을 지운다)을
준다.
게이트웨이는 그 토큰으로 MCP 를 부르고, CompCore 는 **그 사람의 권한**으로 처리한다 — 공유
비밀은 이 창구에서만 통하고, 모든 API 가 「사용자 헤더」 를 믿을 일이 없다. 토큰에는 `portal`
범위가 붙어 **관리자 기능은 막힌다**(AI 가 채팅으로 계정 · 서버 설정에 손대지 않게 —
`shared.auth`). 포털 NEW-SYSTEM-ASK 6규칙: 상수 시간 비교 · 비밀 없으면 404 · 불일치 401 ·
이메일 형식 아니면 401 · 모르는 이메일 생성 · 같은 client 직전 토큰 회수 + revoke 짝.
"""

from __future__ import annotations

import hmac
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote, urlencode

import jwt
from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.modules.accounts.models import User
from app.modules.auth import security, services
from app.modules.auth.cookies import set_refresh_cookie, url_prefix
from app.modules.auth.models import PersonalAccessToken, SsoUsedJti
from app.modules.auth.schemas import LoginResponse
from app.shared.errors import AppError, Forbidden, NotFound, code

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

#: 포털과 시계가 몇 초 어긋나도 받는다. launch 토큰이 90초라 크게 잡으면 재생 창만 넓어진다.
LEEWAY_S = 30
#: 위임 토큰 — 게이트웨이가 12시간 캐시하므로 짧게. 새어 나간 토큰의 수명이 곧 이것이다.
DELEGATE_DAYS = 2
DELEGATE_NAME = "HWAX 포털 게이트웨이"
#: 위임 토큰의 범위 — `portal` 은 「포털이 대신 들고 온 것」 표시다(관리자 기능을 막는다).
DELEGATE_SCOPES = ["read", "write", "portal"]
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SsoError(Exception):
    """화면 · 게이트웨이에 그대로 보여 줄 실패. `status` 는 교환 API 가 돌려줄 코드."""

    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


# ── 사람 찾기 ─────────────────────────────────────────────────────────────────


def resolve_user(
    db: Session, *, email: str, name: str = "", login_id: str = "", jit_create: bool
) -> tuple[User, bool]:
    """SSO 가 준 사람 → CompCore 계정. **LoginId → 이메일(대소문자 무시)** 순서로 찾고, 없으면
    (`jit_create`) 만든다. 반환 (사용자, 새로 만듦).

    이메일로 찾은 계정에는 LoginId 를 새긴다 — 다음부터 그것으로 찾아, 사내에서 메일 주소가
    바뀌어도 같은 사람이 계정 둘이 되지 않는다(LoginId 로 찾았는데 메일이 바뀌었으면, 새 메일을
    아무도 안 쓸 때 따라간다). 정지 · 삭제된 계정은 SSO 로도 못 들어온다 — 퇴사 · 정지는
    IdP 가 아니라 우리가 판단한다."""
    email = (email or "").strip().lower()
    login_id = (login_id or "").strip()
    if not _EMAIL.match(email):
        raise SsoError("SSO 응답에 올바른 이메일이 없습니다.")
    user: User | None = None
    if login_id:
        user = db.scalar(select(User).where(User.sso_login_id == login_id))
    if user is None:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is not None:
        if not user.can_sign_in:
            raise SsoError(
                "정지되었거나 삭제된 계정입니다. 관리자에게 문의하십시오.", status=403
            )
        if login_id and not user.sso_login_id:
            user.sso_login_id = login_id
        if user.email.lower() != email and not db.scalar(
            select(User.id).where(func.lower(User.email) == email)
        ):
            logger.info("sso: 메일 주소 변경 %s → %s", user.email, email)
            user.email = email
        db.commit()
        return user, False
    if not jit_create:
        raise SsoError(
            "CompCore 계정이 없습니다. 관리자에게 계정 생성을 요청하십시오.", status=403
        )
    user = User(
        email=email,
        # 비밀번호로는 못 들어온다(아무도 모르는 값) — 필요하면 관리자가 「비밀번호 초기화」.
        password_hash=security.hash_password(secrets.token_urlsafe(32)),
        display_name=(name or "").strip()[:100] or email.split("@")[0],
        status="active",
        sso_login_id=login_id or None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 같은 사람이 동시에 처음 들어왔다(탭 두 개 · 게이트웨이와 화면) — 먼저 만든 것을 쓴다.
        db.rollback()
        return resolve_user(db, email=email, name=name, login_id=login_id, jit_create=False)
    db.refresh(user)
    logger.info("sso: 계정 생성 %s", email)
    return user, True


# ── 포털 SSO(jwt-handoff) ─────────────────────────────────────────────────────

_jwk: tuple[str, jwt.PyJWKClient] | None = None


def _signing_key(token: str) -> Any:
    """이 토큰의 `kid` 에 맞는 포털 공개키 — 5분 캐시, 모르는 kid 면 다시 받는다(키 교체를
    재기동 없이 따라간다)."""
    global _jwk
    url = get_settings().portal_jwks_url.strip()
    if _jwk is None or _jwk[0] != url:
        _jwk = (url, jwt.PyJWKClient(url, cache_keys=True, lifespan=300, timeout=5))
    try:
        return _jwk[1].get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientError as failure:
        raise SsoError(f"포털 공개키로 확인하지 못했습니다({failure}).") from failure
    except jwt.DecodeError as failure:
        raise SsoError("포털 토큰의 형식이 올바르지 않습니다.") from failure


def _consume(db: Session, claims: dict[str, Any]) -> None:
    """`jti` 를 한 번만 — 중복 삽입이 실패하면 재생이다. leeway 동안은 만료 뒤에도 decode 가
    통과하므로 그만큼 더 남긴다."""
    jti = str(claims.get("jti") or "").strip()
    if not jti:
        raise SsoError("포털 토큰에 jti가 없습니다.")
    now = datetime.now(UTC)
    keep = datetime.fromtimestamp(int(claims["exp"]), tz=UTC) + timedelta(seconds=LEEWAY_S)
    db.execute(delete(SsoUsedJti).where(SsoUsedJti.expires_at < now))
    db.add(SsoUsedJti(jti=jti[:128], expires_at=keep))
    try:
        db.commit()
    except IntegrityError as failure:
        db.rollback()
        raise SsoError(
            "이미 사용한 포털 로그인 토큰입니다. 포털에서 다시 시작하십시오."
        ) from failure


def verify_launch(db: Session, token: str) -> dict[str, Any]:
    """포털 launch 토큰 — 서명 · aud · iss · 만료 · scope · 1회용. 통과하면 클레임."""
    settings = get_settings()
    token = (token or "").strip()
    if not token:
        raise SsoError("포털 토큰이 없습니다.")
    key = _signing_key(token)
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.portal_audience,
            issuer=settings.portal_issuer.strip() or None,
            leeway=LEEWAY_S,
            options={"require": ["exp", "iat", "aud", "jti"]},
        )
    except jwt.ExpiredSignatureError as failure:
        raise SsoError(
            "포털 로그인 토큰이 만료되었습니다. 포털에서 다시 시작하십시오."
        ) from failure
    except jwt.InvalidAudienceError as failure:
        raise SsoError("이 플랫폼용 토큰이 아닙니다(aud).") from failure
    except jwt.InvalidIssuerError as failure:
        raise SsoError("알 수 없는 발급자의 토큰입니다(iss).") from failure
    except jwt.PyJWTError as failure:
        raise SsoError(f"포털 토큰을 확인하지 못했습니다({failure}).") from failure
    if claims.get("scope") != "launch":
        raise SsoError("포털 launch 토큰이 아닙니다(scope).")
    _consume(db, claims)
    return claims


def _portal_user(db: Session, token: str) -> User:
    claims = verify_launch(db, token)
    user, created = resolve_user(
        db,
        email=str(claims.get("email") or ""),
        name=str(claims.get("name") or ""),
        login_id=str(claims.get("login_id") or claims.get("LoginId") or ""),
        jit_create=get_settings().portal_jit_create,
    )
    if user.must_change_password:
        # 관리자가 임시 비밀번호로 만든 계정에 포털로 처음 왔다. 그대로 두면 「비밀번호
        # 변경」 화면이 **현재(임시) 비밀번호**를 묻는데, 포털로 오는 사람은 그것을 모를 수
        # 있다 — 갇힌다. 포털이 사람을 확인했으니 임시 비밀번호는 없앤다(아무도 모르는 값으로).
        # 비밀번호로도 들어오려면 관리자가 「비밀번호 초기화」.
        user.password_hash = security.hash_password(secrets.token_urlsafe(32))
        user.must_change_password = False
        db.commit()
    logger.info("portal sso: %s%s", user.email, " (새 계정)" if created else "")
    return user


def _portal_on() -> None:
    if not get_settings().portal_jwks_url.strip():
        # 꺼져 있으면 있는지조차 흘리지 않는다.
        raise NotFound(code("COMMON", 404), "존재하지 않는 엔드포인트입니다.")


def _session(db: Session, request: Request, response: Response, user: User) -> LoginResponse:
    """비밀번호 로그인과 **같은 세션** — refresh 쿠키(접두어를 붙인 경로)와 access 토큰."""
    access, expires_in, refresh_raw = services.issue_session(
        db, user, request.headers.get("user-agent")
    )
    set_refresh_cookie(request, response, refresh_raw)
    return LoginResponse(
        access_token=access, expires_in=expires_in, user=services.user_out(user)
    )


@router.post("/portal-callback", include_in_schema=False)
def portal_callback(
    request: Request, token: str = Form(""), db: Session = Depends(get_db)
) -> Response:
    """타일 클릭 — 포털 화면이 폼(`token`)으로 POST 한다. 통과하면 쿠키를 심고 화면으로, 아니면
    로그인 화면에 까닭을 실어(`sso_error`)."""
    _portal_on()
    prefix = url_prefix(request)
    try:
        user = _portal_user(db, token)
    except SsoError as failure:
        target = f"{prefix}/login?{urlencode({'sso_error': str(failure)})}"
        return RedirectResponse(target, status_code=303)
    redirect = RedirectResponse(f"{prefix}/", status_code=303)
    _session(db, request, redirect, user)
    return redirect


class PortalExchangeRequest(BaseModel):
    token: str


@router.post("/portal-exchange", response_model=LoginResponse)
def portal_exchange(
    payload: PortalExchangeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """주소로 **바로** 들어온 사람 — 화면이 포털의 표준 launch(`POST /systems/{id}/launch`)를
    포털 세션으로 불러 받은 토큰을 바꾼다. 비밀번호 로그인과 같은 모양으로 답한다."""
    _portal_on()
    try:
        user = _portal_user(db, payload.token)
    except SsoError as failure:
        raise AppError(code("AUTH", 110), str(failure), status=failure.status) from failure
    return _session(db, request, response, user)


# ── 게이트웨이 위임 창구 ──────────────────────────────────────────────────────


def _gate(request: Request) -> None:
    """세 창구 공통 — 꺼짐 404 · 허용 밖 IP 403 · 비밀 불일치 401."""
    settings = get_settings()
    secret = settings.heax_sso_secret.strip()
    if not secret:
        raise NotFound(code("COMMON", 404), "존재하지 않는 엔드포인트입니다.")
    allowed = {one.strip() for one in settings.heax_sso_allowed_ips.split(",") if one.strip()}
    client = request.client.host if request.client else ""
    if allowed and client not in allowed:
        logger.warning("auth/sso: 허용되지 않은 위치 %s", client)
        raise Forbidden(code("AUTH", 111), "허용되지 않은 위치입니다.")
    given = (request.headers.get("x-heax-gateway-secret") or "").strip().encode("utf-8")
    if not hmac.compare_digest(given, secret.encode("utf-8")):
        logger.warning("auth/sso: 비밀 불일치 (%s)", client)
        raise AppError(code("AUTH", 112), "게이트웨이 비밀이 일치하지 않습니다.", status=401)


def _asked_email(request: Request) -> str:
    email = (request.headers.get("x-heax-user-email") or "").strip().lower()
    if not email:
        raise AppError(code("AUTH", 113), "X-Heax-User-Email이 필요합니다.", status=400)
    if not _EMAIL.match(email):
        # 형식 검사 없이는 쓰레기 문자열로 계정이 만들어진다(NEW-SYSTEM-ASK).
        raise AppError(
            code("AUTH", 113), "X-Heax-User-Email이 이메일 형식이 아닙니다.", status=401
        )
    return email


def delegate_name(client: str) -> str:
    """위임 토큰의 이름 — 사람의 토큰 목록에 이대로 보인다. client 마다 하나."""
    client = (client or "").strip()[:40]
    return f"{DELEGATE_NAME} ({client})" if client else DELEGATE_NAME


@router.post("/sso", include_in_schema=False)
def issue_delegate(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    _gate(request)
    email = _asked_email(request)
    # 이름은 퍼센트 인코딩으로 온다(헤더는 latin-1) — 처음 만들 때 표시 이름으로만 쓴다.
    name = unquote(request.headers.get("x-heax-user-name") or "")
    try:
        user, created = resolve_user(
            db, email=email, name=name, jit_create=get_settings().heax_sso_jit_create
        )
    except SsoError as failure:
        # 비활성 · 자동 생성 꺼짐은 **403** — 404 는 「창구가 꺼짐」 으로 예약돼 있다(포털이
        # 404 를 받으면 창구 전체가 꺼진 줄 알고 수동 등록으로 내려간다).
        raise Forbidden(code("AUTH", 114), str(failure)) from failure
    label = delegate_name(request.headers.get("x-heax-client") or "")
    db.execute(
        delete(PersonalAccessToken).where(
            PersonalAccessToken.user_id == user.id, PersonalAccessToken.name == label
        )
    )
    raw, prefix, token_hash = security.new_pat()
    db.add(
        PersonalAccessToken(
            user_id=user.id,
            name=label,
            prefix=prefix,
            token_hash=token_hash,
            scopes=list(DELEGATE_SCOPES),
            expires_at=datetime.now(UTC) + timedelta(days=DELEGATE_DAYS),
        )
    )
    db.commit()
    logger.info(
        "auth/sso: %s 에게 발급(%s)%s", user.email, label, " — 새 계정" if created else ""
    )
    # 포털 표준(옛 heax.py) 봉투 그대로 — 소비자는 access_token 을 깊이 찾고 expires_in 을 같은
    # 객체에서 읽는다.
    return JSONResponse(
        {
            "success": True,
            "data": {
                "access_token": raw,
                "token_type": "bearer",
                "expires_in": DELEGATE_DAYS * 86400,
                "needs_workspace": False,
            },
        }
    )


@router.post("/sso/verify", include_in_schema=False, status_code=204)
def verify_delegate(request: Request) -> Response:
    """비밀만 확인한다 — 포털이 설정을 점검할 때. 계정을 건드리지 않는다."""
    _gate(request)
    return Response(status_code=204)


@router.post("/sso/revoke", include_in_schema=False)
def revoke_delegate(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """그 사람 · 그 client 의 위임 토큰을 지운다. 사람이나 토큰이 없어도 200(지울 것이 없을
    뿐)."""
    _gate(request)
    email = _asked_email(request)
    user_id = db.scalar(select(User.id).where(func.lower(User.email) == email))
    revoked = 0
    if user_id is not None:
        name = delegate_name(request.headers.get("x-heax-client") or "")
        result = db.execute(
            delete(PersonalAccessToken).where(
                PersonalAccessToken.user_id == user_id, PersonalAccessToken.name == name
            )
        )
        revoked = int(getattr(result, "rowcount", 0) or 0)
        db.commit()
    return JSONResponse({"ok": True, "revoked": revoked})
