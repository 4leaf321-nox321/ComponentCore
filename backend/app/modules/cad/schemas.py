from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- 레시피 ---------------------------------------------------------------------


class RecipeRequest(BaseModel):
    recipe: dict[str, Any]


class InterferenceRequest(RecipeRequest):
    tolerance: float | None = Field(default=None, ge=0)
    """이 부피(mm³) 이하의 겹침은 닿은 것으로 본다. 없으면 0.5."""


class GeometryRequest(RecipeRequest):
    material: str | None = None
    """주면 질량 · 무게중심 · 관성까지 낸다(steel · aluminum · abs …)."""


class SweepRequest(GeometryRequest):
    """치수 하나를 값마다 바꿔 보는 요청 — 「연결부는 그대로, 두께만 바꿔 가며」."""

    param: str
    values: list[float] = Field(min_length=1, max_length=40)


class RecipeProblemsOut(BaseModel):
    ok: bool
    problems: list[str]
    """비어 있으면 통과. 있으면 어느 칸이 왜 틀렸는지."""


class RecipeInfoOut(BaseModel):
    """레시피를 실제로 만들어 본 결과(요약). 화면 미리보기가 glTF 와 함께 받는다."""

    summary: dict[str, Any]


class BeamRequest(BaseModel):
    """보 1차 공진 — 목표 주파수를 주면 **두께를 되짚고**, 두께를 주면 주파수를 낸다."""

    length_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    thickness_mm: float | None = Field(default=None, gt=0)
    target_hz: float | None = Field(default=None, gt=0)
    material: str = "aluminum"
    support: str = "cantilever"
    added_mass_g: float = Field(default=0, ge=0)


class RecipeSchemaOut(BaseModel):
    schema_: dict[str, Any] = Field(alias="schema")
    """노드 종류와 칸 — JSON Schema. 편집기가 폼을 그리고 AI 프롬프트가 읽는다."""
    templates: dict[str, dict[str, Any]]
    template_labels: dict[str, str]

    model_config = ConfigDict(populate_by_name=True)
