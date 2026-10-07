"""레시피 평가기 — 노드를 차례로 build123d 형상으로 만든다.

실패는 `RecipeError(node_id, message)` 로 — 어느 노드가 왜 실패했는지가 편집기와 AI 에 그대로
간다. OpenCascade 가 던지는 예외는 메시지가 사람에게 뜻이 없으므로("BRep_API: command not
done") 노드 종류에 맞는 말로 바꾼다.
"""

from __future__ import annotations

import contextlib
import copy
import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

from build123d import (
    Align,
    Axis,
    Box,
    Circle,
    Compound,
    Cone,
    Cylinder,
    Edge,
    Ellipse,
    Face,
    FilletPolyline,
    FontStyle,
    GeomType,
    Helix,
    Keep,
    Kind,
    Line,
    Location,
    Part,
    Plane,
    Polygon,
    Polyline,
    Pos,
    RadiusArc,
    Rectangle,
    RectangleRounded,
    RegularPolygon,
    Rot,
    Shape,
    Shell,
    Side,
    Sketch,
    SlotCenterToCenter,
    SlotOverall,
    Sphere,
    Spline,
    TangentArc,
    Text,
    ThreePointArc,
    Torus,
    Transition,
    Trapezoid,
    Triangle,
    Until,
    Vector,
    Wedge,
    Wire,
    chamfer,
    draft,
    extrude,
    fillet,
    import_step,
    loft,
    make_brake_formed,
    make_face,
    make_hull,
    mirror,
    offset,
    revolve,
    scale,
    section,
    split,
    sweep,
)
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

from app.core import fasteners
from app.core.recipe import blend, datums, defeature, deform, hardware, mates, surfaces
from app.core.recipe import schema as S
from app.core.recipe.bend import BendError, bend
from app.core.recipe.frame import FrameError, frame
from app.core.recipe.imprint import ImprintError, imprint
from app.core.recipe.unfold import UnfoldError, unfold

#: `import_step` 의 `file` 열쇠 → 실제 경로. 없으면 import_step 노드가 실패한다.
FileResolver = Callable[[str], Path]
#: `component` 의 `source` → 그 도면의 레시피(JSON). 조립이 쓴다 — 코어는 DB 를 모른다.
ComponentResolver = Callable[[str], dict[str, Any]]
#: 조립 안의 조립 안의 조립… 어딘가에서 멈춘다. 고리를 만들면 여기서 걸린다.
MAX_COMPONENT_DEPTH = 5


class RecipeError(ValueError):
    def __init__(self, node_id: str, message: str) -> None:
        super().__init__(f"{node_id}: {message}")
        self.node_id = node_id
        self.message = message


@dataclass
class NodeInfo:
    id: str
    op: str
    kind: str
    """sketch | part | compound"""
    bbox: tuple[tuple[float, float, float], tuple[float, float, float]] | None
    volume: float | None
    faces: int
    edges: int
    placement: dict[str, Any] | None = None
    """구성품(`component`)의 자리 — 회전 행렬 · 이동, 구속이 있으면 남은 움직임까지
    (`mates.placement`). 화면이 3D 에서 고른 점을 구성품의 좌표로 되돌린다."""


@dataclass
class Evaluation:
    shape: Shape
    """보통 Part(입체). `allow_sketch` 로 평가했을 때만 Sketch(면)일 수 있다 — `is_sketch`."""
    nodes: list[NodeInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)
    """레시피의 좌표계를 **이 평가의 치수로** 푼 것 — 원점 · X · Y · Z(`core/frames.py`)."""
    datums: list[dict[str, Any]] = field(default_factory=list)
    """기준축 · 기준면 — 미리보기가 3D 에 그린다(`datums.describe`)."""
    tags: dict[str, list[int]] = field(default_factory=dict)
    """`divide_face` 가 붙인 이름 → **그때의 면 번호들**.

    번호는 이 평가 안에서만 뜻이 있다(다음 설계점에서는 다른 번호다). 그래서 저장하지 않고
    **평가할 때마다 다시 찾는다** — 그것이 치수를 바꿔도 같은 자리를 가리키는 유일한 길이다."""

    @property
    def is_sketch(self) -> bool:
        return isinstance(self.shape, Sketch)

    def summary(self) -> dict[str, Any]:
        box = self.shape.bounding_box()
        return {
            "is_sketch": self.is_sketch,
            "bbox": {
                "min": _xyz(box.min),
                "max": _xyz(box.max),
                "size": _xyz(box.size),
            },
            "volume": 0.0 if self.is_sketch else round(float(self.shape.volume), 1),
            "surface_area": round(float(self.shape.area), 1),
            "solid_count": len(self.shape.solids()),
            "face_count": len(self.shape.faces()),
            "edge_count": len(self.shape.edges()),
            "nodes": [vars(one) for one in self.nodes],
            "warnings": list(self.warnings),
        }


def _turns(path: list[tuple[float, float]]) -> tuple[list[float], float]:
    """꺾이는 곳마다 도는 방향(외적, + 는 왼쪽)과 꺾은선 전체가 도는 방향(단위 방향의 외적 합 —
    `_sharp_sheet` 와 같은 식)."""
    directions = []
    for (x0, y0), (x1, y1) in itertools.pairwise(path):
        length = math.hypot(x1 - x0, y1 - y0) or 1.0
        directions.append(((x1 - x0) / length, (y1 - y0) / length))
    corners = [a[0] * b[1] - a[1] * b[0] for a, b in itertools.pairwise(directions)]
    return corners, sum(corners)


def _cylinder_radii(shape: Any) -> list[float]:
    radii = []
    for face in shape.faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() == GeomAbs_Cylinder:
            radii.append(round(float(surface.Cylinder().Radius()), 3))
    return sorted(radii)


def _bends_only(node: S.SheetMetalNode, points: list[Vector]) -> list[Vector]:
    """꺾이지 않는 점(한 줄 위의 가운데 점)을 뺀 꺾은선 — 굽힘이 아니다. 그대로 두면
    둥글리는 자리에서 터졌다(FilletPolyline 의 IndexError, 2026-10-04 점검). 제자리로
    되돌아가는 점(180°)은 판을 접어 겹치는 것이라 말한다."""
    kept = [points[0]]
    for before, here, after in zip(points, points[1:], points[2:], strict=False):
        ax, ay = here.X - before.X, here.Y - before.Y
        bx, by = after.X - here.X, after.Y - here.Y
        size = math.hypot(ax, ay) * math.hypot(bx, by)
        if size == 0:
            raise RecipeError(node.id, "꺾은선에 길이가 0인 구간이 있습니다.")
        if abs(ax * by - ay * bx) / size < 1e-9:
            if ax * bx + ay * by < 0:
                raise RecipeError(
                    node.id, "꺾은선이 제자리로 되돌아갑니다. 판이 겹쳐 접힐 수 없습니다."
                )
            continue
        kept.append(here)
    kept.append(points[-1])
    return kept


def inside_bends(node: S.SheetMetalNode) -> int:
    """두께가 **굽힘 안쪽**에 붙는 굽힘의 수 — 2026-10-04 고침 전에는 이 굽힘의 안쪽 반지름이
    r - t 였고 이제 r 이다(모양이 바뀐 자리). 반지름 0(각진 굽힘)은 바뀌지 않았다. 형상을 짓지
    않고 꺾은선만 본다 — 서버 화면의 「판금 굽힘 점검」 이 저장된 도면을 훑는다."""
    if node.bend_radius <= 0 or len(node.path) < 3:
        return 0
    try:
        points = _bends_only(node, [Vector(x, y, 0) for x, y in node.path])
    except RecipeError:
        return 0  # 짓지도 못하는 꺾은선 — 점검이 평가해서 실패로 말한다
    corners, net = _turns([(float(one.X), float(one.Y)) for one in points])
    on_left = (net > 0) == (node.side == "right")
    return sum(1 for turn in corners if (turn > 0) == on_left)


def _rounded_sheet(node: S.SheetMetalNode, plane: Plane, points: list[Vector]) -> Shape:
    """둥근 굽힘의 판 — `bend_radius` 는 어느 쪽이든 **안쪽** 반지름이다.

    두께가 붙는 쪽은 `_sharp_sheet` 와 같다: `left` 면 꺾은선이 도는 쪽의 바깥(꺾은선이 안쪽
    면), `right` 면 안쪽(꺾은선이 바깥 면). 두께가 굽힘 안쪽에 붙는 곳은 꺾은선을 r + t 로,
    바깥에 붙는 곳은 r 로 둥글린다 — 그래야 안쪽이 r 이다. 예전에는 늘 r 로 둥글려 안쪽이
    r - t 가 되었고, r = t 면 굽힘이 실패하고 r < t 면 두께가 틀린 판이 나왔다(2026-10-04).

    make_brake_formed(`offset_2d`)가 두께를 어느 쪽으로 붙일지는 **믿지 않는다** — 평면의
    원점 · 반지름에 따라 뒤집힌다(실측: YZ 원점 (10, 0, 0)). 그래서 양쪽을 다 지어 보고
    **굽힘 반지름이 바로 나온 쪽**(굽힘마다 안쪽 r · 바깥 r + t)을 고른다 — 반대쪽이면 반지름이
    r ± t 로 어긋나 갈린다."""
    path = [(float(one.X), float(one.Y)) for one in points]
    corners, net = _turns(path)
    radius, thickness = float(node.bend_radius), float(node.thickness)
    # 두께가 진행 방향의 **왼쪽**인가 — `right`(안쪽)면 전체가 도는 쪽, `left` 면 그 반대.
    on_left = (net > 0) == (node.side == "right")
    radii = [radius + thickness if (turn > 0) == on_left else radius for turn in corners]
    line = Wire((plane * FilletPolyline(*points, radius=radii)).edges())
    expected = sorted([radius] * len(corners) + [radius + thickness] * len(corners))
    for side in (Side.LEFT, Side.RIGHT):
        try:
            formed = make_brake_formed(
                thickness=thickness, station_widths=node.width, line=line, side=side
            )
        except Exception:
            continue
        if _cylinder_radii(formed) == [round(one, 3) for one in expected]:
            return formed
    raise RecipeError(
        node.id,
        "판을 굽히지 못했습니다. 굽힘 반지름을 줄이거나 꺾은선의 짧은 구간을 늘리십시오"
        "(굽힘 안쪽에 두께가 붙는 곳은 꺾은선이 반지름 + 두께로 돕니다).",
    )


def _sharp_sheet(node: S.SheetMetalNode, plane: Plane) -> Shape:
    """각진 굽힘의 판 — 꺾은선을 두께만큼 **맞대어**(마이터) 띄운 단면을 폭만큼 민다.

    두께가 붙는 쪽은 make_brake_formed 와 같다: `left` 면 꺾은선이 도는 쪽의 **바깥**
    (꺾은선이 안쪽 선), `right` 면 안쪽."""
    points = [(float(x), float(y)) for x, y in node.path]
    directions = []
    for (x0, y0), (x1, y1) in itertools.pairwise(points):
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 1e-9:
            raise RecipeError(node.id, "꺾은선에 길이가 0인 구간이 있습니다.")
        directions.append(((x1 - x0) / length, (y1 - y0) / length))
    turn = sum(a[0] * b[1] - a[1] * b[0] for a, b in itertools.pairwise(directions))
    # 왼쪽으로 돌면(반시계) 바깥은 오른쪽이다.
    outside = -1.0 if turn > 0 else 1.0
    sign = outside if node.side == "left" else -outside
    normals = [(-d[1] * sign, d[0] * sign) for d in directions]
    t = node.thickness
    offset = [(points[0][0] + t * normals[0][0], points[0][1] + t * normals[0][1])]
    for index in range(1, len(points) - 1):
        (ax, ay), (bx, by) = normals[index - 1], normals[index]
        (dx, dy), (ex, ey) = directions[index - 1], directions[index]
        px, py = points[index]
        # 두 띄운 선의 만나는 점 — 꺾이지 않은 곳(나란함)이면 그냥 띄운다.
        cross = dx * ey - dy * ex
        if abs(cross) < 1e-12:
            offset.append((px + t * ax, py + t * ay))
            continue
        qx, qy = px + t * ax, py + t * ay
        rx, ry = px + t * bx, py + t * by
        k = ((rx - qx) * ey - (ry - qy) * ex) / cross
        offset.append((qx + k * dx, qy + k * dy))
    offset.append((points[-1][0] + t * normals[-1][0], points[-1][1] + t * normals[-1][1]))
    outline = [*points, *reversed(offset)]
    profile = plane * Polygon(*outline, align=None)
    return extrude(profile, amount=node.width, dir=plane.z_dir)


def _xyz(vector: Any) -> tuple[float, float, float]:
    return (round(vector.X, 3), round(vector.Y, 3), round(vector.Z, 3))


_PLANES: dict[str, Plane] = {
    "XY": Plane.XY,
    "XZ": Plane.XZ,
    "YZ": Plane.YZ,
    "YX": Plane.YX,
    "ZX": Plane.ZX,
    "ZY": Plane.ZY,
}
_AXES = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}


def _plane(spec: S.PlaneSpec) -> Plane:
    if spec.normal is not None:
        if spec.x_dir is not None:
            return Plane(origin=spec.origin, x_dir=spec.x_dir, z_dir=spec.normal)
        return Plane(origin=spec.origin, z_dir=spec.normal)
    base = _PLANES[spec.name]
    return Plane(origin=spec.origin, x_dir=base.x_dir, z_dir=base.z_dir)


# --- 스케치 -------------------------------------------------------------------


#: 스키마의 자리 이름 → build123d 의 Align.
_ALIGN = {"min": Align.MIN, "center": Align.CENTER, "max": Align.MAX}


def _align(names: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(_ALIGN[name] for name in names)


def _shape2d(one: S.SketchShape) -> Sketch:
    if isinstance(one, S.Rect):
        face: Sketch = Rectangle(
            one.width, one.height, rotation=one.rotation, align=_align(one.align)
        )
    elif isinstance(one, S.CircleShape):
        face = Circle(one.radius, align=_align(one.align))
    elif isinstance(one, S.PolygonShape):
        face = Polygon(*one.points, rotation=one.rotation)
    elif isinstance(one, S.RegularPolygonShape):
        face = RegularPolygon(
            one.radius, one.sides, rotation=one.rotation, align=_align(one.align)
        )
    elif isinstance(one, S.PolylineShape):
        face = _polyline(one)
    elif isinstance(one, S.PathShape):
        face = _path(one)
    elif isinstance(one, S.RoundedRect):
        if one.radius >= min(one.width, one.height) / 2:
            raise ValueError("모서리 반지름은 너비와 높이의 절반보다 작아야 합니다.")
        face = RectangleRounded(
            one.width, one.height, one.radius, rotation=one.rotation, align=_align(one.align)
        )
    elif isinstance(one, S.TriangleShape):
        try:
            face = Triangle(
                a=one.a,
                b=one.b,
                c=one.c,
                A=one.A,
                B=one.B,
                C=one.C,
                rotation=one.rotation,
                align=_align(one.align),
            )
        except Exception as failure:
            raise ValueError(
                f"지정한 변과 각으로는 삼각형을 구성할 수 없습니다({failure})."
            ) from failure
    elif isinstance(one, S.TrapezoidShape):
        face = Trapezoid(
            one.width,
            one.height,
            one.left_angle,
            one.right_angle,
            rotation=one.rotation,
            align=_align(one.align),
        )
    elif isinstance(one, S.EllipseShape):
        face = Ellipse(
            one.x_radius, one.y_radius, rotation=one.rotation, align=_align(one.align)
        )
    elif isinstance(one, S.ConstrainedShape):
        face = _constrained(one)
    elif isinstance(one, S.TextShape):
        face = Text(
            one.text,
            one.size,
            font_style=FontStyle.BOLD if one.bold else FontStyle.REGULAR,
            rotation=one.rotation,
            align=_align(one.align),
        )
    else:
        face = (
            SlotCenterToCenter(one.length, one.width, rotation=one.rotation)
            if one.measure == "centers"
            else SlotOverall(
                one.length, one.width, rotation=one.rotation, align=_align(one.align)
            )
        )
    return Pos(one.at[0], one.at[1]) * face


def _centerline(start: S.XY, segments: list[S.Segment]) -> list[Any]:
    """점을 이은 엣지들 — 직선 · 반지름 호 · 접선 호 · 지나는 점 호. 겹치는 점은 건너뛴다."""
    edges: list[Any] = []
    cursor = Vector(start[0], start[1], 0)
    for index, segment in enumerate(segments):
        target = Vector(segment.to[0], segment.to[1], 0)
        if (target - cursor).length < 1e-6:
            continue
        if segment.tangent:
            if not edges:
                raise ValueError(
                    f"구간 {index + 1}: 접선 호는 이전 구간이 있어야 방향을 정할 수 있습니다."
                )
            edges.append(TangentArc(cursor, target, tangent=edges[-1] % 1))
        elif segment.radius is not None:
            span = (target - cursor).length
            if abs(segment.radius) < span / 2 - 1e-9:
                raise ValueError(
                    f"구간 {index + 1}: 반지름({abs(segment.radius)})이 두 점 사이 거리"
                    f"({round(span, 2)})의 절반보다 작습니다."
                )
            edges.append(RadiusArc(cursor, target, segment.radius))
        elif segment.via is not None:
            edges.append(
                ThreePointArc(cursor, Vector(segment.via[0], segment.via[1], 0), target)
            )
        else:
            edges.append(Line(cursor, target))
        cursor = target
    return edges


def _path(shape: S.PathShape) -> Sketch:
    """중심선을 폭의 절반만큼 양쪽으로 띄워 닫힌 면으로. 열린 와이어의 offset 은 양 끝이 둥근
    닫힌 곡선을 준다(실측) — make_face 로 면을 만든다."""
    edges = _centerline(shape.start, shape.segments)
    if not edges:
        raise ValueError("선의 길이가 0입니다.")
    kind = Kind.ARC if shape.corners == "round" else Kind.INTERSECTION
    outline = offset(Wire(edges), shape.width / 2, kind=kind)
    wires = outline.wires()
    if len(wires) != 1 or not wires[0].is_closed:
        raise ValueError("선이 자기 자신과 겹칩니다. 폭을 줄이거나 점을 수정하십시오.")
    face = make_face(wires[0])
    if not face.is_valid or face.area < 1e-6:
        raise ValueError("선에서 면을 생성하지 못했습니다.")
    sketch = Sketch(face.wrapped)
    if shape.rotation:
        sketch = sketch.rotate(Axis.Z, shape.rotation)
    return sketch


def _constrained(shape: S.ConstrainedShape) -> Sketch:
    """구속 윤곽 — 점을 풀어 직선 · 호로 잇는다."""
    from app.core.recipe.sketch_solver import solve

    solved = solve(shape).points
    edges: list[Edge] = []
    for segment in shape.segments:
        a = Vector(*solved[segment.start], 0)
        b = Vector(*solved[segment.end], 0)
        if segment.center is None:
            edges.append(Line(a, b))
            continue
        c = Vector(*solved[segment.center], 0)
        start = math.atan2(a.Y - c.Y, a.X - c.X)
        end = math.atan2(b.Y - c.Y, b.X - c.X)
        sweep = (
            (end - start) % (2 * math.pi) if segment.ccw else -((start - end) % (2 * math.pi))
        )
        if abs(sweep) < 1e-9:
            raise ValueError("호의 양 끝점이 같은 위치에 있습니다.")
        radius = (a - c).length
        middle = start + sweep / 2
        mid = Vector(c.X + radius * math.cos(middle), c.Y + radius * math.sin(middle), 0)
        edges.append(ThreePointArc(a, mid, b))
    face = Face(Wire(edges))
    if not face.is_valid or face.area < 1e-6:
        raise ValueError(
            "구속 윤곽이 자체 교차하거나 면적이 0입니다. 스케치한 위치를 확인하십시오."
        )
    sketch = Sketch(face.wrapped)
    return sketch.rotate(Axis.Z, shape.rotation) if shape.rotation else sketch


def _polyline(shape: S.PolylineShape) -> Sketch:
    """점을 이어 닫힌 윤곽으로. 구간에 `via` 가 있으면 그 점을 지나는 호."""
    if shape.corner_radius > 0:
        if any(segment.via is not None for segment in shape.segments):
            raise ValueError("모서리 라운드는 호(via)와 함께 사용할 수 없습니다.")
        points = [shape.start, *[segment.to for segment in shape.segments]]
        if points[-1] == points[0]:
            points = points[:-1]
        rounded = FilletPolyline(*points, radius=shape.corner_radius, close=True)
        face = make_face(rounded.wires()[0])
        if not face.is_valid or face.area < 1e-6:
            raise ValueError("모서리 반지름이 너무 큽니다. 반지름을 줄이십시오.")
        sketch = Sketch(face.wrapped)
        return sketch.rotate(Axis.Z, shape.rotation) if shape.rotation else sketch
    edges = _centerline(shape.start, shape.segments)
    cursor = edges[-1] @ 1 if edges else Vector(shape.start[0], shape.start[1], 0)
    start = Vector(shape.start[0], shape.start[1], 0)
    if (cursor - start).length > 1e-6:
        edges.append(Line(cursor, start))
    if len(edges) < 2:
        raise ValueError("윤곽이 닫히지 않습니다. 점이 2개 이상이어야 합니다.")
    face = Face(Wire(edges))
    if not face.is_valid or face.area < 1e-6:
        raise ValueError("윤곽이 자체 교차하거나 면적이 0입니다.")
    sketch = Sketch(face.wrapped)
    if shape.rotation:
        sketch = sketch.rotate(Axis.Z, shape.rotation)
    return sketch


def _sketch(node: S.SketchNode) -> Sketch:
    result: Sketch | None = None
    for index, one in enumerate(node.shapes):
        face = _shape2d(one)
        if one.mode == "cut":
            if result is None:
                raise RecipeError(
                    node.id,
                    f"shapes[{index}]: 뺄 대상이 없습니다. cut 도형이 처음에 있습니다.",
                )
            result = _as_sketch(result - face)
        else:
            result = face if result is None else _as_sketch(result + face)
    assert result is not None
    if not result.faces():
        raise RecipeError(
            node.id, "스케치에 남은 면이 없습니다. cut 도형이 모든 면을 제거했습니다."
        )
    if node.hull:
        result = make_hull(result.edges())
    return _plane(node.plane) * _offset2d(result, node.offset, node.id)


def _as_sketch(shape: Shape) -> Sketch:
    """불리언이 면을 **둘로 가르면** Sketch 가 아니라 Compound 를 돌려준다(실측 — 사각형을
    선으로 가를 때). 면들을 다시 스케치로 묶는다."""
    if isinstance(shape, Sketch):
        return shape
    return Sketch(children=[copy.copy(f) for f in shape.faces()])


def _offset2d(sketch: Sketch, amount: float, node_id: str) -> Sketch:
    """윤곽을 띄운다. 음수로 다 사라지면 오류."""
    if amount == 0:
        return sketch
    try:
        moved = offset(sketch, amount, kind=Kind.ARC)
    except Exception as failure:
        raise RecipeError(node_id, f"윤곽을 {amount}만큼 오프셋하지 못했습니다.") from failure
    if not moved.faces() or moved.area < 1e-6:
        raise RecipeError(node_id, f"윤곽을 {amount}만큼 오프셋한 결과 남는 면이 없습니다.")
    return moved


def _relocate_section(sketch: Sketch, origin: Vector, tangent: Vector) -> Sketch:
    """단면 스케치를 어디 그렸든 경로 시작점에, 경로 방향을 보게 옮긴다."""
    face = sketch.faces()[0]
    local = Plane(face.center(), z_dir=face.normal_at()).to_local_coords(sketch)
    return Plane(origin=origin, z_dir=tangent) * local


# --- 3D 노드 -------------------------------------------------------------------


def _as_part(shape: Shape, node_id: str) -> Part:
    if isinstance(shape, Part):
        return shape
    if isinstance(shape, Sketch):
        raise RecipeError(
            node_id,
            "이 피처에는 스케치를 사용할 수 없습니다. 먼저 돌출(extrude) 또는 "
            "회전(revolve)하십시오.",
        )
    return Part(shape.wrapped)


def _seam_edges(part: Part) -> list[Any]:
    """곡면(원기둥 · 원뿔 …)의 이음선 — 한 면에만 속한 엣지. 필렛하면 OCC 가 터진다.

    `vertical` 로 고르면 구멍의 이음선이 수직선이라 함께 잡힌다(실측 — AI 가 첫 시도에서
    걸렸다). 이름 있는 선택자는 **평면 사이의 진짜 모서리**만 뜻하게 한다."""
    seams: list[Any] = []
    for face in part.faces():
        if face.geom_type == GeomType.PLANE:
            continue
        seams.extend(face.edges())
    return seams


def _faces(part: Part, select: S.FaceSelect, node_id: str) -> list[Any]:
    faces = part.faces()
    if isinstance(select, S.SelectRule):
        return _ruled(part, select, "faces", node_id)
    if isinstance(select, S.EdgeNear):
        targets = [Vector(*point) for point in select.near]
        picked = [
            f
            for f in faces
            if any((f.center() - t).length <= select.tolerance for t in targets)
        ]
        if len(picked) < len(targets):
            raise RecipeError(node_id, "선택한 위치에 면이 없습니다. 형상이 변경되었습니다.")
        return picked
    if select == "none":
        return []
    if select == "all":
        return list(faces)
    if select == "sides":
        picked = [f for f in faces if abs(f.normal_at().Z) < 0.1]
        if not picked:
            raise RecipeError(node_id, "측면이 없습니다.")
        return picked
    ordered = faces.sort_by(Axis.Z)
    return [ordered[-1] if select == "top" else ordered[0]]


def _ruled(part: Part, rule: S.SelectRule, what: str, node_id: str) -> list[Any]:
    """규칙(`recipe_find` 의 질의)에 맞는 엣지 · 면 — 설계점마다 다시 찾는다."""
    from app.core.recipe.query import select_features

    query = {**rule.query, "what": what}
    rows = select_features(part, query)["items"]
    if not rows:
        raise RecipeError(
            node_id,
            f"규칙에 맞는 {'엣지가' if what == 'edges' else '면이'} 없습니다({rule.query}).",
        )
    every = part.edges() if what == "edges" else part.faces()
    return [every[row["index"]] for row in rows]


def _edges(part: Part, select: S.EdgeSelect, node_id: str) -> Any:
    edges = part.edges()
    if isinstance(select, S.SelectRule):
        return _ruled(part, select, "edges", node_id)
    if isinstance(select, S.EdgeNear):
        targets = [Vector(*point) for point in select.near]
        edges = [
            e
            for e in edges
            if any((e.position_at(0.5) - t).length <= select.tolerance for t in targets)
        ]
        if len(edges) < len(targets):
            raise RecipeError(
                node_id,
                f"선택한 위치 {len(targets)}곳 중 {len(edges)}곳에서만 엣지를 찾았습니다. "
                "형상이 변경되어 해당 위치에 엣지가 없습니다.",
            )
    elif select in ("vertical", "horizontal"):
        seams = _seam_edges(part)
        straight = [e for e in edges if e.geom_type == GeomType.LINE]
        picked = (
            [e for e in straight if abs(e.tangent_at(0.5).Z) > 1 - 1e-6]
            if select == "vertical"
            else [e for e in straight if abs(e.tangent_at(0.5).Z) < 1e-6]
        )
        edges = [e for e in picked if not any(e.is_same(seam) for seam in seams)]
    elif select == "top":
        edges = part.faces().sort_by(Axis.Z)[-1].edges()
    elif select == "bottom":
        edges = part.faces().sort_by(Axis.Z)[0].edges()
    if not edges:
        raise RecipeError(node_id, f"선택한 엣지가 없습니다(edges={select}).")
    return edges


def _copies(source: Shape, node: S.PatternNode, made: dict[str, Any]) -> list[Shape]:
    out: list[Shape] = []
    if node.kind == "linear":
        dx, dy, dz = node.spacing
        for k in range(node.count):
            out.append(source.moved(Location((dx * k, dy * k, dz * k))))
    elif node.kind == "grid":
        dx, dy, dz = node.spacing
        ex, ey, ez = node.spacing_y
        for i in range(node.count):
            for j in range(node.count_y):
                out.append(
                    source.moved(Location((dx * i + ex * j, dy * i + ey * j, dz * i + ez * j)))
                )
    else:
        step = node.angle / (node.count if node.angle >= 360 else node.count - 1)
        axis = datums.axis(node.axis, made)
        for k in range(node.count):
            out.append(source.rotate(axis, step * k))
    return out


def _bolt(node: S.BoltNode) -> Part:
    """머리 · 와셔 · 몸통 — 지그 생성기의 볼트와 같은 표(`fasteners`). `at` 은 머리가 앉는
    면."""
    d = node.nominal
    x, y, seat = node.at
    sign = -1.0 if node.down else 1.0
    washer_d, washer_t = fasteners.washer(d) if node.washer else (0.0, 0.0)
    head_w, head_h, key = fasteners.head(d, node.head)
    shank_len = node.length
    shank: Part = Pos(x, y, seat + sign * shank_len / 2) * Cylinder(d / 2, shank_len)
    parts: list[Part] = [shank]
    if node.washer:
        parts.append(Pos(x, y, seat - sign * washer_t / 2) * Cylinder(washer_d / 2, washer_t))
    z_head = seat - sign * washer_t
    if node.head == "socket":
        head: Part = Pos(x, y, z_head - sign * head_h / 2) * Cylinder(head_w / 2, head_h)
        # 육각 구멍 — 머리 높이의 절반 깊이(ISO 4762 의 렌치 물림 깊이에 가깝다).
        head = head - Pos(x, y, z_head - sign * head_h) * extrude(
            RegularPolygon(key / 3**0.5, 6), head_h / 2, both=True
        )
    else:
        head = Pos(x, y, z_head - sign * head_h / 2) * extrude(
            RegularPolygon(head_w / 3**0.5, 6), head_h / 2, both=True
        )
    bolt = parts[0]
    for one in [*parts[1:], head]:
        bolt = bolt + one
    return bolt


def _to_part(shape: Shape) -> Part:
    """Compound(복사본 묶음) · Solid(STEP 하나) 를 Part 로 — 불리언은 Part 끼리 한다.

    `Part(solid.wrapped)` 는 부피가 0 으로 나온다(Part 는 Compound 를 감싼다고 전제) — 실측.
    솔리드들을 자식으로 다시 묶는다."""
    if isinstance(shape, Part):
        return shape
    labeled = _labeled_children(shape)
    if labeled:
        # 조립(group) — 구성품을 통째로 자식으로 두어 이름표가 메시까지 간다.
        children = []
        for one in labeled:
            child = copy.copy(one)
            child.label = one.label
            children.append(child)
        return Part(children=children)
    solids = list(shape.solids())
    if solids:
        return Part(children=[copy.copy(one) for one in solids])
    return Part(shape.wrapped)


def _labeled_children(shape: Shape) -> list[Shape]:
    """group 이 이름표를 붙인 자식들 — 모두 붙어 있을 때만. 아니면 빈 목록."""
    children = list(getattr(shape, "children", ()) or ())
    if children and all(getattr(child, "label", "") for child in children):
        return children
    return []


def _cleaned(part: Part) -> Part:
    """불리언 뒤에 정리한다. **면이 정확히 포개진 두 덩어리**(거울 · 대칭 회전체)를 합치면
    OCC 가 안쪽이 뒤집힌 솔리드를 내놓는데(부피가 음수) `clean()` 이 그것을 바로잡는다 —
    실측."""
    try:
        return part.clean()
    except Exception:
        return part


def _hole_dimensions(node: S.HoleNode) -> tuple[float, float | None, float | None]:
    """(구멍 지름, 카운터 지름, 카운터보어 깊이) — thread 표와 직접 준 값을 합친다."""
    table = fasteners.THREADS.get(node.thread or "")
    if table:
        tap_drill, clearance, cbore_d, cbore_depth, csink_d = table
        diameter = node.diameter or (tap_drill if node.kind == "tap" else clearance)
        counter = node.counter_diameter or (csink_d if node.kind == "countersink" else cbore_d)
        depth = node.counter_depth or cbore_depth
        return diameter, counter, depth
    assert node.diameter is not None
    return node.diameter, node.counter_diameter, node.counter_depth


def _hole(part: Part, node: S.HoleNode) -> Part:
    """구멍 도구를 **평면 좌표**에서 만들어 옮긴다: 평면 원점이 표면, -Z 가 안쪽."""
    box = part.bounding_box()
    diameter, counter_d, counter_depth = _hole_dimensions(node)
    radius = diameter / 2
    reach = box.size.length * 2 + 2  # 관통이면 이만큼
    depth = node.depth if node.depth is not None else reach
    if node.plane is not None:
        plane = _plane(node.plane)
    else:
        plane = Plane(origin=(0, 0, box.max.Z), z_dir=(0, 0, 1))

    result = part
    for x, y in node.at:
        # 표면 위로 조금 올려 시작한다(1mm) — 표면과 정확히 포개지면 불리언이 흔들린다.
        tool: Part = Pos(x, y, -depth / 2 + 1) * Cylinder(radius, depth + 2)
        if node.kind == "counterbore" and counter_d and counter_depth:
            tool = tool + Pos(x, y, -counter_depth / 2 + 1) * Cylinder(
                counter_d / 2, counter_depth + 2
            )
        elif node.kind == "countersink" and counter_d:
            half_angle = math.radians(node.countersink_angle / 2)
            sink_depth = (counter_d / 2 - radius) / math.tan(half_angle)
            # Cone(bottom, top, height) 은 중심이 원점 — 밑(큰 쪽)이 표면에 오게 뒤집어 놓는다.
            cone = (
                Pos(x, y, -sink_depth / 2)
                * Rot(180, 0, 0)
                * Cone(counter_d / 2, radius, sink_depth)
            )
            cap = Pos(x, y, 1) * Cylinder(counter_d / 2, 2)
            tool = tool + cone + cap
        result = result - (plane * tool)
    return result


#: 패치의 평면에서 이만큼 떨어진 면은 그 패치가 아니다(mm) — `at` 은 소수 셋째 자리까지다.
_PATCH_PLANE_TOL = 1e-2


def _tagged_faces(part: Part, patches: dict[str, dict[str, Any]]) -> dict[str, list[int]]:
    """패치가 있던 자리에서 **지금의 면 번호**를 되찾는다.

    나눈 뒤에 필렛 · 패턴이 그 조각을 또 갈라 놓을 수 있으므로 「나눌 때 본 면」 하나를
    기억해 두면 틀린다. 패치 안에 들어가고 **같은 평면 위에서** 법선이 같은 면을 **모두**
    모은다.
    """
    if not patches:
        return {}
    rows = [(index, face) for index, face in enumerate(part.faces())]
    out: dict[str, list[int]] = {}
    for tag, patch in patches.items():
        at = Vector(*patch["at"])
        normal = Vector(*patch["normal"])
        region = patch.get("region")
        found = []
        for index, face in rows:
            if region is not None and face.geom_type != GeomType.PLANE:
                # 곡면 패치(새기기 — 볼트 몸통과 너트 구멍처럼 원통끼리 닿는 자리) — 법선이
                # 곳곳에서 달라 한 법선으로 못 가린다. 영역의 면과 **같은 쪽을 보는지**로 본다:
                # 맞닿은 두 바디의 면은 모양이 같고 방향만 반대다.
                if not _same_side(face, region):
                    continue
            elif (
                face.geom_type != GeomType.PLANE
                or face.normal_at(face.center()).dot(normal) < 0.95
            ):
                continue
            if region is None and abs((face.center() - at).dot(normal)) > _PATCH_PLANE_TOL:
                # **같은 평면 위여야 한다.** 경계상자만 보면 평행하게 떨어진 면도 든다 — 실측
                # (2026-10-03, 전단 이음 픽스처): 위판 윗면의 클램프 패치(z 10)와 아래판 윗면의
                # 새긴 자리(z 5)가 둘 다 잡혀 클램프 압력이 이음 속에도 걸릴 뻔했다. 스케치 ·
                # 새김 패치는 `region` 과 겹친 넓이가 거른다.
                continue
            # **중심만으로는 안 된다**(실측): 원 패치를 뚫으면 남은 고리 모양 면의 무게중심도
            # 패치 중심과 같은 자리에 온다. 경계상자가 패치 안에 들어가는지로 가린다 — 조각이
            # 더 갈렸어도 그 조각들은 모두 안에 들어간다.
            box = face.bounding_box()
            half = patch["extent"] + 1e-6
            inside = all(
                abs(low - middle) <= half and abs(high - middle) <= half
                for low, high, middle in (
                    (box.min.X, box.max.X, at.X),
                    (box.min.Y, box.max.Y, at.Y),
                    (box.min.Z, box.max.Z, at.Z),
                )
            )
            if inside and _within(face, patch.get("region")):
                found.append(index)
        out[tag] = found
    return out


def _same_side(face: Any, region: list[Any]) -> bool:
    """곡면이 영역의 면과 같은 방향을 보나 — 면 위의 한 점에서 두 법선을 견준다."""
    point = face.position_at(0.5, 0.5)
    mine = face.normal_at(point)
    for one in region:
        if one.geom_type != face.geom_type:
            continue
        with contextlib.suppress(Exception):
            if (one.distance_to(point) < 1e-4) and one.normal_at(point).dot(mine) > 0.9:
                return True
    return False


def _within(face: Any, region: list[Any] | None) -> bool:
    """그 면이 패치 안에 드나 — 스케치 패치는 모양이 제멋대로라 경계상자로는 모자란다(고리
    모양 패치의 가운데 섬도 경계상자 안에 든다). 겹친 넓이가 면 넓이와 같으면 안이다."""
    if not region:
        return True
    overlap = 0.0
    for one in region:
        with contextlib.suppress(Exception):
            overlap += float((face & one).area)
    return overlap >= face.area * 0.99


def _same_volume(one: Part, other: Part) -> bool:
    """면을 나눠도 부피는 그대로여야 한다 — 다만 **상대 오차로** 본다. 핀 · 블록을 합친
    428 만 mm³ 판의 윗면을 나누면 부피가 0.000024 mm³ 달라진다(적분 영역이 바뀌는 수치
    잡음, 실측 2026-10-02). 절대값 1e-6 으로 보던 때는 큰 부품의 면을 나눌 수 없었다."""
    return abs(one.volume - other.volume) <= max(1e-6, abs(other.volume) * 1e-9)


def _face_under_sketch(part: Part, drawn: Any, node_id: str) -> Any:
    """스케치와 같은 평면에 있고 스케치와 가장 넓게 겹치는 평면."""
    if not isinstance(drawn, Sketch) or not drawn.faces():
        raise RecipeError(node_id, "sketch: 스케치를 선택하십시오.")
    first = drawn.faces()[0]
    normal, point = first.normal_at(), first.center()
    best, best_overlap = None, 0.0
    for face in part.faces():
        if face.geom_type != GeomType.PLANE:
            continue
        if abs(abs(face.normal_at().dot(normal)) - 1) > 1e-6:
            continue
        if abs((face.center() - point).dot(normal)) > 1e-4:
            continue
        overlap = 0.0
        for one in drawn.faces():
            with contextlib.suppress(Exception):
                overlap += float((face & one).area)
        if overlap > best_overlap:
            best, best_overlap = face, overlap
    if best is None:
        raise RecipeError(
            node_id,
            "스케치가 놓인 면이 없습니다. 면 위에 스케치하거나(3D 뷰에서 면 클릭) on으로 "
            "면을 선택하십시오.",
        )
    return best


def _divide_by_sketch(
    part: Part, face: Any, plane: Plane, node: S.DivideFaceNode, made: dict[str, Any]
) -> tuple[Part, dict[str, Any]]:
    """스케치의 윤곽을 그 면에 비춰 나눈다 — 도형이 여럿이면 패치도 여럿(한 태그), 구멍
    뚫린 도형이면 고리. 패치는 원 · 사각과 달리 모양이 제멋대로라, 태그로 되찾을 때
    경계상자가 아니라 **패치 안에 드는가**로 가린다(`region`)."""
    from OCP.BRepFeat import BRepFeat_SplitShape
    from OCP.TopoDS import TopoDS

    assert node.sketch is not None
    drawn = made[node.sketch]
    if not isinstance(drawn, Sketch):
        raise RecipeError(node.id, f"‘{node.sketch}’은(는) 스케치가 아닙니다.")
    region = []
    for one in drawn.faces():
        if abs(abs(one.normal_at().dot(plane.z_dir)) - 1) > 1e-6:
            raise RecipeError(
                node.id,
                "스케치 평면이 분할할 면과 평행해야 합니다. 해당 면 위에 작성한 스케치를 "
                "사용하십시오.",
            )
        local = plane.to_local_coords(one)
        region.append(plane * (Pos(0, 0, -local.center().Z) * local))
    splitter = BRepFeat_SplitShape(part.wrapped)
    for one in region:
        for wire in [one.outer_wire(), *one.inner_wires()]:
            splitter.Add(TopoDS.Wire_s(wire.wrapped), TopoDS.Face_s(face.wrapped))
    splitter.Build()
    divided = Part(splitter.Shape())
    if not divided.is_valid or not _same_volume(divided, part):
        raise RecipeError(
            node.id,
            "면을 분할하는 중 형상이 변경되었습니다. 스케치가 면 밖으로 벗어나지 "
            "않았는지 확인하십시오.",
        )
    box = Compound(children=[copy.copy(one) for one in region]).bounding_box()
    at = (box.min + box.max) * 0.5
    return divided, {
        "at": [round(float(v), 3) for v in (at.X, at.Y, at.Z)],
        "normal": [round(float(v), 3) for v in plane.z_dir],
        "extent": round(float(max(box.size.X, box.size.Y, box.size.Z)) / 2, 3),
        "region": region,
    }


def _divide_face(
    part: Part, node: S.DivideFaceNode, made: dict[str, Any]
) -> tuple[Part, dict[str, Any]]:
    """면 하나를 패치와 나머지로 나눈다. 형상은 그대로다 — **부피가 변하지 않는다.**

    OCC 의 `BRepFeat_SplitShape` 는 「이 면 위에 이 선을 그어 나눠라」 를 그대로 하는 도구다
    (실측: 상자 윗면에 Ø16 원 → 면 6 → 7, 부피 보존). 불리언으로 흉내 내면 얇은 판이 생기거나
    부피가 미세하게 달라진다.

    돌려주는 둘째 값은 **패치가 어디인가**(중심 · 법선 · 크기)다. 태그는 면 번호로 저장할 수
    없다 — 뒤의 필렛 하나가 번호를 통째로 밀기 때문이다. 대신 이 자리로 **다시 찾는다.**
    """
    from OCP.BRepFeat import BRepFeat_SplitShape
    from OCP.TopoDS import TopoDS

    from app.core.recipe.query import find_features

    if node.shape == "sketch" and "on" not in node.model_fields_set:
        # 나눌 면을 안 골랐으면 **스케치가 놓인 면** — 면 위에 그린 스케치가 곧 그 면을 말한다.
        face = _face_under_sketch(part, made[node.sketch or ""], node.id)
    else:
        query = {"what": "faces", **dict(node.on)}
        if node.at is not None and "near" not in query:
            query["near"] = list(node.at)
        rows = find_features(part, query)["items"]
        if not rows:
            raise RecipeError(node.id, f"분할할 면을 찾지 못했습니다(on: {node.on}).")
        face = part.faces()[rows[0]["index"]]
    if face.geom_type != GeomType.PLANE:
        raise RecipeError(
            node.id, "평면만 분할할 수 있습니다. 곡면 분할은 아직 지원하지 않습니다."
        )

    plane = Plane(face)
    if node.shape == "sketch":
        return _divide_by_sketch(part, face, plane, node, made)
    center = Vector(*node.at) if node.at is not None else face.center()
    # 면 위로 투영한 자리 — 사람이 찍은 점이 면에서 조금 떠 있어도 패치는 면 위에 놓인다.
    local = plane.to_local_coords(center)
    if node.shape == "circle":
        if not node.radius:
            raise RecipeError(node.id, "circle에는 radius가 필요합니다.")
        patch = plane * Pos(local.X, local.Y) * Circle(node.radius)
        extent = float(node.radius)
    else:
        if not node.size:
            raise RecipeError(node.id, "rect에는 size([가로, 세로])가 필요합니다.")
        patch = plane * Pos(local.X, local.Y) * Rectangle(node.size[0], node.size[1])
        extent = float(max(node.size)) / 2

    splitter = BRepFeat_SplitShape(part.wrapped)
    splitter.Add(TopoDS.Wire_s(patch.wire().wrapped), TopoDS.Face_s(face.wrapped))
    splitter.Build()
    divided = Part(splitter.Shape())
    if not divided.is_valid or not _same_volume(divided, part):
        raise RecipeError(
            node.id,
            "면을 분할하는 중 형상이 변경되었습니다. 패치가 면 밖으로 벗어나지 "
            "않았는지 확인하십시오.",
        )

    at = plane.from_local_coords(Vector(local.X, local.Y, 0))
    return divided, {
        "at": [round(float(v), 3) for v in (at.X, at.Y, at.Z)],
        "normal": [round(float(v), 3) for v in plane.z_dir],
        "extent": round(extent, 3),
    }


def _evaluate_node(
    node: S.Node,
    made: dict[str, Any],
    resolve_file: FileResolver | None,
    resolve_component: ComponentResolver | None = None,
    depth: int = 0,
    patches: dict[str, dict[str, Any]] | None = None,
    notes: list[str] | None = None,
    placements: dict[str, dict[str, Any]] | None = None,
) -> Shape:
    patches = patches if patches is not None else {}
    notes = notes if notes is not None else []
    placements = placements if placements is not None else {}
    # 평면 칸이 기준면을 가리키면 그 원점 · 법선으로 — 아래 가지들은 기준을 몰라도 된다.
    node = datums.with_datums(node, made)
    if isinstance(node, S.DatumAxisNode):
        return datums.make_axis(node, made)
    if isinstance(node, S.DatumPlaneNode):
        return datums.make_plane(node, made, _plane)
    if isinstance(node, S.SketchNode):
        return _sketch(node)
    if isinstance(node, S.ExtrudeNode):
        sketch = made[node.sketch]
        if not isinstance(sketch, Sketch):
            raise RecipeError(node.id, f"‘{node.sketch}’은(는) 스케치가 아닙니다.")
        if node.until != "distance":
            assert node.target is not None
            normal = sketch.faces()[0].normal_at()
            direction = normal if node.direction == "normal" else -normal
            until = Until.NEXT if node.until == "next" else Until.LAST
            try:
                return extrude(
                    sketch,
                    until=until,
                    target=_as_part(made[node.target], node.id),
                    dir=direction,
                )
            except Exception as failure:
                raise RecipeError(
                    node.id,
                    "해당 방향에 도달할 면이 없습니다. "
                    "스케치가 대상 바깥에서 대상을 향해야 합니다.",
                ) from failure
        if node.direction == "both":
            return extrude(sketch, node.distance / 2, both=True, taper=node.taper)
        amount = node.distance if node.direction == "normal" else -node.distance
        return extrude(sketch, amount, taper=node.taper)
    if isinstance(node, S.SheetMetalNode):
        points = [Vector(x, y, 0) for x, y in node.path]
        plane = _plane(node.plane)
        if node.bend_radius > 0 and len(points) > 2:
            points = _bends_only(node, points)
        if node.bend_radius > 0 and len(points) > 2:
            formed = _rounded_sheet(node, plane, points)
        else:
            # **각진 굽힘은 우리가 세운다** — make_brake_formed 는 모서리를 비스듬히 잘라
            # 두께가 한결같지 않은 판을 낸다(실측: t=2 ㄱ자의 부피가 5760 이 아니라 4080).
            formed = _sharp_sheet(node, plane)
        # 판은 평면의 한쪽으로만 자라고, 그 쪽은 꺾은선이 도는 방향에 따라 바뀐다(실측) —
        # 재어서 꺾은선이 **폭의 가운데**에 오게 되돌린다. 그래야 구멍 자리를 평면 좌표 그대로
        # 주고 좌우 대칭도 그대로다.
        box = formed.bounding_box()
        middle = ((box.min + box.max) * 0.5 - plane.origin).dot(plane.z_dir)
        return _to_part(formed.moved(Location((plane.z_dir * -middle).to_tuple())))
    if isinstance(node, S.BendNode):
        try:
            return bend(_as_part(made[node.target], node.id), node)
        except BendError as failure:
            raise RecipeError(node.id, str(failure)) from failure
    if isinstance(node, S.DeformNode):
        return _deformed(node, made)
    if isinstance(node, S.UnfoldNode):
        try:
            flat = unfold(
                _as_part(made[node.target], node.id), k_factor=node.k_factor, flip=node.flip
            )
        except UnfoldError as failure:
            raise RecipeError(node.id, str(failure)) from failure
        notes.extend(f"{node.id}: {one}" for one in flat.notes)
        return flat.solid
    if isinstance(node, S.FrameNode):
        try:
            return frame(node)
        except FrameError as failure:
            raise RecipeError(node.id, str(failure)) from failure
    if isinstance(node, S.HelixNode):
        sketch = made[node.sketch]
        if not isinstance(sketch, Sketch):
            raise RecipeError(node.id, f"‘{node.sketch}’은(는) 스케치가 아닙니다.")
        rot = {"Z": Rot(0, 0, 0), "X": Rot(0, 90, 0), "Y": Rot(-90, 0, 0)}[node.axis]
        path = (
            Pos(*node.at)
            * rot
            * Helix(
                pitch=node.pitch,
                height=node.height,
                radius=node.radius,
                lefthand=node.lefthand,
            )
        )
        placed = _relocate_section(sketch, path.position_at(0), path.tangent_at(0))
        try:
            return sweep(placed, path, is_frenet=True)
        except Exception as failure:
            raise RecipeError(
                node.id,
                "나선을 따라 스윕하지 못했습니다. 단면이 겹치지 않으려면 피치보다 "
                "작아야 합니다.",
            ) from failure
    if isinstance(node, S.SweepNode):
        sketch = made[node.sketch]
        if not isinstance(sketch, Sketch):
            raise RecipeError(node.id, f"‘{node.sketch}’은(는) 스케치가 아닙니다.")
        points = [Vector(*p) for p in node.path]
        if any((b - a).length < 1e-6 for a, b in pairwise(points)):
            raise RecipeError(node.id, "경로에 같은 점이 연속으로 있습니다.")
        path = Wire(Spline(*points)) if node.smooth else Wire(Polyline(*points))
        try:
            return sweep(sketch, path, transition=Transition.ROUND)
        except Exception as failure:
            raise RecipeError(
                node.id,
                "경로를 따라 스윕하지 못했습니다. 단면이 경로 시작점에 있는지, 경로의 "
                "꺾임이 단면 크기에 비해 급하지 않은지 확인하십시오.",
            ) from failure
    if isinstance(node, S.RevolveNode):
        sketch = made[node.sketch]
        if not isinstance(sketch, Sketch):
            raise RecipeError(node.id, f"‘{node.sketch}’은(는) 스케치가 아닙니다.")
        return revolve(sketch, datums.axis(node.axis, made), node.angle)
    if isinstance(node, S.BoxNode):
        return Pos(*node.at) * Box(
            node.length, node.width, node.height, align=_align(node.align)
        )
    if isinstance(node, S.CylinderNode):
        rot = {"Z": Rot(0, 0, 0), "X": Rot(0, 90, 0), "Y": Rot(90, 0, 0)}[node.axis]
        return (
            Pos(*node.at) * rot * Cylinder(node.radius, node.height, align=_align(node.align))
        )
    if isinstance(node, S.UnionNode):
        parts = [_to_part(made[t]) for t in node.targets]
        result = parts[0]
        for other in parts[1:]:
            result = result + other
        return _cleaned(result)
    if isinstance(node, S.CutNode):
        result = _to_part(made[node.target])
        for tool in node.tools:
            result = result - _to_part(made[tool])
        if not result.solids():
            raise RecipeError(node.id, "잘라 낸 결과 남는 형상이 없습니다.")
        return _cleaned(result)
    if isinstance(node, S.IntersectNode):
        parts = [_to_part(made[t]) for t in node.targets]
        result = parts[0]
        for other in parts[1:]:
            result = result & other
        if not result.solids():
            raise RecipeError(node.id, "겹치는 부분이 없습니다.")
        return _cleaned(result)
    if isinstance(node, S.FilletNode):
        part = _as_part(made[node.target], node.id)
        edges = _edges(part, node.edges, node.id)  # RecipeError 는 ValueError 라 try 밖에서
        if node.radius_end is not None:
            start = Vector(*node.start) if node.start is not None else None
            try:
                return blend.fillet(part, edges, node.radius, node.radius_end, start)
            except blend.BlendError as failure:
                raise RecipeError(node.id, str(failure)) from failure
        try:
            return fillet(edges, node.radius)
        except ValueError as failure:
            raise RecipeError(
                node.id,
                f"반지름 {node.radius}의 필렛을 생성하지 못했습니다. 반지름을 인접한 "
                "면보다 작게 줄이거나 edges의 선택 범위를 줄이십시오.",
            ) from failure
    if isinstance(node, S.ChamferNode):
        part = _as_part(made[node.target], node.id)
        edges = _edges(part, node.edges, node.id)
        if node.length2 is not None or node.angle is not None or node.reference is not None:
            reference = (
                _faces(part, node.reference, node.id) if node.reference is not None else None
            )
            try:
                return blend.chamfer(
                    part,
                    edges,
                    node.length,
                    length2=node.length2,
                    angle=node.angle,
                    reference=reference,
                )
            except blend.BlendError as failure:
                raise RecipeError(node.id, str(failure)) from failure
        try:
            return chamfer(edges, node.length)
        except ValueError as failure:
            raise RecipeError(
                node.id, f"길이 {node.length}의 챔퍼를 생성하지 못했습니다. 길이를 줄이십시오."
            ) from failure
    if isinstance(node, S.HoleNode):
        return _hole(_as_part(made[node.target], node.id), node)
    if isinstance(node, S.DivideFaceNode):
        # 패치가 어디인지는 여기서 안다. 태그로 되찾는 일은 평가가 끝난 뒤에 한다 —
        # 뒤의 노드(필렛 · 패턴)가 면을 또 갈라 놓을 수 있기 때문이다.
        divided, patch = _divide_face(_as_part(made[node.target], node.id), node, made)
        patches[node.tag] = patch
        return divided
    if isinstance(node, S.ShellNode):
        part = _as_part(made[node.target], node.id)
        openings = _faces(part, node.open, node.id)
        try:
            if not openings:
                # 뚫는 면이 없으면 offset 은 **안쪽 덩어리**를 돌려준다(실측) — 빼서 껍질을
                # 만든다.
                return _cleaned(part - offset(part, -node.thickness))
            return offset(part, -node.thickness, openings=openings)
        except Exception as failure:
            raise RecipeError(
                node.id,
                f"두께 {node.thickness}의 쉘을 생성하지 못했습니다. 두께를 줄이십시오.",
            ) from failure
    if isinstance(node, S.LoftNode):
        sections = []
        for name in node.sketches:
            piece = made[name]
            if not isinstance(piece, Sketch):
                raise RecipeError(node.id, f"‘{name}’은(는) 스케치가 아닙니다.")
            sections.append(piece)
        return loft(sections, ruled=node.ruled)
    if isinstance(node, S.SphereNode):
        return Pos(*node.at) * Sphere(node.radius, align=_align(node.align))
    if isinstance(node, S.ConeNode):
        rot = {"Z": Rot(0, 0, 0), "X": Rot(0, 90, 0), "Y": Rot(-90, 0, 0)}[node.axis]
        cone = Cone(
            node.bottom_radius,
            node.top_radius,
            node.height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        return Pos(*node.at) * rot * cone
    if isinstance(node, S.TorusNode):
        rot = {"Z": Rot(0, 0, 0), "X": Rot(0, 90, 0), "Y": Rot(90, 0, 0)}[node.axis]
        return Pos(*node.at) * rot * Torus(node.major_radius, node.minor_radius)
    if isinstance(node, S.PatternNode):
        copies = _copies(made[node.source], node, made)
        if isinstance(copies[0], Sketch):
            return Sketch(children=copies)
        return Compound(children=copies)
    if isinstance(node, S.TransformNode):
        rx, ry, rz = node.rotate
        # 회전 · 배율은 `pivot` 둘레로 — 원점으로 옮겨 돌리고 키운 뒤 제자리로.
        source = Pos(*(-one for one in node.pivot)) * made[node.target]
        if node.scale != 1.0:
            source = scale(source, node.scale)
        return Pos(*node.translate) * Pos(*node.pivot) * Rot(rx, ry, rz) * source
    if isinstance(node, S.BoltNode):
        return _bolt(node)
    if isinstance(node, S.PinNode):
        x, y, z = node.at
        pin: Part = Pos(x, y, z + node.length / 2) * Cylinder(node.diameter / 2, node.length)
        if node.chamfer > 0:
            with contextlib.suppress(Exception):  # 끝이 너무 작으면 모따기 없이
                pin = chamfer(
                    pin.edges().sort_by(Axis.Z)[-1], min(node.chamfer, node.diameter / 5)
                )
        return pin
    if isinstance(node, S.NutNode):
        return hardware.placed(
            hardware.nut(node.thread), Vector(*node.at), Vector(*node.direction)
        )
    if isinstance(node, S.WasherNode):
        return hardware.placed(
            hardware.washer(node.thread), Vector(*node.at), Vector(*node.direction)
        )
    if isinstance(node, S.BearingNode):
        return hardware.placed(
            hardware.bearing(node.designation), Vector(*node.at), Vector(*node.direction)
        )
    if isinstance(node, S.SpringNode):
        return hardware.placed(
            hardware.spring(node), Vector(*node.at), Vector(*node.direction)
        )
    if isinstance(node, S.BracketNode):
        return hardware.bracket(node)
    if isinstance(node, S.FastenNode):
        return hardware.fasten(_as_part(made[node.target], node.id), node, _bolt)
    if isinstance(node, S.StandoffNode):
        x, y, z = node.at
        return Pos(x, y, z + node.height / 2) * (
            Cylinder(node.outer / 2, node.height) - Cylinder(node.hole / 2, node.height * 2)
        )
    if isinstance(node, S.WedgeNode):
        return Pos(*node.at) * Wedge(
            node.length,
            node.width,
            node.height,
            align=_align(node.align),
            xmin=node.top_x_min,
            zmin=node.top_z_min,
            xmax=node.length if node.top_x_max is None else node.top_x_max,
            zmax=node.height if node.top_z_max is None else node.top_z_max,
        )
    if isinstance(node, S.DraftNode):
        part = _as_part(made[node.target], node.id)
        chosen = _faces(part, node.faces, node.id)
        if not chosen:
            raise RecipeError(node.id, "구배를 적용할 면을 선택하지 않았습니다.")
        try:
            result = draft(chosen, neutral_plane=_plane(node.neutral), angle=node.angle)
        except Exception as failure:
            raise RecipeError(
                node.id,
                f"{node.angle}°의 구배를 적용하지 못했습니다. 각도를 줄이거나 선택한 면을 "
                "줄이십시오.",
            ) from failure
        return _to_part(result)
    if isinstance(node, S.DefeatureNode):
        part = _as_part(made[node.target], node.id)
        doomed = _faces(part, node.faces, node.id)
        if node.holes_below is not None:
            doomed += defeature.holes(part, node.holes_below)
        if node.fillets_below is not None:
            doomed += defeature.fillets(part, node.fillets_below)
        result, left = defeature.remove(part, doomed)
        if left:
            notes.append(
                f"{node.id}: 면 {left}개는 인접 면을 연장하여 메울 수 없어 남겨 "
                "두었습니다. 서로 이어진 필렛이 끝면 둘레를 모두 감싸는 경우에 발생합니다. "
                "기준값을 줄이거나 제거할 면을 직접 선택하십시오."
            )
        return result
    if isinstance(node, S.ImprintNode):
        try:
            result, contacts = imprint(_to_part(made[node.target]))
        except ImprintError as failure:
            raise RecipeError(node.id, str(failure)) from failure
        if not contacts:
            notes.append(f"{node.id}: 서로 접촉하는 바디가 없어 임프린트할 위치가 없습니다.")
        patches.update(contacts)
        return result
    if isinstance(node, S.SplitNode):
        part = _as_part(made[node.target], node.id)
        keep = {"top": Keep.TOP, "bottom": Keep.BOTTOM, "both": Keep.BOTH}[node.keep]
        knife: Any = _plane(node.plane)
        if node.tool is not None:
            knife = made[node.tool]
            if not surfaces.is_surface(knife):
                raise RecipeError(
                    node.id, f"tool: ‘{node.tool}’은(는) 곡면(surface)이 아닙니다."
                )
            faces = knife.faces()
            knife = faces[0] if len(faces) == 1 else Shell(faces)
        result = split(part, bisect_by=knife, keep=keep)
        if not result.solids():
            raise RecipeError(
                node.id,
                "분할 후 남길 쪽에 형상이 없습니다. "
                + (
                    "곡면이 솔리드를 가로질러야 합니다."
                    if node.tool
                    else "평면이 솔리드를 지나야 합니다."
                ),
            )
        return _to_part(result)
    if isinstance(node, S.SurfaceNode):
        try:
            if node.kind == "grid":
                return surfaces.grid(node.grid or [])
            if node.kind == "loft":
                return surfaces.loft(node.curves or [], ruled=node.ruled, smooth=node.smooth)
            return surfaces.fill(node.boundary or [], node.through, smooth=node.smooth)
        except surfaces.SurfaceError as failure:
            raise RecipeError(node.id, str(failure)) from failure
    if isinstance(node, S.ThickenNode):
        target = made[node.target]
        if not surfaces.is_surface(target):
            raise RecipeError(
                node.id, f"target: ‘{node.target}’은(는) 곡면(surface)이 아닙니다."
            )
        try:
            return surfaces.thicken(target, node.thickness, node.side)
        except surfaces.SurfaceError as failure:
            raise RecipeError(node.id, str(failure)) from failure
    if isinstance(node, S.SectionNode):
        part = _as_part(made[node.target], node.id)
        cut = section(part, section_by=_plane(node.plane))
        if not cut.faces() or cut.area < 1e-6:
            raise RecipeError(node.id, "지정한 평면이 솔리드를 지나지 않습니다.")
        return _offset2d(
            Sketch(children=[copy.copy(f) for f in cut.faces()]), node.offset, node.id
        )
    if isinstance(node, S.OffsetNode):
        part = _as_part(made[node.target], node.id)
        kind = Kind.ARC if node.corners == "round" else Kind.INTERSECTION
        try:
            result = offset(part, node.amount, kind=kind)
        except Exception as failure:
            raise RecipeError(
                node.id,
                f"{node.amount}만큼 오프셋하지 못했습니다. 가장 얇은 부분의 두께보다 작은 "
                "값을 지정하십시오.",
            ) from failure
        if not result.solids() or result.volume <= 0:
            raise RecipeError(node.id, "오프셋한 결과 남는 형상이 없습니다.")
        return _to_part(result)
    if isinstance(node, S.MirrorNode):
        source = made[node.target]
        mirrored = mirror(source, about=datums.plane(node.plane, made))
        if not node.keep_original:
            return mirrored
        return _cleaned(_to_part(source) + _to_part(mirrored))
    if isinstance(node, S.GroupNode):
        # **붙이지 않는다.** 자식으로 담아야 부품 · 지그가 따로 남는다(복사본으로 — Compound 는
        # 자식을 옮겨 가 원본을 비운다). 자식에 대상 id 를 이름표로 — 메시가 「이 면은 어느
        # 구성품인가」 를 화면에 알려 줄 수 있게.
        children = []
        for target in node.targets:
            child = copy.copy(made[target])
            child.label = target
            children.append(child)
        return Compound(children=children)
    if isinstance(node, S.ComponentNode):
        if resolve_component is None:
            raise RecipeError(node.id, "이 작업에서는 다른 도면을 가져올 수 없습니다.")
        if depth >= MAX_COMPONENT_DEPTH:
            raise RecipeError(
                node.id,
                "조립 단계가 너무 깊습니다. 도면끼리 서로를 가져오고 있지 않은지 "
                "확인하십시오.",
            )
        try:
            source = resolve_component(node.source)
        except Exception as failure:
            raise RecipeError(
                node.id, f"가져올 도면을 찾지 못했습니다: {failure}"
            ) from failure
        # 가져온 쪽의 변수를 덮어쓴다 — 조립의 변수가 구성품 치수로 흘러가는 길.
        merged = {**source, "params": {**(source.get("params") or {}), **node.params}}
        try:
            inner = S.parse(merged)
        except Exception as failure:
            raise RecipeError(
                node.id, f"가져온 도면이 올바르지 않습니다: {failure}"
            ) from failure
        sub = _evaluate_recipe(
            inner,
            resolve_file=resolve_file,
            resolve_component=resolve_component,
            depth=depth + 1,
        )
        rx, ry, rz = node.rotate
        initial = Pos(*node.translate) * Rot(rx, ry, rz)
        if not node.mates:
            placements[node.id] = mates.placement(initial)
            return initial * sub.shape
        specs = [_mate_spec(one, sub.shape, made) for one in node.mates]
        try:
            location, report = mates.solve(sub.shape, specs, initial)
        except mates.MateError as failure:
            raise RecipeError(node.id, str(failure)) from failure
        placements[node.id] = mates.placement(location, report)
        return location * sub.shape
    if isinstance(node, S.ImportStepNode):
        if resolve_file is None:
            raise RecipeError(node.id, "이 작업에서는 STEP을 불러올 수 없습니다.")
        try:
            path = resolve_file(node.file)
        except Exception as failure:
            raise RecipeError(node.id, f"파일을 찾지 못했습니다: {failure}") from failure
        shape = import_step(path)
        if not shape.solids():
            raise RecipeError(node.id, "STEP 파일에 솔리드가 없습니다.")
        return _to_part(shape)
    raise RecipeError(node.id, f"알 수 없는 연산입니다: {node.op}")  # pragma: no cover


def _deformed(node: S.DeformNode, made: dict[str, Any]) -> Part:
    """비틀기 · 테이퍼 — 구간을 비우면 대상이 축 위에서 차지하는 구간 전체."""
    target = _as_part(made[node.target], node.id)
    axis = datums.axis(node.axis, made)
    base, direction = axis.position, axis.direction.normalized()
    box = target.bounding_box()
    corners = [
        (Vector(x, y, z) - base).dot(direction)
        for x in (box.min.X, box.max.X)
        for y in (box.min.Y, box.max.Y)
        for z in (box.min.Z, box.max.Z)
    ]
    start = min(corners) if node.start is None else node.start
    end = max(corners) if node.end is None else node.end
    if end - start < 1e-6:
        raise RecipeError(
            node.id, "변형할 구간의 길이가 0입니다. 축이 대상을 가로지르는지 확인하십시오."
        )
    move = deform.mapping(
        Axis(base, direction), start, end, math.radians(node.twist), node.taper
    )
    tolerance = max(1e-3, 1e-5 * box.diagonal)
    # 구간이 대상 안에서 시작 · 끝나면 그 자리에서 면을 가른다 — 변형이 거기서 꺾인다.
    cuts = [
        Plane(origin=base + direction * at, z_dir=direction)
        for at in (start, end)
        if min(corners) + tolerance < at < max(corners) - tolerance
    ]
    try:
        return deform.deform(target, move, tolerance=tolerance, cuts=cuts)
    except deform.DeformError as failure:
        raise RecipeError(node.id, str(failure)) from failure


def _mate_spec(mate: S.Mate, local: Shape, made: dict[str, Any]) -> mates.Spec:
    """구속 하나를 풀 수 있는 꼴로 — `this` 는 구성품 자신에서, `to` 는 앞의 피처 ·
    기준에서."""
    where = f"구속({mates.LABELS[mate.type]})"
    try:
        this = mates.element(local, mate.this)
    except mates.MateError as failure:
        raise mates.MateError(f"{where} this: {failure}") from failure
    if mate.to in S.GLOBAL_AXES:
        to = mates.datum_element(datums.axis(mate.to, made))
    elif mate.to in S.GLOBAL_PLANES:
        to = mates.datum_element(datums.plane(mate.to, made))
    else:
        target = made[mate.to]
        if datums.is_datum(target):
            to = mates.datum_element(target)
        elif mate.select is None:
            raise mates.MateError(
                f"{where}: select가 없습니다. ‘{mate.to}’에서 사용할 면 또는 축을 "
                "선택하십시오."
            )
        else:
            try:
                to = mates.element(target, mate.select)
            except mates.MateError as failure:
                raise mates.MateError(f"{where} select: {failure}") from failure
    return mates.Spec(
        kind=mate.type,
        this=this,
        to=to,
        offset=mate.offset,
        angle=mate.angle,
        flip=mate.flip,
    )


def _info(node: S.Node, shape: Any, placement: dict[str, Any] | None = None) -> NodeInfo:
    if datums.is_datum(shape):
        return NodeInfo(
            id=node.id, op=node.op, kind="datum", bbox=None, volume=None, faces=0, edges=0
        )
    is_sketch = isinstance(shape, Sketch)
    box = shape.bounding_box()
    return NodeInfo(
        id=node.id,
        op=node.op,
        kind="sketch" if is_sketch else ("part" if isinstance(shape, Part) else "compound"),
        bbox=(_xyz(box.min), _xyz(box.max)),
        volume=None if is_sketch else round(float(shape.volume), 1),
        faces=len(shape.faces()),
        edges=len(shape.edges()),
        placement=placement,
    )


def evaluate(
    recipe: S.Recipe,
    *,
    resolve_file: FileResolver | None = None,
    resolve_component: ComponentResolver | None = None,
    allow_sketch: bool = False,
) -> Evaluation:
    """레시피를 만든다. `allow_sketch` 는 **미리보기용** — 스케치까지만 그린 상태도 면으로
    보여 준다. 저장 · 지그는 입체여야 하므로 기본은 거절이다.

    `resolve_component` 는 조립이 쓴다 — `component` 가 가리키는 도면의 레시피를 주는 함수."""
    made = _evaluate_recipe(
        recipe,
        resolve_file=resolve_file,
        resolve_component=resolve_component,
        allow_sketch=allow_sketch,
    )
    # 좌표계는 형상과 무관하다 — 식은 이미 풀렸으니(`parse`) 원점 · 축만 셈한다.
    from app.core import frames

    for one in recipe.coordinate_systems:
        try:
            made.frames.append(frames.from_definition(one.name, "cad", one.model_dump()))
        except ValueError as failure:
            raise RecipeError(one.name, str(failure)) from failure
    return made


def _evaluate_recipe(
    recipe: S.Recipe,
    *,
    resolve_file: FileResolver | None = None,
    resolve_component: ComponentResolver | None = None,
    allow_sketch: bool = False,
    depth: int = 0,
) -> Evaluation:
    made: dict[str, Any] = {}
    infos: list[NodeInfo] = []
    patches: dict[str, dict[str, Any]] = {}
    #: 실패는 아니지만 알려야 할 것 — 요약의 `warnings` 로 화면과 AI 에 간다.
    notes: list[str] = []
    placements: dict[str, dict[str, Any]] = {}
    for node in recipe.nodes:
        try:
            shape = _evaluate_node(
                node, made, resolve_file, resolve_component, depth, patches, notes, placements
            )
        except RecipeError:
            raise
        except (datums.DatumError, hardware.HardwareError, mates.MateError) as failure:
            raise RecipeError(node.id, str(failure)) from failure
        except Exception as failure:
            # OCC 의 말은 사람에게 뜻이 없다 — 노드와 연산 이름을 붙여 준다.
            raise RecipeError(
                node.id,
                f"{node.op}을(를) 생성하지 못했습니다"
                f"({type(failure).__name__}: {str(failure).rstrip('.')}).",
            ) from failure
        if isinstance(shape, Part) and (not shape.is_valid or shape.volume <= 0):
            raise RecipeError(
                node.id,
                f"{node.op}의 결과가 유효한 솔리드가 아닙니다. 면이 정확히 포개지거나 "
                "서로 스치는 도형은 약간 겹치도록 배치하십시오.",
            )
        made[node.id] = shape
        infos.append(_info(node, shape, placements.get(node.id)))

    result_id = _result_id(recipe, made)
    result = made[result_id]
    marks = [
        datums.describe(name, value) for name, value in made.items() if datums.is_datum(value)
    ]
    if isinstance(result, Sketch):
        if allow_sketch:
            result.label = "sketch"
            return Evaluation(
                shape=result,
                nodes=infos,
                warnings=[
                    "아직 스케치(2D)입니다. 돌출 또는 회전을 추가하면 솔리드가 됩니다.",
                    *notes,
                ],
                datums=marks,
            )
        raise RecipeError(
            result_id, "결과가 스케치입니다. extrude 또는 revolve로 솔리드를 생성하십시오."
        )
    if surfaces.is_surface(result):
        # 곡면은 미리보기에서만 그대로 보인다 — 저장 · 지그는 입체여야 한다.
        if allow_sketch:
            shown = Sketch(children=[copy.copy(face) for face in result.faces()])
            shown.label = "sketch"
            return Evaluation(
                shape=shown,
                nodes=infos,
                warnings=[
                    "곡면입니다(두께 없음). thicken으로 두께를 부여하거나 split의 tool로 "
                    "사용하십시오.",
                    *notes,
                ],
                datums=marks,
            )
        raise RecipeError(
            result_id,
            "결과가 곡면입니다. thicken으로 두께를 부여하거나 split의 tool로 사용하십시오.",
        )
    part = _to_part(result)
    if not part.solids():
        raise RecipeError(result_id, "결과에 솔리드가 없습니다.")
    part.label = "model"
    return Evaluation(
        shape=part,
        nodes=infos,
        warnings=notes,
        tags=_tagged_faces(part, patches),
        datums=marks,
    )


def _result_id(recipe: S.Recipe, made: dict[str, Any]) -> str:
    """결과로 삼을 노드. 기준(축 · 면)은 형상이 아니므로 결과가 될 수 없다 — 「결과」 를 비워
    두었으면(마지막 노드) 기준을 건너뛰고 그 앞의 형상을 쓴다. 기준을 막 더한 미리보기가
    빈 화면이 되지 않게."""
    if not datums.is_datum(made[recipe.result_id]):
        return recipe.result_id
    if recipe.result is not None:
        raise RecipeError(
            recipe.result_id, "기준(축·면)은 결과가 될 수 없습니다. 형상 피처를 선택하십시오."
        )
    shapes = [node.id for node in recipe.nodes if not datums.is_datum(made[node.id])]
    if not shapes:
        raise RecipeError(recipe.result_id, "형상이 없습니다. 기준(축·면)만 있습니다.")
    return shapes[-1]
