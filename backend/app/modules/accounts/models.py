"""계정.

사용자는 **지우지 않고 정지**한다. deleted_at 이 있는 행은 로그인할 수 없지만, 그 사람이
만든 지그 프로젝트의 소유자 참조는 살아 있다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 계정 상태. active 정상 / suspended 관리자가 정지.
USER_STATUSES = ("active", "suspended")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    """로그인 아이디. **이메일 형식을 강제하지 않는다** — `admin` 같은 짧은 아이디를 쓴다."""
    password_hash: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(100))

    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    is_system_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    """관리자가 만든 계정의 임시 비밀번호. 첫 로그인 때 변경을 강제한다."""

    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_failed_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    @property
    def can_sign_in(self) -> bool:
        return self.deleted_at is None and self.status == "active"
