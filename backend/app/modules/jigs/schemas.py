"""지그 API 의 요청·응답 형태."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    product_spec: dict[str, Any] | None = None
    """STEP 없이 만들 때의 제품 도형(`core/primitives.py` 스펙). 파일은 따로 올린다."""


class ProjectUpdateRequest(BaseModel):
    """부분 수정 — 안 보낸 것과 비운 것을 구별한다."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    product_spec: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID
    owner_name: str
    product_filename: str | None
    product_size_bytes: int | None
    product_spec: dict[str, Any] | None
    has_product_file: bool
    run_count: int
    last_run_status: str | None
    created_at: datetime
    updated_at: datetime


class RunCreateRequest(BaseModel):
    options: dict[str, Any] = Field(default_factory=dict)
    """`JigOptions` 의 일부. 안 준 키는 기본값."""


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    options: dict[str, Any]
    summary: dict[str, Any] | None
    error: str | None
    files: list[str]
    """내려받을 수 있는 파일 키(`jig_step` · `assembly_step` · `jig_glb` · `product_glb` …)."""
    started_at: datetime
    finished_at: datetime | None


class OptionsOut(BaseModel):
    """기본 옵션 — 화면이 폼의 초깃값으로 쓴다. 손으로 두 벌 적지 않는다."""

    defaults: dict[str, Any]
    primitive_kinds: list[str]
