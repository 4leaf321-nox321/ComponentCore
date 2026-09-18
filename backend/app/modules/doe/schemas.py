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


class PreviewRequest(BaseModel):
    factors: list[FactorIn]
    method: str = "factorial"
    samples: int = Field(default=20, ge=1, le=500)
    seed: int = 1


class StudyCreateRequest(PreviewRequest):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    recipe: dict[str, Any]
    material: str = "aluminum"
    work_id: uuid.UUID | None = None


class PointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    params: dict[str, Any]
    status: str
    error: str
    metrics: dict[str, Any] | None
    step_file: str


class StudySummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    work_id: uuid.UUID | None
    method: str
    samples: int
    seed: int
    material: str
    point_count: int
    created_at: datetime


class StudyOut(StudySummaryOut):
    recipe: dict[str, Any]
    factors: list[dict[str, Any]]
    export_dir_windows: str
    """화면 · 해석 쪽이 여는 경로(F:\\…). 서버가 보는 경로는 안 내보낸다."""
    job: dict[str, Any] | None = None
    points: list[PointOut] = Field(default_factory=list)
    done: int = 0
    failed: int = 0
