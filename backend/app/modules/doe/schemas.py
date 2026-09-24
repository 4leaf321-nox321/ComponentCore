from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FactorIn(BaseModel):
    """인자 하나 — 고정이거나, 구간이거나, 값 목록."""

    name: str = Field(min_length=1, max_length=40)
    mode: str = "fixed"
    value: float | None = None
    start: float | None = None
    end: float | None = None
    steps: int = 5
    values: list[float] = Field(default_factory=list)
    resolution: float | None = Field(default=None, gt=0)
    """값을 맞추는 가공 단위(mm). 없으면 0.1 — 0.333 같은 치수는 가공할 수 없다."""


class PreviewRequest(BaseModel):
    factors: list[FactorIn]
    method: str = "factorial"
    samples: int = Field(default=20, ge=1)
    """LHS 표본 수. 상한은 서버 설정(관리자가 바꾼다) — 서비스가 본다."""
    seed: int = 1


class StudyCreateRequest(PreviewRequest):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    recipe: dict[str, Any]
    conditions: dict[str, Any] = Field(default_factory=dict)
    """해석 조건 한 벌 — 대상 버전의 것을 그대로 넘기면 스냅샷으로 박힌다.
    비면 형상만 훑는다."""
    work_id: uuid.UUID | None = None


class PointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    params: dict[str, Any]
    status: str
    error: str
    interference: dict[str, Any] | None = None
    """조립이면 구성품끼리 겹침 보고(ok · items · total_volume). 구성품이 하나면 None."""
    step_file: str
    point_file: str = ""
    """이 점의 모든 것(변수 · 영역 · 풀린 조건). 해석이 물을 유일한 창구다."""


class StudySummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    work_id: uuid.UUID | None
    work_name: str | None
    work_kind: str | None
    """대상 — 어느 도면(부품 · 지그 · 조립)을 훑는가. 지워졌으면 None(스냅샷은 남는다)."""
    method: str
    samples: int
    seed: int
    point_count: int
    created_at: datetime


class StudyOut(StudySummaryOut):
    recipe: dict[str, Any]
    conditions: dict[str, Any] = Field(default_factory=dict)
    """이 스터디가 돌던 때의 해석 조건 — 작업이 나중에 바뀌어도 여기 남는다."""
    factors: list[dict[str, Any]]
    keep_forever: bool = False
    """영구보관 — 보관 기한이 지나도 공유 폴더를 남긴다."""
    released_at: datetime | None = None
    """해석이 「다 읽었다」 고 알린 때 — 알린 폴더는 먼저 치워진다."""
    export_dir_windows: str
    """공유 폴더 경로(F:\\…). 아직 안 보냈으면 빈 문자열."""
    exported_at: datetime | None
    """화면 · 해석 쪽이 여는 경로(F:\\…). 서버가 보는 경로는 안 내보낸다."""
    job: dict[str, Any] | None = None
    points: list[PointOut] = Field(default_factory=list)
    done: int = 0
    failed: int = 0
