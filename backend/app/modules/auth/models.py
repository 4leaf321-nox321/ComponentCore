"""refresh 토큰 — 폐기할 수 있어야 하므로 JWT 가 아니라 DB 의 한 행이다.

원문은 어디에도 저장하지 않는다. sha256 해시만 둔다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    """회전 이력. 폐기된 토큰이 다시 쓰이면 탈취 신호로 볼 수 있다 — 그 판정에 "방금
    회전한 것인가" 를 물으려면 사슬이 필요하다(services.rotate_refresh)."""

    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class PersonalAccessToken(Base):
    """스크립트 · MCP(AI) 가 API 를 부를 때 쓰는 자격 증명.

    사람 세션(refresh)과 기계 자격(PAT)은 수명과 폐기 방식이 다르므로 표를 나눈다. 원문은
    저장하지 않는다 — sha256 해시만.
    """

    __tablename__ = "personal_access_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    """어디에 쓰는 토큰인지 — 폐기할 때 이것만 보고 판단한다. 버전 출처에도 남는다."""
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default='["read"]')
    """`read` 는 조회, `write` 는 만들고 고치기(작업 · 버전 · 지그 생성 · 승격). 기본은
    읽기뿐."""
    prefix: Mapped[str] = mapped_column(String(64), index=True)
    """평문의 앞자리 — 목록에서 어느 토큰인지 알아보는 용도."""
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
