from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- 레시피 ---------------------------------------------------------------------


class RecipeRequest(BaseModel):
    recipe: dict[str, Any]


class ViewsRequest(RecipeRequest):
    views: list[str] = Field(default_factory=lambda: ["iso", "front", "top", "right"])
    width: int = Field(default=640, ge=120, le=2000)


class SketchSolveRequest(BaseModel):
    shape: dict[str, Any]
    """구속 윤곽(`type: "constrained"`) 하나."""
    params: dict[str, Any] = Field(default_factory=dict)
    """치수 칸의 `=변수` 를 풀 도면 변수."""


class MidSurfaceRequest(RecipeRequest):
    node: str | None = None
    """중간면을 뽑을 노드 — 없으면 레시피의 결과."""


class UnfoldRequest(RecipeRequest):
    k_factor: float = Field(default=0.5, ge=0, le=1)
    """중립면 위치 — 안쪽 면에서 두께의 몇 할. 굽힐 때(`bend`)와 같아야 한다."""
    flip: bool = False
    """기준면을 반대쪽 겉면으로 — 굽힘의 위 · 아래가 바뀐다."""
    node: str | None = None
    """펼 노드 — 없으면 레시피의 결과."""


class DrawingRequest(RecipeRequest):
    title: str = Field(default="", max_length=120)
    """표제란의 이름 — 비우면 「(이름 없음)」."""
    sheet: str = Field(default="A3", pattern="^(A3|A4)$")
    material: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=200)
    """도면 왼쪽 아래에 적을 한 줄(공차 · 다듬질 같은 것)."""
    node: str | None = None
    """그릴 노드 — 없으면 레시피의 결과."""


class CutListRequest(RecipeRequest):
    node: str
    """구조 프레임(`frame`) 노드의 id."""


class FindRequest(RecipeRequest):
    query: dict[str, Any] = Field(default_factory=dict)
    """what · kind · role · of_face_role · axis · radius · min_length · max_length · near ·
    limit."""


class SelectorsRequest(RecipeRequest):
    pick: dict[str, Any] = Field(default_factory=dict)
    """`what`(faces · edges · vertices) 와 `point`([x, y, z] — 3D 에서 찍은 자리). 화면은
    누른 면 · 엣지의 번호 `index`(`/cad/recipe/mesh` 의 번호)도 준다 — 중심이 같은 두 면(판
    윗면과 그 위 블록의 아랫면)을 가른다."""
    picks: list[dict[str, Any]] | None = Field(default=None, max_length=500)
    """**여럿을 한 번에** — 화면의 사각형 선택(Shift + 끌기). 주면 `pick` 대신 이것을 보고
    `{"items": [후보 한 벌, …]}` 을 같은 순서로 돌려준다. 도면을 **한 번만** 만든다 — 하나씩
    부르면 스무 개를 고른 사각형이 도면을 스무 번 만든다."""


class FramesRequest(RecipeRequest):
    conditions: dict[str, Any] | None = None
    """해석 조건 한 벌 — 그 안의 좌표계(`coordinate_systems`)를 함께 푼다."""


class ConditionNotesRequest(BaseModel):
    recipe: dict[str, Any]
    conditions: dict[str, Any]


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


class MatePickRequest(RecipeRequest):
    node: str
    """구속을 거는 구성품(`component`)의 id."""
    side: str = Field(pattern="^(this|to)$")
    """`this` — 그 구성품에서 고른 것(답은 가져온 도면의 좌표로 된 질의). `to` — 앞에 놓인
    것(`target`)에서 고른 것."""
    target: str | None = None
    what: str = Field(default="faces", pattern="^(faces|edges)$")
    point: list[float] = Field(min_length=3, max_length=3)
    """3D 에서 누른 자리(조립의 좌표) — 면이면 그 면의 가운데, 엣지면 가운데 점."""


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
