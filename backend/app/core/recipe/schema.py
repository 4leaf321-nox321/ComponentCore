"""레시피의 모양 — 노드 종류와 각 칸.

pydantic 으로 적는 이유: 검증 메시지가 곧 **AI 에게 돌려주는 말**이다. "nodes[3].radius 는
0 보다 커야 합니다" 가 나와야 AI 가 스스로 고치고, 사람도 어느 칸인지 안다.

노드는 **순서대로** 평가되고 앞 노드를 id 로 가리킨다. 순환은 없다(앞만 가리킨다).
"""

from __future__ import annotations

from collections.abc import Mapping
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


class Segment(BaseModel):
    """임의 윤곽의 한 구간 — 다음 점까지 직선, `via` 가 있으면 그 점을 지나는 호."""

    model_config = ConfigDict(extra="forbid")

    to: XY
    via: XY | None = None


class PolylineShape(_Shape):
    """임의 윤곽 — 시작점에서 구간을 이어 닫는다(마지막 점이 시작점과 다르면 직선으로 닫는다).
    브래킷 측면 · 계단 · 플랜지처럼 사각형으로 안 되는 모양."""

    type: Literal["polyline"]
    start: XY
    segments: list[Segment] = Field(min_length=2)


SketchShape = Annotated[
    Rect | CircleShape | PolygonShape | RegularPolygonShape | Slot | PolylineShape,
    Field(discriminator="type"),
]

PlaneName = Literal["XY", "XZ", "YZ", "YX", "ZX", "ZY"]


class PlaneSpec(BaseModel):
    """스케치가 놓이는 평면 — 이름 + 원점, 또는 **어느 면 위**(법선 · x 방향).

    3D 에서 면을 누르면 편집기가 그 면의 중심 · 법선으로 채운다. `normal` 이 있으면 `name` 은
    무시된다."""

    model_config = ConfigDict(extra="forbid")

    name: PlaneName = "XY"
    origin: XYZ = (0.0, 0.0, 0.0)
    normal: XYZ | None = None
    """평면의 법선(= 돌출 방향). 있으면 이름 대신 이것으로 평면을 만든다."""
    x_dir: XYZ | None = None
    """스케치의 X 방향. 비우면 법선과 직교하는 방향 하나를 고른다."""


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


class SphereNode(_Node):
    op: Literal["sphere"]
    radius: Positive
    at: XYZ = (0.0, 0.0, 0.0)


class ConeNode(_Node):
    op: Literal["cone"]
    bottom_radius: Positive
    top_radius: float = Field(default=0.0, ge=0)
    height: Positive
    at: XYZ = (0.0, 0.0, 0.0)
    """밑면 중심."""
    axis: Literal["X", "Y", "Z"] = "Z"


class TorusNode(_Node):
    op: Literal["torus"]
    major_radius: Positive
    minor_radius: Positive
    at: XYZ = (0.0, 0.0, 0.0)
    axis: Literal["X", "Y", "Z"] = "Z"


class LoftNode(_Node):
    """두 개 이상의 스케치를 잇는 입체 — 노즐 · 손잡이 · 덕트."""

    op: Literal["loft"]
    sketches: list[str] = Field(min_length=2)
    ruled: bool = False
    """직선으로 잇는다(각진 전이). 끄면 매끄럽게."""


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


class EdgeNear(BaseModel):
    """**위치로 고른 엣지** — 3D 에서 누른 엣지의 중점들. 인덱스가 아니라 위치라서 형상을 조금
    고쳐도 같은 자리의 엣지를 다시 찾는다."""

    model_config = ConfigDict(extra="forbid")

    near: list[XYZ] = Field(min_length=1)
    tolerance: float = Field(default=1.0, gt=0)


EdgeSelect = Literal["all", "vertical", "horizontal", "top", "bottom"] | EdgeNear


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


#: 미터 나사 — (탭 드릴, 여유 구멍, 카운터보어 지름, 카운터보어 깊이, 카운터싱크 지름). mm.
THREADS: dict[str, tuple[float, float, float, float, float]] = {
    "M3": (2.5, 3.4, 6.5, 3.4, 6.9),
    "M4": (3.3, 4.5, 8.0, 4.6, 8.9),
    "M5": (4.2, 5.5, 10.0, 5.7, 10.9),
    "M6": (5.0, 6.6, 11.0, 6.8, 12.9),
    "M8": (6.8, 9.0, 15.0, 9.0, 17.0),
    "M10": (8.5, 11.0, 18.0, 11.0, 21.0),
    "M12": (10.2, 13.5, 20.0, 13.0, 25.0),
}


class HoleNode(_Node):
    """구멍 — 단순 · 카운터보어 · 카운터싱크 · 탭. `plane` 을 주면 그 면에서 안쪽으로, 안 주면
    대상의 윗면(+Z)에서 아래로. `thread` 를 주면 지름을 표에서 채운다(M3~M12)."""

    op: Literal["hole"]
    target: str
    at: list[XY] = Field(min_length=1)
    """평면 위의 위치들(plane 을 안 주면 XY)."""
    kind: Literal["simple", "counterbore", "countersink", "tap"] = "simple"
    thread: str | None = None
    """M3 · M4 · M5 · M6 · M8 · M10 · M12. 주면 diameter 와 카운터 치수를 표에서 채운다."""
    diameter: Positive | None = None
    """thread 가 없으면 필수. simple 은 관통 지름, tap 은 탭 드릴 지름."""
    depth: Positive | None = None
    """비우면 관통."""
    counter_diameter: Positive | None = None
    """카운터보어 · 카운터싱크의 큰 지름. thread 가 있으면 표에서."""
    counter_depth: Positive | None = None
    """카운터보어 깊이. thread 가 있으면 표에서."""
    countersink_angle: float = Field(default=90.0, gt=0, lt=180)
    plane: PlaneSpec | None = None
    """어느 면에서 뚫나. 3D 에서 면을 누르면 채워진다."""

    @model_validator(mode="after")
    def _check_dimensions(self) -> HoleNode:
        if self.thread is not None and self.thread not in THREADS:
            raise ValueError(
                f"thread: 모르는 나사입니다: {self.thread} (가능: {', '.join(THREADS)})"
            )
        if self.thread is None and self.diameter is None:
            raise ValueError("diameter: thread 를 안 주면 지름이 필요합니다")
        if self.kind in ("counterbore", "countersink") and self.thread is None:
            if self.counter_diameter is None:
                raise ValueError("counter_diameter: 카운터 지름이 필요합니다(또는 thread)")
            if self.kind == "counterbore" and self.counter_depth is None:
                raise ValueError("counter_depth: 카운터보어 깊이가 필요합니다(또는 thread)")
        return self


FaceSelect = Literal["top", "bottom", "none"] | EdgeNear


class ShellNode(_Node):
    """속을 비운다 — `open` 면을 뚫고 나머지를 `thickness` 두께의 껍질로."""

    op: Literal["shell"]
    target: str
    thickness: Positive
    open: FaceSelect = "top"
    """뚫을 면: top · bottom · none(닫힌 속 빈 덩어리) · {"near": [[x,y,z]]}(면 중심 위치)."""


class PatternNode(_Node):
    """어떤 노드를 여러 벌 복제한다 — 결과는 한 덩어리(합집합)가 아니라 **복사본들의 묶음**이라
    보통 cut 의 tools 나 union 의 targets 로 쓴다."""

    op: Literal["pattern"]
    source: str
    kind: Literal["linear", "circular", "grid"] = "linear"
    count: int = Field(ge=1, le=200)
    spacing: XYZ = (10.0, 0.0, 0.0)
    """linear: 복사본 사이 간격 벡터. grid: X 방향 간격은 이 벡터, Y 방향은 spacing_y."""
    count_y: int = Field(default=1, ge=1, le=200)
    """grid: Y 방향 개수."""
    spacing_y: XYZ = (0.0, 10.0, 0.0)
    """grid: Y 방향 간격 벡터."""
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
    | SphereNode
    | ConeNode
    | TorusNode
    | LoftNode
    | UnionNode
    | CutNode
    | IntersectNode
    | FilletNode
    | ChamferNode
    | HoleNode
    | ShellNode
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
                            f"'{name}' 은 앞에 없는 피처입니다"
                        )
            seen.add(node.id)
        if self.result is not None and self.result not in seen:
            raise ValueError(f"result: '{self.result}' 피처가 없습니다")
        return self

    @property
    def result_id(self) -> str:
        return self.result or self.nodes[-1].id


#: 노드 종류별로 다른 노드를 가리키는 칸.
_REFERENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "extrude": ("sketch",),
    "revolve": ("sketch",),
    "loft": ("sketches",),
    "shell": ("target",),
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


#: pydantic 의 영어 문구 → 사람 말. 화면과 AI 가 같은 말을 읽는다. 없는 것은 원문 그대로.
_MESSAGES: dict[str, str] = {
    "too_short": "적어도 {min_length}개가 있어야 합니다",
    "too_long": "많아야 {max_length}개입니다",
    "missing": "값이 빠졌습니다",
    "greater_than": "{gt}보다 커야 합니다",
    "greater_than_equal": "{ge} 이상이어야 합니다",
    "less_than_equal": "{le} 이하여야 합니다",
    "string_pattern_mismatch": "쓸 수 없는 문자가 있습니다",
    "string_too_short": "값이 필요합니다",
    "string_too_long": "너무 깁니다",
    "extra_forbidden": "이 피처에는 없는 칸입니다",
    "int_parsing": "정수여야 합니다",
    "float_parsing": "숫자여야 합니다",
    "bool_parsing": "예/아니오 값이어야 합니다",
    "union_tag_invalid": "모르는 종류입니다: {tag} (가능: {expected_tags})",
    "literal_error": "가능한 값: {expected}",
    "model_type": '위치로 고르려면 {{"near": [[x, y, z], …]}} 모양이어야 합니다',
    "dict_type": '위치로 고르려면 {{"near": [[x, y, z], …]}} 모양이어야 합니다',
}


def _humanize(error: Mapping[str, Any]) -> str:
    kind = str(error.get("type", ""))
    context = {key: str(value) for key, value in (error.get("ctx") or {}).items()}
    template = _MESSAGES.get(kind)
    if template is not None:
        try:
            return template.format(**context)
        except KeyError:
            return template
    return str(error.get("msg", "")).removeprefix("Value error, ")


def parse(raw: dict[str, Any]) -> Recipe:
    try:
        return Recipe.model_validate(raw)
    except ValidationError as failure:
        problems: list[str] = []
        for error in failure.errors()[:8]:
            where = ".".join(str(part) for part in error["loc"] if not _is_union_tag(part))
            problems.append(f"{where or 'recipe'}: {_humanize(error)}")
        raise RecipeValidationError(problems) from failure


def _is_union_tag(part: Any) -> bool:
    """pydantic 이 유니온 경로에 끼우는 `SketchNode` · `literal[...]` 같은 조각은 사람에게 뜻이
    없다."""
    return isinstance(part, str) and (part[:1].isupper() or part.startswith("literal["))


def describe() -> dict[str, Any]:
    """노드 종류와 칸을 JSON 스키마로 — 편집기가 폼을 그리고 AI 프롬프트가 읽는다."""
    return Recipe.model_json_schema()
