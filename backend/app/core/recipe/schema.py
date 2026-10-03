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


class SketchSegment(BaseModel):
    """구속 윤곽의 한 구간 — 점 이름 `from` 에서 `to` 까지. `center` 를 주면 그 점을 중심으로
    하는 호(`ccw` 면 반시계로 돈다), 아니면 직선."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start: str = Field(alias="from")
    end: str = Field(alias="to")
    center: str | None = None
    ccw: bool = True


SKETCH_CONSTRAINTS: dict[str, tuple[int, int, bool]] = {
    # 종류: (점 수, 구간 수, 값이 있어야 하나). 수평 · 수직은 구간 하나 또는 점 둘.
    "fix": (1, 0, False),
    "coincident": (2, 0, False),
    "horizontal": (0, 1, False),
    "vertical": (0, 1, False),
    "distance": (2, 0, True),
    "length": (0, 1, True),
    "dx": (2, 0, True),
    "dy": (2, 0, True),
    "angle": (0, 2, True),
    "parallel": (0, 2, False),
    "perpendicular": (0, 2, False),
    "equal": (0, 2, False),
    "radius": (0, 1, True),
    "tangent": (0, 2, False),
    "on": (1, 1, False),
    "midpoint": (1, 1, False),
    "symmetric": (2, 1, False),
}


class SketchConstraint(BaseModel):
    """구속 하나 — 점은 이름으로, 구간은 `segments` 의 번호(0 부터)로 가리킨다.

    fix(점 · `at`) · coincident(점 둘) · horizontal · vertical(구간, 또는 점 둘) ·
    distance · dx · dy(점 둘, 값) · length(직선 구간, 값) · angle(구간 둘, 값 도 — 그린
    쪽으로) · parallel · perpendicular · equal(구간 둘 — 선끼리 길이, 호끼리 반지름) ·
    radius(호 구간, 값) · tangent(구간 둘 — 선과 호, 호와 호) · on(점이 구간 위) ·
    midpoint(점이 구간 가운데) · symmetric(점 둘이 직선 구간에 대칭)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "fix",
        "coincident",
        "horizontal",
        "vertical",
        "distance",
        "length",
        "dx",
        "dy",
        "angle",
        "parallel",
        "perpendicular",
        "equal",
        "radius",
        "tangent",
        "on",
        "midpoint",
        "symmetric",
    ]
    points: list[str] = Field(default_factory=list, max_length=2)
    segments: list[int] = Field(default_factory=list, max_length=2)
    value: float | None = None
    at: XY | None = None
    """`fix` 의 자리 — 비우면 그린 자리에 고정."""


class ConstrainedShape(_Shape):
    """**구속 윤곽** — 점을 대충 두고 치수 · 관계를 적으면 풀이가 점을 맞춘다.

    `points` 는 이름 → 그린 자리, `segments` 는 닫힌 고리(앞 구간의 `to` 가 다음 구간의 `from`,
    마지막의 `to` 가 처음의 `from`), `constraints` 는 관계와 치수. 치수 칸에 `=변수` 를 쓰면
    실험계획이 훑는다. 정해지지 않은 쪽은 그린 자리를 지키고, 맞지 않는 구속은 몇째인지
    말한다."""

    type: Literal["constrained"]
    points: dict[str, XY] = Field(min_length=2, max_length=60)
    segments: list[SketchSegment] = Field(min_length=2, max_length=60)
    constraints: list[SketchConstraint] = Field(default_factory=list, max_length=120)

    @model_validator(mode="after")
    def _closed(self) -> ConstrainedShape:
        names = set(self.points)
        for index, segment in enumerate(self.segments):
            for role, name in (
                ("from", segment.start),
                ("to", segment.end),
                ("center", segment.center),
            ):
                if name is not None and name not in names:
                    raise ValueError(f"segments[{index}].{role}: 없는 점 '{name}'")
            following = self.segments[(index + 1) % len(self.segments)]
            if segment.end != following.start:
                raise ValueError(
                    f"segments[{index}].to: 다음 구간의 from('{following.start}')과 같아야 "
                    "윤곽이 닫힙니다"
                )
        for index, one in enumerate(self.constraints):
            points, segments, valued = SKETCH_CONSTRAINTS[one.type]
            where = f"constraints[{index}] ({one.type})"
            if one.type in ("horizontal", "vertical"):
                if not (len(one.segments) == 1 and not one.points) and not (
                    len(one.points) == 2 and not one.segments
                ):
                    raise ValueError(f"{where}: 구간 하나 또는 점 둘입니다")
            elif len(one.points) != points or len(one.segments) != segments:
                raise ValueError(f"{where}: 점 {points} 개 · 구간 {segments} 개가 필요합니다")
            if valued and one.value is None:
                raise ValueError(f"{where}: 값(value)이 필요합니다")
            for name in one.points:
                if name not in names:
                    raise ValueError(f"{where}: 없는 점 '{name}'")
            for number in one.segments:
                if not 0 <= number < len(self.segments):
                    raise ValueError(f"{where}: 없는 구간 {number}")
            if one.type == "radius" and self.segments[one.segments[0]].center is None:
                raise ValueError(f"{where}: 호(center 가 있는 구간)여야 합니다")
            if one.type in (
                "length",
                "parallel",
                "perpendicular",
                "angle",
                "symmetric",
            ) and any(
                self.segments[number].center is not None
                for number in (one.segments if one.type != "symmetric" else one.segments[:1])
            ):
                raise ValueError(f"{where}: 직선 구간이어야 합니다")
        return self


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
    | TextShape
    | ConstrainedShape,
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
    datum: str | None = None
    """앞의 **기준면**(`datum_plane`) id — 있으면 이름 · 원점 · 법선 대신 그 면을 쓴다."""


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


class UnfoldNode(_Node):
    """판 펴기 — 굽힌 판(두께가 한결같은 입체)을 **전개도**로: 펼친 판을 XY 평면에 눕혀
    두께만큼 세운다. 레이저 · 워터젯에 보낼 모양이다(굽힘선 · 방향은 「전개도 DXF」 가 층으로
    따로 적는다).

    레시피로 굽힌 판(`bend` · `sheet_metal`)도, 가져온 판금 STEP 도 편다. 굽힘은 중립면(안쪽
    반지름 + `k_factor · t`)의 길이로 펴므로 `k_factor` 는 굽힐 때와 같아야 한다."""

    op: Literal["unfold"]
    target: str
    k_factor: float = Field(default=0.5, ge=0, le=1)
    """중립면 위치 — 안쪽 면에서 두께의 몇 할. 굽힐 때(`bend`)와 같은 값."""
    flip: bool = False
    """기준면을 **반대쪽 겉면**으로 — 전개도가 뒤집혀 굽힘의 위 · 아래가 바뀐다."""


class Bend(BaseModel):
    """굽힘 하나 — 굽힘선은 `along` 에 수직이고, 펼친 판의 `at` 자리에서 굽기 시작한다."""

    model_config = ConfigDict(extra="forbid")

    at: float
    """굽기 시작하는 자리 — **펼친 판**에서 `along` 방향의 좌표(mm). along 이 X 면 x 값."""
    radius: Positive
    """안쪽 반지름."""
    toward: Literal["up", "down"] = "up"
    """어느 쪽으로 — up 은 판의 위쪽(누운 판이면 +Z, 선 판이면 +Y, 그다음 +X)."""
    until: Literal["angle", "end"] = "angle"
    """어디까지 — `angle` 만큼(angle), 또는 남은 판을 **끝까지 감는다**(end — 원통에 감기)."""
    angle: float = Field(default=90.0, gt=0, lt=360)
    """굽힘 각(도). `until: end` 면 쓰지 않는다 — 남은 길이와 반지름이 정한다."""


class DeformNode(_Node):
    """**비틀기 · 테이퍼** — 축을 따라 단면을 돌리고(`twist`) 줄인다(`taper`). 비틀린 띠 ·
    날개, 끝으로 갈수록 가늘어지는 보.

    축 위의 자리가 `start` → `end` 로 갈 때 그 높이의 단면을 축 둘레로 0 → `twist` 도 돌리고,
    축에서의 거리를 1 → `taper` 배로 줄인다. 그 앞은 그대로, 그 뒤는 끝의 변형 그대로. 비우면
    대상이 축 위에서 차지하는 구간 전체. 곡면은 NURBS 로 맞춘다(허용 오차 안에서 근사)."""

    op: Literal["deform"]
    target: str
    axis: str = "Z"
    """변형의 축 — 원점을 지나는 `X` · `Y` · `Z`, 또는 앞의 **기준축**(`datum_axis`) id."""
    twist: float = Field(default=0.0, ge=-720, le=720)
    """`start` 에서 `end` 까지 도는 각(도). 축 방향을 보고 반시계가 양(+)."""
    taper: Positive = 1.0
    """`end` 의 단면 배율(`start` 는 1). 0.5 면 끝이 절반."""
    start: float | None = None
    """변형이 시작하는 자리 — 축의 원점에서 축 방향으로 잰 거리(mm)."""
    end: float | None = None

    @model_validator(mode="after")
    def _something(self) -> DeformNode:
        if not self.twist and self.taper == 1:
            raise ValueError(
                "twist · taper 중 하나는 있어야 합니다 — 지금은 바꾸는 것이 없습니다"
            )
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("end: start 보다 커야 합니다")
        return self


class BendGroup(BaseModel):
    """다른 방향의 굽힘선 묶음 — 상자의 다른 날개. `at` 은 이 묶음의 `along` 방향 좌표."""

    model_config = ConfigDict(extra="forbid")

    along: XYZ
    bends: list[Bend] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _in_order(self) -> BendGroup:
        _check_bend_order(self.bends)
        return self


def _check_bend_order(bends: list[Bend]) -> None:
    for index in range(1, len(bends)):
        if bends[index].at <= bends[index - 1].at:
            raise ValueError(
                f"bends[{index}].at: 앞 굽힘({bends[index - 1].at})보다 뒤여야 합니다"
            )
    for index, one in enumerate(bends[:-1]):
        if one.until == "end":
            raise ValueError(f"bends[{index}].until: 끝까지 감기(end)는 마지막 굽힘만 됩니다")


class BendNode(_Node):
    """**펼친 판을 굽힌다** — 평평한 판을 굽힘선에서 반지름 R 로 접거나 원통에 감는다. 판금
    전개도 · 띠 · 감는 판처럼 「펴진 모양으로 그린 뒤 굽히는」 것.

    구멍 · 노치 · 윤곽은 **펼친 상태에서** 그린다. 굽힘 구간에 걸린 구멍도 같이 휘고 그 벽은
    반지름 방향으로 선다. 펼친 길이는 중립면(`k_factor`)에서 보존된다.

    판은 위 · 아래 면이 평평하고 옆면이 수직이어야 한다(두께가 한결같다). 포켓 · 단차 · 위아래
    모서리의 필렛 · 모따기는 굽힌 **뒤에** 만든다."""

    op: Literal["bend"]
    target: str
    bends: list[Bend] = Field(min_length=1, max_length=20)
    """앞에서부터(`at` 이 커지는 순서). 굽힘마다 그 뒤쪽 판이 통째로 따라 돈다."""
    along: XYZ = (1.0, 0.0, 0.0)
    """굽혀 나가는 방향(판 위의 방향). 굽힘선은 이것에 수직이다."""
    k_factor: float = Field(default=0.5, ge=0, le=1)
    """중립면의 자리 — 안쪽 면에서 두께의 몇 할인가. 펼친 길이가 이 층에서 보존된다(판금의
    K 계수, 보통 0.3 ~ 0.5)."""
    also: list[BendGroup] = Field(default_factory=list, max_length=7)
    """**다른 방향의 굽힘선** — 상자 날개처럼. 묶음마다 `along` 과 굽힘들. 판은 「바탕」 과
    묶음마다의 날개(그 묶음의 첫 굽힘선 너머)로 나뉘고, 날개는 서로 따로 굽는다."""
    corner_relief: bool = False
    """두 날개가 모서리에서 겹치면(사각 판의 네 변을 다 접을 때) 겹친 자리를 따낸다. 아니면
    거절한다 — 펼친 판에서 모서리를 직접 따내도 된다."""

    @model_validator(mode="after")
    def _in_order(self) -> BendNode:
        _check_bend_order(self.bends)
        return self


# --- 구조 프레임의 단면 -------------------------------------------------------------


class _Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")


#: 알루미늄 프로파일 계열 — 크기(mm) → (슬롯 입구, 입술 두께, 안쪽 폭, 슬롯 깊이, 가운데 구멍).
#: 제조사마다 조금씩 다른 **근사 단면**이다(강성 · 질량이 몇 % 다를 수 있다).
T_SLOT_SERIES: dict[int, tuple[float, float, float, float, float]] = {
    20: (6.2, 1.8, 11.0, 6.1, 4.2),
    30: (8.2, 2.2, 16.5, 9.0, 6.8),
    40: (8.2, 4.3, 20.0, 12.2, 6.8),
    45: (10.0, 4.4, 20.0, 13.0, 8.5),
}


class TSlotProfile(_Profile):
    """알루미늄 프로파일(T 슬롯) — 정사각 단면의 네 변에 슬롯, 가운데 구멍. 계열 20 · 30 ·
    40 · 45."""

    type: Literal["t_slot"]
    size: float = 20.0
    """계열(한 변, mm) — 20 · 30 · 40 · 45."""

    @model_validator(mode="after")
    def _series(self) -> TSlotProfile:
        if round(self.size) not in T_SLOT_SERIES or abs(self.size - round(self.size)) > 1e-9:
            raise ValueError(f"size: {' · '.join(map(str, T_SLOT_SERIES))} 중 하나입니다")
        return self


class SquareTubeProfile(_Profile):
    """각관(정사각 파이프)."""

    type: Literal["square_tube"]
    width: Positive
    thickness: Positive
    """벽 두께."""

    @model_validator(mode="after")
    def _wall(self) -> SquareTubeProfile:
        if self.thickness * 2 >= self.width:
            raise ValueError("thickness: 벽 두께의 두 배가 폭보다 작아야 합니다")
        return self


class RectTubeProfile(_Profile):
    """사각관(직사각 파이프) — `height` 가 단면의 위쪽 방향."""

    type: Literal["rect_tube"]
    width: Positive
    height: Positive
    thickness: Positive

    @model_validator(mode="after")
    def _wall(self) -> RectTubeProfile:
        if self.thickness * 2 >= min(self.width, self.height):
            raise ValueError("thickness: 벽 두께의 두 배가 폭 · 높이보다 작아야 합니다")
        return self


class RoundTubeProfile(_Profile):
    """원관(파이프)."""

    type: Literal["round_tube"]
    diameter: Positive
    """바깥 지름."""
    thickness: Positive

    @model_validator(mode="after")
    def _wall(self) -> RoundTubeProfile:
        if self.thickness * 2 >= self.diameter:
            raise ValueError("thickness: 벽 두께의 두 배가 지름보다 작아야 합니다")
        return self


class RoundBarProfile(_Profile):
    """환봉."""

    type: Literal["round_bar"]
    diameter: Positive


class FlatBarProfile(_Profile):
    """평철 · 각재(속이 찬 직사각)."""

    type: Literal["flat_bar"]
    width: Positive
    height: Positive


class AngleProfile(_Profile):
    """앵글(L) — 가로 다리 `width`, 세로 다리 `height`, 두께 `thickness`. 모서리가 단면의 왼쪽
    아래(`roll` 로 돌린다)."""

    type: Literal["angle"]
    width: Positive
    height: Positive
    thickness: Positive

    @model_validator(mode="after")
    def _legs(self) -> AngleProfile:
        if self.thickness >= min(self.width, self.height):
            raise ValueError("thickness: 다리 길이보다 작아야 합니다")
        return self


class ChannelProfile(_Profile):
    """채널(ㄷ) — 웨브 높이 `height`, 플랜지 폭 `width`, 두께 `thickness`. 열린 쪽이 +X."""

    type: Literal["channel"]
    width: Positive
    height: Positive
    thickness: Positive

    @model_validator(mode="after")
    def _legs(self) -> ChannelProfile:
        if self.thickness >= self.width or self.thickness * 2 >= self.height:
            raise ValueError("thickness: 플랜지 폭과 웨브 높이의 절반보다 작아야 합니다")
        return self


class HBeamProfile(_Profile):
    """H 형강 — 플랜지 폭 `width`, 높이 `height`, 웨브 두께 `web`, 플랜지 두께 `flange`."""

    type: Literal["h_beam"]
    width: Positive
    height: Positive
    web: Positive
    flange: Positive

    @model_validator(mode="after")
    def _plates(self) -> HBeamProfile:
        if self.web >= self.width or self.flange * 2 >= self.height:
            raise ValueError("web · flange: 웨브는 폭보다, 플랜지 둘은 높이보다 얇아야 합니다")
        return self


FrameProfile = Annotated[
    TSlotProfile
    | SquareTubeProfile
    | RectTubeProfile
    | RoundTubeProfile
    | RoundBarProfile
    | FlatBarProfile
    | AngleProfile
    | ChannelProfile
    | HBeamProfile,
    Field(discriminator="type"),
]


class FrameNode(_Node):
    """**구조 프레임** — 알루미늄 프로파일 · 각관 · 원관 · 앵글 · 채널 · H 형강을 선을 따라
    세운다. 지그의 받침 틀 · 기둥 · 가로대.

    `paths` 는 경로 여럿, 경로 하나는 점 목록이다 — 점 사이가 부재 하나. 마지막 점이 처음 점과
    같으면 **닫힌 틀**이다(그 모서리도 잇는다). 단면의 가운데(경계상자)가 경로 위에 온다.
    단면의 위쪽은 +Z(부재가 서 있으면 +X) — `roll` 로 부재 축 둘레로 돌린다.

    꺾인 곳(`corner`): `miter` 는 두 부재를 이등분 면에서 맞댄다(용접 틀) · `butt` 는 앞 부재가
    모서리까지 지나가고 뒤 부재가 그 옆면에 맞닿는다(프로파일 볼트 조립) · `none` 은 둘 다
    모서리까지 늘여 겹친다. 다른 경로에 닿는 끝(기둥 → 틀)은 `meet` 가 정한다.

    자를 길이 · 각은 절단 목록(`/cad/recipe/cutlist`, MCP `recipe_cutlist`)이 준다."""

    op: Literal["frame"]
    profile: FrameProfile
    paths: list[list[XYZ]] = Field(min_length=1, max_length=100)
    corner: Literal["miter", "butt", "none"] = "miter"
    meet: Literal["butt", "overlap"] = "butt"
    """경로의 **열린 끝**이 다른 경로의 부재에 닿을 때 — `butt` 는 그 부재의 옆면까지 맞춘다
    (기둥이 틀 밑면에서 멈춘다, 모자라면 늘인다), `overlap` 은 그대로 겹친다."""
    roll: float = 0.0
    """단면을 부재 축 둘레로 돌린다(도)."""
    separate: bool = False
    """부재를 합치지 않고 따로 둔다 — 볼트로 조립하는 프레임을 부재마다 해석할 때. 기본은
    한 덩어리(용접 · 본딩으로 본다)."""

    @model_validator(mode="after")
    def _paths(self) -> FrameNode:
        for index, path in enumerate(self.paths):
            if len(path) < 2:
                raise ValueError(f"paths[{index}]: 점이 둘 이상이어야 부재가 됩니다")
        return self


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
    axis: str = "Z"
    """회전축 — 원점을 지나는 `X` · `Y` · `Z`, 또는 앞의 **기준축**(`datum_axis`) id."""
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


class SelectRule(BaseModel):
    """**규칙으로 고른다** — `recipe_find` 의 질의(`kind` · `axis` · `radius` · `normal` ·
    `body` · `of_face` …). 위치로 고르면 DOE 가 치수를 바꾸는 순간 그 자리에 엣지 · 면이
    없어 실패한다(실측 2026-10-02: 판 두께를 훑자 모따기 엣지를 못 찾았다). 규칙은
    설계점마다 다시 찾는다.

    예 — 블록 윗면의 테두리: `{"query": {"of_face": {"body": "블록", "normal": [0, 0, 1]}}}`,
    지름 30 구멍의 위 원: `{"query": {"kind": "circle", "radius": 15, "near": [0, 0, 20]}}`.
    `near` 가 없으면 맞는 것 **전부**, 있으면 가장 가까운 하나(`limit` 을 주면 그만큼)."""

    model_config = ConfigDict(extra="forbid")

    query: dict[str, Any] = Field(min_length=1)


EdgeSelect = Literal["all", "vertical", "horizontal", "top", "bottom"] | EdgeNear | SelectRule


class FilletNode(_Node):
    op: Literal["fillet"]
    target: str
    edges: EdgeSelect = "all"
    radius: Positive
    radius_end: Positive | None = None
    """주면 **반지름이 변한다** — 엣지를 따라 `radius` 에서 이 값으로 고르게."""
    start: XYZ | None = None
    """`radius_end` 를 줄 때 `radius` 가 걸리는 끝 — 이 점에 가까운 끝. 비우면 엣지의 방향대로
    (어느 끝인지 알 수 없다)."""


class ChamferNode(_Node):
    """모따기 — 같은 길이, 두 거리(`length2`), 또는 거리와 각(`angle`)."""

    op: Literal["chamfer"]
    target: str
    edges: EdgeSelect = "all"
    length: Positive
    length2: Positive | None = None
    """주면 **비대칭** — `length` 는 기준면 쪽, 이것은 다른 면 쪽 거리."""
    angle: float | None = Field(default=None, gt=0, lt=90)
    """주면 **거리-각도** — 기준면에서 `length` 만큼, 그 면에서 이 각(도)으로 깎는다."""
    reference: FaceSelect | None = None
    """`length` 를 재는 면(기준면). 비우면 엣지의 두 면 중 더 위(+Z)를 보는 면."""

    @model_validator(mode="after")
    def _one_way(self) -> ChamferNode:
        if self.length2 is not None and self.angle is not None:
            raise ValueError("length2(두 거리)와 angle(거리-각도) 중 하나만 씁니다")
        return self


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


FaceSelect = Literal["top", "bottom", "sides", "all", "none"] | EdgeNear | SelectRule


class ShellNode(_Node):
    """속을 비운다 — `open` 면을 뚫고 나머지를 `thickness` 두께의 껍질로."""

    op: Literal["shell"]
    target: str
    thickness: Positive
    open: FaceSelect = "top"
    """뚫을 면: top · bottom · none(닫힌 속 빈 덩어리) · {"near": [[x,y,z]]}(면 중심 위치)."""


class DivideFaceNode(_Node):
    """면을 **영역으로 나눈다** — 하중 · 접촉을 면의 일부에만 걸 수 있게.

    형상은 그대로다(부피가 변하지 않는다). 면 하나가 둘로 갈릴 뿐이고, 안쪽 조각에 `tag` 가
    붙어 해석 조건이 그것을 선택 그룹으로 집는다. **왜 노드인가**: 면을 나누는 것은 형상의
    일이라 레시피에 있어야 설계점마다(치수를 바꿔도) 같은 자리에 다시 생긴다.
    """

    op: Literal["divide_face"]
    target: str
    on: dict[str, Any] = Field(default_factory=lambda: {"role": "top"})
    """나눌 면 고르기 — `query.find_features` 의 말(`role` · `kind` · `radius` · `near`)."""
    shape: Literal["circle", "rect", "sketch"] = "circle"
    radius: Positive | None = None
    """`circle` 의 반지름."""
    size: XY | None = None
    """`rect` 의 가로 · 세로."""
    sketch: str | None = None
    """`sketch` — 앞의 스케치. 그 윤곽(도형 여럿이면 여럿, 구멍 뚫린 도형이면 고리)을 면에 비춰
    나눈다. 스케치 평면이 그 면과 나란해야 한다 — 면 위에 그리면 된다(`plane` 에 그 면, 또는
    3D 에서 면을 눌러 만든 스케치)."""
    at: XYZ | None = None
    """패치의 한가운데(전역 좌표). 면 위로 투영한다. 비우면 면의 한가운데. `sketch` 는 스케치의
    자리를 그대로 쓴다."""
    tag: str = Field(min_length=1, max_length=60)
    """생긴 안쪽 면에 붙는 이름. 조건은 `{"tag": "패드"}` 로 집는다."""

    @model_validator(mode="after")
    def _shape_needs(self) -> DivideFaceNode:
        if self.shape == "sketch" and self.sketch is None:
            raise ValueError("sketch: 모양을 스케치로 하려면 그 스케치를 고릅니다")
        return self


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
    axis: str = "Z"
    """circular: 회전축 — 원점을 지나는 `X` · `Y` · `Z`, 또는 앞의 기준축(`datum_axis`) id."""
    angle: float = Field(default=360.0, gt=0, le=360)
    """circular: 전체 각도."""


class TransformNode(_Node):
    op: Literal["transform"]
    target: str
    translate: XYZ = (0.0, 0.0, 0.0)
    rotate: XYZ = (0.0, 0.0, 0.0)
    """X · Y · Z 축 회전(도). 회전 뒤 이동."""
    scale: float = Field(default=1.0, gt=0)
    """배율. 크기 · 회전 · 이동 순."""
    pivot: XYZ = (0.0, 0.0, 0.0)
    """회전 · 배율의 중심. 기본은 원점."""


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


#: ISO 4032 육각 너트 — 호칭 → (맞변 거리, 높이). mm.
NUTS: dict[str, tuple[float, float]] = {
    "M3": (5.5, 2.4),
    "M4": (7.0, 3.2),
    "M5": (8.0, 4.7),
    "M6": (10.0, 5.2),
    "M8": (13.0, 6.8),
    "M10": (16.0, 8.4),
    "M12": (18.0, 10.8),
}
#: ISO 7089 평와셔 — 호칭 → (안지름, 바깥지름, 두께). mm.
WASHERS: dict[str, tuple[float, float, float]] = {
    "M3": (3.2, 7.0, 0.5),
    "M4": (4.3, 9.0, 0.8),
    "M5": (5.3, 10.0, 1.0),
    "M6": (6.4, 12.0, 1.6),
    "M8": (8.4, 16.0, 1.6),
    "M10": (10.5, 20.0, 2.0),
    "M12": (13.0, 24.0, 2.5),
}
#: 깊은 홈 볼 베어링 — 호칭 → (안지름, 바깥지름, 폭). mm.
BEARINGS: dict[str, tuple[float, float, float]] = {
    "625": (5, 16, 5),
    "626": (6, 19, 6),
    "608": (8, 22, 7),
    "6000": (10, 26, 8),
    "6001": (12, 28, 8),
    "6002": (15, 32, 9),
    "6003": (17, 35, 10),
    "6004": (20, 42, 12),
    "6005": (25, 47, 12),
    "6200": (10, 30, 9),
    "6201": (12, 32, 10),
    "6202": (15, 35, 11),
    "6203": (17, 40, 12),
    "6204": (20, 47, 14),
    "6205": (25, 52, 15),
}
#: 알루미늄 프로파일 코너 브래킷 — 계열 → (다리 길이, 폭, 두께, 구멍 지름). mm. 근사 치수.
BRACKETS: dict[int, tuple[float, float, float, float]] = {
    20: (20.0, 20.0, 3.0, 5.5),
    30: (28.0, 28.0, 4.0, 6.6),
    40: (38.0, 38.0, 5.0, 8.5),
    45: (43.0, 43.0, 5.0, 9.0),
}


def _known(value: str, table: dict[str, Any], field: str) -> None:
    if value not in table:
        raise ValueError(f"{field}: {' · '.join(table)} 중 하나입니다")


class NutNode(_Node):
    """육각 너트(ISO 4032) — `at` 은 **너트가 앉는 면의 점**, `direction` 쪽으로 쌓인다."""

    op: Literal["nut"]
    at: XYZ
    thread: str
    """M3 · M4 · M5 · M6 · M8 · M10 · M12."""
    direction: XYZ = (0.0, 0.0, 1.0)

    @model_validator(mode="after")
    def _table(self) -> NutNode:
        _known(self.thread, NUTS, "thread")
        return self


class WasherNode(_Node):
    """평와셔(ISO 7089) — `at` 은 **와셔가 앉는 면의 점**, `direction` 쪽으로 쌓인다."""

    op: Literal["washer"]
    at: XYZ
    thread: str
    direction: XYZ = (0.0, 0.0, 1.0)

    @model_validator(mode="after")
    def _table(self) -> WasherNode:
        _known(self.thread, WASHERS, "thread")
        return self


class BearingNode(_Node):
    """깊은 홈 볼 베어링 — 안 · 바깥 링을 한 고리로 단순화. `at` 은 **한쪽 면의 가운데**,
    `direction` 쪽으로 폭만큼."""

    op: Literal["bearing"]
    at: XYZ
    designation: str
    """608 · 625 · 626 · 6000 ~ 6005 · 6200 ~ 6205."""
    direction: XYZ = (0.0, 0.0, 1.0)

    @model_validator(mode="after")
    def _table(self) -> BearingNode:
        _known(self.designation, BEARINGS, "designation")
        return self


class SpringNode(_Node):
    """압축 스프링 — 선 지름 `wire`, 평균 지름 `diameter`, 자유 길이 `length`, 감김 수 `coils`.
    `at` 은 **밑면 가운데**, `direction` 쪽으로 선다."""

    op: Literal["spring"]
    at: XYZ = (0.0, 0.0, 0.0)
    wire: Positive
    diameter: Positive
    """평균 지름(선의 가운데로 잰 코일 지름)."""
    length: Positive
    coils: float = Field(gt=0.5, le=200)
    direction: XYZ = (0.0, 0.0, 1.0)

    @model_validator(mode="after")
    def _fits(self) -> SpringNode:
        if self.wire >= self.diameter:
            raise ValueError("wire: 선 지름이 평균 지름보다 작아야 합니다")
        if (self.length - self.wire) / self.coils <= self.wire * 1.05:
            raise ValueError(
                "coils: 감김이 촘촘해 코일끼리 닿습니다 — 줄이거나 길이를 늘리세요"
            )
        return self


class BracketNode(_Node):
    """알루미늄 프로파일 **코너 브래킷**(L) — 계열 20 · 30 · 40 · 45. `at` 은 두 프로파일 면이
    만나는 **안쪽 모서리의 점**, `legs` 는 두 다리가 뻗는 방향(서로 수직). 다리마다 구멍
    하나."""

    op: Literal["bracket"]
    at: XYZ
    size: float = 40.0
    legs: tuple[XYZ, XYZ] = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))

    @model_validator(mode="after")
    def _series(self) -> BracketNode:
        if round(self.size) not in BRACKETS or abs(self.size - round(self.size)) > 1e-9:
            raise ValueError(f"size: {' · '.join(map(str, BRACKETS))} 중 하나입니다")
        a, b = self.legs
        if (
            abs(sum(x * y for x, y in zip(a, b, strict=True)))
            > 1e-6 * (sum(x * x for x in a) * sum(y * y for y in b)) ** 0.5
        ):
            raise ValueError("legs: 두 다리 방향이 서로 수직이어야 합니다")
        return self


class FastenNode(_Node):
    """**구멍에 맞춰 놓는다** — 규칙으로 찾은 구멍마다 볼트 · 너트 · 와셔 · 핀을 그 축에.

    좌표 없이 「이 판의 M6 구멍들에 볼트」 — 치수가 바뀌어 구멍이 움직여도 따라간다. 나사
    호칭을 비우면 구멍 지름으로 고른다(여유 구멍 ±0.3 · 탭 드릴 ±0.2). 카운터보어면 턱에
    앉는다(가장 가는 구멍의 끝).

    - `bolt` — 머리가 `side` 쪽 끝에 앉고 몸통이 구멍으로. `length` 를 비우면 구멍 깊이
    - `nut` · `washer` — `side` 쪽 끝에서 바깥으로 쌓인다
    - `pin` — 반대쪽 끝에서 들어가 `side` 쪽으로 나온다. 지름은 구멍 그대로, `length` 를
      비우면 구멍 깊이 + 지름만큼 나온다"""

    op: Literal["fasten"]
    target: str
    holes: dict[str, Any] = Field(default_factory=lambda: {"kind": "cylinder"})
    """구멍 고르기 — `recipe_find` 의 면 질의(원통면). 예
    `{"kind": "cylinder", "radius": 3.3}`."""
    part: Literal["bolt", "nut", "washer", "pin"] = "bolt"
    thread: str | None = None
    """M3 ~ M12. 비우면 구멍 지름으로 고른다."""
    length: Positive | None = None
    head: Literal["hex", "socket"] = "socket"
    washer: bool = False
    """볼트 머리 밑에 와셔."""
    side: Literal["top", "bottom"] = "top"
    """구멍의 어느 끝 — 위(+Z 쪽, 구멍이 누웠으면 +X · +Y 쪽) · 아래."""

    @model_validator(mode="after")
    def _table(self) -> FastenNode:
        if self.thread is not None:
            _known(self.thread, THREADS, "thread")
        return self


class DraftNode(_Node):
    """고른 면에 구배를 준다 — 기준 평면은 그대로 두고 면을 기울인다. 금형 · 빼기 편한 포켓."""

    op: Literal["draft"]
    target: str
    faces: FaceSelect = "sides"
    angle: float = Field(default=3.0, gt=0, lt=45)
    neutral: PlaneSpec = Field(default_factory=PlaneSpec)
    """이 평면에 닿는 자리는 치수가 그대로다."""


class DefeatureNode(_Node):
    """**면을 지우고 메운다** — 작은 구멍 · 필렛이나 고른 면을 없애고 이웃 면을 늘려 막는다.
    해석용 단순화(작은 필렛 · 구멍이 메시를 촘촘하게 만든다)와, 피처 이력이 없는 가져온 STEP 을
    고칠 때.

    무엇을 지울지(하나 이상):
    - `faces` — 고른 면(3D 에서 누른 자리 `{"near": [[x, y, z], …]}`)
    - `holes_below` — 지름이 이보다 작은 **구멍**(카운터보어 · 카운터싱크의 턱 · 원뿔도 함께)
    - `fillets_below` — 반지름이 이보다 작은 **필렛**(둥근 모서리 — 볼록 · 오목 모두)

    기준으로 고른 것이 하나도 없으면 그대로 지나간다 — DOE 가 구멍을 키워 기준을 넘으면 그
    설계점에서는 남는다."""

    op: Literal["defeature"]
    target: str
    faces: FaceSelect = "none"
    holes_below: Positive | None = None
    """이 지름(mm)보다 작은 구멍을 지운다."""
    fillets_below: Positive | None = None
    """이 반지름(mm)보다 작은 필렛을 지운다."""

    @model_validator(mode="after")
    def _something(self) -> DefeatureNode:
        if self.faces == "none" and self.holes_below is None and self.fillets_below is None:
            raise ValueError(
                "faces · holes_below · fillets_below 중 하나는 있어야 지울 것이 있습니다"
            )
        if self.faces in ("all", "top", "bottom", "sides"):
            raise ValueError('faces: 지울 면은 3D 에서 고른 자리({"near": [...]})로 줍니다')
        return self


class ImprintNode(_Node):
    """**접촉 자리 새기기** — 조립(group)의 바디끼리 닿는 자리를 서로의 면에 새겨 나눈다.

    판 위에 블록이 앉으면 판 윗면이 「블록이 닿는 자리」 와 나머지로 갈린다 — 접촉면 짝이
    넓이 · 자리까지 꼭 같아지고, 해석의 메시가 두 바디에서 맞물린다. 닿는 자리마다 태그가
    붙는다: `받침판/블록`(받침판 쪽 면), `블록/받침판`(블록 쪽 면) — 조건이
    `{"what": "faces", "tag": "받침판/블록"}` 로 집는다. 겹치는(간섭) 바디는 거절한다."""

    op: Literal["imprint"]
    target: str


class SplitNode(_Node):
    """평면으로 자른다 — 반쪽 지그 · 단면 확인. `keep` 은 평면 법선 쪽(top)인가 반대(bottom)
    인가. both 면 두 조각 다(묶음). `tool` 에 곡면 노드를 주면 평면 대신 **그 곡면으로**
    가른다(top 은 곡면의 앞 쪽) — 제품의 굽은 면을 따라 잘라 낸 둥지."""

    op: Literal["split"]
    target: str
    plane: PlaneSpec = Field(default_factory=PlaneSpec)
    keep: Literal["top", "bottom", "both"] = "top"
    tool: str | None = None
    """가를 곡면(`surface` 노드 id). 주면 `plane` 은 쓰지 않는다."""


class SurfaceNode(_Node):
    """**곡면** — 입체가 아니라 면. 그대로는 결과가 될 수 없고 `thicken` 으로 두께를 주거나
    `split` 의 `tool` 로 쓴다.

    - `grid`: 점 격자(행마다 같은 수, 2 x 2 이상)를 **지나는** 자유 곡면 — 잰 점으로 받은 면.
    - `loft`: 3D 곡선 둘 이상(`curves` — 곡선마다 점들)을 잇는다. `ruled` 면 곡선 사이를
      직선으로.
    - `fill`: 닫힌 3D 테두리(`boundary`)를 메운다. `through` 의 점을 지난다.
    `smooth` 면 곡선 · 테두리가 점을 지나는 스플라인, 아니면 꺾은선."""

    op: Literal["surface"]
    kind: Literal["grid", "loft", "fill"]
    grid: list[list[XYZ]] | None = None
    curves: list[list[XYZ]] | None = None
    boundary: list[XYZ] | None = None
    through: list[XYZ] = Field(default_factory=list, max_length=50)
    ruled: bool = False
    smooth: bool = True

    @model_validator(mode="after")
    def _enough(self) -> SurfaceNode:
        if self.kind == "grid":
            rows = self.grid or []
            if len(rows) < 2 or len(rows[0]) < 2:
                raise ValueError("grid: 2 x 2 점 이상이 필요합니다")
            if any(len(row) != len(rows[0]) for row in rows):
                raise ValueError("grid: 행마다 점의 수가 같아야 합니다")
        if self.kind == "loft":
            curves = self.curves or []
            if len(curves) < 2 or any(len(one) < 2 for one in curves):
                raise ValueError("curves: 곡선 둘 이상, 곡선마다 점 둘 이상입니다")
        if self.kind == "fill" and len(self.boundary or []) < 3:
            raise ValueError("boundary: 테두리는 점 셋 이상입니다")
        return self


class ThickenNode(_Node):
    """곡면에 **두께**를 — 입체가 된다. `side` 는 면의 앞(법선 쪽) · 뒤 · 양쪽(반씩)."""

    op: Literal["thicken"]
    target: str
    thickness: Positive
    side: Literal["front", "back", "both"] = "front"


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
    plane: str = "YZ"
    """대칭면 — 원점을 지나는 이름 있는 평면(`XY` · `YZ` · `XZ` …), 또는 앞의 기준면
    (`datum_plane`) id."""
    keep_original: bool = True


class GroupNode(_Node):
    """여럿을 **붙이지 않고 한 묶음으로** — 조립의 마지막 줄.

    `union` 은 하나로 녹여 붙인다. 조립은 그러면 안 된다 — 부품과 지그는 **서로 다른 덩어리**로
    남아야 따로 보고, 따로 빼고, 간섭을 잴 수 있다."""

    op: Literal["group"]
    targets: list[str] = Field(min_length=1)


MATE_KINDS = ("touch", "flush", "concentric", "parallel", "perpendicular", "angle")


class Mate(BaseModel):
    """조립 구속 하나 — **이 구성품의 면 · 축을 앞에 놓인 것의 면 · 축에.**

    - `touch` 맞대기: 평면끼리, 법선이 마주 본다. `offset` 은 두 면 사이 틈(mm).
    - `flush` 면 맞춤: 평면끼리, 법선이 같은 쪽. `offset` 은 저 면에서 법선 쪽으로 띄운 거리.
    - `concentric` 동심: 축끼리(원통면 · 원뿔면 · 직선 엣지 · 원 엣지). `flip` 은 축의 방향을
      뒤집는다(기본은 손으로 놓은 쪽에 가까운 방향).
    - `parallel` 평행 · `perpendicular` 직각 · `angle` 각도(`angle`, 도): 방향만 — 평면은 법선,
      축은 축 방향끼리 잰다.

    `this` 는 이 구성품(**가져온 도면의 좌표**)에서 하나를 집는 질의 — `recipe_find` 와
    같은 말(`{"what": "faces", "role": "bottom"}`). `to` 는 앞의 피처 id 와 `select`(그
    형상에서 하나를 집는 질의), 또는 기준축 · 기준면(`X` · `XY` · 기준 피처 id — 그때는
    `select` 없이)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["touch", "flush", "concentric", "parallel", "perpendicular", "angle"]
    this: dict[str, Any]
    to: str = Field(min_length=1)
    select: dict[str, Any] | None = None
    offset: float = 0.0
    angle: float | None = Field(default=None, ge=0, le=180)
    flip: bool = False

    @model_validator(mode="after")
    def _check_angle(self) -> Mate:
        if self.type == "angle" and self.angle is None:
            raise ValueError("angle: 각도 구속에는 각(도)이 필요합니다")
        if self.offset and self.type not in ("touch", "flush"):
            raise ValueError("offset: 맞대기 · 면 맞춤에만 씁니다")
        return self


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
    mates: list[Mate] = Field(default_factory=list, max_length=6)
    """조립 구속 — 주면 `translate` · `rotate` 는 **처음 자리**가 되고, 구속이 정한 만큼만
    옮긴다(정하지 않은 쪽은 손으로 놓은 그대로). 차례대로: 방향 다음 위치."""


class ImportStepNode(_Node):
    """외부 CAD 에서 온 형상 — 레시피의 뿌리. `file` 은 호출자가 경로로 푸는 열쇠(작업물
    id)."""

    op: Literal["import_step"]
    file: str = Field(min_length=1)


#: 원점을 지나는 전역 축 — 축 칸에서 기준축 id 대신 쓰는 이름. 피처 id 로 쓰면 이것이 먼저다.
GLOBAL_AXES = ("X", "Y", "Z")
#: 원점을 지나는 이름 있는 평면 — 평면 칸에서 기준면 id 대신 쓰는 이름.
GLOBAL_PLANES = ("XY", "XZ", "YZ", "YX", "ZX", "ZY")
#: 형상을 만들지 않는 노드 — 축 · 평면 칸만 가리킨다.
DATUM_OPS = ("datum_axis", "datum_plane")


def _one_way(node: BaseModel, ways: dict[str, bool]) -> None:
    """정의 방법이 **꼭 하나**인지 — 둘을 섞으면 어느 쪽인지 알 수 없다."""
    chosen = [name for name, given in ways.items() if given]
    if len(chosen) != 1:
        raise ValueError(
            f"{' · '.join(ways)} 중 하나로 정합니다"
            + (f" — 지금 {' · '.join(chosen)}" if chosen else " — 지금 없음")
        )


class DatumAxisNode(_Node):
    """**기준축** — 형상을 만들지 않고, 회전체(`revolve`) · 원형 패턴이 도는 축이 된다. 원점을
    지나는 X · Y · Z 말고 아무 축이나 쓸 수 있게.

    정하는 법(하나만):
    - `origin` + `direction` — 점과 방향
    - `through` — 두 점
    - `target` + `select` — 앞 입체의 **원통 · 원뿔면의 축** 또는 **직선 엣지**
      (`recipe_find` 의 질의, 예 `{"what": "faces", "kind": "cylinder", "near": [x, y, z]}`).
      치수가 바뀌면 그 구멍 · 엣지를 따라간다."""

    op: Literal["datum_axis"]
    origin: XYZ | None = None
    direction: XYZ | None = None
    through: list[XYZ] | None = Field(default=None, min_length=2, max_length=2)
    target: str | None = None
    select: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _defined(self) -> DatumAxisNode:
        _one_way(
            self,
            {
                "origin + direction": self.origin is not None or self.direction is not None,
                "through": self.through is not None,
                "target + select": self.target is not None or self.select is not None,
            },
        )
        if (self.origin is None) != (self.direction is None):
            raise ValueError("origin 과 direction 은 함께 줍니다")
        if (self.target is None) != (self.select is None):
            raise ValueError("target 과 select 는 함께 줍니다")
        return self


class DatumPlaneNode(_Node):
    """**기준면** — 형상을 만들지 않고, 스케치 · 자르기 · 단면 · 대칭이 놓이는 평면이 된다.
    평면 칸(`plane`)에 `{"datum": "<이 id>"}` 로, 대칭면(`mirror.plane`)에 id 로 쓴다.

    정하는 법(하나만). 그다음 `offset` 으로 법선 쪽으로 띄우고, `hinge` + `angle` 로 축 둘레로
    기울인다:
    - `plane` — 이름 있는 평면 또는 원점 · 법선
    - `points` — 세 점
    - `target` + `select` — 앞 입체의 **평면** 하나(`recipe_find` 의 질의). 치수가 바뀌면
      그 면을 따라간다 — 「윗면에서 10 띄운 면」."""

    op: Literal["datum_plane"]
    plane: PlaneSpec | None = None
    points: list[XYZ] | None = Field(default=None, min_length=3, max_length=3)
    target: str | None = None
    select: dict[str, Any] | None = None
    offset: float = 0.0
    """법선 쪽으로 띄운다(음수면 반대쪽)."""
    hinge: str | None = None
    """기울일 축 — `X` · `Y` · `Z` 또는 앞의 기준축 id. `angle` 과 함께."""
    angle: float = Field(default=0.0, ge=-360, le=360)
    """`hinge` 둘레로 돌리는 각(도). 「이 엣지를 지나 30° 기운 면」 은 엣지로 기준축을 만들고
    그 엣지를 지나는 면을 그 축 둘레로 30°."""

    @model_validator(mode="after")
    def _defined(self) -> DatumPlaneNode:
        _one_way(
            self,
            {
                "plane": self.plane is not None,
                "points": self.points is not None,
                "target + select": self.target is not None or self.select is not None,
            },
        )
        if (self.target is None) != (self.select is None):
            raise ValueError("target 과 select 는 함께 줍니다")
        if self.angle and self.hinge is None:
            raise ValueError("angle 은 hinge(기울일 축)와 함께 줍니다")
        return self


Node = Annotated[
    SketchNode
    | ExtrudeNode
    | RevolveNode
    | SweepNode
    | HelixNode
    | SheetMetalNode
    | BendNode
    | DeformNode
    | SurfaceNode
    | ThickenNode
    | UnfoldNode
    | FrameNode
    | BoxNode
    | WedgeNode
    | BoltNode
    | PinNode
    | StandoffNode
    | NutNode
    | WasherNode
    | BearingNode
    | SpringNode
    | BracketNode
    | FastenNode
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
    | DivideFaceNode
    | PatternNode
    | TransformNode
    | MirrorNode
    | SplitNode
    | ComponentNode
    | GroupNode
    | DraftNode
    | DefeatureNode
    | ImprintNode
    | SectionNode
    | OffsetNode
    | ImportStepNode
    | DatumAxisNode
    | DatumPlaneNode,
    Field(discriminator="op"),
]


#: 좌표계 이름으로 못 쓰는 말 — 조건의 `cs` 가 이것을 **전역**으로 읽는다.
RESERVED_FRAMES = {"global", "전역"}


class CoordinateSystem(BaseModel):
    """이름 붙인 좌표계 — 해석 조건이 「이 방향으로 x · y · z」 를 말할 때 가리킨다.

    형상을 바꾸지 않는다. 원점 · 회전에 치수 식(`"=길이/2"`)을 쓸 수 있어 실험계획이 치수를
    바꾸면 **같이 움직인다**. 방향은 두 방식 중 하나로 적는다 — **X · Y 방향 벡터**(Z 는 둘의
    외적) 또는 **회전**(X → Y → Z 고정 축, 도). 벡터가 있으면 벡터를 쓴다."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=40)
    origin: XYZ = (0.0, 0.0, 0.0)
    x_axis: XYZ | None = None
    """X 방향(길이는 상관없다). 비우면 전역 X."""
    y_axis: XYZ | None = None
    """Y 방향 — X 에 수직이 아니어도 된다(수직으로 맞춘다). Z 는 X 와 Y 의 외적."""
    rotate: XYZ | None = None
    """회전 — X → Y → Z 고정 축 순서(도). `x_axis` 가 없을 때 쓴다."""


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    units: Literal["mm"] = "mm"
    params: dict[str, float] = Field(default_factory=dict)
    """이름 붙인 치수. 어느 숫자 칸에든 `"=이름 * 2"` 로 쓴다 — 하나를 고치면 다 따라온다."""
    nodes: list[Node] = Field(min_length=1, max_length=500)
    result: str | None = None
    """결과로 삼을 노드. 비우면 마지막 노드."""
    coordinate_systems: list[CoordinateSystem] = Field(default_factory=list, max_length=50)
    """이름 붙인 좌표계 — 형상과 무관하고, 해석 조건의 `cs` 가 가리킨다."""

    @model_validator(mode="after")
    def _check_frames(self) -> Recipe:
        seen: set[str] = set()
        for index, frame in enumerate(self.coordinate_systems):
            if frame.name in RESERVED_FRAMES:
                raise ValueError(
                    f"coordinate_systems[{index}]: 「{frame.name}」 은 전역 좌표계의 "
                    "이름입니다"
                )
            if frame.name in seen:
                raise ValueError(f"coordinate_systems[{index}]: 「{frame.name}」 이 겹칩니다")
            seen.add(frame.name)
        return self

    @model_validator(mode="after")
    def _check_references(self) -> Recipe:
        seen: dict[str, str] = {}
        for index, node in enumerate(self.nodes):
            if node.id in seen:
                raise ValueError(f"nodes[{index}]: id '{node.id}' 가 겹칩니다")
            datums = datum_references(node)
            for key, value in _references(node):
                names = value if isinstance(value, list) else [value]
                for name in names:
                    if name not in seen:
                        raise ValueError(
                            f"nodes[{index}] ({node.id}).{key}: "
                            f"'{name}' 은 앞에 없는 피처입니다"
                        )
                    # 기준은 형상이 아니다 — 축 · 평면 칸에만 쓴다.
                    # 구속은 기준축 · 기준면에도 건다(`mates[…].to`).
                    if (
                        seen[name] in DATUM_OPS
                        and key not in {one[0] for one in datums}
                        and not key.startswith("mates[")
                    ):
                        raise ValueError(
                            f"nodes[{index}] ({node.id}).{key}: '{name}' 은 기준(축 · 면)"
                            "이라 형상이 아닙니다 — 축 · 평면 칸에 씁니다"
                        )
            for key, name, wanted in datums:
                if seen[name] != wanted:
                    what = (
                        "기준축(datum_axis)"
                        if wanted == "datum_axis"
                        else "기준면(datum_plane)"
                    )
                    raise ValueError(
                        f"nodes[{index}] ({node.id}).{key}: '{name}' 은 {what}이 아닙니다"
                    )
            seen[node.id] = node.op
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
    "split": ("target", "tool"),
    "draft": ("target",),
    "section": ("target",),
    "offset": ("target",),
    "bend": ("target",),
    "deform": ("target",),
    "thicken": ("target",),
    "unfold": ("target",),
    "divide_face": ("target", "sketch"),
    "defeature": ("target",),
    "imprint": ("target",),
    "fasten": ("target",),
    "datum_axis": ("target",),
    "datum_plane": ("target",),
}


def _references(node: Any) -> list[tuple[str, str | list[str]]]:
    out = []
    for key in _REFERENCE_FIELDS.get(node.op, ()):
        value = getattr(node, key)
        if value is not None:  # extrude.target 처럼 비어도 되는 칸
            out.append((key, value))
    if node.op == "component":
        for index, mate in enumerate(node.mates):
            if mate.to not in GLOBAL_AXES and mate.to not in GLOBAL_PLANES:
                out.append((f"mates[{index}].to", mate.to))
    return out + [(key, name) for key, name, _ in datum_references(node)]


def datum_references(node: Any) -> list[tuple[str, str, str]]:
    """기준을 가리키는 칸 — (칸, id, 있어야 할 종류). 전역 이름(`X` · `XY` …)은 빼고."""
    out: list[tuple[str, str, str]] = []
    if node.op in ("revolve", "pattern", "deform") and node.axis not in GLOBAL_AXES:
        out.append(("axis", node.axis, "datum_axis"))
    if node.op == "datum_plane" and node.hinge is not None and node.hinge not in GLOBAL_AXES:
        out.append(("hinge", node.hinge, "datum_axis"))
    if node.op == "mirror" and node.plane not in GLOBAL_PLANES:
        out.append(("plane", node.plane, "datum_plane"))
    for key in type(node).model_fields:
        value = getattr(node, key)
        if isinstance(value, PlaneSpec) and value.datum is not None:
            out.append((f"{key}.datum", value.datum, "datum_plane"))
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
