"""내 작업(Work) — 사람이 그리고 있는 문서. **내 공간**의 것이라 소유자(와 관리자)만 본다.

작업 하나 = 형상(레시피 버전들) + 그 형상을 제품으로 한 지그 생성(옵션 · 실행 기록). 저장은 늘
여기로만 되고, 남에게 내놓는 것은 **승격**이다 — 부품(parts) 이나 지그(jigs) 카탈로그에 불변
버전으로 복사된다.

**버전은 고치지 않는다.** 새 버전을 만든다. 되돌리기도 옛 레시피로 새 버전. 올린 STEP 도
`import_step` 노드 하나짜리 버전이다 — 그래서 제품은 늘 「이 작업의 형상」 하나로 통일된다.
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

#: 버전이 어디서 왔나.
VERSION_SOURCES = ("template", "manual", "ai", "import", "restore", "copy")


class Work(Base):
    __tablename__ = "works"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    current_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jig_options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """마지막으로 쓴 지그 옵션 — 다음에 열면 그대로 있다."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class WorkVersion(Base):
    __tablename__ = "work_versions"
    __table_args__ = (UniqueConstraint("work_id", "number", name="uq_work_versions_number"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("works.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    recipe: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    """이 버전을 평가한 작업(`kind="cad"`). 상태 · 요약 · STEP · glTF 는 그쪽에 있다."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
