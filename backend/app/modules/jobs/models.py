"""작업(Job)과 작업물(Artifact) — 이 플랫폼에서 "무언가를 만드는 일" 의 단위.

지그 생성 · CAD 평가 · AI 편집이 전부 작업이다. 종류(kind)마다 실행하는 함수가 다르고
(`registry.py`), 표는 하나다 — 그래야 「내 작업」 목록 하나가 전부를 보여 준다.

**DB 가 큐다.** `queued` 행을 워커가 `FOR UPDATE SKIP LOCKED` 로 집어 간다. 별도 큐 서버를
두지 않는 이유: 작업이 분당 몇 건이고, 큐 서버는 설치 · 백업 · 장애 지점을 하나 더 만든다.
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

#: 작업 상태. queued → running → done | failed.
JOB_STATUSES = ("queued", "running", "done", "failed")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kind: Mapped[str] = mapped_column(String(40), index=True)
    """무슨 일인가 — `registry.py` 에 등록된 이름(jig · cad …)."""
    status: Mapped[str] = mapped_column(
        String(20), default="queued", server_default="queued", index=True
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("works.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    """이 작업이 어느 「내 작업」 의 것인가. 작업(work)이 곧 공간이다 — 보는 권한이 여기서
    나온다."""

    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """실행에 필요한 입력의 **스냅숏** — 제품 파일 경로 · 도형 스펙 등. 프로젝트가 나중에
    바뀌어도 이 작업이 무엇으로 돌았는지는 여기 남는다."""
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    progress: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """끝난 단계들 — 도는 동안 화면이 이것을 폴링한다. `[{"name", "millis", "detail"}]`."""
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """끝난 뒤의 요약. 종류마다 모양이 다르다(jig 는 `JigResult.summary()`)."""
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    """filestore 루트 기준 상대 경로."""

    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Artifact(Base):
    """작업이 남긴 파일 하나.

    **계보를 안다** — 어느 작업이 만들었고(job_id), 무엇에서 나왔나(parent_id). 나중에 게시 ·
    버전 · "이 STEP 은 어느 레시피에서 왔나" 가 전부 이 두 칸에서 나온다.
    """

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("works.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(40), index=True)
    """무엇인가 — jig_step · assembly_step · jig_glb · product_glb · product_step …"""
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    """filestore 루트 기준 상대 경로."""
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
