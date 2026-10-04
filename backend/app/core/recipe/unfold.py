"""판금 펴기 — 굽힌 판(두께가 한결같은 입체)을 **펼친 모양**(전개도)으로.

레이저 · 워터젯은 전개도를 받는다. 레시피로 굽힌 판(`bend` · `sheet_metal`)뿐 아니라
**고객이 준 판금 STEP** 도 펴야 하므로 레시피가 아니라 형상에서 편다:

1. 두께 `t` — 기준면(가장 넓은 평면, 또는 고른 면)에서 재료 안쪽으로 광선을 쏴 반대 면까지.
2. **겉면 한쪽**을 모은다 — 기준면에서 직선 엣지로 이어진 면 중 「안쪽으로 t 만큼 가면 반대
   겉면이 있는」 면만(옆벽 · 끝면 · 구멍 벽은 그 거리가 t 가 아니라 빠진다).
3. 이어 붙이며 편다 — 평면은 **강체로** 옮기고, 굽힘(원통면)은 **중립면**(안쪽 반지름 +
   `k_factor · t`)의 호 길이로 편다. 각진 굽힘(반지름 0)은 굽힘 여유(`θ · k · t`, 바깥쪽이면
   `- 2t·tan(θ/2)`)만큼 띄운다.
4. 펼친 면들을 합쳐 한 장 — 평면의 구멍은 그대로 따라오고(강체), 굽힘 구간의 구멍은 경계를
   점으로 따라 옮긴다(근사).

`k_factor` 는 굽힐 때(`bend`)와 같은 값이어야 굽혔다 편 판이 처음 판과 같다(시험의 잣대).
굽힘의 방향(`up` · `down`)은 **기준면이 위를 보게** 펼친 전개도에서 날개가 올라오는가다.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from build123d import Face, GeomType, Part, Polyline, Shape, Vector, Wire, extrude
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepTools import BRepTools
from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.gp import gp_Ax1, gp_Ax3, gp_Dir, gp_Lin, gp_Pnt, gp_Pnt2d, gp_Trsf, gp_Vec
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_REVERSED
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape

#: 굽힐 때(`bend`)의 기본값과 같다 — 다르면 굽혔다 편 판이 처음 판과 어긋난다.
DEFAULT_K = 0.5
#: 굽힘 구간의 곡선 경계(구멍 등)를 점으로 옮길 때의 간격(mm).
_SAMPLE = 0.25


class UnfoldError(ValueError):
    """펼 수 없다 — 왜인지 사람 말로."""


@dataclass
class BendLine:
    """전개도의 굽힘 하나 — 굽힘 구간의 가운데 선과 각 · 안쪽 반지름 · 방향."""

    start: tuple[float, float]
    end: tuple[float, float]
    angle: float
    """도."""
    radius: float
    """안쪽 반지름(mm). 각진 굽힘이면 0."""
    direction: str
    """up · down — 기준면이 위를 보게 펼친 전개도에서 날개가 올라오나 내려가나."""
    allowance: float
    """굽힘 여유 — 전개도에서 굽힘 구간의 폭(mm)."""


@dataclass
class Unfolded:
    face: Face
    """전개도 — XY 평면(z=0)의 면 한 장(구멍 포함)."""
    solid: Part
    """전개도를 두께만큼 세운 판(z 0 ~ t)."""
    thickness: float
    k_factor: float
    bends: list[BendLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        box = self.face.bounding_box()
        return {
            "thickness": round(self.thickness, 4),
            "k_factor": self.k_factor,
            "size": [round(box.size.X, 3), round(box.size.Y, 3)],
            "area": round(float(self.face.area), 3),
            "bends": [
                {
                    "start": [round(v, 3) for v in one.start],
                    "end": [round(v, 3) for v in one.end],
                    "angle": round(one.angle, 3),
                    "radius": round(one.radius, 4),
                    "direction": one.direction,
                    "allowance": round(one.allowance, 4),
                }
                for one in self.bends
            ],
            "notes": list(self.notes),
        }


# --- 작은 벡터 셈 -------------------------------------------------------------------


def _v(p: gp_Pnt) -> Vector:
    return Vector(p.X(), p.Y(), p.Z())


def _unit2(x: float, y: float) -> tuple[float, float]:
    n = math.hypot(x, y)
    return (x / n, y / n)


def _add2(
    a: tuple[float, float], b: tuple[float, float], k: float = 1.0
) -> tuple[float, float]:
    return (a[0] + k * b[0], a[1] + k * b[1])


# --- 면 하나의 성질 -----------------------------------------------------------------


def _inside_point(face: Face) -> tuple[Vector, Vector] | None:
    """면 **안의** 한 점과 그 자리의 바깥 법선. 구멍 난 면의 가운데는 구멍 속이라 격자로
    찾는다."""
    wrapped = face.wrapped
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(wrapped)
    surface = BRepAdaptor_Surface(wrapped)
    inside = BRepTopAdaptor_FClass2d(wrapped, 1e-7)
    for steps in (1, 3, 5, 9):
        for i in range(steps):
            for j in range(steps):
                u = umin + (umax - umin) * (i + 0.5) / steps
                v = vmin + (vmax - vmin) * (j + 0.5) / steps
                if inside.Perform(gp_Pnt2d(u, v)) != TopAbs_IN:
                    continue
                props = BRepLProp_SLProps(surface, u, v, 1, 1e-7)
                if not props.IsNormalDefined():
                    continue
                normal = props.Normal()
                if wrapped.Orientation() == TopAbs_REVERSED:
                    normal.Reverse()
                return _v(props.Value()), Vector(normal.X(), normal.Y(), normal.Z())
    return None


def _depth(solid: Any, point: Vector, normal: Vector) -> float | None:
    """면의 한 점에서 **재료 안쪽으로** 가면 얼마 만에 반대쪽 경계를 만나나."""
    inward = gp_Dir(-normal.X, -normal.Y, -normal.Z)
    nudge = 1e-5
    start = gp_Pnt(
        point.X - normal.X * nudge, point.Y - normal.Y * nudge, point.Z - normal.Z * nudge
    )
    hit = BRepIntCurveSurface_Inter()
    hit.Init(solid.wrapped, gp_Lin(start, inward), 1e-7)
    nearest: float | None = None
    while hit.More():
        distance = hit.W()
        if distance > 1e-7 and (nearest is None or distance < nearest):
            nearest = distance
        hit.Next()
    return nearest + nudge if nearest is not None else None


def _cylinder(face: Face) -> tuple[Vector, Vector, float]:
    surface = BRepAdaptor_Surface(face.wrapped).Cylinder()
    axis = surface.Axis()
    location, direction = axis.Location(), axis.Direction()
    return (
        Vector(location.X(), location.Y(), location.Z()),
        Vector(direction.X(), direction.Y(), direction.Z()),
        float(surface.Radius()),
    )


# --- 펼치는 자리(3D → 2D) --------------------------------------------------------


@dataclass
class _PlaneMap:
    """평면 하나를 강체로 — 면의 (X3, Y3) 좌표를 전개도의 (X2, Y2) 로."""

    origin3: Vector
    x3: Vector
    y3: Vector
    origin2: tuple[float, float]
    x2: tuple[float, float]
    y2: tuple[float, float]

    def __call__(self, p: Vector) -> tuple[float, float]:
        d = p - self.origin3
        a, b = d.dot(self.x3), d.dot(self.y3)
        return (
            self.origin2[0] + a * self.x2[0] + b * self.y2[0],
            self.origin2[1] + a * self.x2[1] + b * self.y2[1],
        )


@dataclass
class _CylMap:
    """원통(굽힘)을 중립면의 호 길이로 — 축 높이는 `d2` 로, 각은 `rn` 을 곱해 `n2` 로."""

    axis_point: Vector
    axis: Vector
    start_radial: Vector
    sign: float
    neutral: float
    origin2: tuple[float, float]
    d2: tuple[float, float]
    n2: tuple[float, float]

    def angle(self, p: Vector) -> float:
        d = p - self.axis_point
        q = d - self.axis * d.dot(self.axis)
        raw = math.atan2(self.start_radial.cross(q).dot(self.axis), self.start_radial.dot(q))
        value = raw * self.sign
        # 한 바퀴를 넘는 굽힘은 없다 — 시작선 바로 뒤의 작은 음수는 0 으로.
        return 0.0 if -1e-7 < value < 0 else value % (2 * math.pi)

    def __call__(self, p: Vector) -> tuple[float, float]:
        h = (p - self.axis_point).dot(self.axis)
        s = self.angle(p) * self.neutral
        return (
            self.origin2[0] + h * self.d2[0] + s * self.n2[0],
            self.origin2[1] + h * self.d2[1] + s * self.n2[1],
        )


Map = _PlaneMap | _CylMap


@dataclass
class _Placed:
    face: Face
    map: Map
    kind: str
    """plane · cylinder."""


def unfold(
    shape: Shape, *, k_factor: float = DEFAULT_K, base: Face | None = None, flip: bool = False
) -> Unfolded:
    """굽힌 판 → 전개도. `base` 를 안 주면 가장 넓은 평면이 기준면이다(위를 본다). `flip` 이면
    그 반대쪽 겉면을 기준으로 — 전개도가 뒤집혀 굽힘의 위 · 아래가 바뀐다."""
    solids = shape.solids()
    if len(solids) != 1:
        raise UnfoldError(
            f"판 1개(솔리드 1개)만 전개할 수 있습니다. 현재 솔리드는 {len(solids)}개입니다."
        )
    solid = solids[0]
    faces = list(solid.faces())
    if base is None:
        planes = [one for one in faces if one.geom_type == GeomType.PLANE]
        if not planes:
            raise UnfoldError("평면이 없습니다. 판금이 아닙니다.")
        base = max(planes, key=lambda one: float(one.area))
    found = _inside_point(base)
    if found is None:
        raise UnfoldError("기준면 안의 점을 찾지 못했습니다.")
    thickness = _depth(solid, *found)
    if thickness is None:
        raise UnfoldError("두께를 측정하지 못했습니다.")
    tol = max(1e-3, thickness * 0.02)
    # 판인가 — 두께가 기준면의 폭(넓이 · 2 / 둘레)보다 작아야 한다. 정육면체도 「마주 보는
    # 면까지 같은 거리」 라 판처럼 보인다.
    perimeter = sum(float(one.length) for one in base.edges())
    width = 2 * float(base.area) / perimeter if perimeter > 0 else 0.0
    if thickness >= width:
        raise UnfoldError(
            f"판금이 아닙니다. 두께 {thickness:.3g} mm가 기준면의 폭({width:.3g} mm)보다 "
            "큽니다."
        )
    if flip:
        base = _opposite(faces, *found, thickness, tol)
        found = _inside_point(base)
        if found is None:
            raise UnfoldError("반대쪽 기준면 안의 점을 찾지 못했습니다.")

    index = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(solid.wrapped, TopAbs_FACE, index)
    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(solid.wrapped, TopAbs_EDGE, TopAbs_FACE, edge_faces)
    by_index = {index.FindIndex(one.wrapped): one for one in faces}

    skin_cache: dict[int, tuple[Vector, Vector] | None] = {}

    def skin(face: Face) -> tuple[Vector, Vector] | None:
        """같은 쪽 겉면인가 — 안쪽으로 t 를 가면 반대 겉면이 있다. 그 점과 법선을 준다."""
        key = index.FindIndex(face.wrapped)
        if key not in skin_cache:
            point = _inside_point(face)
            ok = None
            if point is not None and face.geom_type in (GeomType.PLANE, GeomType.CYLINDER):
                depth = _depth(solid, *point)
                if depth is not None and abs(depth - thickness) <= tol:
                    ok = point
            skin_cache[key] = ok
        return skin_cache[key]

    # 기준면 — 그 평면의 좌표를 그대로 전개도로(바깥 법선이 +Z 쪽).
    point, normal = found
    x3 = _in_plane_x(base, normal)
    y3 = normal.cross(x3).normalized()
    placed: dict[int, _Placed] = {
        index.FindIndex(base.wrapped): _Placed(
            base, _PlaneMap(point, x3, y3, (0.0, 0.0), (1.0, 0.0), (0.0, 1.0)), "plane"
        )
    }
    bends: list[BendLine] = []
    notes: list[str] = []
    queue: deque[int] = deque([index.FindIndex(base.wrapped)])
    while queue:
        current = placed[queue.popleft()]
        for edge in current.face.edges():
            if not _straight(edge):
                continue  # 굽힘선은 늘 직선이다 — 구멍 둘레(원)로는 건너가지 않는다
            neighbors = edge_faces.FindFromKey(edge.wrapped)
            for raw in neighbors:
                key = index.FindIndex(raw)
                if key in placed or key not in by_index:
                    continue
                other = by_index[key]
                if skin(other) is None:
                    continue
                placement = _attach(current, other, edge, thickness, k_factor, skin(other))
                if placement is None:
                    continue
                result, bend = placement
                placed[key] = result
                if bend is not None:
                    bends.append(bend)
                queue.append(key)

    pieces = [_flat_face(one) for one in placed.values()]
    flat, laid = _laid_flat(_merged(pieces), _merged_bends(bends))
    total = sum(float(one.area) for one in pieces)
    if float(flat.area) < total * (1 - 1e-4):
        notes.append(
            f"전개하면 플랜지끼리 겹칩니다(겹친 면적 {total - float(flat.area):.1f} mm²). "
            "모서리에 릴리프를 적용해야 합니다."
        )
    missing = [
        one for one in faces if index.FindIndex(one.wrapped) not in placed and skin(one)
    ]
    if len(missing) > len(placed):
        notes.append("반대쪽 겉면이 더 많습니다. 기준면을 반대쪽에서 선택하십시오.")
    plate = extrude(flat, amount=thickness)
    return Unfolded(
        face=flat,
        solid=Part(plate.wrapped),
        thickness=thickness,
        k_factor=k_factor,
        bends=laid,
        notes=notes,
    )


def _opposite(faces: list[Face], point: Vector, normal: Vector, t: float, tol: float) -> Face:
    """기준면의 **반대쪽 겉면** — 두께만큼 안쪽의 점을 담은, 법선이 반대인 평면."""
    target = point - normal * t
    for face in faces:
        if face.geom_type != GeomType.PLANE:
            continue
        found = _inside_point(face)
        if found is None or found[1].dot(normal) > -0.999:
            continue
        if abs((target - found[0]).dot(found[1])) > tol:
            continue
        if face.distance_to(target) <= tol:
            return face
    raise UnfoldError("기준면의 반대쪽 겉면을 찾지 못했습니다.")


def _straight(edge: Any) -> bool:
    """직선인가 — 직선으로 적힌 것뿐 아니라 **곧은 B-스플라인**도(`bend` 가 감은 판의 이음매는
    조정점을 옮긴 스플라인이라 모양만 직선이다)."""
    curve = BRepAdaptor_Curve(edge.wrapped)
    if curve.GetType() == GeomAbs_Line:
        return True
    first, last = curve.FirstParameter(), curve.LastParameter()
    a, b = curve.Value(first), curve.Value(last)
    start, end = Vector(a.X(), a.Y(), a.Z()), Vector(b.X(), b.Y(), b.Z())
    chord = end - start
    if chord.length < 1e-9:
        return False
    direction = chord.normalized()
    for step in (0.25, 0.5, 0.75):
        p = curve.Value(first + (last - first) * step)
        offset = Vector(p.X(), p.Y(), p.Z()) - start
        if (offset - direction * offset.dot(direction)).length > 1e-6 + 1e-7 * chord.length:
            return False
    return True


def _in_plane_x(face: Face, normal: Vector) -> Vector:
    """평면의 X 방향 — 가장 긴 직선 엣지 쪽으로(전개도가 반듯하게 눕는다)."""
    lines = [one for one in face.edges() if _straight(one)]
    if lines:
        longest = max(lines, key=lambda one: float(one.length))
        direction = (longest.end_point() - longest.start_point()).normalized()
        if abs(direction.dot(normal)) < 1e-6:
            return direction
    helper = Vector(1, 0, 0) if abs(normal.X) < 0.9 else Vector(0, 1, 0)
    return (helper - normal * helper.dot(normal)).normalized()


def _attach(
    current: _Placed,
    other: Face,
    edge: Any,
    thickness: float,
    k_factor: float,
    other_point: tuple[Vector, Vector] | None,
) -> tuple[_Placed, BendLine | None] | None:
    """`current` 에 이어 `other` 를 편다 — 둘이 나눠 가진 직선 엣지가 이음매다."""
    assert other_point is not None
    a3, b3 = edge.start_point(), edge.end_point()
    a2, b2 = current.map(a3), current.map(b3)
    if math.hypot(b2[0] - a2[0], b2[1] - a2[1]) < 1e-9:
        return None
    d2 = _unit2(b2[0] - a2[0], b2[1] - a2[1])
    along = (b3 - a3).normalized()
    here = _inside_point(current.face)
    assert here is not None
    c2 = current.map(here[0])
    n2 = (-d2[1], d2[0])
    if (c2[0] - a2[0]) * n2[0] + (c2[1] - a2[1]) * n2[1] > 0:
        n2 = (-n2[0], -n2[1])  # 이미 편 면에서 멀어지는 쪽

    inside, normal = other_point
    if other.geom_type == GeomType.CYLINDER:
        axis_point, axis, radius = _cylinder(other)
        if abs(abs(axis.dot(along)) - 1) > 1e-6:
            return None  # 축과 나란하지 않은 이음매 — 굽힘이 아니다
        if axis.dot(along) < 0:
            axis = -axis
        radial = (a3 - axis_point) - axis * (a3 - axis_point).dot(axis)
        start_radial = radial.normalized()
        # 안쪽 겉면이면 바깥 법선이 축을 본다 — 그때 안쪽 반지름은 이 면의 반지름이다.
        towards_axis = normal.dot(
            (inside - axis_point) - axis * (inside - axis_point).dot(axis)
        )
        inner = towards_axis < 0
        r_in = radius if inner else radius - thickness
        neutral = r_in + k_factor * thickness
        probe = _CylMap(axis_point, axis, start_radial, 1.0, neutral, (0, 0), (1, 0), (0, 1))
        raw = probe.angle(inside)
        sign = 1.0 if raw <= math.pi else -1.0
        h_a = (a3 - axis_point).dot(axis)
        origin2 = (a2[0] - h_a * d2[0], a2[1] - h_a * d2[1])
        mapping = _CylMap(axis_point, axis, start_radial, sign, neutral, origin2, d2, n2)
        span = max(mapping.angle(_v_edge(one)) for one in other.vertices())
        if current.kind == "cylinder" and isinstance(current.map, _CylMap):
            same = (current.map.axis_point - axis_point).cross(axis).length < 1e-6 and abs(
                current.map.neutral - neutral
            ) < 1e-9
            if same:
                # 한 굽힘이 이음매로 쪼개진 것 — 같은 자리 그대로 잇는다.
                return _Placed(other, current.map, "cylinder"), None
        middle = _add2(origin2, n2, span * neutral / 2)
        bend_line = BendLine(
            start=_add2(middle, d2, (a3 - axis_point).dot(axis)),
            end=_add2(middle, d2, (b3 - axis_point).dot(axis)),
            angle=math.degrees(span),
            radius=r_in,
            direction="up" if inner else "down",
            allowance=span * neutral,
        )
        return _Placed(other, mapping, "cylinder"), bend_line

    if other.geom_type != GeomType.PLANE:
        return None
    offset = 0.0
    bend: BendLine | None = None
    if current.kind == "plane":
        here_normal = here[1]
        cos = max(-1.0, min(1.0, here_normal.dot(normal)))
        theta = math.acos(cos)
        if theta > 1e-6:
            # 각진 굽힘 — 안쪽(오목)이면 굽힘 여유만큼, 바깥(볼록)이면 두 날개가 t·tan 만큼
            # 길다.
            toward = (inside - a3).dot(here_normal) > 0
            allowance = theta * k_factor * thickness
            offset = allowance if toward else allowance - 2 * thickness * math.tan(theta / 2)
            middle_shift = offset / 2
            bend = BendLine(
                start=_add2(a2, n2, middle_shift),
                end=_add2(b2, n2, middle_shift),
                angle=math.degrees(theta),
                radius=0.0,
                direction="up" if toward else "down",
                allowance=allowance,
            )
    away = (inside - a3) - along * (inside - a3).dot(along)
    if away.length < 1e-9:
        return None
    y3 = away.normalized()
    mapping_plane = _PlaneMap(a3, along, y3, _add2(a2, n2, offset), d2, n2)
    return _Placed(other, mapping_plane, "plane"), bend


def _v_edge(vertex: Any) -> Vector:
    return Vector(vertex.X, vertex.Y, vertex.Z)


def _flat_face(one: _Placed) -> Face:
    """편 자리로 옮긴 면 한 장(XY 평면)."""
    if isinstance(one.map, _PlaneMap):
        return _moved_plane(one.face, one.map)
    return _unrolled(one.face, one.map)


def _moved_plane(face: Face, mapping: _PlaneMap) -> Face:
    """평면은 강체로 — 구멍 · 호가 그대로 따라온다."""
    o = mapping.origin3
    z3 = mapping.x3.cross(mapping.y3)
    source = gp_Ax3(
        gp_Pnt(o.X, o.Y, o.Z),
        gp_Dir(z3.X, z3.Y, z3.Z),
        gp_Dir(mapping.x3.X, mapping.x3.Y, mapping.x3.Z),
    )
    z2 = mapping.x2[0] * mapping.y2[1] - mapping.x2[1] * mapping.y2[0]
    target = gp_Ax3(
        gp_Pnt(mapping.origin2[0], mapping.origin2[1], 0.0),
        gp_Dir(0, 0, 1 if z2 > 0 else -1),
        gp_Dir(mapping.x2[0], mapping.x2[1], 0),
    )
    moved = BRepBuilderAPI_Transform(face.wrapped, _to_target(source, target), True).Shape()
    return Face(TopoDS.Face_s(moved))


def _to_target(source: gp_Ax3, target: gp_Ax3) -> gp_Trsf:
    """`source` 좌표계에 놓인 것을 `target` 좌표계의 같은 자리로 옮기는 변환."""
    to_local = gp_Trsf()
    to_local.SetTransformation(source)  # 전역 → source 의 지역 좌표
    from_local = gp_Trsf()
    from_local.SetTransformation(target)
    from_local.Invert()  # target 의 지역 좌표 → 전역
    return from_local.Multiplied(to_local)


def _unrolled(face: Face, mapping: _CylMap) -> Face:
    """굽힘(원통) — 경계를 점으로 옮겨 다각형으로. 축과 나란한 직선 · 둘레의 원호는 전개도에서
    직선이라 끝점만, 그 밖의 곡선(굽힘에 걸친 구멍)은 촘촘히."""
    wires: list[Wire] = []
    for wire in face.wires():
        points: list[tuple[float, float]] = []
        for edge in wire.order_edges():
            curve = BRepAdaptor_Curve(edge.wrapped)
            kind = curve.GetType()
            first, last = curve.FirstParameter(), curve.LastParameter()
            flat_line = kind == GeomAbs_Line or _straight(edge)
            if flat_line or (kind == GeomAbs_Circle and _coaxial(curve, mapping)):
                count = 1
            else:
                count = max(8, int(float(edge.length) / _SAMPLE))
            samples = [first + (last - first) * i / count for i in range(count + 1)]
            if edge.wrapped.Orientation() == TopAbs_REVERSED:
                samples.reverse()
            for parameter in samples[:-1]:
                p = curve.Value(parameter)
                points.append(mapping(Vector(p.X(), p.Y(), p.Z())))
        if len(points) >= 3:
            wires.append(Polyline(*[(x, y, 0.0) for x, y in points], close=True))
    if not wires:
        raise UnfoldError("굽힘 면의 경계를 변환하지 못했습니다.")
    outer = max(wires, key=lambda one: Face(one).area)
    holes = [one for one in wires if one is not outer]
    return Face(outer, holes)


def _coaxial(curve: BRepAdaptor_Curve, mapping: _CylMap) -> bool:
    circle = curve.Circle()
    axis = circle.Axis()
    direction = Vector(axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z())
    location = Vector(axis.Location().X(), axis.Location().Y(), axis.Location().Z())
    return (
        abs(abs(direction.dot(mapping.axis)) - 1) < 1e-6
        and (location - mapping.axis_point).cross(mapping.axis).length < 1e-6
    )


def _merged(pieces: list[Face]) -> Face:
    """편 면들을 한 장으로 — 이음매가 같은 선이라 합치면 한 면이 된다."""
    if len(pieces) == 1:
        return pieces[0]
    merged = pieces[0].fuse(*pieces[1:]).clean()
    faces = merged.faces()
    if len(faces) != 1:
        raise UnfoldError(
            f"전개한 조각들이 하나의 면으로 합쳐지지 않습니다(조각 {len(faces)}개). "
            "겉면이 끊어진 판입니다."
        )
    return faces[0]


def _merged_bends(bends: list[BendLine]) -> list[BendLine]:
    """같은 굽힘이 조각으로 잡힌 것(굽힘에 걸친 구멍이 굽힘 면을 쪼갠다)은 하나로 — 같은 선
    위에 있고 각 · 반지름 · 방향이 같으면 끝을 늘려 합친다."""
    out: list[BendLine] = []
    for one in bends:
        d = _unit2(one.end[0] - one.start[0], one.end[1] - one.start[1])
        for index, other in enumerate(out):
            same_kind = (
                abs(one.angle - other.angle) < 1e-6
                and abs(one.radius - other.radius) < 1e-6
                and one.direction == other.direction
            )
            od = _unit2(other.end[0] - other.start[0], other.end[1] - other.start[1])
            parallel = abs(abs(d[0] * od[0] + d[1] * od[1]) - 1) < 1e-9
            gap = (other.start[0] - one.start[0], other.start[1] - one.start[1])
            on_line = abs(gap[0] * d[1] - gap[1] * d[0]) < 1e-6
            if same_kind and parallel and on_line:
                ends = [one.start, one.end, other.start, other.end]
                ends.sort(key=lambda p: p[0] * od[0] + p[1] * od[1])
                out[index] = BendLine(
                    ends[0],
                    ends[-1],
                    other.angle,
                    other.radius,
                    other.direction,
                    other.allowance,
                )
                break
        else:
            out.append(one)
    return out


def _laid_flat(face: Face, bends: list[BendLine]) -> tuple[Face, list[BendLine]]:
    """전개도를 반듯하게 눕힌다 — 가장 긴 직선 엣지를 X 로, 경계상자의 왼쪽 아래를 원점으로.
    굽힘선도 같이 옮긴다."""
    lines = [one for one in face.edges() if _straight(one)]
    angle = 0.0
    if lines:
        longest = max(lines, key=lambda one: float(one.length))
        d = longest.end_point() - longest.start_point()
        angle = math.atan2(d.Y, d.X)
    c, s = math.cos(-angle), math.sin(-angle)

    def turn(p: tuple[float, float]) -> tuple[float, float]:
        return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)

    trsf = gp_Trsf()
    trsf.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), -angle)
    turned = Face(TopoDS.Face_s(BRepBuilderAPI_Transform(face.wrapped, trsf, True).Shape()))
    box = turned.bounding_box()
    shift = gp_Trsf()
    shift.SetTranslation(gp_Vec(-box.min.X, -box.min.Y, -box.min.Z))
    placed = Face(TopoDS.Face_s(BRepBuilderAPI_Transform(turned.wrapped, shift, True).Shape()))

    def move(p: tuple[float, float]) -> tuple[float, float]:
        q = turn(p)
        return (q[0] - box.min.X, q[1] - box.min.Y)

    return placed, [
        BendLine(
            move(one.start), move(one.end), one.angle, one.radius, one.direction, one.allowance
        )
        for one in bends
    ]


__all__ = ["DEFAULT_K", "BendLine", "UnfoldError", "Unfolded", "unfold"]
