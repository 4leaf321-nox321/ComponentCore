from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID | None
    work_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class StageOut(BaseModel):
    name: str
    millis: int
    detail: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    requested_by_id: uuid.UUID | None
    requested_by_name: str | None
    work_id: uuid.UUID | None
    work_name: str | None
    options: dict[str, Any]
    progress: list[StageOut]
    summary: dict[str, Any] | None
    error: str | None
    artifacts: list[ArtifactOut]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None = None
    """도는 중에 취소를 요청했다 — 워커가 다음 단계에서 멈춘다(화면은 「멈추는 중」)."""
