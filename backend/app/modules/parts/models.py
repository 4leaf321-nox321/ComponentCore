"""부품 카탈로그 — 내 작업의 형상을 **승격**한 것. 로그인한 누구나 본다.

부품 버전은 불변이다. 고치려면 내 작업에서 고쳐 다시 승격한다(v2). 어느 작업의 어느 버전에서
왔는지(`work_version_id`)를 남긴다 — 「이 부품은 어디서 왔나」 를 물을 수 있어야 한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    """처음 승격한 사람. 이후 버전은 이 사람(또는 관리자)만 올린다."""
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("works.id", ondelete="SET NULL"), nullable=True
    )
    """어느 작업에서 승격됐나. 그 작업이 지워져도 부품은 남는다."""
    current_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class PartVersion(Base):
    __tablename__ = "part_versions"
    __table_args__ = (UniqueConstraint("part_id", "number", name="uq_part_versions_number"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("parts.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    work_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("work_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recipe: Mapped[dict[str, Any]] = mapped_column(JSONB)
    """승격 시점의 레시피 복사본 — 작업이 지워져도 남는다."""
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    """STEP · glTF 작업물을 든 평가 작업(작업 버전의 것을 그대로 가리킨다)."""
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    promoted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
