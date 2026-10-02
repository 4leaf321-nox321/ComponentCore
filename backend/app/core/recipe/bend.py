"""판 굽히기 — 펼친 판을 굽힘선에서 반지름 R 로 접거나 원통에 감는다(`bend` 노드).

판을 굽힘선마다 띠로 자른다. 평평한 띠는 돌출한 뒤 **강체로** 옮기고, 굽힘 띠는 원통에
**정확히** 감는다 — 펼친 윤곽의 각 엣지를 원통의 매개변수 평면(각 · 축 높이)으로 옮긴다.
그 옮김은 한쪽 방향 배율뿐인 아핀이라 B-스플라인의 조정점만 옮기면 곡선이 정확히 따라온다
(호는 타원호가 된다). 그 면을 두께만큼 띄우면 옆벽은 반지름 방향으로 선다 — 실제 굽힘과
같다. 마지막에 띠들을 하나로 합친다.

길이는 중립면에서 보존한다: 안쪽 면에서 `k_factor · 두께` 떨어진 층의 호 길이가 펼친 길이다.
`k_factor` 0.5 면 굽힌 뒤 부피가 펼친 판과 같다(시험이 이것으로 정확도를 본다).

좌표: 판의 **아래 면**을 z=0 으로 두는 지역 좌표계(u = 굽혀 나가는 방향, v = 굽힘선 방향,
z = 판의 위쪽)에서 계산하고 마지막에 제자리로 돌린다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import (
    Face,
    GeomType,
    Location,
    Part,
    Plane,
    Pos,
    Rectangle,
    Shape,
    Solid,
    Vector,
    extrude,
)
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Transform,
)
from OCP.BRepGProp import BRepGProp
from OCP.BRepLib import BRepLib
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.Geom import Geom_CylindricalSurface
from OCP.Geom2d import Geom2d_TrimmedCurve
from OCP.Geom2dConvert import Geom2dConvert
from OCP.GeomAPI import GeomAPI
from OCP.gp import gp_Ax1, gp_Ax2, gp_Ax3, gp_Dir, gp_Pln, gp_Pnt, gp_Pnt2d, gp_Trsf
from OCP.GProp import GProp_GProps
from OCP.ShapeFix import ShapeFix_Face
from OCP.TopAbs import TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Shape

from app.core.recipe import schema as S

#: 높이 · 길이를 같다고 볼 오차(mm).
_TOL = 1e-4
#: 법선이 수직 · 평행인지 볼 오차(코사인).
_ANGLE_TOL = 1e-6


class BendError(ValueError):
    """사람이 읽고 고칠 수 있는 실패 — 평가기가 노드 id 를 붙여 돌려준다."""


@dataclass
class _Plate:
    plane: Plane
    """지역 좌표계 — 원점은 판의 아래 면, x = 굽혀 나가는 방향, z = 판의 위쪽."""
    thickness: float
    pattern: list[Face]
    """펼친 윤곽 — 지역 좌표의 z=0 위."""


@dataclass
class _Zone:
    start: float
    length: float
    radius: float
    angle: float
    """라디안, 부호 있음 — 양수가 위(+z)."""


def bend(part: Part, node: S.BendNode) -> Part:
    plate = _plate(part, Vector(*node.along))
    t = plate.thickness
    u_min, u_max, v_min, v_max = _extent(plate.pattern)
    zones = _zones(node, t, u_min, u_max)

    # 자를 띠: 평평 · 굽힘 · 평평 … 순서. 굽힘 띠 뒤의 모든 것은 그 굽힘만큼 돈다.
    pieces: list[Shape] = []
    carried = Location()
    flat_from = u_min - 1.0
    for zone in zones:
        pieces += [carried * one for one in _flat(plate, flat_from, zone.start, v_min, v_max)]
        for face in _strip(plate.pattern, zone.start, zone.start + zone.length, v_min, v_max):
            pieces.append(carried * _wrapped(face, zone, t, node.k_factor))
        carried = carried * _after(zone, t)
        flat_from = zone.start + zone.length
    pieces += [carried * one for one in _flat(plate, flat_from, u_max + 1.0, v_min, v_max)]

    if not pieces:  # pragma: no cover — 윤곽이 있으면 띠도 있다
        raise BendError("굽힐 판이 없습니다")
    placed = plate.plane.location * _fused(pieces)
    return Part(children=[_upright(one) for one in placed.solids()])


# --- 판을 알아본다 ---------------------------------------------------------------


def _plate(part: Part, along: Vector) -> _Plate:
    """두께가 한결같은 판인가 — 위 · 아래 면이 한 법선으로 평평하고 나머지 면이 그 법선에
    수직(옆벽)이어야 한다. 아니면 무엇이 걸리는지 말한다."""
    faces = list(part.faces())
    planar = [one for one in faces if one.geom_type == GeomType.PLANE]
    if not planar:
        raise BendError("평평한 면이 없습니다 — 판(두께가 한결같은 입체)만 굽힙니다")
    biggest = max(planar, key=lambda one: one.area)
    normal = _canonical(biggest.normal_at())

    heights: list[float] = []
    horizontal: list[tuple[float, Face]] = []
    for one in faces:
        if (
            one.geom_type == GeomType.PLANE
            and abs(abs(one.normal_at().dot(normal)) - 1) < _ANGLE_TOL
        ):
            height = one.center().dot(normal)
            heights.append(height)
            horizontal.append((height, one))
            continue
        if not _is_wall(one, normal):
            raise BendError(
                "판의 위 · 아래 모서리를 다듬은 면(필렛 · 모따기 · 구배)이나 기운 면이 "
                "있습니다 — 그런 것은 굽힌 뒤에 만드세요"
            )
    levels = _levels(heights)
    if len(levels) != 2:
        raise BendError(
            "두께가 한결같은 판이 아닙니다 — 높이가 "
            + " · ".join(f"{level:g}" for level in levels)
            + " 인 면이 있습니다. 포켓 · 단차는 굽힌 뒤에 만드세요"
        )
    low, high = levels

    direction = along - normal * along.dot(normal)
    if along.length < _TOL or direction.length < 0.1 * along.length:
        raise BendError("along: 판 위의 방향이어야 합니다 — 판의 두께 방향을 가리킵니다")
    plane = Plane(origin=normal * low, x_dir=direction.normalized(), z_dir=normal)
    pattern = [
        plane.to_local_coords(one) for height, one in horizontal if abs(height - low) < _TOL
    ]
    return _Plate(
        plane=plane, thickness=high - low, pattern=[Face(one.wrapped) for one in pattern]
    )


def _canonical(normal: Vector) -> Vector:
    """판의 위쪽 — Z 가 양수인 쪽, Z 가 0 이면 Y, 그다음 X. 같은 판이면 늘 같은 쪽이다."""
    for value in (normal.Z, normal.Y, normal.X):
        if abs(value) > _ANGLE_TOL:
            return normal if value > 0 else -normal
    return normal  # pragma: no cover — 길이 0 인 법선은 없다


def _is_wall(face: Face, normal: Vector) -> bool:
    """옆벽인가 — 면 위 어디서나 법선이 판의 법선에 수직."""
    for u in (0.1, 0.5, 0.9):
        for v in (0.1, 0.5, 0.9):
            if abs(face.normal_at(u, v).dot(normal)) > 1e-5:
                return False
    return True


def _levels(heights: list[float]) -> list[float]:
    out: list[float] = []
    for height in sorted(heights):
        if not out or height - out[-1] > _TOL:
            out.append(height)
    return out


def _extent(faces: list[Face]) -> tuple[float, float, float, float]:
    boxes = [one.bounding_box() for one in faces]
    return (
        min(box.min.X for box in boxes),
        max(box.max.X for box in boxes),
        min(box.min.Y for box in boxes),
        max(box.max.Y for box in boxes),
    )


# --- 굽힘 구간 ---------------------------------------------------------------------


def _zones(node: S.BendNode, t: float, u_min: float, u_max: float) -> list[_Zone]:
    zones: list[_Zone] = []
    for index, one in enumerate(node.bends):
        where = f"bends[{index}]"
        # 판 끝(u_min)에서 바로 굽기 시작해도 된다 — 통째로 감기.
        if not u_min - _TOL <= one.at < u_max - _TOL:
            raise BendError(
                f"{where}.at: 판({u_min:g} ~ {u_max:g}) 안이어야 합니다 — "
                f"{one.at:g} 은 밖입니다"
            )
        if zones and one.at < zones[-1].start + zones[-1].length - _TOL:
            before = zones[-1].start + zones[-1].length
            raise BendError(
                f"{where}.at: 앞 굽힘이 {before:g} 까지입니다 — 그 뒤에서 시작하세요"
            )
        neutral = one.radius + node.k_factor * t
        if one.until == "end":
            length = u_max - one.at
            angle = length / neutral
            if angle >= 2 * math.pi - 1e-3:
                raise BendError(
                    f"{where}: 끝까지 감으면 {math.degrees(angle):.0f}° 로 한 바퀴를 "
                    "넘습니다 — 반지름을 키우거나 판을 줄이세요"
                )
        else:
            angle = math.radians(one.angle)
            length = neutral * angle
            if one.at + length > u_max + _TOL:
                raise BendError(
                    f"{where}: 굽힘 구간({one.at:g} ~ {one.at + length:g})이 판 끝"
                    f"({u_max:g})을 넘습니다 — 각도 · 반지름을 줄이거나, 끝까지 감으려면 "
                    "until: end"
                )
        sign = 1.0 if one.toward == "up" else -1.0
        zones.append(_Zone(start=one.at, length=length, radius=one.radius, angle=sign * angle))
    return zones


def _after(zone: _Zone, t: float) -> Location:
    """굽힘 뒤쪽 판이 옮겨 가는 자리 — 굽힘 구간 길이만큼 당긴 뒤 굽힘 축 둘레로 돈다."""
    center_z = t + zone.radius if zone.angle > 0 else -zone.radius
    turn = gp_Trsf()
    turn.SetRotation(gp_Ax1(gp_Pnt(zone.start, 0, center_z), gp_Dir(0, 1, 0)), -zone.angle)
    pull = gp_Trsf()
    pull.SetTranslation(gp_Pnt(0, 0, 0), gp_Pnt(-zone.length, 0, 0))
    return Location(TopLoc_Location(turn.Multiplied(pull)))


# --- 띠 ---------------------------------------------------------------------------


def _strip(
    pattern: list[Face], start: float, end: float, v_min: float, v_max: float
) -> list[Face]:
    """윤곽에서 u ∈ [start, end] 띠."""
    if end - start < _TOL:
        return []
    band = Pos((start + end) / 2, (v_min + v_max) / 2) * Rectangle(
        end - start, v_max - v_min + 2.0
    )
    out: list[Face] = []
    for face in pattern:
        common = face & band
        out += [Face(one.wrapped) for one in common.faces() if one.area > _TOL**2]
    return out


def _flat(plate: _Plate, start: float, end: float, v_min: float, v_max: float) -> list[Shape]:
    """평평한 띠 — 그대로 두께만큼 세운다."""
    return [
        extrude(face, plate.thickness, dir=(0, 0, 1))
        for face in _strip(plate.pattern, start, end, v_min, v_max)
    ]


def _wrapped(face: Face, zone: _Zone, t: float, k_factor: float) -> Shape:
    """굽힘 띠 하나를 원통에 감는다. 아래로 굽히는 것을 만들고, 위로는 판의 가운데 면에
    거울로 비춘다 — 아래 면(안쪽)과 위 면(안쪽)이 바뀌는 것 말고는 같은 굽힘이다."""
    neutral = zone.radius + k_factor * t
    solid = _wrapped_down(face, zone.start, zone.radius, neutral, t)
    if zone.angle > 0:
        mirror = gp_Trsf()
        mirror.SetMirror(gp_Ax2(gp_Pnt(0, 0, t / 2), gp_Dir(0, 0, 1)))
        solid = _upright(_transformed(solid, mirror))
    return solid


def _transformed(shape: Shape, trsf: gp_Trsf) -> Shape:
    return _solid(BRepBuilderAPI_Transform(shape.wrapped, trsf, True).Shape())


def _wrapped_down(face: Face, start: float, radius: float, neutral: float, t: float) -> Shape:
    """아래로 굽힌 띠. 축은 (start, *, -radius) 를 지나 v 방향, 판의 아래 면이 안쪽(반지름
    radius)이다. 원통의 매개변수 (U, V) = ((u - start) / neutral, v) — 한쪽 배율뿐인 아핀."""
    surface = Geom_CylindricalSurface(
        gp_Ax3(gp_Pnt(start, 0, -radius), gp_Dir(0, 1, 0), gp_Dir(0, 0, 1)), radius
    )
    flat = gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))

    def wire_on_surface(wire: object) -> object:
        maker = BRepBuilderAPI_MakeWire()
        explorer = BRepTools_WireExplorer(TopoDS.Wire_s(wire))
        while explorer.More():
            edge = explorer.Current()
            adaptor = BRepAdaptor_Curve(edge)
            first, last = adaptor.FirstParameter(), adaptor.LastParameter()
            curve = GeomAPI.To2d_s(BRep_Tool.Curve_s(edge, 0.0, 0.0), flat)
            spline = Geom2dConvert.CurveToBSplineCurve_s(
                Geom2d_TrimmedCurve(curve, first, last)
            )
            for i in range(1, spline.NbPoles() + 1):
                pole = spline.Pole(i)
                spline.SetPole(i, gp_Pnt2d((pole.X() - start) / neutral, pole.Y()))
            mapped = BRepBuilderAPI_MakeEdge(
                spline, surface, spline.FirstParameter(), spline.LastParameter()
            ).Edge()
            if edge.Orientation() == TopAbs_REVERSED:
                mapped.Reverse()
            BRepLib.BuildCurves3d_s(mapped, 1e-7)
            maker.Add(mapped)
            explorer.Next()
        return maker.Wire()

    builder = BRepBuilderAPI_MakeFace(
        surface, wire_on_surface(face.outer_wire().wrapped), True
    )
    for inner in face.inner_wires():
        builder.Add(wire_on_surface(inner.wrapped))
    fix = ShapeFix_Face(builder.Face())
    fix.Perform()
    wrapped = Face(fix.Face())

    # 두께는 축에서 멀어지는 쪽으로 — 면의 방향(앞 · 뒤)에 따라 부호가 바뀐다.
    point = wrapped.position_at(0.5, 0.5)
    outward = Vector(point.X - start, 0, point.Z + radius)
    depth = t if wrapped.normal_at(0.5, 0.5).dot(outward) > 0 else -t
    maker = BRepOffsetAPI_MakeThickSolid()
    maker.MakeThickSolidBySimple(wrapped.wrapped, depth)
    maker.Build()
    if not maker.IsDone():
        raise BendError("굽힘 구간을 두껍게 만들지 못했습니다 — 반지름을 키워 보세요")
    return _upright(_solid(maker.Shape()))


# --- 합치기 -------------------------------------------------------------------------


def _fused(pieces: list[Shape]) -> Part:
    result = Part(children=[pieces[0]])
    for one in pieces[1:]:
        result = result + Part(children=[one])
    try:
        return result.clean()
    except Exception:  # pragma: no cover — clean 이 실패해도 합친 것은 쓸 수 있다
        return result


def _upright(shape: Shape) -> Shape:
    """안팎이 뒤집힌 솔리드(부피가 음수)를 바로 세운다 — 띄우기 · 거울에서 나온다."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    if props.Mass() < 0:
        return _solid(shape.wrapped.Reversed())
    return shape


def _solid(shape: TopoDS_Shape) -> Solid:
    if shape.ShapeType() != TopAbs_SOLID:
        raise BendError("굽힘 구간이 입체가 되지 못했습니다 — 반지름을 키워 보세요")
    return Solid(TopoDS.Solid_s(shape))
