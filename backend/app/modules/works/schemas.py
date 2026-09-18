"""내 작업 API 의 요청 · 응답."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.jobs.schemas import JobOut


class WorkCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    recipe: dict[str, Any]
    """첫 버전의 레시피(템플릿 · 직접 그린 것 · 부품에서 복사)."""
    source: str = "manual"
    note: str = Field(default="", max_length=2000)


class WorkUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    jig_options: dict[str, Any] | None = None


class VersionCreateRequest(BaseModel):
    recipe: dict[str, Any]
    source: str = "manual"
    note: str = Field(default="", max_length=2000)


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work_id: uuid.UUID
    number: int
    recipe: dict[str, Any]
    source: str
    note: str
    created_by_id: uuid.UUID | None
    created_by_name: str | None
    job: JobOut | None
    """평가 작업 — 상태 · 요약 · STEP · glTF 작업물."""
    promoted_part_id: uuid.UUID | None
    promoted_part_version: int | None
    """이 버전이 부품 카탈로그에 올라가 있으면 어디에."""
    created_at: datetime


class WorkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID
    owner_name: str
    current_version: int
    version_count: int
    current: VersionOut | None
    jig_options: dict[str, Any]
    jig_run_count: int
    last_jig_status: str | None
    promoted_part_id: uuid.UUID | None
    promoted_jig_id: uuid.UUID | None
    """이 작업에서 승격된 부품 · 지그(있으면). 다시 승격하면 그쪽에 다음 버전이 붙는다."""
    created_at: datetime
    updated_at: datetime


class WorkSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID
    owner_name: str
    current_version: int
    current_status: str | None
    jig_run_count: int
    last_jig_status: str | None
    promoted_part_id: uuid.UUID | None
    promoted_jig_id: uuid.UUID | None
    updated_at: datetime


class JigRunRequest(BaseModel):
    options: dict[str, Any] = Field(default_factory=dict)
    """`JigOptions` 의 일부. 안 준 키는 기본값. 작업에 마지막 옵션으로 남는다."""


class PromotePartRequest(BaseModel):
    """현재 버전을 부품으로. 이 작업에서 이미 승격한 부품이 있으면 거기에 다음 버전으로
    붙는다."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    """새 부품일 때 이름. 비우면 작업 이름."""
    note: str = Field(default="", max_length=2000)


class PromoteJigRequest(BaseModel):
    """지그 생성 작업 하나를 지그로. 제품(그때의 형상 버전)이 부품에 없으면 함께 승격한다."""

    job_id: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)
    promote_product: bool = True
    """제품 버전이 부품 카탈로그에 없을 때 함께 올린다. 끄면 제품 참조 없이(스냅숏만)
    올라간다."""


class PromoteJigRecipeRequest(BaseModel):
    """**손으로 그린 지그**(레시피 버전)를 지그로. 자동 생성기가 만들 수 없는 지그 — 공진을
    맞추는 시험 지그처럼 우리가 형상을 정하는 것들이다."""

    number: int | None = None
    """올릴 버전. 비우면 현재 버전."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)
    part_id: uuid.UUID | None = None
    """이 지그가 잡는 부품(카탈로그). 안 고르면 홀로 선 지그로 올라간다."""


class PromoteJigOut(BaseModel):
    jig_id: uuid.UUID
    jig_version: int
    part_id: uuid.UUID | None
    part_version: int | None
    part_promoted_now: bool
