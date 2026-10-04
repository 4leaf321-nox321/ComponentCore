"""refresh 쿠키와 주소 접두어 — 비밀번호 로그인(`routes`)과 포털 SSO(`sso`)가 같이 쓴다.

포털 뒤(`https://portal/compcore/…`)에서는 브라우저가 보는 경로에 접두어가 붙는다. 쿠키
path 가 `/api/auth` 그대로면 브라우저가 `/compcore/api/auth/refresh` 에 쿠키를 싣지 않아 새로
고칠 때마다 로그아웃된다 — 접두어를 붙인 경로로 심는다.
"""

from __future__ import annotations

import re

from fastapi import Request, Response

from app.config import get_settings

_PREFIX = re.compile(r"(/[A-Za-z0-9._~-]+)+")


def url_prefix(request: Request) -> str:
    """프록시가 벗긴 주소 접두어(`/compcore`) — 프록시를 믿을 때만 `X-Forwarded-Prefix` 에서.
    없으면 빈 글자(루트에 뜬 단독 설치). 꾸민 값이 열린 리다이렉트가 되지 않게 모양을 본다."""
    if not get_settings().trust_proxy:
        return ""
    raw = (request.headers.get("x-forwarded-prefix") or "").strip().rstrip("/")
    return raw if raw and _PREFIX.fullmatch(raw) else ""


def _path(request: Request) -> str:
    return f"{url_prefix(request)}/api/auth"


def set_refresh_cookie(request: Request, response: Response, raw: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.refresh_cookie_name,
        raw,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.refresh_cookie_secure,
        path=_path(request),
    )


def clear_refresh_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(get_settings().refresh_cookie_name, path=_path(request))
