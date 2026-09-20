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
    recipe: dict[str, Any] | None = None
    """첫 버전의 레시피(템플릿 · 직접 그린 것 · 부품에서 복사).

    **비워도 된다** — 조립처럼 「빈 채로 만들어 놓고 채우는」 것이 있다. 그러면 버전 없이
    작업만 생기고, 화면이 첫 버전을 만들 때까지 기다린다."""
    kind: str = "part"
    """part | jig | assembly — **무엇을 그리는가.** 그리는 방법은 같고, 승격할 곳이 다르다."""
    jig_for_part_id: uuid.UUID | None = None
    source: str = "manual"
    note: str = Field(default="", max_length=2000)


class WorkUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    jig_options: dict[str, Any] | None = None
    kind: str | None = None
    """그리다 보니 지그였을 수 있다 — 종류는 바꿀 수 있다."""
    jig_for_part_id: uuid.UUID | None = None
    tags: list[str] | None = None
    """꼬리표 전체를 바꾼다(빈 목록이면 다 뗀다)."""


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
    kind: str
    jig_for_part_id: uuid.UUID | None
    jig_for_part_name: str | None
    current_version: int
    version_count: int
    current: VersionOut | None
    jig_options: dict[str, Any]
    jig_run_count: int
    last_jig_status: str | None
    promoted_part_id: uuid.UUID | None
    promoted_jig_id: uuid.UUID | None
    """이 작업에서 승격된 부품 · 지그(있으면). 다시 승격하면 그쪽에 다음 버전이 붙는다."""
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class WorkSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID
    owner_name: str
    kind: str
    current_version: int
    current_status: str | None
    jig_run_count: int
    last_jig_status: str | None
    promoted_part_id: uuid.UUID | None
    promoted_jig_id: uuid.UUID | None
    tags: list[str] = []
    updated_at: datetime
    deleted_at: datetime | None = None


class JigFromPartRequest(BaseModel):
    """부품에서 **지그 작업을 생성**한다 — 규칙(3-2-1)으로 판 · 받침 · 핀 · 클램프를 놓는다."""

    source: str = Field(min_length=6)
    """`work:<내 부품 작업 id>` 또는 `part:<공용 부품 id>`. 그 현재 버전이 제품이 된다."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    """지그 작업 이름. 비우면 「〈부품〉 지그」."""
    options: dict[str, Any] = Field(default_factory=dict)
    """`JigOptions` 의 일부. 안 준 키는 기본값. 지그 작업에 `jig_options` 로 남는다."""


class WorkPatchRequest(BaseModel):
    """현재 도면에 연산 몇 개를 적용해 새 버전으로."""

    ops: list[dict[str, Any]] = Field(min_length=1)
    note: str = Field(default="", max_length=2000)


class AssembleRequest(BaseModel):
    """부품 + 지그를 맞는 자리에 놓은 조립 작업."""

    part_source: str = Field(min_length=6)
    """`work:<내 부품 작업 id>` 또는 `part:<공용 부품 id>`."""
    jig_work_id: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=120)


class AssembleOut(BaseModel):
    work: WorkOut
    placement: dict[str, Any]
    """어떻게 놓았나 — mode(generated | guessed) · translate · product_lift · height_param."""


class JigFromPartOut(BaseModel):
    """만들어진 지그 작업과, 돌고 있는 생성 작업. 끝나면 `adopt` 로 결과가 첫 버전이 된다."""

    work: WorkOut
    job: dict[str, Any]


class PromotePartRequest(BaseModel):
    """현재 버전을 부품으로. 이 작업에서 이미 승격한 부품이 있으면 거기에 다음 버전으로
    붙는다."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    """새 부품일 때 이름. 비우면 작업 이름."""
    note: str = Field(default="", max_length=2000)


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
