"""비틀기 · 테이퍼 — 축을 따라 단면을 돌리고(twist) 줄인다(taper).

비틀린 띠 · 날개, 끝으로 갈수록 가늘어지는 보처럼 「단면은 그대로인데 축을 따라 조금씩 바뀌는」
모양. 축 위의 자리 s 가 `start` → `end` 로 갈 때 그 높이의 단면을 축 둘레로 0 → `twist` 만큼
돌리고, 축에서의 거리를 1 → `taper` 배로 줄인다(그 앞은 그대로, 그 뒤는 끝의 변형 그대로).

어떻게: 형상을 NURBS 로 바꾼 뒤 **면마다 새 곡면을 맞춘다** — 원래 곡면의 매개변수 자리마다
변형한 점을 지나는 3차 B-스플라인(그레빌 점 보간). 매개변수 영역이 같으니 면을 자르는 곡선
(pcurve)이 그대로 맞고, 엣지는 그 곡선에서 다시 세운다. 마디를 늘려 가며 어긋남이 허용치
안에 들 때까지 — 조정점만 옮기는 방식은 90° 비틀기에서 부피가 0.3 % 어긋났는데, 보간은
0.0003 % 다. 면들을 꿰매어 다시 솔리드로.

비틀기는 부피를 바꾸지 않고, 테이퍼(선형 배율 k)는 부피를 A · L · (1 + (k-1) + (k-1)²/3) 로
바꾼다 — 시험이 이 둘로 정확도를 본다.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
from build123d import Axis, Face, GeomType, Part, Plane, Rectangle, Shape, Solid
from OCP.BRep import BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_NurbsConvert,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepLib import BRepLib
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.Geom import Geom_BSplineSurface
from OCP.gp import gp_Pnt
from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
from OCP.TColgp import TColgp_Array2OfPnt
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SHELL, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape
from OCP.TopTools import TopTools_ListOfShape

Point = np.ndarray
Mapping = Callable[[Point], Point]

#: 맞춘 곡면의 차수와 마디 수의 시작 · 끝.
_DEGREE = 3
_SPANS = (8, 64)


class DeformError(ValueError):
    """사람이 읽고 고칠 수 있는 실패 — 평가기가 노드 id 를 붙인다."""


def mapping(axis: Axis, start: float, end: float, twist: float, taper: float) -> Mapping:
    """점 → 비틀고 줄인 점. `twist` 는 라디안, 축 위의 자리는 `axis.position` 에서 잰다."""
    origin = np.array(tuple(axis.position), dtype=float)
    a = np.array(tuple(axis.direction), dtype=float)
    a /= np.linalg.norm(a)
    length = end - start

    def moved(point: Point) -> Point:
        p = point - origin
        s = float(p @ a)
        ratio = min(1.0, max(0.0, (s - start) / length))
        radial = p - s * a
        angle = twist * ratio
        turned = radial * math.cos(angle) + np.cross(a, radial) * math.sin(angle)
        return origin + s * a + (1 + (taper - 1) * ratio) * turned

    return moved


def deform(
    shape: Shape, move: Mapping, *, tolerance: float, cuts: list[Plane] | None = None
) -> Part:
    """솔리드마다 변형해 다시 묶는다. `cuts` 는 변형이 꺾이는 자리(구간의 시작 · 끝) — 면을
    거기서 갈라 두면 한 면이 꺾인 변형을 맞추느라 마디를 끝없이 늘리지 않는다."""
    solids = shape.solids()
    if not solids:
        raise DeformError("솔리드가 없습니다 — 입체만 비틀고 줄입니다")
    return Part(children=[_solid(one, move, tolerance, cuts or []) for one in solids])


def _split(solid: Solid, cuts: list[Plane]) -> TopoDS_Shape:
    """꺾이는 자리에서 가른 조각들(솔리드 묶음)."""
    if not cuts:
        return solid.wrapped
    reach = solid.bounding_box().diagonal * 4 + 10.0
    arguments, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    arguments.Append(solid.wrapped)
    for plane in cuts:
        tools.Append((plane.location * Rectangle(reach, reach).face()).wrapped)
    splitter = BRepAlgoAPI_Splitter()
    splitter.SetArguments(arguments)
    splitter.SetTools(tools)
    splitter.Build()
    if not splitter.IsDone():  # pragma: no cover — 평면으로 가르기는 실패하지 않는다
        raise DeformError("변형 구간의 경계에서 형상을 가르지 못했습니다")
    return splitter.Shape()


def _on_cut(face: TopoDS_Face, cuts: list[Plane], tolerance: float) -> bool:
    """가른 자리에 생긴 속면인가 — 조각끼리 맞닿은 면은 바깥이 아니다."""
    if not cuts:
        return False
    built = Face(face)
    if built.geom_type != GeomType.PLANE:
        return False
    center, normal = built.center(), built.normal_at()
    return any(
        abs(abs(normal.dot(plane.z_dir)) - 1) < 1e-6
        and abs((center - plane.origin).dot(plane.z_dir)) < tolerance
        for plane in cuts
    )


def _solid(solid: Solid, move: Mapping, tolerance: float, cuts: list[Plane]) -> Solid:
    nurbs = BRepBuilderAPI_NurbsConvert(_split(solid, cuts), True).Shape()
    sewing = BRepBuilderAPI_Sewing(max(tolerance * 10, 1e-4))
    explorer = TopExp_Explorer(nurbs, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        if not _on_cut(face, cuts, tolerance):
            sewing.Add(_face(face, move, tolerance))
        explorer.Next()
    sewing.Perform()
    fixed = ShapeFix_Shape(sewing.SewedShape())
    fixed.Perform()
    shells = TopExp_Explorer(fixed.Shape(), TopAbs_SHELL)
    if not shells.More():
        raise DeformError("변형한 면들을 하나로 꿰매지 못했습니다 — 각을 줄여 보세요")
    made = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(shells.Current())).Solid()
    upright = ShapeFix_Solid(made)
    upright.Perform()
    out = upright.Solid()
    if not BRepCheck_Analyzer(out).IsValid():
        raise DeformError(
            "변형한 형상이 올바르지 않습니다 — 비틀기 각을 줄이거나 구간을 늘리세요"
        )
    return Solid(out)


def _face(face: TopoDS_Face, move: Mapping, tolerance: float) -> TopoDS_Shape:
    """면 하나 — 같은 매개변수 영역에 변형한 곡면을 맞추고, 자르는 곡선으로 다시 자른다."""
    surface = BRep_Tool.Surface_s(face)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    fitted = _fitted(surface, move, (u0, u1, v0, v1), tolerance)
    outer = BRepTools.OuterWire_s(face)
    builder: BRepBuilderAPI_MakeFace | None = None
    holes = []
    wires = TopExp_Explorer(face, TopAbs_WIRE)
    while wires.More():
        wire = TopoDS.Wire_s(wires.Current())
        rebuilt = _wire(wire, face, fitted)
        if wire.IsSame(outer):
            builder = BRepBuilderAPI_MakeFace(fitted, rebuilt, True)
        else:
            holes.append(rebuilt)
        wires.Next()
    if builder is None:  # pragma: no cover — 면에는 바깥 테두리가 있다
        raise DeformError("면의 바깥 테두리를 찾지 못했습니다")
    for hole in holes:
        builder.Add(hole)
    made = builder.Face()
    if face.Orientation() == TopAbs_REVERSED:
        made.Reverse()
    return made


def _wire(wire: object, face: TopoDS_Face, surface: Geom_BSplineSurface) -> object:
    maker = BRepBuilderAPI_MakeWire()
    edges = BRepTools_WireExplorer(wire, face)
    while edges.More():
        edge = edges.Current()
        curve = BRep_Tool.CurveOnSurface_s(edge, face, 0.0, 0.0)
        first, last = BRep_Tool.Range_s(edge, face)
        made = BRepBuilderAPI_MakeEdge(curve, surface, first, last).Edge()
        if edge.Orientation() == TopAbs_REVERSED:
            made.Reverse()
        BRepLib.BuildCurves3d_s(made, 1e-7)
        maker.Add(made)
        edges.Next()
    return maker.Wire()


# --- 곡면 맞추기 ------------------------------------------------------------------


def _knots(low: float, high: float, spans: int) -> list[float]:
    """양 끝을 차수+1 번 겹친(clamped) 고른 마디."""
    inner = [low + (high - low) * i / spans for i in range(1, spans)]
    return [low] * (_DEGREE + 1) + inner + [high] * (_DEGREE + 1)


def _greville(knots: list[float]) -> list[float]:
    count = len(knots) - _DEGREE - 1
    return [sum(knots[i + 1 : i + _DEGREE + 1]) / _DEGREE for i in range(count)]


def _basis(knots: list[float], params: list[float]) -> np.ndarray:
    """B-스플라인 기저의 값 — 행은 매개변수, 열은 조정점(콕스-드 부어)."""
    count = len(knots) - _DEGREE - 1
    last = max(i for i in range(len(knots) - 1) if knots[i] < knots[i + 1])
    out = np.zeros((len(params), count))
    for row, raw in enumerate(params):
        # 끝의 그레빌 점((a+a+a)/3)이 반올림으로 마디 밖에 한 끗 나가면 기저가 다 0 이 된다.
        x = min(max(raw, knots[0]), knots[-1])
        values = np.array(
            [
                1.0 if knots[i] <= x < knots[i + 1] or (i == last and x >= knots[-1]) else 0.0
                for i in range(len(knots) - 1)
            ]
        )
        for degree in range(1, _DEGREE + 1):
            nxt = np.zeros(len(knots) - 1 - degree)
            for i in range(len(nxt)):
                left = knots[i + degree] - knots[i]
                right = knots[i + degree + 1] - knots[i + 1]
                a = (x - knots[i]) / left * values[i] if left else 0.0
                b = (knots[i + degree + 1] - x) / right * values[i + 1] if right else 0.0
                nxt[i] = a + b
            values = nxt
        out[row] = values[:count]
    return out


def _array(values: list[float]) -> TColStd_Array1OfReal:
    out = TColStd_Array1OfReal(1, len(values))
    for index, value in enumerate(values, start=1):
        out.SetValue(index, value)
    return out


def _fitted(
    surface: object, move: Mapping, bounds: tuple[float, float, float, float], tolerance: float
) -> Geom_BSplineSurface:
    """변형한 곡면 — 마디를 늘려 가며 어긋남이 허용치 안에 들 때까지."""
    u0, u1, v0, v1 = bounds

    def target(u: float, v: float) -> Point:
        point = surface.Value(u, v)  # type: ignore[attr-defined]
        return move(np.array([point.X(), point.Y(), point.Z()]))

    spans = _SPANS[0]
    while True:
        made = _interpolated(target, (u0, u1, v0, v1), spans)
        # 그레빌 점 사이(보간이 가장 멀어지는 자리)에서 어긋남을 잰다.
        checks = [
            (
                u0 + (u1 - u0) * (i + 0.5) / (spans + 1),
                v0 + (v1 - v0) * (j + 0.5) / (spans + 1),
            )
            for i in range(spans + 1)
            for j in range(spans + 1)
        ]
        miss = 0.0
        for u, v in checks:
            point = made.Value(u, v)
            want = target(u, v)
            miss = max(
                miss, float(np.linalg.norm(np.array([point.X(), point.Y(), point.Z()]) - want))
            )
        if miss <= tolerance or spans >= _SPANS[1]:
            return made
        spans *= 2


def _interpolated(
    target: Callable[[float, float], Point],
    bounds: tuple[float, float, float, float],
    spans: int,
) -> Geom_BSplineSurface:
    u0, u1, v0, v1 = bounds
    knots_u, knots_v = _knots(u0, u1, spans), _knots(v0, v1, spans)
    at_u, at_v = _greville(knots_u), _greville(knots_v)
    points = np.array([[target(u, v) for v in at_v] for u in at_u])
    inverse_u = np.linalg.inv(_basis(knots_u, at_u))
    inverse_v = np.linalg.inv(_basis(knots_v, at_v))
    poles = np.einsum("ia,abk,jb->ijk", inverse_u, points, inverse_v)
    grid = TColgp_Array2OfPnt(1, len(at_u), 1, len(at_v))
    for i in range(len(at_u)):
        for j in range(len(at_v)):
            grid.SetValue(i + 1, j + 1, gp_Pnt(*poles[i, j]))
    distinct_u = [u0 + (u1 - u0) * i / spans for i in range(spans + 1)]
    distinct_v = [v0 + (v1 - v0) * i / spans for i in range(spans + 1)]
    return Geom_BSplineSurface(
        grid,
        _array(distinct_u),
        _array(distinct_v),
        _mults(spans),
        _mults(spans),
        _DEGREE,
        _DEGREE,
    )


def _mults(spans: int) -> TColStd_Array1OfInteger:
    out = TColStd_Array1OfInteger(1, spans + 1)
    for index in range(1, spans + 2):
        out.SetValue(index, _DEGREE + 1 if index in (1, spans + 1) else 1)
    return out
