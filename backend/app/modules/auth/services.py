"""인증 로직. 오류는 전부 AppError 로 던진다."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.auth.models import RefreshToken
from app.modules.auth.schemas import UserOut
from app.shared.errors import AppError, Forbidden, code

_INVALID_LOGIN = "아이디 또는 비밀번호가 올바르지 않습니다."


def _now() -> datetime:
    return datetime.now(UTC)


def ensure_can_sign_in(user: User) -> None:
    if user.deleted_at is not None:
        raise Forbidden(code("AUTH", 2), "삭제된 계정입니다. 관리자에게 문의하세요.")
    if user.status != "active":
        raise Forbidden(code("AUTH", 2), "정지된 계정입니다. 관리자에게 문의하세요.")


#: 시험이 갈아 끼운다 — 실제로 자면 시험이 30초씩 선다.
_sleep = time.sleep


def login_delay_seconds(failures: int) -> float:
    """이번 실패가 몇 번째인가 -> 몇 초 늦출까. **잠금은 없다.**"""
    settings = get_settings()
    over = failures - settings.login_delay_after + 1
    if over <= 0:
        return 0.0
    return float(
        min(settings.login_delay_step_seconds * over, settings.login_delay_max_seconds)
    )


def _note_failure(db: Session, user: User) -> float:
    settings = get_settings()
    now = _now()
    window = timedelta(minutes=settings.login_failure_window_minutes)
    if user.last_failed_login_at is None or now - user.last_failed_login_at > window:
        user.failed_logins = 0
    user.failed_logins += 1
    user.last_failed_login_at = now
    db.commit()
    return login_delay_seconds(user.failed_logins)


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))

    # 계정이 없을 때도 해시 비교를 한 번 수행해 응답 시간으로 계정 존재 여부가 새지 않게.
    if user is None:
        security.verify_password(password, security.hash_password("dummy"))
        raise AppError(code("AUTH", 1), _INVALID_LOGIN, status=401)

    if not security.verify_password(password, user.password_hash):
        delay = _note_failure(db, user)
        if delay > 0:
            _sleep(delay)
        raise AppError(code("AUTH", 1), _INVALID_LOGIN, status=401)

    ensure_can_sign_in(user)
    if user.failed_logins:
        user.failed_logins = 0
        user.last_failed_login_at = None
        db.commit()
    return user


def issue_session(db: Session, user: User, user_agent: str | None) -> tuple[str, int, str]:
    """(access JWT, 만료 초, refresh 평문)."""
    settings = get_settings()
    raw = security.new_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=security.hash_token(raw),
            expires_at=_now() + timedelta(days=settings.refresh_token_days),
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    db.commit()
    access, expires_in = security.create_access_token(user.id)
    return access, expires_in, raw


#: 회전한 옛 토큰을 **동시 갱신**으로 봐 주는 시간(React StrictMode 의 이중 effect).
REFRESH_GRACE = timedelta(seconds=30)


def rotate_refresh(
    db: Session, raw: str, user_agent: str | None
) -> tuple[User, str, int, str]:
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(raw))
    )
    if token is None:
        raise AppError(
            code("AUTH", 3), "세션이 만료되었습니다. 다시 로그인해 주세요.", status=401
        )

    if token.revoked_at is not None:
        replacement = (
            db.get(RefreshToken, token.replaced_by_id) if token.replaced_by_id else None
        )
        just_rotated = _now() - token.revoked_at <= REFRESH_GRACE
        if replacement is not None and just_rotated and replacement.revoked_at is None:
            token = replacement
        else:
            revoke_all_for_user(db, token.user_id)
            raise AppError(
                code("AUTH", 5),
                "세션이 무효화되었습니다. 다시 로그인해 주세요.",
                status=401,
                details={"reason": "reuse_of_revoked_token"},
            )

    if token.expires_at <= _now():
        raise AppError(
            code("AUTH", 3), "세션이 만료되었습니다. 다시 로그인해 주세요.", status=401
        )

    user = db.get(User, token.user_id)
    if user is None:
        raise Forbidden(code("AUTH", 2), "삭제된 계정입니다. 관리자에게 문의하세요.")
    ensure_can_sign_in(user)

    settings = get_settings()
    new_raw = security.new_opaque_token()
    new_token = RefreshToken(
        user_id=user.id,
        token_hash=security.hash_token(new_raw),
        expires_at=_now() + timedelta(days=settings.refresh_token_days),
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(new_token)
    db.flush()

    token.revoked_at = _now()
    token.replaced_by_id = new_token.id
    db.commit()

    access, expires_in = security.create_access_token(user.id)
    return user, access, expires_in, new_raw


def revoke_refresh(db: Session, raw: str) -> None:
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(raw))
    )
    if token is not None and token.revoked_at is None:
        token.revoked_at = _now()
        db.commit()


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    tokens = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    for token in tokens:
        token.revoked_at = _now()
    db.commit()


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not security.verify_password(current, user.password_hash):
        raise AppError(code("AUTH", 4), "현재 비밀번호가 올바르지 않습니다.", status=400)
    if current == new:
        raise AppError(code("AUTH", 6), "이전과 다른 비밀번호를 사용하세요.", status=400)

    user.password_hash = security.hash_password(new)
    user.must_change_password = False
    db.commit()
    # 비밀번호를 바꾼 이유가 유출일 수 있으므로 기존 세션을 전부 끊는다.
    revoke_all_for_user(db, user.id)


def user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)
