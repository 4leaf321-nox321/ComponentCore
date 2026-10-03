"""곡면 — 입체가 아니라 **면**. 자유 곡면을 만들어 두께를 주거나(`thicken`) 칼로 쓴다(`split`).

지그에서 곡면이 쓰이는 자리: 제품의 굽은 면에 맞닿는 받침(잰 점들로 곡면을 세워 두께를
준다), 굽은 면을 따라 블록을 잘라 낸 둥지(곡면으로 블록을 가른다), 덕트 · 덮개처럼 곡선
몇 개로 정해지는 얇은 판.

- `grid` — 점 격자(행마다 같은 수)를 **지나는** B-스플라인 곡면. 잰 점 · 표로 받은 형상.
- `loft` — 3D 곡선(점을 지나는 스플라인, 또는 꺾은선) 둘 이상을 잇는 곡면.
- `fill` — 닫힌 3D 테두리를 메우는 곡면(지나야 할 안쪽 점을 줄 수 있다).
"""

from __future__ import annotations

from typing import Any

from build123d import Face, Polyline, Shape, Shell, Solid, Spline, Wire
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepOffsetAPI import (
    BRepOffsetAPI_MakeOffsetShape,
    BRepOffsetAPI_MakeThickSolid,
    BRepOffsetAPI_ThruSections,
)
from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
from OCP.gp import gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.TColgp import TColgp_Array2OfPnt
from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID
from OCP.TopoDS import TopoDS

XYZ = tuple[float, float, float]


class SurfaceError(ValueError):
    """사람이 읽고 고칠 수 있는 실패."""


def is_surface(shape: Any) -> bool:
    """솔리드 없이 면만 — 곡면 노드의 결과."""
    return isinstance(shape, Shape) and not shape.solids() and bool(shape.faces())


def grid(points: list[list[XYZ]]) -> Face:
    """점 격자를 지나는 곡면."""
    rows, cols = len(points), len(points[0])
    array = TColgp_Array2OfPnt(1, rows, 1, cols)
    for i, row in enumerate(points):
        for j, point in enumerate(row):
            array.SetValue(i + 1, j + 1, gp_Pnt(*point))
    builder = GeomAPI_PointsToBSplineSurface()
    try:
        builder.Interpolate(array)
    except Exception as failure:
        raise SurfaceError(
            f"점 격자로 곡면을 세우지 못했습니다 — 겹친 점이 없나 보세요 ({failure})"
        ) from failure
    return _checked(Face(BRepBuilderAPI_MakeFace(builder.Surface(), 1e-6).Face()))


def _curve(points: list[XYZ], smooth: bool) -> Wire:
    if len(points) == 2 or not smooth:
        return Wire(Polyline(*points).edges())
    return Wire([Spline(*points)])


def loft(curves: list[list[XYZ]], *, ruled: bool, smooth: bool) -> Shape:
    """곡선 둘 이상을 잇는 곡면(셸)."""
    builder = BRepOffsetAPI_ThruSections(False, ruled, 1e-6)
    for one in curves:
        builder.AddWire(_curve(one, smooth).wrapped)
    builder.Build()
    if not builder.IsDone():
        raise SurfaceError(
            "곡선들을 잇지 못했습니다 — 곡선마다 점의 차례(방향)가 같은지 보세요"
        )
    made = builder.Shape()
    return _checked(Shell(made) if made.ShapeType() == TopAbs_SHELL else Face(made))


def fill(boundary: list[XYZ], through: list[XYZ], *, smooth: bool) -> Face:
    """닫힌 테두리를 메우는 곡면 — `through` 의 점을 지난다."""
    if smooth:
        edges: Any = [Spline(*boundary, boundary[0], periodic=False)]
    else:
        edges = Polyline(*boundary, close=True)
    try:
        made = Face.make_surface(edges, surface_points=through or None)
    except Exception as failure:
        raise SurfaceError(
            f"테두리를 메우지 못했습니다 — 테두리가 스스로 꼬이지 않았나 보세요 ({failure})"
        ) from failure
    return _checked(made)


def thicken(surface: Shape, thickness: float, side: str) -> Solid:
    """곡면에 두께를 — `front` 는 면의 앞(법선) 쪽, `back` 은 뒤, `both` 는 양쪽으로 반씩."""
    base = surface.wrapped
    amount = thickness if side != "back" else -thickness
    if side == "both":
        moved = BRepOffsetAPI_MakeOffsetShape()
        moved.PerformBySimple(base, -thickness / 2)
        if not moved.IsDone():
            raise SurfaceError("곡면을 가운데로 옮기지 못했습니다 — 두께를 줄여 보세요")
        base = moved.Shape()
    maker = BRepOffsetAPI_MakeThickSolid()
    maker.MakeThickSolidBySimple(base, amount)
    maker.Build()
    if not maker.IsDone() or maker.Shape().ShapeType() != TopAbs_SOLID:
        raise SurfaceError("두께를 주지 못했습니다 — 곡률 반지름보다 두꺼운지 보세요")
    solid = maker.Shape()
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props)
    if props.Mass() < 0:  # 면의 앞뒤에 따라 안팎이 뒤집혀 나온다
        solid = solid.Reversed()
    made = Solid(TopoDS.Solid_s(solid))
    if not made.is_valid:
        raise SurfaceError("두께를 준 입체가 올바르지 않습니다 — 두께를 줄여 보세요")
    return made


def _checked(shape: Shape) -> Any:
    if not BRepCheck_Analyzer(shape.wrapped).IsValid() or not shape.faces():
        raise SurfaceError(
            "곡면이 올바르지 않습니다 — 점 · 곡선이 스스로 꼬이지 않았나 보세요"
        )
    return shape
