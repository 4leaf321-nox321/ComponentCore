"""레시피의 모양 — 노드 종류와 각 칸.

pydantic 으로 적는 이유: 검증 메시지가 곧 **AI 에게 돌려주는 말**이다. "nodes[3].radius 는
0 보다 커야 합니다" 가 나와야 AI 가 스스로 고치고, 사람도 어느 칸인지 안다.

노드는 **순서대로** 평가되고 앞 노드를 id 로 가리킨다. 순환은 없다(앞만 가리킨다).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

XY = tuple[float, float]
XYZ = tuple[float, float, float]
Positive = Annotated[float, Field(gt=0)]

# --- 스케치 도형 ---------------------------------------------------------------


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: XY = (0.0, 0.0)
    """중심(다각형은 원점 오프셋)."""
    rotation: float = 0.0
    mode: Literal["add", "cut"] = "add"
    """cut 이면 앞의 도형에서 뺀다(구멍 · 노치)."""


class Rect(_Shape):
    type: Literal["rect"]
    width: Positive
    height: Positive


class CircleShape(_Shape):
    type: Literal["circle"]
    radius: Positive


class PolygonShape(_Shape):
    type: Literal["polygon"]
    points: list[XY] = Field(min_length=3)


class RegularPolygonShape(_Shape):
    type: Literal["regular_polygon"]
    radius: Positive
    sides: int = Field(ge=3, le=64)


class Slot(_Shape):
    type: Literal["slot"]
    length: Positive
    """양 끝 반원을 포함한 전체 길이."""
    width: Positive


SketchShape = Annotated[
    Rect | CircleShape | PolygonShape | RegularPolygonShape | Slot, Field(discriminator="type")
]

PlaneName = Literal["XY", "XZ", "YZ", "YX", "ZX", "ZY"]


class PlaneSpec(BaseModel):
    """스케치가 놓이는 평면. 이름 + 원점 이동. 3단계에서 「어느 면 위」 가 더해진다."""

    model_config = ConfigDict(extra="forbid")

    name: PlaneName = "XY"
    origin: XYZ = (0.0, 0.0, 0.0)


# --- 노드 ---------------------------------------------------------------------


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z_][A-Za-z0-9_-]*$")
    label: str = ""
    """사람이 붙이는 이름 — 편집기의 피처 트리에 보인다."""


class SketchNode(_Node):
    op: Literal["sketch"]
    plane: PlaneSpec = Field(default_factory=PlaneSpec)
    shapes: list[SketchShape] = Field(min_length=1)


class ExtrudeNode(_Node):
    op: Literal["extrude"]
    sketch: str
    distance: Positive
    direction: Literal["normal", "reverse", "both"] = "normal"
    """평면 법선 쪽(normal) · 반대(reverse) · 양쪽(both, 절반씩)."""


class RevolveNode(_Node):
    op: Literal["revolve"]
    sketch: str
    axis: Literal["X", "Y", "Z"] = "Z"
    angle: float = Field(default=360.0, gt=0, le=360)


class BoxNode(_Node):
    op: Literal["box"]
    length: Positive
    width: Positive
    height: Positive
    at: XYZ = (0.0, 0.0, 0.0)
    """중심."""


class CylinderNode(_Node):
    op: Literal["cylinder"]
    radius: Positive
    height: Positive
    at: XYZ = (0.0, 0.0, 0.0)
    axis: Literal["X", "Y", "Z"] = "Z"


class UnionNode(_Node):
    op: Literal["union"]
    targets: list[str] = Field(min_length=2)


class CutNode(_Node):
    op: Literal["cut"]
    target: str
    tools: list[str] = Field(min_length=1)


class IntersectNode(_Node):
    op: Literal["intersect"]
    targets: list[str] = Field(min_length=2)


EdgeSelect = Literal["all", "vertical", "horizontal", "top", "bottom"]


class FilletNode(_Node):
    op: Literal["fillet"]
    target: str
    edges: EdgeSelect = "all"
    radius: Positive


class ChamferNode(_Node):
    op: Literal["chamfer"]
    target: str
    edges: EdgeSelect = "all"
    length: Positive


class HoleNode(_Node):
    op: Literal["hole"]
    target: str
    at: list[XY] = Field(min_length=1)
    """XY 위치들 — 위(+Z)에서 아래로 뚫는다."""
    diameter: Positive
    depth: Positive | None = None
    """비우면 관통."""


class PatternNode(_Node):
    """어떤 노드를 여러 벌 복제한다 — 결과는 한 덩어리(합집합)가 아니라 **복사본들의 묶음**이라
    보통 cut 의 tools 나 union 의 targets 로 쓴다."""

    op: Literal["pattern"]
    source: str
    kind: Literal["linear", "circular"] = "linear"
    count: int = Field(ge=2, le=200)
    spacing: XYZ = (10.0, 0.0, 0.0)
    """linear: 복사본 사이 간격 벡터."""
    axis: Literal["X", "Y", "Z"] = "Z"
    """circular: 회전축(원점 통과)."""
    angle: float = Field(default=360.0, gt=0, le=360)
    """circular: 전체 각도."""


class TransformNode(_Node):
    op: Literal["transform"]
    target: str
    translate: XYZ = (0.0, 0.0, 0.0)
    rotate: XYZ = (0.0, 0.0, 0.0)
    """X · Y · Z 축 회전(도). 회전 뒤 이동."""


class MirrorNode(_Node):
    op: Literal["mirror"]
    target: str
    plane: PlaneName = "YZ"
    keep_original: bool = True


class ImportStepNode(_Node):
    """외부 CAD 에서 온 형상 — 레시피의 뿌리. `file` 은 호출자가 경로로 푸는 열쇠(작업물
    id)."""

    op: Literal["import_step"]
    file: str = Field(min_length=1)


Node = Annotated[
    SketchNode
    | ExtrudeNode
    | RevolveNode
    | BoxNode
    | CylinderNode
    | UnionNode
    | CutNode
    | IntersectNode
    | FilletNode
    | ChamferNode
    | HoleNode
    | PatternNode
    | TransformNode
    | MirrorNode
    | ImportStepNode,
    Field(discriminator="op"),
]


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    units: Literal["mm"] = "mm"
    nodes: list[Node] = Field(min_length=1, max_length=500)
    result: str | None = None
    """결과로 삼을 노드. 비우면 마지막 노드."""

    @model_validator(mode="after")
    def _check_references(self) -> Recipe:
        seen: set[str] = set()
        for index, node in enumerate(self.nodes):
            if node.id in seen:
                raise ValueError(f"nodes[{index}]: id '{node.id}' 가 겹칩니다")
            for key, value in _references(node):
                names = value if isinstance(value, list) else [value]
                for name in names:
                    if name not in seen:
                        raise ValueError(
                            f"nodes[{index}] ({node.id}).{key}: "
                            f"'{name}' 은 앞에 없는 노드입니다"
                        )
            seen.add(node.id)
        if self.result is not None and self.result not in seen:
            raise ValueError(f"result: '{self.result}' 노드가 없습니다")
        return self

    @property
    def result_id(self) -> str:
        return self.result or self.nodes[-1].id


#: 노드 종류별로 다른 노드를 가리키는 칸.
_REFERENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "extrude": ("sketch",),
    "revolve": ("sketch",),
    "union": ("targets",),
    "cut": ("target", "tools"),
    "intersect": ("targets",),
    "fillet": ("target",),
    "chamfer": ("target",),
    "hole": ("target",),
    "pattern": ("source",),
    "transform": ("target",),
    "mirror": ("target",),
}


def _references(node: Any) -> list[tuple[str, str | list[str]]]:
    return [(key, getattr(node, key)) for key in _REFERENCE_FIELDS.get(node.op, ())]


class RecipeValidationError(ValueError):
    """어느 칸이 왜 틀렸는지 — 사람과 AI 가 그대로 읽는 말."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__(" / ".join(problems))
        self.problems = problems


def parse(raw: dict[str, Any]) -> Recipe:
    try:
        return Recipe.model_validate(raw)
    except ValidationError as failure:
        problems: list[str] = []
        for error in failure.errors()[:8]:
            where = ".".join(str(part) for part in error["loc"] if not _is_union_tag(part))
            message = str(error["msg"]).removeprefix("Value error, ")
            problems.append(f"{where or 'recipe'}: {message}")
        raise RecipeValidationError(problems) from failure


def _is_union_tag(part: Any) -> bool:
    """pydantic 이 판별 유니온 경로에 끼우는 `SketchNode` 같은 이름은 사람에게 뜻이 없다."""
    return isinstance(part, str) and part[:1].isupper()


def describe() -> dict[str, Any]:
    """노드 종류와 칸을 JSON 스키마로 — 편집기가 폼을 그리고 AI 프롬프트가 읽는다."""
    return Recipe.model_json_schema()
