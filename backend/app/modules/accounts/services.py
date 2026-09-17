"""계정 로직 — 계정 자체의 생애(생성·정지·삭제)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.accounts.schemas import AccountOut
from app.modules.auth import security
from app.shared.errors import AppError, Conflict, NotFound, code


def _now() -> datetime:
    return datetime.now(UTC)


def account_out(user: User) -> AccountOut:
    return AccountOut.model_validate(user)


def get_account(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound(code("ACCOUNTS", 1), "계정을 찾을 수 없습니다.")
    return user


def list_accounts(db: Session, *, status: str | None, limit: int, offset: int) -> list[User]:
    query = select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc())
    if status:
        query = query.where(User.status == status)
    return list(db.scalars(query.limit(limit).offset(offset)))


def active_system_admin_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count()).where(
                User.is_system_admin.is_(True),
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )
        or 0
    )


def create_account(
    db: Session, *, email: str, display_name: str, is_system_admin: bool
) -> tuple[User, str]:
    """관리자가 만든다. 임시 비밀번호를 돌려주고 첫 로그인에서 변경을 강제한다."""
    normalized = email.strip().lower()
    if db.scalar(select(User).where(User.email == normalized)) is not None:
        raise Conflict(code("ACCOUNTS", 2), "이미 있는 아이디입니다.")

    temporary = secrets.token_urlsafe(9)
    user = User(
        email=normalized,
        password_hash=security.hash_password(temporary),
        display_name=display_name.strip(),
        status="active",
        is_system_admin=is_system_admin,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, temporary


def _guard_last_admin(db: Session, user: User) -> None:
    """마지막 활성 시스템 관리자를 정지·강등·삭제하면 아무도 관리 화면에 못 들어간다."""
    if user.is_system_admin and user.can_sign_in and active_system_admin_count(db) <= 1:
        raise AppError(
            code("ACCOUNTS", 3),
            "마지막 시스템 관리자입니다. 다른 관리자를 먼저 지정하세요.",
        )


def set_status(db: Session, *, user_id: uuid.UUID, status: str, actor: User) -> User:
    user = get_account(db, user_id)
    if status == "suspended":
        if user.id == actor.id:
            raise AppError(code("ACCOUNTS", 4), "자기 계정은 정지할 수 없습니다.")
        _guard_last_admin(db, user)
    user.status = status
    db.commit()
    db.refresh(user)
    return user


def set_system_admin(db: Session, *, user_id: uuid.UUID, grant: bool, actor: User) -> User:
    user = get_account(db, user_id)
    if not grant:
        if user.id == actor.id:
            raise AppError(code("ACCOUNTS", 5), "자기 권한은 내릴 수 없습니다.")
        _guard_last_admin(db, user)
    user.is_system_admin = grant
    db.commit()
    db.refresh(user)
    return user


def reset_password(db: Session, *, user_id: uuid.UUID) -> str:
    user = get_account(db, user_id)
    temporary = secrets.token_urlsafe(9)
    user.password_hash = security.hash_password(temporary)
    user.must_change_password = True
    db.commit()
    return temporary


def delete_account(db: Session, *, user_id: uuid.UUID, actor: User) -> User:
    """행은 남고 접근만 끊긴다 — 프로젝트의 소유자 참조를 잃지 않기 위해서다."""
    user = get_account(db, user_id)
    if user.id == actor.id:
        raise AppError(code("ACCOUNTS", 6), "자기 계정은 지울 수 없습니다.")
    _guard_last_admin(db, user)
    user.deleted_at = _now()
    db.commit()
    db.refresh(user)
    return user
