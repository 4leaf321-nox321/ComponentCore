"""지그 프로젝트와 생성 실행.

프로젝트는 **제품 하나**다 — 올린 STEP 이 있거나(product_path), 없으면 기본 도형 스펙
(product_spec)이 제품이다. 실행(run)은 옵션 한 벌로 파이프라인을 돌린 기록이고, 결과 파일은
filestore 에, 요약은 JSONB 에 남는다. 같은 제품으로 옵션을 바꿔 여러 번 돌리므로 1:N 이다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 실행 상태.
RUN_STATUSES = ("running", "done", "failed")


class JigProject(Base):
    __tablename__ = "jig_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )

    product_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """올린 파일의 원래 이름. 화면에 보이는 값."""
    product_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    """filestore 루트 기준 상대 경로. 비어 있으면 product_spec 이 제품이다."""
    product_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """STEP 이 없을 때의 제품 — `core/primitives.py` 의 스펙. 둘 다 없으면 시연 제품."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class JigRun(Base):
    __tablename__ = "jig_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jig_projects.id", ondelete="CASCADE"), index=True
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="running", server_default="running"
    )
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """그때 쓴 `JigOptions`. 옛 실행을 같은 옵션으로 다시 돌릴 수 있어야 한다."""
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """`JigResult.summary()` — 기하 요약 · 특징 · 계획 · 간섭 · 파일 이름 · 단계별 시간."""
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    """filestore 루트 기준 상대 경로. 결과 파일이 전부 여기 있다."""

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
