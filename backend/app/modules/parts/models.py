"""부품 카탈로그 — 내 작업의 형상을 **승격**한 것. 로그인한 누구나 본다.

부품 버전은 불변이다. 고치려면 내 작업에서 고쳐 다시 승격한다(v2). 어느 작업의 어느 버전에서
왔는지(`work_version_id`)를 남긴다 — 「이 부품은 어디서 왔나」 를 물을 수 있어야 한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Part(Base):
    __tablename__ = "parts"
    __table_args__ = (
        # 찾기(`shared/search.py`)의 `ILIKE %낱말%` 이 타는 트라이그램 색인 — 마이그레이션
        # 0028. 모델에도 적어 둬야 `alembic check` 가 「지울 것」 으로 읽지 않는다.
        Index(
            "ix_parts_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_parts_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
        Index("ix_parts_tags_trgm", text("(tags::text) gin_trgm_ops"), postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    """처음 승격한 사람. 이후 버전은 이 사람(또는 관리자)만 올린다."""
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    """꼬리표 — 승격할 때 **내 작업의 것을 그대로 물려받는다.** 공용 공간은 남의 것까지
    쌓이므로 이름만으로는 못 찾는다(내 작업은 열두 개쯤이라 이름으로 충분하다)."""
    folder: Mapped[str] = mapped_column(String(255), default="", server_default="", index=True)
    """놓인 **폴더** — `고객A/2026` 같은 경로, 빈 것이 맨 위(`shared/folders.py`). 여럿이 함께
    쓰는 공간이라 옮기기는 주인 · 관리자만, 남의 것이 든 폴더의 이름은 관리자만 바꾼다."""
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
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """승격 시점의 해석 조건 복사본(경계 · 하중 · 접촉 · 물성 …). 레시피와 같은 형상이라 선택
    그룹이 그대로 맞는다 — 「내 작업으로 복사」 가 옮긴다. 작업의 조건은 제자리에서 바뀌므로
    가리키지 않고 복사한다. 등록할 때 빼면 비어 있다."""
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
