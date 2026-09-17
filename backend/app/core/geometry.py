"""1단계 — Geometry Understanding.

STEP 을 읽고(또는 이미 만든 형상을 받아) **정규화**한다: 바닥이 z=0, XY 중심이 원점.
뒤 단계 전부가 이 좌표계를 전제하므로 정규화는 여기 한 곳에서만 한다.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Compound, Location, Shape, import_step

from app.core.model import BBox, ProductGeometry, xyz


class GeometryError(ValueError):
    """읽을 수 없거나 비어 있는 형상. 메시지는 화면에 그대로 나간다."""


def load_step(path: Path) -> Shape:
    if not path.exists():
        raise GeometryError(f"파일이 없습니다: {path.name}")
    try:
        shape = import_step(path)
    except Exception as failure:
        raise GeometryError(f"STEP 을 읽지 못했습니다: {failure}") from failure
    if not shape.solids():
        raise GeometryError(
            "STEP 에 솔리드가 없습니다 — 면(서피스)만 있는 파일은 지그를 잡을 수 없습니다."
        )
    return shape


def normalize(shape: Shape) -> Shape:
    """바닥 z=0 · XY 중심 원점으로 옮긴 **복사본**."""
    box = shape.bounding_box()
    center = box.center()
    return shape.moved(Location((-center.X, -center.Y, -box.min.Z)))


def understand(shape: Shape) -> ProductGeometry:
    normalized = normalize(shape)
    box = normalized.bounding_box()
    if box.size.X < 1e-3 or box.size.Y < 1e-3 or box.size.Z < 1e-3:
        raise GeometryError("형상의 크기가 0 입니다.")
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
