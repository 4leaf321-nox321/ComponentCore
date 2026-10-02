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
    tags: list[str] = Field(default_factory=list)
    """꼬리표 — 승격이 내 작업의 것을 물려받는다. 목록에서 이것으로 거른다(`?tag=`)."""
    description: str
    owner_id: uuid.UUID
    owner_name: str
    work_id: uuid.UUID | None
    part_id: uuid.UUID | None
    part_name: str | None
    current_version: int
    version_count: int
    current: JigVersionOut | None
    folder: str = ""
    created_at: datetime
    updated_at: datetime


class JigSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    tags: list[str] = Field(default_factory=list)
    """꼬리표 — **목록에도 보여야 한다.** 거르개로 쓰는 자리가 목록이다."""
    description: str
    owner_id: uuid.UUID
    """누가 올렸나 — 화면이 「옮길 수 있나」 를 미리 가린다(판정은 서버)."""
    owner_name: str
    part_id: uuid.UUID | None
    part_name: str | None
    current_version: int
    interference_ok: bool | None
    folder: str = ""
    """놓인 폴더 — `고객A/2026`, 빈 것이 맨 위."""
    updated_at: datetime


class JigUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    folder: str | None = Field(default=None, max_length=255)
    """옮길 폴더 — 빈 문자열이면 맨 위로."""
