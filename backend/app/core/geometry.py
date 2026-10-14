"""1단계 — Geometry Understanding.

STEP 을 읽고(또는 이미 만든 형상을 받아) **정규화**한다: 바닥이 z=0, XY 중심이 원점.
뒤 단계 전부가 이 좌표계를 전제하므로 정규화는 여기 한 곳에서만 한다.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Compound, Location, Rotation, Shape, import_step

from app.core.model import BBox, ProductGeometry, xyz


class GeometryError(ValueError):
    """읽을 수 없거나 비어 있는 형상. 메시지는 화면에 그대로 나간다."""


def read_step(path: Path) -> Shape:
    """STEP 을 **읽기만** — 솔리드든 시트 바디(면, 해석용 셸 모델)든 받는다. 작업을 STEP 에서
    시작할 때 쓴다(2026-10-15 — 예전에는 지그용 검사를 빌려 써서 셸 모델 STEP 이 올라가지
    않았다). 솔리드도 면도 없으면(선 · 점뿐) 거절한다."""
    if not path.exists():
        raise GeometryError(f"파일이 없습니다: {path.name}")
    try:
        shape = import_step(path)
    except Exception as failure:
        raise GeometryError(f"STEP 파일을 읽지 못했습니다: {failure}") from failure
    if not shape.solids() and not shape.faces():
        raise GeometryError("STEP 파일에 솔리드도 면도 없습니다.")
    return shape


def load_step(path: Path) -> Shape:
    """지그를 만들 제품 — **솔리드가 있어야** 한다(받침 · 클램프가 닿을 몸체)."""
    shape = read_step(path)
    if not shape.solids():
        raise GeometryError(
            "STEP 파일에 솔리드가 없습니다. 서피스만 있는 파일(셸 모델)로는 지그를 생성할 수 "
            "없습니다 — 두께를 준 입체가 필요합니다."
        )
    return shape


def normalize(shape: Shape) -> Shape:
    """바닥 z=0 · XY 중심 원점으로 옮긴 **복사본**."""
    box = shape.bounding_box()
    center = box.center()
    return shape.moved(Location((-center.X, -center.Y, -box.min.Z)))


#: 낙하 자세 — 무엇이 아래를 보나. 회전은 정규화(바닥 z=0) **전에** 한다.
DROP_ORIENTATIONS = ("bottom", "top", "+x", "-x", "+y", "-y", "edge", "corner")


def pose(shape: Shape, orientation: str) -> Shape:
    """고른 면(또는 모서리 · 꼭짓점)이 아래(-Z)를 보게 통째로 돌린 복사본.

    SpaceClaim 시절 DropTest 의 규칙: 면 이름 하나, 또는 둘(모서리) · 셋(꼭짓점)을 더해
    정규화한 방향이 아래를 본다. edge 는 bottom+(+x), corner 는 bottom+(+x)+(+y) 로 잡았다."""
    if orientation == "bottom":
        return shape
    turns = {
        "top": Rotation(180, 0, 0),
        "+x": Rotation(0, 90, 0),  # +X 면이 아래로
        "-x": Rotation(0, -90, 0),
        "+y": Rotation(-90, 0, 0),
        "-y": Rotation(90, 0, 0),
        "edge": Rotation(0, 45, 0),
        "corner": Rotation(35.264, 45, 0),
    }
    if orientation not in turns:
        raise GeometryError(
            f"알 수 없는 낙하 자세입니다: {orientation} "
            f"(선택 가능: {', '.join(DROP_ORIENTATIONS)})"
        )
    return shape.moved(turns[orientation])


def understand(shape: Shape) -> ProductGeometry:
    normalized = normalize(shape)
    box = normalized.bounding_box()
    if box.size.X < 1e-3 or box.size.Y < 1e-3 or box.size.Z < 1e-3:
        raise GeometryError("형상의 크기가 0입니다.")
    solids = normalized.solids()
    return ProductGeometry(
        shape=normalized,
        bbox=BBox(min=xyz(box.min), max=xyz(box.max), size=xyz(box.size)),
        volume=float(normalized.volume),
        surface_area=float(normalized.area),
        solid_count=len(solids),
        face_count=len(normalized.faces()),
        edge_count=len(normalized.edges()),
        center_of_mass=xyz(normalized.center()),
    )


def as_compound(shape: Shape) -> Compound:
    return shape if isinstance(shape, Compound) else Compound(children=[shape])
