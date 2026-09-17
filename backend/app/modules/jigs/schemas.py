from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.jobs.schemas import JobOut


class JigVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    jig_id: uuid.UUID
    number: int
    job: JobOut | None
    """지그 생성 작업 — STEP · glTF 작업물."""
    options: dict[str, Any]
    summary: dict[str, Any] | None
    part_id: uuid.UUID | None
    part_name: str | None
    part_version: int | None
    note: str
    promoted_by_name: str | None
    created_at: datetime


class JigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID
    owner_name: str
    work_id: uuid.UUID | None
    part_id: uuid.UUID | None
    part_name: str | None
    current_version: int
    version_count: int
    current: JigVersionOut | None
    created_at: datetime
    updated_at: datetime


class JigSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_name: str
    part_id: uuid.UUID | None
    part_name: str | None
    current_version: int
    interference_ok: bool | None
    updated_at: datetime


class JigUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
