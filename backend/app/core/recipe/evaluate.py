"""레시피 평가기 — 노드를 차례로 build123d 형상으로 만든다.

실패는 `RecipeError(node_id, message)` 로 — 어느 노드가 왜 실패했는지가 편집기와 AI 에 그대로
간다. OpenCascade 가 던지는 예외는 메시지가 사람에게 뜻이 없으므로("BRep_API: command not
done") 노드 종류에 맞는 말로 바꾼다.
"""

from __future__ import annotations

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
    Rectangle,
    RegularPolygon,
    Rot,
    Shape,
    Sketch,
    SlotOverall,
    Sphere,
    Spline,
    Text,
    ThreePointArc,
    Torus,
    Transition,
    Until,
    Vector,
    Wire,
    chamfer,
    extrude,
    fillet,
    import_step,
    loft,
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


def _shape2d(one: S.SketchShape) -> Sketch:
    if isinstance(one, S.Rect):
        face: Sketch = Rectangle(one.width, one.height, rotation=one.rotation)
    elif isinstance(one, S.CircleShape):
        face = Circle(one.radius)
    elif isinstance(one, S.PolygonShape):
        face = Polygon(*one.points, rotation=one.rotation)
    elif isinstance(one, S.RegularPolygonShape):
        face = RegularPolygon(one.radius, one.sides, rotation=one.rotation)
    elif isinstance(one, S.PolylineShape):
        face = _polyline(one)
    elif isinstance(one, S.EllipseShape):
        face = Ellipse(one.x_radius, one.y_radius, rotation=one.rotation)
    elif isinstance(one, S.TextShape):
        face = Text(
            one.text,
            one.size,
            font_style=FontStyle.BOLD if one.bold else FontStyle.REGULAR,
            rotation=one.rotation,
        )
    else:
        face = SlotOverall(one.length, one.width, rotation=one.rotation)
    return Pos(one.at[0], one.at[1]) * face


def _polyline(shape: S.PolylineShape) -> Sketch:
    """점을 이어 닫힌 윤곽으로. 구간에 `via` 가 있으면 그 점을 지나는 호."""
    edges: list[Any] = []
    cursor = Vector(shape.start[0], shape.start[1], 0)
    for segment in shape.segments:
        target = Vector(segment.to[0], segment.to[1], 0)
        if (target - cursor).length < 1e-6:
            continue
        if segment.via is not None:
            edges.append(
                ThreePointArc(cursor, Vector(segment.via[0], segment.via[1], 0), target)
            )
        else:
            edges.append(Line(cursor, target))
        cursor = target
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
            result = result - face
        else:
            result = face if result is None else result + face
    assert result is not None
    if not result.faces():
        raise RecipeError(node.id, "스케치에 남은 면이 없습니다 — cut 이 전부를 지웠습니다")
    return _plane(node.plane) * _offset2d(result, node.offset, node.id)


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


def _to_part(shape: Shape) -> Part:
    """Compound(복사본 묶음) · Solid(STEP 하나) 를 Part 로 — 불리언은 Part 끼리 한다.

    `Part(solid.wrapped)` 는 부피가 0 으로 나온다(Part 는 Compound 를 감싼다고 전제) — 실측.
    솔리드들을 자식으로 다시 묶는다."""
    if isinstance(shape, Part):
        return shape
    solids = list(shape.solids())
    if solids:
        return Part(children=[copy.copy(one) for one in solids])
    return Part(shape.wrapped)


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


def _evaluate_node(
    node: S.Node,
    made: dict[str, Shape],
    resolve_file: FileResolver | None,
) -> Shape:
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
        return Pos(*node.at) * Box(node.length, node.width, node.height)
    if isinstance(node, S.CylinderNode):
        rot = {"Z": Rot(0, 0, 0), "X": Rot(0, 90, 0), "Y": Rot(90, 0, 0)}[node.axis]
        return Pos(*node.at) * rot * Cylinder(node.radius, node.height)
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
        return Pos(*node.at) * Sphere(node.radius)
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
    recipe: S.Recipe, *, resolve_file: FileResolver | None = None, allow_sketch: bool = False
) -> Evaluation:
    """레시피를 만든다. `allow_sketch` 는 **미리보기용** — 스케치까지만 그린 상태도 면으로
    보여 준다. 저장 · 지그는 입체여야 하므로 기본은 거절이다."""
    made: dict[str, Shape] = {}
    infos: list[NodeInfo] = []
    for node in recipe.nodes:
        try:
            shape = _evaluate_node(node, made, resolve_file)
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
    return Evaluation(shape=part, nodes=infos)
