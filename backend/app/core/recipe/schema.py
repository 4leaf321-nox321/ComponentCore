"""레시피의 모양 — 노드 종류와 각 칸.

pydantic 으로 적는 이유: 검증 메시지가 곧 **AI 에게 돌려주는 말**이다. "nodes[3].radius 는
0 보다 커야 합니다" 가 나와야 AI 가 스스로 고치고, 사람도 어느 칸인지 안다.

노드는 **순서대로** 평가되고 앞 노드를 id 로 가리킨다. 순환은 없다(앞만 가리킨다).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.recipe.params import ExpressionError, resolve

XY = tuple[float, float]
XYZ = tuple[float, float, float]
Positive = Annotated[float, Field(gt=0)]

# --- 스케치 도형 ---------------------------------------------------------------


#: 치수를 어느 자리에 맞출 것인가 — **한쪽을 고정하고 반대쪽을 늘릴 때** 쓴다.
#: min = 작은 쪽 끝을 `at` 에 두고 키운다 · center = 가운데 · max = 큰 쪽 끝.
AlignName = Literal["min", "center", "max"]
Align2 = tuple[AlignName, AlignName]
Align3 = tuple[AlignName, AlignName, AlignName]


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: XY = (0.0, 0.0)
    """중심(다각형은 원점 오프셋)."""
    rotation: float = 0.0
    mode: Literal["add", "cut"] = "add"
    """cut 이면 앞의 도형에서 뺀다(구멍 · 노치)."""


class _Aligned(BaseModel):
    """`at` 을 도형의 어디로 볼 것인가. 기본은 가운데.

    「왼쪽 끝을 고정하고 오른쪽으로 늘린다」 는 `align: ["min", "center"]` 로 한다 — 폭을
    키워도 왼쪽 끝은 `at` 에 그대로 있다. 매개변수(`params`)와 함께 쓰면 치수 하나를 고쳐
    한쪽으로만 자라는 판을 만들 수 있다."""

    align: Align2 = ("center", "center")


class Rect(_Shape, _Aligned):
    type: Literal["rect"]
    width: Positive
    height: Positive


class CircleShape(_Shape, _Aligned):
    type: Literal["circle"]
    radius: Positive


class PolygonShape(_Shape):
    type: Literal["polygon"]
    points: list[XY] = Field(min_length=3)


class RegularPolygonShape(_Shape, _Aligned):
    type: Literal["regular_polygon"]
    radius: Positive
    sides: int = Field(ge=3, le=64)


class Slot(_Shape, _Aligned):
    type: Literal["slot"]
    length: Positive
    """`measure` 에 따라 전체 길이이거나 양 끝 **중심 사이** 거리."""
    width: Positive
    measure: Literal["overall", "centers"] = "overall"
    """overall = 반원까지 포함한 전체 길이 · centers = 두 끝 원의 중심 사이(도면이 쓰는 값)."""


class Segment(BaseModel):
    """한 구간 — 다음 점(`to`)까지 어떻게 가나.

    - 아무것도 없으면 **직선**
    - `radius` 면 그 반지름의 **호**. 부호가 휘는 쪽(양수 = 가는 방향의 왼쪽)
    - `tangent` 면 **앞 구간 끝 방향으로 매끄럽게 이어지는 호**(반지름은 저절로 정해진다)
    - `via` 면 그 점을 **지나는 호**(사람이 3D · 캔버스에서 찍은 자리)

    글로 지시할 때는 `radius` · `tangent` 가 낫다 — `via` 는 호 위의 점을 미리 계산해야 한다.
    """

    model_config = ConfigDict(extra="forbid")

    to: XY
    via: XY | None = None
    radius: float | None = None
    tangent: bool = False

    @model_validator(mode="after")
    def _one_way(self) -> Segment:
        chosen = [self.via is not None, self.radius is not None, self.tangent]
        if sum(chosen) > 1:
            raise ValueError("via · radius · tangent 중 하나만 씁니다")
        if self.radius is not None and self.radius == 0:
            raise ValueError("radius: 0 은 호가 되지 않습니다 — 빼면 직선입니다")
        return self


class PolylineShape(_Shape):
    """임의 윤곽 — 시작점에서 구간을 이어 닫는다(마지막 점이 시작점과 다르면 직선으로 닫는다).
    브래킷 측면 · 계단 · 플랜지처럼 사각형으로 안 되는 모양."""

    type: Literal["polyline"]
    start: XY
    segments: list[Segment] = Field(min_length=2)
    corner_radius: float = Field(default=0.0, ge=0)
    """모든 모서리를 이 반지름으로 둥글린다(0 이면 각지게). 호(`via`)가 있으면 쓸 수 없다."""


class RoundedRect(_Shape, _Aligned):
    type: Literal["rounded_rect"]
    width: Positive
    height: Positive
    radius: Positive
    """모서리 반지름 — 너비 · 높이의 절반보다 작아야 한다."""


class TrapezoidShape(_Shape, _Aligned):
    """사다리꼴 — 밑변 너비와 양쪽 빗변 각도. 90° 면 직각."""

    type: Literal["trapezoid"]
    width: Positive
    height: Positive
    left_angle: float = Field(default=75.0, gt=0, lt=180)
    right_angle: float | None = Field(default=None, gt=0, lt=180)
    """비우면 왼쪽과 같다(좌우 대칭)."""


class PathShape(_Shape):
    """두께 있는 선 — 중심선을 찍고 폭을 준다. 리브 · 얇은 벽 · 브래킷 단면처럼 「선을 따라
    살이 붙는」 모양. 양 끝은 둥글다."""

    type: Literal["path"]
    start: XY
    segments: list[Segment] = Field(min_length=1)
    width: Positive
    corners: Literal["round", "sharp"] = "round"


class TriangleShape(_Shape, _Aligned):
    """변과 각으로 만드는 삼각형 — 세 값이면 정해진다(예: a · b 와 낀각 C, 또는 a · B · C).
    변은 소문자, 마주 보는 각은 대문자다."""

    type: Literal["triangle"]
    a: Positive | None = None
    b: Positive | None = None
    c: Positive | None = None
    A: float | None = Field(default=None, gt=0, lt=180)
    B: float | None = Field(default=None, gt=0, lt=180)
    C: float | None = Field(default=None, gt=0, lt=180)

    @model_validator(mode="after")
    def _enough(self) -> TriangleShape:
        given = [v for v in (self.a, self.b, self.c, self.A, self.B, self.C) if v is not None]
        if len(given) < 3:
            raise ValueError("변 · 각을 셋은 주어야 삼각형이 정해집니다")
        if all(v is None for v in (self.a, self.b, self.c)):
            raise ValueError("변을 적어도 하나는 주어야 크기가 정해집니다")
        return self


class EllipseShape(_Shape, _Aligned):
    type: Literal["ellipse"]
    x_radius: Positive
    y_radius: Positive


class TextShape(_Shape, _Aligned):
    """글자 — 각인(cut) · 양각(add). 폰트는 서버의 것이라 글꼴 모양은 기기마다 조금 다를 수
    있다. 획이 얇으면 돌출이 깨지니 크기 5mm 이상을 권한다."""

    type: Literal["text"]
    text: str = Field(min_length=1, max_length=80)
    size: Positive
    """글자 높이(mm)."""
    bold: bool = False


SketchShape = Annotated[
    Rect
    | CircleShape
    | PolygonShape
    | RegularPolygonShape
    | Slot
    | PolylineShape
    | PathShape
    | RoundedRect
    | TrapezoidShape
    | TriangleShape
    | EllipseShape
    | TextShape,
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

    id: str = Field(min_length=1, max_length=40, pattern=r"^[^\W\d][\w-]*$")
    """피처 이름. 글자 · 숫자 · `_` · `-` 만 쓰고 숫자로 시작하지 않는다. **한글도 된다** —
    「베이스」 「핀1」 처럼 쓰면 레시피를 읽기가 훨씬 낫다(치수 이름도 마찬가지)."""
    label: str = ""
    """사람이 붙이는 이름 — 편집기의 피처 트리에 보인다."""


class SketchNode(_Node):
    op: Literal["sketch"]
    plane: PlaneSpec = Field(default_factory=PlaneSpec)
    shapes: list[SketchShape] = Field(min_length=1)
    hull: bool = False
    """도형들을 **감싸는 볼록 윤곽** 하나로 — 흩어진 자리를 덮는 베이스 판을 만들 때."""
    offset: float = 0.0
    """도형을 다 합친 뒤 윤곽을 밖(양수) · 안(음수)으로 띄운다 — 2D 여유."""


class ExtrudeNode(_Node):
    op: Literal["extrude"]
    sketch: str
    distance: Positive
    direction: Literal["normal", "reverse", "both"] = "normal"
    """평면 법선 쪽(normal) · 반대(reverse) · 양쪽(both, 절반씩)."""
    taper: float = Field(default=0.0, ge=-60, le=60)
    """구배(도). 양수면 갈수록 좁아진다 — 금형 빼기 · 위치 결정 핀의 안내 경사."""
    until: Literal["distance", "next", "last"] = "distance"
    """어디까지 — 거리(distance) · `target` 의 다음 면까지(next) · 마지막 면까지(last,
    관통)."""
    target: str | None = None
    """`until` 이 next · last 일 때 부딪힐 입체."""

    @model_validator(mode="after")
    def _until_needs_target(self) -> ExtrudeNode:
        if self.until != "distance":
            if self.target is None:
                raise ValueError(
                    "target: 「다음 면까지」 「마지막 면까지」 는 대상 입체가 있어야 합니다"
                )
            if self.direction == "both":
                raise ValueError("direction: 면까지 돌출은 한쪽 방향만 됩니다")
        return self


class SheetMetalNode(_Node):
    """판금 절곡 — 옆에서 본 꺾은선(`path`)을 따라 `thickness` 두께의 판을 세우고 `width` 만큼
    민다. 브래킷 · ㄱ자 앵글 · 덮개처럼 「판을 접어 만드는」 것.

    치수를 말로 주기 좋다: 「2t 판, 30 올라갔다 20 꺾임, 폭 40, 굽힘 R4」."""

    op: Literal["sheet_metal"]
    thickness: Positive
    width: Positive
    """꺾은선을 민 길이 — 판의 폭. 꺾은선이 폭의 **가운데**에 온다(양쪽으로 절반씩)."""
    path: list[XY] = Field(min_length=2)
    """평면 위의 꺾은선. 점 사이는 직선이고 꺾이는 곳이 굽힘이다."""
    plane: PlaneSpec = Field(default_factory=lambda: PlaneSpec(name="XZ"))
    """꺾은선이 놓이는 평면. 기본 XZ — 옆에서 본 모습을 그리고 Y 로 민다."""
    bend_radius: float = Field(default=0.0, ge=0)
    """굽힘 안쪽 반지름. 0 이면 각지게."""
    side: Literal["left", "right"] = "left"
    """두께가 붙는 쪽 — 꺾은선이 안쪽인가(left) 바깥쪽인가(right)."""


class HelixNode(_Node):
    """스케치(단면)를 나선을 따라 밀어 — 스프링 · 나사산. 단면은 XY 에 원점 중심으로 그리면
    나선 시작점에 알맞게 놓인다."""

    op: Literal["helix"]
    sketch: str
    radius: Positive
    pitch: Positive
    height: Positive
    at: XYZ = (0.0, 0.0, 0.0)
    """나선 축의 밑점."""
    axis: Literal["X", "Y", "Z"] = "Z"
    lefthand: bool = False


class SweepNode(_Node):
    """스케치를 경로를 따라 밀어 입체로 — 파이프 · 손잡이 · 케이블 홈. 경로는 3D 점들이며
    스케치는 첫 점에 놓여 있어야 자연스럽다(스케치 평면의 원점 = 경로 시작)."""

    op: Literal["sweep"]
    sketch: str
    path: list[XYZ] = Field(min_length=2)
    smooth: bool = False
    """점들을 매끄러운 곡선(스플라인)으로 잇는다. 끄면 직선 구간과 둥근 모서리."""


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
    """`align` 이 가리키는 자리. 기본은 중심."""
    align: Align3 = ("center", "center", "center")
    """축마다 min · center · max. 바닥을 바닥판에 붙이려면 Z 를 min 으로."""


class CylinderNode(_Node):
    op: Literal["cylinder"]
    radius: Positive
    height: Positive
    at: XYZ = (0.0, 0.0, 0.0)
    axis: Literal["X", "Y", "Z"] = "Z"
    align: Align3 = ("center", "center", "center")
    """축 방향(보통 Z)을 min 으로 두면 `at` 이 **밑면 중심**이 된다 — 핀 · 보스에 쓴다."""


class SphereNode(_Node):
    op: Literal["sphere"]
    radius: Positive
    at: XYZ = (0.0, 0.0, 0.0)
    align: Align3 = ("center", "center", "center")


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


FaceSelect = Literal["top", "bottom", "sides", "all", "none"] | EdgeNear


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
    scale: float = Field(default=1.0, gt=0)
    """원점 기준 배율. 크기 · 회전 · 이동 순."""


class WedgeNode(_Node):
    """쐐기 — 밑면은 length · width, 윗면은 (top_x_min…top_x_max) · (top_z_min…top_z_max) 로
    좁아지는 경사 블록. 지그의 경사 받침 · 쐐기 고임."""

    op: Literal["wedge"]
    length: Positive
    """X."""
    width: Positive
    """Y."""
    height: Positive
    """Z."""
    top_x_min: float = 0.0
    top_x_max: float | None = None
    """비우면 length — 윗면이 X 로 안 줄어든다."""
    top_z_min: float = 0.0
    top_z_max: float | None = None
    at: XYZ = (0.0, 0.0, 0.0)
    align: Align3 = ("center", "center", "center")

    @model_validator(mode="after")
    def _top_order(self) -> WedgeNode:
        if self.top_x_max is not None and self.top_x_max <= self.top_x_min:
            raise ValueError("top_x_max: top_x_min 보다 커야 합니다")
        if self.top_z_max is not None and self.top_z_max <= self.top_z_min:
            raise ValueError("top_z_max: top_z_min 보다 커야 합니다")
        return self


class BoltNode(_Node):
    """볼트 — 머리(육각 · 소켓) + 와셔 + 몸통. `at` 은 **머리가 앉는 면의 점**, 몸통은 -Z 로
    내려간다(`down=False` 면 +Z). 나사산은 없고 몸통은 호칭 지름 그대로. ISO 비례(머리 지름
    1.5d, 육각 높이 0.65d, 소켓 1.0d). 지그에 볼트를 손수 원통으로 그리지 않게."""

    op: Literal["bolt"]
    at: XYZ
    nominal: Positive
    """호칭 지름(M6 이면 6)."""
    length: Positive
    """머리 아래 몸통 길이."""
    head: Literal["hex", "socket"] = "hex"
    washer: bool = False
    down: bool = True


class PinNode(_Node):
    """위치 핀 — 원기둥에 끝 모따기. `at` 은 **밑면 중심**, 위(+Z)로 선다."""

    op: Literal["pin"]
    at: XYZ
    diameter: Positive
    length: Positive
    chamfer: float = Field(default=0.8, ge=0)


class StandoffNode(_Node):
    """스페이서(스탠드오프) — 가운데 구멍 난 원통. `at` 은 **밑면 중심**, 위로 선다."""

    op: Literal["standoff"]
    at: XYZ
    outer: Positive
    hole: Positive
    height: Positive

    @model_validator(mode="after")
    def _hole_fits(self) -> StandoffNode:
        if self.hole >= self.outer:
            raise ValueError("구멍이 바깥 지름보다 작아야 합니다")
        return self


class DraftNode(_Node):
    """고른 면에 구배를 준다 — 기준 평면은 그대로 두고 면을 기울인다. 금형 · 빼기 편한 포켓."""

    op: Literal["draft"]
    target: str
    faces: FaceSelect = "sides"
    angle: float = Field(default=3.0, gt=0, lt=45)
    neutral: PlaneSpec = Field(default_factory=PlaneSpec)
    """이 평면에 닿는 자리는 치수가 그대로다."""


class SplitNode(_Node):
    """평면으로 자른다 — 반쪽 지그 · 단면 확인. `keep` 은 평면 법선 쪽(top)인가 반대(bottom)
    인가. both 면 두 조각 다(묶음)."""

    op: Literal["split"]
    target: str
    plane: PlaneSpec = Field(default_factory=PlaneSpec)
    keep: Literal["top", "bottom", "both"] = "top"


class SectionNode(_Node):
    """입체를 평면으로 자른 **단면**(스케치). 돌출하면 그 높이의 윤곽이 되고, `offset` 으로
    여유를 주면 포켓 윤곽이 된다."""

    op: Literal["section"]
    target: str
    plane: PlaneSpec = Field(default_factory=PlaneSpec)
    offset: float = 0.0
    """윤곽을 밖(양수) · 안(음수)으로 띄운다."""


class OffsetNode(_Node):
    """전체를 두껍게(양수) · 얇게(음수) — 제품 형상에 **여유(클리어런스)** 를 주거나 수축을
    반영한다. 지그 포켓은 제품을 이걸로 키운 뒤 빼서 만든다."""

    op: Literal["offset"]
    target: str
    amount: float
    corners: Literal["round", "sharp"] = "round"
    """밖으로 키울 때 모서리를 둥글릴지(round) 뾰족하게 이을지(sharp)."""

    @model_validator(mode="after")
    def _nonzero(self) -> OffsetNode:
        if self.amount == 0:
            raise ValueError("amount: 0 이면 아무것도 안 바뀝니다")
        return self


class MirrorNode(_Node):
    op: Literal["mirror"]
    target: str
    plane: PlaneName = "YZ"
    keep_original: bool = True


class GroupNode(_Node):
    """여럿을 **붙이지 않고 한 묶음으로** — 조립의 마지막 줄.

    `union` 은 하나로 녹여 붙인다. 조립은 그러면 안 된다 — 부품과 지그는 **서로 다른 덩어리**로
    남아야 따로 보고, 따로 빼고, 간섭을 잴 수 있다."""

    op: Literal["group"]
    targets: list[str] = Field(min_length=1)


class ComponentNode(_Node):
    """**다른 도면을 그대로 가져다 놓는다** — 조립의 한 칸.

    STEP 을 가져오는 `import_step` 과 다른 점: 가져오는 것이 **레시피**라 살아 있다. 가져온
    쪽의 변수를 `params` 로 덮어쓸 수 있고, 그 값에 조립의 변수를 넘길 수 있다:

        {"op": "component", "source": "part:3f9a…", "params": {"두께": "=지그_두께"},
         "translate": [0, 0, 12]}

    그래서 조립을 실험계획으로 훑으면 **구성품의 치수까지 따라 바뀐다.** `source` 는 호출자가
    푸는 열쇠다(부품 · 지그 · 내 작업의 버전) — 코어는 그것이 무엇인지 모른다."""

    op: Literal["component"]
    source: str = Field(min_length=1)
    params: dict[str, float] = Field(default_factory=dict)
    """가져온 도면의 변수를 덮어쓴다. 없는 이름을 주면 그 도면이 거절한다."""
    translate: XYZ = (0.0, 0.0, 0.0)
    rotate: XYZ = (0.0, 0.0, 0.0)
    """X · Y · Z 축 회전(도). 회전 뒤 이동 — `transform` 과 같은 규칙."""


class ImportStepNode(_Node):
    """외부 CAD 에서 온 형상 — 레시피의 뿌리. `file` 은 호출자가 경로로 푸는 열쇠(작업물
    id)."""

    op: Literal["import_step"]
    file: str = Field(min_length=1)


Node = Annotated[
    SketchNode
    | ExtrudeNode
    | RevolveNode
    | SweepNode
    | HelixNode
    | SheetMetalNode
    | BoxNode
    | WedgeNode
    | BoltNode
    | PinNode
    | StandoffNode
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
    | SplitNode
    | ComponentNode
    | GroupNode
    | DraftNode
    | SectionNode
    | OffsetNode
    | ImportStepNode,
    Field(discriminator="op"),
]


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    units: Literal["mm"] = "mm"
    params: dict[str, float] = Field(default_factory=dict)
    """이름 붙인 치수. 어느 숫자 칸에든 `"=이름 * 2"` 로 쓴다 — 하나를 고치면 다 따라온다."""
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
    "extrude": ("sketch", "target"),
    "revolve": ("sketch",),
    "sweep": ("sketch",),
    "helix": ("sketch",),
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
    "group": ("targets",),
    "split": ("target",),
    "draft": ("target",),
    "section": ("target",),
    "offset": ("target",),
}


def _references(node: Any) -> list[tuple[str, str | list[str]]]:
    out = []
    for key in _REFERENCE_FIELDS.get(node.op, ()):
        value = getattr(node, key)
        if value is not None:  # extrude.target 처럼 비어도 되는 칸
            out.append((key, value))
    return out


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
    """치수 식(`"=이름*2"`)을 먼저 숫자로 풀고 나서 모양을 본다 — 식이 틀렸으면 그 말부터."""
    try:
        resolved = resolve(raw)
    except ExpressionError as failure:
        raise RecipeValidationError([str(failure)]) from failure
    try:
        return Recipe.model_validate(resolved)
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
