"""레시피 평가기 — 노드를 차례로 build123d 형상으로 만든다.

실패는 `RecipeError(node_id, message)` 로 — 어느 노드가 왜 실패했는지가 편집기와 AI 에 그대로
간다. OpenCascade 가 던지는 예외는 메시지가 사람에게 뜻이 없으므로("BRep_API: command not
done") 노드 종류에 맞는 말로 바꾼다.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from build123d import (
    Axis,
    Box,
    Circle,
    Compound,
    Cylinder,
    Location,
    Part,
    Plane,
    Polygon,
    Pos,
    Rectangle,
    RegularPolygon,
    Rot,
    Shape,
    Sketch,
    SlotOverall,
    Vector,
    chamfer,
    extrude,
    fillet,
    import_step,
    mirror,
    revolve,
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
    shape: Part
    nodes: list[NodeInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        box = self.shape.bounding_box()
        return {
            "bbox": {
                "min": _xyz(box.min),
                "max": _xyz(box.max),
                "size": _xyz(box.size),
            },
            "volume": round(float(self.shape.volume), 1),
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
    else:
        face = SlotOverall(one.length, one.width, rotation=one.rotation)
    return Pos(one.at[0], one.at[1]) * face


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
    return _plane(node.plane) * result


# --- 3D 노드 -------------------------------------------------------------------


def _as_part(shape: Shape, node_id: str) -> Part:
    if isinstance(shape, Part):
        return shape
    if isinstance(shape, Sketch):
        raise RecipeError(
            node_id, "스케치는 여기 쓸 수 없습니다 — 먼저 extrude · revolve 하세요"
        )
    return Part(shape.wrapped)


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
    elif select == "vertical":
        edges = edges.filter_by(Axis.Z)
    elif select == "horizontal":
        edges = [e for e in edges if abs(e.tangent_at(0.5).Z) < 1e-6]
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


def _hole(part: Part, node: S.HoleNode) -> Part:
    box = part.bounding_box()
    radius = node.diameter / 2
    if node.depth is None:
        height = box.size.Z * 2 + 2
        z = box.center().Z
    else:
        height = node.depth
        z = box.max.Z - node.depth / 2
    result = part
    for x, y in node.at:
        result = result - Pos(x, y, z) * Cylinder(radius, height)
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
        if node.direction == "both":
            return extrude(sketch, node.distance / 2, both=True)
        amount = node.distance if node.direction == "normal" else -node.distance
        return extrude(sketch, amount)
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
                f"반지름 {node.radius} 으로 필렛을 만들지 못했습니다 — "
                f"인접한 면보다 작게 줄이거나 edges 를 좁히세요",
            ) from failure
    if isinstance(node, S.ChamferNode):
        part = _as_part(made[node.target], node.id)
        edges = _edges(part, node.edges, node.id)
        try:
            return chamfer(edges, node.length)
        except ValueError as failure:
            raise RecipeError(
                node.id, f"길이 {node.length} 으로 모따기를 만들지 못했습니다 — 줄여 보세요"
            ) from failure
    if isinstance(node, S.HoleNode):
        return _hole(_as_part(made[node.target], node.id), node)
    if isinstance(node, S.PatternNode):
        copies = _copies(made[node.source], node)
        if isinstance(copies[0], Sketch):
            return Sketch(children=copies)
        return Compound(children=copies)
    if isinstance(node, S.TransformNode):
        rx, ry, rz = node.rotate
        return Pos(*node.translate) * Rot(rx, ry, rz) * made[node.target]
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


def evaluate(recipe: S.Recipe, *, resolve_file: FileResolver | None = None) -> Evaluation:
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
        raise RecipeError(
            recipe.result_id, "결과가 스케치입니다 — extrude · revolve 로 입체를 만드세요"
        )
    part = _to_part(result)
    if not part.solids():
        raise RecipeError(recipe.result_id, "결과에 솔리드가 없습니다")
    part.label = "model"
    return Evaluation(shape=part, nodes=infos)
