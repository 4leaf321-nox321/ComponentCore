"""레시피 평가기 — 노드를 차례로 build123d 형상으로 만든다.

실패는 `RecipeError(node_id, message)` 로 — 어느 노드가 왜 실패했는지가 편집기와 AI 에 그대로
간다. OpenCascade 가 던지는 예외는 메시지가 사람에게 뜻이 없으므로("BRep_API: command not
done") 노드 종류에 맞는 말로 바꾼다.
"""

from __future__ import annotations

import contextlib
import copy
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

from app.core.recipe import schema as S

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


@dataclass
class Evaluation:
    shape: Shape
    """보통 Part(입체). `allow_sketch` 로 평가했을 때만 Sketch(면)일 수 있다 — `is_sketch`."""
    nodes: list[NodeInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)
    """레시피의 좌표계를 **이 평가의 치수로** 푼 것 — 원점 · X · Y · Z(`core/frames.py`)."""
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
            raise ValueError("모서리 반지름이 너비 · 높이의 절반보다 작아야 합니다")
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
                f"그 변 · 각으로는 삼각형이 되지 않습니다 ({failure})"
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
                    f"구간 {index + 1}: 접선 호는 앞 구간이 있어야 방향이 정해집니다"
                )
            edges.append(TangentArc(cursor, target, tangent=edges[-1] % 1))
        elif segment.radius is not None:
            span = (target - cursor).length
            if abs(segment.radius) < span / 2 - 1e-9:
                raise ValueError(
                    f"구간 {index + 1}: 반지름 {abs(segment.radius)} 이 두 점 사이 "
                    f"{round(span, 2)} 의 절반보다 작습니다"
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
        raise ValueError("선의 길이가 없습니다")
    kind = Kind.ARC if shape.corners == "round" else Kind.INTERSECTION
    outline = offset(Wire(edges), shape.width / 2, kind=kind)
    wires = outline.wires()
    if len(wires) != 1 or not wires[0].is_closed:
        raise ValueError("선이 스스로 겹칩니다 — 폭을 줄이거나 점을 고치세요")
    face = make_face(wires[0])
    if not face.is_valid or face.area < 1e-6:
        raise ValueError("선에서 면을 만들지 못했습니다")
    sketch = Sketch(face.wrapped)
    if shape.rotation:
        sketch = sketch.rotate(Axis.Z, shape.rotation)
    return sketch


def _polyline(shape: S.PolylineShape) -> Sketch:
    """점을 이어 닫힌 윤곽으로. 구간에 `via` 가 있으면 그 점을 지나는 호."""
    if shape.corner_radius > 0:
        if any(segment.via is not None for segment in shape.segments):
            raise ValueError("모서리 둥글리기는 호(via)와 함께 쓸 수 없습니다")
        points = [shape.start, *[segment.to for segment in shape.segments]]
        if points[-1] == points[0]:
            points = points[:-1]
        rounded = FilletPolyline(*points, radius=shape.corner_radius, close=True)
        face = make_face(rounded.wires()[0])
        if not face.is_valid or face.area < 1e-6:
            raise ValueError("모서리 반지름이 너무 큽니다 — 줄이세요")
        sketch = Sketch(face.wrapped)
        return sketch.rotate(Axis.Z, shape.rotation) if shape.rotation else sketch
    edges = _centerline(shape.start, shape.segments)
    cursor = edges[-1] @ 1 if edges else Vector(shape.start[0], shape.start[1], 0)
    start = Vector(shape.start[0], shape.start[1], 0)
    if (cursor - start).length > 1e-6:
        edges.append(Line(cursor, start))
    if len(edges) < 2:
        raise ValueError("윤곽이 닫히지 않습니다 — 점이 둘 이상이어야 합니다")
    face = Face(Wire(edges))
    if not face.is_valid or face.area < 1e-6:
        raise ValueError("윤곽이 스스로 교차하거나 면적이 없습니다")
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
                    node.id, f"shapes[{index}]: 뺄 것이 없습니다 — cut 이 맨 앞입니다"
                )
            result = _as_sketch(result - face)
        else:
            result = face if result is None else _as_sketch(result + face)
    assert result is not None
    if not result.faces():
        raise RecipeError(node.id, "스케치에 남은 면이 없습니다 — cut 이 전부를 지웠습니다")
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
        raise RecipeError(node_id, f"윤곽을 {amount} 만큼 띄우지 못했습니다") from failure
    if not moved.faces() or moved.area < 1e-6:
        raise RecipeError(node_id, f"윤곽을 {amount} 만큼 줄이니 남는 것이 없습니다")
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
            node_id, "스케치는 여기 쓸 수 없습니다 — 먼저 돌출(extrude) · 회전(revolve) 하세요"
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
    if isinstance(select, S.EdgeNear):
        targets = [Vector(*point) for point in select.near]
        picked = [
            f
            for f in faces
            if any((f.center() - t).length <= select.tolerance for t in targets)
        ]
        if len(picked) < len(targets):
            raise RecipeError(node_id, "고른 자리에 면이 없습니다 — 형상이 바뀌었습니다")
        return picked
    if select == "none":
        return []
    if select == "all":
        return list(faces)
    if select == "sides":
        picked = [f for f in faces if abs(f.normal_at().Z) < 0.1]
        if not picked:
            raise RecipeError(node_id, "옆면이 없습니다")
        return picked
    ordered = faces.sort_by(Axis.Z)
    return [ordered[-1] if select == "top" else ordered[0]]


def _edges(part: Part, select: S.EdgeSelect, node_id: str) -> Any:
    edges = part.edges()
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
                f"고른 자리 {len(targets)} 곳 중 {len(edges)} 곳에서만 엣지를 찾았습니다 — "
                f"형상이 바뀌어 그 자리에 엣지가 없습니다",
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
        raise RecipeError(node_id, f"고른 엣지가 없습니다 (edges={select})")
    return edges


def _copies(source: Shape, node: S.PatternNode) -> list[Shape]:
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
        axis = _AXES[node.axis]
        for k in range(node.count):
            out.append(source.rotate(axis, step * k))
    return out


def _bolt(node: S.BoltNode) -> Part:
    """머리 · 와셔 · 몸통 — 지그 생성기의 볼트와 같은 비례. `at` 이 머리가 앉는 면."""
    d = node.nominal
    x, y, seat = node.at
    sign = -1.0 if node.down else 1.0
    washer_t = 0.2 * d if node.washer else 0.0
    head_h = d if node.head == "socket" else 0.65 * d
    head_d = 1.5 * d
    shank_len = node.length
    shank: Part = Pos(x, y, seat + sign * shank_len / 2) * Cylinder(d / 2, shank_len)
    parts: list[Part] = [shank]
    if node.washer:
        parts.append(Pos(x, y, seat - sign * washer_t / 2) * Cylinder(d, washer_t))
    z_head = seat - sign * washer_t
    if node.head == "socket":
        head: Part = Pos(x, y, z_head - sign * head_h / 2) * Cylinder(head_d / 2, head_h)
        head = head - Pos(x, y, z_head - sign * head_h) * Cylinder(0.4 * d, head_h)
    else:
        head = Pos(x, y, z_head - sign * head_h / 2) * extrude(
            RegularPolygon(head_d / 2, 6), head_h / 2, both=True
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
    table = S.THREADS.get(node.thread or "")
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


def _tagged_faces(part: Part, patches: dict[str, dict[str, Any]]) -> dict[str, list[int]]:
    """패치가 있던 자리에서 **지금의 면 번호**를 되찾는다.

    나눈 뒤에 필렛 · 패턴이 그 조각을 또 갈라 놓을 수 있으므로 「나눌 때 본 면」 하나를
    기억해 두면 틀린다. 패치 안에 들어가고 법선이 같은 면을 **모두** 모은다.
    """
    if not patches:
        return {}
    rows = [(index, face) for index, face in enumerate(part.faces())]
    out: dict[str, list[int]] = {}
    for tag, patch in patches.items():
        at = Vector(*patch["at"])
        normal = Vector(*patch["normal"])
        found = []
        for index, face in rows:
            if face.geom_type != GeomType.PLANE:
                continue
            if face.normal_at(face.center()).dot(normal) < 0.95:
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
            if inside:
                found.append(index)
        out[tag] = found
    return out


def _divide_face(part: Part, node: S.DivideFaceNode) -> tuple[Part, dict[str, Any]]:
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

    query = {"what": "faces", **dict(node.on)}
    if node.at is not None and "near" not in query:
        query["near"] = list(node.at)
    rows = find_features(part, query)["items"]
    if not rows:
        raise RecipeError(node.id, f"나눌 면을 찾지 못했습니다 — on: {node.on}")
    faces = part.faces()
    face = faces[rows[0]["index"]]
    if face.geom_type != GeomType.PLANE:
        raise RecipeError(
            node.id, "평면만 나눌 수 있습니다 — 곡면에 띠를 두르는 것은 아직 안 됩니다"
        )

    plane = Plane(face)
    center = Vector(*node.at) if node.at is not None else face.center()
    # 면 위로 투영한 자리 — 사람이 찍은 점이 면에서 조금 떠 있어도 패치는 면 위에 놓인다.
    local = plane.to_local_coords(center)
    if node.shape == "circle":
        if not node.radius:
            raise RecipeError(node.id, "circle 은 radius 가 있어야 합니다")
        patch = plane * Pos(local.X, local.Y) * Circle(node.radius)
        extent = float(node.radius)
    else:
        if not node.size:
            raise RecipeError(node.id, "rect 는 size([가로, 세로])가 있어야 합니다")
        patch = plane * Pos(local.X, local.Y) * Rectangle(node.size[0], node.size[1])
        extent = float(max(node.size)) / 2

    splitter = BRepFeat_SplitShape(part.wrapped)
    splitter.Add(TopoDS.Wire_s(patch.wire().wrapped), TopoDS.Face_s(face.wrapped))
    splitter.Build()
    divided = Part(splitter.Shape())
    if not divided.is_valid or abs(divided.volume - part.volume) > 1e-6:
        raise RecipeError(node.id, "면을 나누다 형상이 달라졌습니다 — 패치가 면을 넘었나요?")

    at = plane.from_local_coords(Vector(local.X, local.Y, 0))
    return divided, {
        "at": [round(float(v), 3) for v in (at.X, at.Y, at.Z)],
        "normal": [round(float(v), 3) for v in plane.z_dir],
        "extent": round(extent, 3),
    }


def _evaluate_node(
    node: S.Node,
    made: dict[str, Shape],
    resolve_file: FileResolver | None,
    resolve_component: ComponentResolver | None = None,
    depth: int = 0,
    patches: dict[str, dict[str, Any]] | None = None,
) -> Shape:
    patches = patches if patches is not None else {}
    if isinstance(node, S.SketchNode):
        return _sketch(node)
    if isinstance(node, S.ExtrudeNode):
        sketch = made[node.sketch]
        if not isinstance(sketch, Sketch):
            raise RecipeError(node.id, f"'{node.sketch}' 는 스케치가 아닙니다")
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
                    "그 방향에 부딪힐 면이 없습니다 — "
                    "스케치가 대상 밖에서 대상을 향해야 합니다",
                ) from failure
        if node.direction == "both":
            return extrude(sketch, node.distance / 2, both=True, taper=node.taper)
        amount = node.distance if node.direction == "normal" else -node.distance
        return extrude(sketch, amount, taper=node.taper)
    if isinstance(node, S.SheetMetalNode):
        points = [Vector(x, y, 0) for x, y in node.path]
        flat = (
            FilletPolyline(*points, radius=node.bend_radius)
            if node.bend_radius > 0 and len(points) > 2
            else Polyline(*points)
        )
        plane = _plane(node.plane)
        line = Wire((plane * flat).edges())
        try:
            formed = make_brake_formed(
                thickness=node.thickness,
                station_widths=node.width,
                line=line,
                side=Side.LEFT if node.side == "left" else Side.RIGHT,
            )
        except Exception as failure:
            raise RecipeError(
                node.id,
                "판을 접지 못했습니다 — 굽힘 반지름을 줄이거나 꺾은선의 짧은 구간을 늘리세요",
            ) from failure
        # 판은 평면의 한쪽으로만 자란다(실측) — 꺾은선이 **폭의 가운데**에 오게 되돌린다.
        # 그래야 구멍 자리를 평면 좌표 그대로 주고 좌우 대칭도 그대로다.
        shift = plane.z_dir * (-node.width / 2)
        return _to_part(formed.moved(Location(shift.to_tuple())))
    if isinstance(node, S.HelixNode):
        sketch = made[node.sketch]
        if not isinstance(sketch, Sketch):
            raise RecipeError(node.id, f"'{node.sketch}' 는 스케치가 아닙니다")
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
                node.id, "나선을 따라 밀지 못했습니다 — 단면이 피치보다 작아야 겹치지 않습니다"
            ) from failure
    if isinstance(node, S.SweepNode):
        sketch = made[node.sketch]
        if not isinstance(sketch, Sketch):
            raise RecipeError(node.id, f"'{node.sketch}' 는 스케치가 아닙니다")
        points = [Vector(*p) for p in node.path]
        if any((b - a).length < 1e-6 for a, b in pairwise(points)):
            raise RecipeError(node.id, "경로에 같은 점이 잇달아 있습니다")
        path = Wire(Spline(*points)) if node.smooth else Wire(Polyline(*points))
        try:
            return sweep(sketch, path, transition=Transition.ROUND)
        except Exception as failure:
            raise RecipeError(
                node.id,
                "경로를 따라 밀지 못했습니다 — 단면이 경로 시작점에 놓였는지, 모서리가 "
                "단면보다 급하지 않은지 보세요",
            ) from failure
    if isinstance(node, S.RevolveNode):
        sketch = made[node.sketch]
        if not isinstance(sketch, Sketch):
            raise RecipeError(node.id, f"'{node.sketch}' 는 스케치가 아닙니다")
        return revolve(sketch, _AXES[node.axis], node.angle)
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
            raise RecipeError(node.id, "잘라 내고 남은 것이 없습니다")
        return _cleaned(result)
    if isinstance(node, S.IntersectNode):
        parts = [_to_part(made[t]) for t in node.targets]
        result = parts[0]
        for other in parts[1:]:
            result = result & other
        if not result.solids():
            raise RecipeError(node.id, "겹치는 부분이 없습니다")
        return _cleaned(result)
    if isinstance(node, S.FilletNode):
        part = _as_part(made[node.target], node.id)
        edges = _edges(part, node.edges, node.id)  # RecipeError 는 ValueError 라 try 밖에서
        try:
            return fillet(edges, node.radius)
        except ValueError as failure:
            raise RecipeError(
                node.id,
                f"반지름 {node.radius} 으로 블렌드(필렛)를 만들지 못했습니다 — "
                f"인접한 면보다 작게 줄이거나 edges 를 좁히세요",
            ) from failure
    if isinstance(node, S.ChamferNode):
        part = _as_part(made[node.target], node.id)
        edges = _edges(part, node.edges, node.id)
        try:
            return chamfer(edges, node.length)
        except ValueError as failure:
            raise RecipeError(
                node.id, f"길이 {node.length} 으로 챔퍼를 만들지 못했습니다 — 줄여 보세요"
            ) from failure
    if isinstance(node, S.HoleNode):
        return _hole(_as_part(made[node.target], node.id), node)
    if isinstance(node, S.DivideFaceNode):
        # 패치가 어디인지는 여기서 안다. 태그로 되찾는 일은 평가가 끝난 뒤에 한다 —
        # 뒤의 노드(필렛 · 패턴)가 면을 또 갈라 놓을 수 있기 때문이다.
        divided, patch = _divide_face(_as_part(made[node.target], node.id), node)
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
                node.id, f"두께 {node.thickness} 으로 쉘을 만들지 못했습니다 — 줄여 보세요"
            ) from failure
    if isinstance(node, S.LoftNode):
        sections = []
        for name in node.sketches:
            piece = made[name]
            if not isinstance(piece, Sketch):
                raise RecipeError(node.id, f"'{name}' 는 스케치가 아닙니다")
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
        copies = _copies(made[node.source], node)
        if isinstance(copies[0], Sketch):
            return Sketch(children=copies)
        return Compound(children=copies)
    if isinstance(node, S.TransformNode):
        rx, ry, rz = node.rotate
        source = made[node.target]
        if node.scale != 1.0:
            source = scale(source, node.scale)
        return Pos(*node.translate) * Rot(rx, ry, rz) * source
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
            raise RecipeError(node.id, "구배를 줄 면을 고르지 않았습니다")
        try:
            result = draft(chosen, neutral_plane=_plane(node.neutral), angle=node.angle)
        except Exception as failure:
            raise RecipeError(
                node.id,
                f"{node.angle}° 로 구배를 주지 못했습니다 — 각도를 줄이거나 면을 좁히세요",
            ) from failure
        return _to_part(result)
    if isinstance(node, S.SplitNode):
        part = _as_part(made[node.target], node.id)
        keep = {"top": Keep.TOP, "bottom": Keep.BOTTOM, "both": Keep.BOTH}[node.keep]
        result = split(part, bisect_by=_plane(node.plane), keep=keep)
        if not result.solids():
            raise RecipeError(
                node.id, "자른 쪽에 남는 것이 없습니다 — 평면이 입체를 지나야 합니다"
            )
        return _to_part(result)
    if isinstance(node, S.SectionNode):
        part = _as_part(made[node.target], node.id)
        cut = section(part, section_by=_plane(node.plane))
        if not cut.faces() or cut.area < 1e-6:
            raise RecipeError(node.id, "그 평면은 입체를 지나지 않습니다")
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
                node.id, f"{node.amount} 만큼 키우거나 줄이지 못했습니다 — 얇은 곳보다 작게"
            ) from failure
        if not result.solids() or result.volume <= 0:
            raise RecipeError(node.id, "줄이고 남은 것이 없습니다")
        return _to_part(result)
    if isinstance(node, S.MirrorNode):
        source = made[node.target]
        mirrored = mirror(source, about=_PLANES[node.plane])
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
            raise RecipeError(node.id, "이 자리에서는 다른 도면을 가져올 수 없습니다")
        if depth >= MAX_COMPONENT_DEPTH:
            raise RecipeError(
                node.id, "조립이 너무 깊습니다 — 서로를 가져오고 있지 않은지 보세요"
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
        return Pos(*node.translate) * Rot(rx, ry, rz) * sub.shape
    if isinstance(node, S.ImportStepNode):
        if resolve_file is None:
            raise RecipeError(node.id, "이 자리에서는 STEP 을 불러올 수 없습니다")
        try:
            path = resolve_file(node.file)
        except Exception as failure:
            raise RecipeError(node.id, f"파일을 찾지 못했습니다: {failure}") from failure
        shape = import_step(path)
        if not shape.solids():
            raise RecipeError(node.id, "STEP 에 솔리드가 없습니다")
        return _to_part(shape)
    raise RecipeError(node.id, f"모르는 연산입니다: {node.op}")  # pragma: no cover


def _info(node: S.Node, shape: Shape) -> NodeInfo:
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

    made.frames = [
        frames.from_rotation(one.name, "cad", one.origin, one.rotate)
        for one in recipe.coordinate_systems
    ]
    return made


def _evaluate_recipe(
    recipe: S.Recipe,
    *,
    resolve_file: FileResolver | None = None,
    resolve_component: ComponentResolver | None = None,
    allow_sketch: bool = False,
    depth: int = 0,
) -> Evaluation:
    made: dict[str, Shape] = {}
    infos: list[NodeInfo] = []
    patches: dict[str, dict[str, Any]] = {}
    for node in recipe.nodes:
        try:
            shape = _evaluate_node(node, made, resolve_file, resolve_component, depth, patches)
        except RecipeError:
            raise
        except Exception as failure:
            # OCC 의 말은 사람에게 뜻이 없다 — 노드와 연산 이름을 붙여 준다.
            raise RecipeError(
                node.id,
                f"{node.op} 를 만들지 못했습니다 ({type(failure).__name__}: {failure})",
            ) from failure
        if isinstance(shape, Part) and (not shape.is_valid or shape.volume <= 0):
            raise RecipeError(
                node.id,
                f"{node.op} 의 결과가 유효한 입체가 아닙니다 — "
                f"면이 정확히 포개지거나 서로 스치는 도형은 조금 겹치게 하세요",
            )
        made[node.id] = shape
        infos.append(_info(node, shape))

    result = made[recipe.result_id]
    if isinstance(result, Sketch):
        if allow_sketch:
            result.label = "sketch"
            return Evaluation(
                shape=result,
                nodes=infos,
                warnings=["아직 스케치(2D)입니다 — 돌출 · 회전을 더하면 입체가 됩니다."],
            )
        raise RecipeError(
            recipe.result_id, "결과가 스케치입니다 — extrude · revolve 로 입체를 만드세요"
        )
    part = _to_part(result)
    if not part.solids():
        raise RecipeError(recipe.result_id, "결과에 솔리드가 없습니다")
    part.label = "model"
    return Evaluation(shape=part, nodes=infos, tags=_tagged_faces(part, patches))
