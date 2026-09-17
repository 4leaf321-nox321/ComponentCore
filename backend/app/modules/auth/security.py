"""비밀번호 해시와 토큰 발급 — 암호 관련 원시 연산만 모은다.

**bcrypt 앞에 sha256 을 한 번 건다.** bcrypt 는 입력을 72바이트에서 자르는데, 한글 비밀번호는
글자당 3바이트라 24자를 넘으면 뒤가 조용히 무시된다.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import get_settings


def _prepared(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


#: bcrypt 라운드. 운영 12. 시험만 환경변수로 낮춘다(tests/conftest.py).
BCRYPT_ROUNDS = int(os.environ.get("APP_BCRYPT_ROUNDS", "12"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepared(password), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepared(password), password_hash.encode("ascii"))
    except ValueError:
        return False


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def pat_prefix() -> str:
    """PAT 평문 앞에 붙는 표식 — `<app_slug>_pat_`. 로그와 소스에서 유출을 눈으로 찾게 한다."""
    return f"{get_settings().app_slug}_pat_"


def new_pat() -> tuple[str, str, str]:
    """(평문, 표시용 prefix, 해시). 평문은 발급 응답에서 한 번만 노출된다."""
    prefix = pat_prefix()
    raw = prefix + secrets.token_urlsafe(32)
    return raw, raw[: len(prefix) + 6], hash_token(raw)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """(JWT, 만료까지 초). access 는 짧게 살고 폐기하지 않는다 — 폐기는 refresh 의 몫."""
    settings = get_settings()
    ttl = timedelta(minutes=settings.access_token_minutes)
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "typ": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, int(ttl.total_seconds())


#: 발급·검증 사이의 시계 어긋남 허용치. WSL2 가 NTP 로 재동기화하면 몇 초가 되감긴다.
CLOCK_LEEWAY_SECONDS = 30


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            leeway=CLOCK_LEEWAY_SECONDS,
        )
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "access" else None
