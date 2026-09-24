from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- 레시피 ---------------------------------------------------------------------


class RecipeRequest(BaseModel):
    recipe: dict[str, Any]


class ViewsRequest(RecipeRequest):
    views: list[str] = Field(default_factory=lambda: ["iso", "front", "top", "right"])
    width: int = Field(default=640, ge=120, le=2000)


class FindRequest(RecipeRequest):
    query: dict[str, Any] = Field(default_factory=dict)
    """what · kind · role · of_face_role · axis · radius · min_length · max_length · near ·
    limit."""


class SelectorsRequest(RecipeRequest):
    pick: dict[str, Any] = Field(default_factory=dict)
    """`what`(faces · edges · vertices) 와 `point`([x, y, z] — 3D 에서 찍은 자리)."""
    picks: list[dict[str, Any]] | None = Field(default=None, max_length=500)
    """**여럿을 한 번에** — 화면의 사각형 선택(Shift + 끌기). 주면 `pick` 대신 이것을 보고
    `{"items": [후보 한 벌, …]}` 을 같은 순서로 돌려준다. 도면을 **한 번만** 만든다 — 하나씩
    부르면 스무 개를 고른 사각형이 도면을 스무 번 만든다."""


class MeasureRequest(RecipeRequest):
    a: dict[str, Any]
    b: dict[str, Any]
    """선택자: {point:[x,y,z]} | {hole_near:[…]} | {face_near:[…]} | {edge_near:[…]}."""


class PatchRequest(RecipeRequest):
    ops: list[dict[str, Any]] = Field(min_length=1)


class PlaceRequest(RecipeRequest):
    mover: str
    onto: str
    face: str = "top"
    offset: float = 0.0
    align: str = "center"


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
