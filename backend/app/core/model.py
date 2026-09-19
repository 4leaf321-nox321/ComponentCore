"""단계 사이를 오가는 자료의 모양.

**build123d 객체와 요약(JSON 가능)을 함께 든다.** 기하 객체는 다음 단계가 쓰고, 요약은 DB 와
화면이 쓴다 — 둘을 한 곳에서 만들어야 화면이 보는 값과 실제 기하가 어긋나지 않는다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from build123d import Compound, Part, Shape

XYZ = tuple[float, float, float]


def _r(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def xyz(vector: Any) -> XYZ:
    return (_r(vector.X), _r(vector.Y), _r(vector.Z))


# --- 1. Geometry Understanding -------------------------------------------------


@dataclass
class BBox:
    min: XYZ
    max: XYZ
    size: XYZ


@dataclass
class ProductGeometry:
    """정규화된 제품 — **바닥이 z=0, XY 중심이 원점**이다. 뒤 단계는 이 좌표계를 전제한다."""

    shape: Shape
    bbox: BBox
    volume: float
    surface_area: float
    solid_count: int
    face_count: int
    edge_count: int
    center_of_mass: XYZ

    def summary(self) -> dict[str, Any]:
        return {
            "bbox": asdict(self.bbox),
            "volume": _r(self.volume, 1),
            "surface_area": _r(self.surface_area, 1),
            "solid_count": self.solid_count,
            "face_count": self.face_count,
            "edge_count": self.edge_count,
            "center_of_mass": self.center_of_mass,
        }


# --- 2. Feature Recognition ----------------------------------------------------


@dataclass
class Feature:
    """인식한 특징 하나.

    kind   plane | hole | boss
    role   plane 이면 bottom | top | side, hole 이면 through | blind
    """

    index: int
    kind: str
    role: str
    center: XYZ
    normal: XYZ | None
    area: float
    radius: float | None = None
    depth: float | None = None
    axis: XYZ | None = None

    def summary(self) -> dict[str, Any]:
        return asdict(self)


# --- 3. Fixture Planning -------------------------------------------------------


@dataclass
class BasePlateSpec:
    length: float
    width: float
    thickness: float
    mount_hole_diameter: float
    holes: list[tuple[float, float, float]] = field(default_factory=list)
    """판에 더 뚫을 구멍 (x, y, 지름) — 볼트 고정의 탭 구멍."""


@dataclass
class SupportSpec:
    label: str
    position: XYZ
    """받침 윗면의 중심 — 제품 바닥과 닿는 점(정규화 좌표계, z=0)."""
    diameter: float
    height: float


@dataclass
class LocatorSpec:
    label: str
    kind: str
    """pin | rest. pin 은 구멍에 들어가고, rest 는 옆면에 기댄다."""
    position: XYZ
    direction: XYZ
    """pin 은 축 방향(+Z), rest 는 옆면을 **누르는** 방향(제품 안쪽)."""
    diameter: float | None = None
    engagement: float | None = None
    """pin 이 구멍에 들어가는 깊이."""
    size: XYZ | None = None
    """rest 의 가로·세로·높이."""


@dataclass
class ClampSpec:
    label: str
    pad_position: XYZ
    """패드가 제품 윗면과 닿는 점."""
    post_position: XYZ
    """기둥이 서는 자리(판 위, 제품 밖)."""
    pad_diameter: float
    arm_width: float
    arm_thickness: float


@dataclass
class BoltSpec:
    """부품 관통 구멍을 지나 판에 박히는 볼트 — 진동 · 충격 시험의 기본 고정."""

    label: str
    position: XYZ
    """구멍 축 위, 제품 윗면(구멍이 열리는 곳)의 점(제품 좌표계)."""
    nominal: float
    """호칭 지름(M6 이면 6)."""
    hole_diameter: float
    grip: float
    """머리 아래에서 판 윗면까지 — 부품 두께 + 스페이서."""
    head: str
    washer: bool
    engagement: float
    """판에 박히는 깊이."""


@dataclass
class RollerSpec:
    """3점 굽힘의 지지 롤러 — 축이 폭 방향으로 눕는 원기둥. 받침대 위에 놓인다."""

    label: str
    position: XYZ
    """롤러 축의 중심(제품 좌표계, z 는 축 높이 — 음수: 제품 바닥 아래)."""
    diameter: float
    length: float
    along: str
    """축 방향 — x | y."""


@dataclass
class NoseSpec:
    """로딩 노즈 — 스팬 가운데 위에서 누르는 원기둥 + 위로 뻗는 줄기."""

    position: XYZ
    """노즈 축의 중심(제품 윗면 + 반지름)."""
    diameter: float
    length: float
    along: str
    stem_height: float


@dataclass
class ImpactorSpec:
    """충격 시험의 낙하물 — 강구 또는 펜(둥근 끝 원뿔)."""

    kind: str
    position: XYZ
    """강구는 중심, 펜은 끝점."""
    diameter: float


@dataclass
class FixturePlan:
    base_plate: BasePlateSpec
    supports: list[SupportSpec]
    locators: list[LocatorSpec]
    clamps: list[ClampSpec]
    product_lift: float
    """제품이 판 윗면에서 얼마나 떠 있나(= 받침 높이)."""
    notes: list[str] = field(default_factory=list)
    kind: str = "clamped"
    bolts: list[BoltSpec] = field(default_factory=list)
    rollers: list[RollerSpec] = field(default_factory=list)
    nose: NoseSpec | None = None
    impactor: ImpactorSpec | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "base_plate": asdict(self.base_plate),
            "supports": [asdict(one) for one in self.supports],
            "locators": [asdict(one) for one in self.locators],
            "clamps": [asdict(one) for one in self.clamps],
            "bolts": [asdict(one) for one in self.bolts],
            "rollers": [asdict(one) for one in self.rollers],
            "nose": asdict(self.nose) if self.nose else None,
            "impactor": asdict(self.impactor) if self.impactor else None,
            "product_lift": self.product_lift,
            "notes": list(self.notes),
        }


# --- 4. Elements / Assembly ----------------------------------------------------


@dataclass
class JigElements:
    """만들어진 부품. **모두 최종 좌표계** — 판 윗면이 z=0, 제품은 product_lift 만큼 떠
    있다."""

    base_plate: Part
    supports: list[Part]
    locators: list[Part]
    clamps: list[Part]
    others: list[Part] = field(default_factory=list)
    """형식마다 다른 것 — 볼트 · 롤러 · 로딩 노즈 · 임팩터. 이름표가 곧 화면의 말이다."""

    def all_parts(self) -> list[Part]:
        return [self.base_plate, *self.supports, *self.locators, *self.clamps, *self.others]


# --- 5. Interference -----------------------------------------------------------


@dataclass
class InterferenceItem:
    a: str
    b: str
    volume: float
    ok: bool


@dataclass
class InterferenceReport:
    items: list[InterferenceItem]
    tolerance: float

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)

    @property
    def total_volume(self) -> float:
        return _r(sum(item.volume for item in self.items if not item.ok), 3)

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tolerance": self.tolerance,
            "total_volume": self.total_volume,
            "items": [asdict(item) for item in self.items],
        }


# --- 6. Result -----------------------------------------------------------------


@dataclass
class StageLog:
    name: str
    millis: int
    detail: str


@dataclass
class JigResult:
    geometry: ProductGeometry
    features: list[Feature]
    plan: FixturePlan
    elements: JigElements
    jig: Compound
    """지그 부품 전부(제품 제외)."""
    product: Shape
    """최종 좌표계로 옮긴 제품."""
    interference: InterferenceReport
    files: dict[str, Path]
    stages: list[StageLog]

    def summary(self) -> dict[str, Any]:
        """DB 에 남기고 화면이 읽는 요약. **기하 객체는 안 든다** — JSON 이어야 한다."""
        return {
            "geometry": self.geometry.summary(),
            "features": [one.summary() for one in self.features],
            "feature_counts": _count_by(self.features),
            "plan": self.plan.summary(),
            "interference": self.interference.summary(),
            "files": {key: path.name for key, path in self.files.items()},
            "stages": [asdict(stage) for stage in self.stages],
        }


def _count_by(features: list[Feature]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for one in features:
        key = f"{one.kind}:{one.role}"
        counts[key] = counts.get(key, 0) + 1
    return counts
