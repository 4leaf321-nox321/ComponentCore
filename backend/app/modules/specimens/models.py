"""사내 시험 규격 — 공개 규격(코드의 `core/specimens/data`)과 **같은 모양**의 프리셋을 DB 에
둔다.

사내 시험법 · 고객사 규격은 저장소(공개)에 넣을 수 없고, 관리자가 릴리스 없이 고칠 수 있어야
한다(ADR 0006). 치수 · 규칙은 `body` 한 칸(JSON)이고 코어의 `parse_preset` 이 검사한다 — 목록을
가르는 칸(시험 종류 · 규격 번호 · 이름)만 따로 둔다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SpecimenPreset(Base):
    __tablename__ = "specimen_presets"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test: Mapped[str] = mapped_column(String(20), index=True)
    """시험 종류 — `bending` …(`core.specimens.TESTS`)."""
    standard: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    """프리셋 전부(`core.specimens.presets.Preset` — id 는 이 행의 id)."""
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
