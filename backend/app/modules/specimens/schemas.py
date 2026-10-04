from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PresetOut(BaseModel):
    """시험 규격 프리셋 하나 — 공개 규격(`builtin`, 코드)과 사내 규격(`internal`, DB)이 같은
    모양이다. `preset` 은 `core.specimens.presets.Preset` 그대로(시편 치수 · 배치 규칙 · 해석
    기본값 · 출처 · 검토 여부)."""

    id: str
    origin: Literal["builtin", "internal"]
    test: str
    standard: str
    name: str
    preset: dict[str, Any]
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class PresetIn(BaseModel):
    """사내 규격 저장 — 프리셋 모양 그대로(`id` 는 서버가 정한다). 칸 검사는 코어가 한다."""

    preset: dict[str, Any]


class SpecimenRequest(BaseModel):
    preset_id: str = Field(min_length=1, max_length=64)
    length: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    thickness: float | None = Field(default=None, gt=0)
    """비우면 프리셋의 시편 치수."""
    fixture: bool = True
    """시험 지그(롤러 · 노즈 …)를 함께 그린다."""
    conditions: bool = True
    """해석 조건(구속 · 접촉 · 하중 · 해석 설정)을 붙인다 — 시험 지그가 있어야 한다."""


class SpecimenBuildOut(BaseModel):
    recipe: dict[str, Any]
    conditions: dict[str, Any] | None
    notes: list[str]
    values: dict[str, float] = Field(default_factory=dict)
    """레시피 변수를 푼 값 — 지지 간격 · 처짐 · 반지름을 화면이 식 없이 보인다."""


class SpecimenWorkRequest(SpecimenRequest):
    name: str | None = Field(default=None, max_length=120)
    """비우면 프리셋 이름."""
    folder: str = Field(default="", max_length=255)
