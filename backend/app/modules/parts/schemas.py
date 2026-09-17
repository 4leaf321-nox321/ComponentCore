from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.jobs.schemas import JobOut


class PartVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    part_id: uuid.UUID
    number: int
    recipe: dict[str, Any]
    job: JobOut | None
    note: str
    promoted_by_id: uuid.UUID | None
    promoted_by_name: str | None
    work_version_id: uuid.UUID | None
    created_at: datetime


class PartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID
    owner_name: str
    work_id: uuid.UUID | None
    current_version: int
    version_count: int
    current: PartVersionOut | None
    jig_count: int
    """이 부품을 잡는 지그(카탈로그) 수."""
    created_at: datetime
    updated_at: datetime


class PartSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_name: str
    current_version: int
    jig_count: int
    updated_at: datetime


class PartUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class CopyToWorkRequest(BaseModel):
    """부품(버전)의 레시피로 내 작업을 새로 만든다 — 「내 공간으로 복사」."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    number: int | None = None
    """비우면 현재 버전."""
