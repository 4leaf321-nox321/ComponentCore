"""지그 카탈로그 — 내 작업에서 만든 지그를 **승격**한 것. 로그인한 누구나 본다.

지그 버전 = 지그 생성 작업(결과 STEP · 계획 · 간섭) + **어느 부품 버전의 지그인가**. 제품이
부품 카탈로그에 없으면 승격할 때 함께 부품으로 승격한다 — 지그만 있고 제품이 없는 카탈로그는
반쪽이다.
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


class Jig(Base):
    __tablename__ = "jigs"
    __table_args__ = (
        # 찾기(`shared/search.py`)의 `ILIKE %낱말%` 이 타는 트라이그램 색인 — 마이그레이션
        # 0028. 모델에도 적어 둬야 `alembic check` 가 「지울 것」 으로 읽지 않는다.
        Index(
            "ix_jigs_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_jigs_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
        Index("ix_jigs_tags_trgm", text("(tags::text) gin_trgm_ops"), postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    """꼬리표 — 승격할 때 **내 작업의 것을 그대로 물려받는다.** 공용 공간은 남의 것까지
    쌓이므로 이름만으로는 못 찾는다(내 작업은 열두 개쯤이라 이름으로 충분하다)."""
    folder: Mapped[str] = mapped_column(String(255), default="", server_default="", index=True)
    """놓인 **폴더** — `고객A/2026` 같은 경로, 빈 것이 맨 위(`shared/folders.py`). 여럿이 함께
    쓰는 공간이라 옮기기는 주인 · 관리자만, 남의 것이 든 폴더의 이름은 관리자만 바꾼다."""
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("works.id", ondelete="SET NULL"), nullable=True
    )
    part_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("parts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    """이 지그가 잡는 부품. 버전은 `JigVersion.part_version_id` 가 정확히 가리킨다."""
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


class JigVersion(Base):
    __tablename__ = "jig_versions"
    __table_args__ = (UniqueConstraint("jig_id", "number", name="uq_jig_versions_number"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jig_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jigs.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    """지그 생성 작업 — 요약(계획 · 간섭)과 STEP · glTF 작업물."""
    part_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("part_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    recipe: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """등록 시점의 레시피 복사본 — 「내 작업 공간으로 복사」 가 이것으로 새 작업을 연다.
    생성기로 만든 옛 버전은 비어 있다(짝이 되는 작업 버전이 없다)."""
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """등록 시점의 해석 조건 복사본 — 부품(`PartVersion.conditions`)과 같은 규칙. 등록할 때
    빼면 비어 있다."""
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """작업 요약의 복사본 — 작업이 지워져도 계획은 남는다."""
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    promoted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
