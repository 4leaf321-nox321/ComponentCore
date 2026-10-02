"""비대칭 모따기 · 반지름이 변하는 필렛 — build123d 가 안 하는 것을 OCC 로 직접.

- 모따기: 두 거리(`length` · `length2`) 또는 거리와 각(`length` · `angle`). 어느 면에서
  `length` 를 재는지가 뜻을 가른다 — `reference` 로 고른 면, 안 고르면 **두 면 중 더
  위(+Z)를 보는 면**.
  build123d 의 `chamfer` 는 기준면을 하나만 받아 그 면에 안 붙은 엣지가 섞이면 거절하고,
  거리-각도는 없다.
- 필렛: `radius` 에서 `radius_end` 로 엣지를 따라 고르게 변한다. 어느 끝이 `radius` 인지는
  `start` 점에 가까운 끝 — 엣지의 매개변수 방향은 사람이 알 수 없다.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from build123d import Edge, Face, Part, Solid, Vector
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape


class BlendError(ValueError):
    """사람이 읽고 고칠 수 있는 실패 — 평가기가 노드 id 를 붙인다."""


def chamfer(
    part: Part,
    edges: Iterable[Edge],
    length: float,
    *,
    length2: float | None = None,
    angle: float | None = None,
    reference: list[Face] | None = None,
) -> Part:
    """모따기 — `length2` 면 두 거리, `angle` 이면 거리와 각(도, `length` 를 잰 면에서)."""
    neighbours = _faces_of_edges(part)
    builder = BRepFilletAPI_MakeChamfer(part.wrapped)
    for edge in edges:
        side = _measured_side(edge, neighbours, reference)
        if angle is not None:
            builder.AddDA(length, math.radians(angle), edge.wrapped, side.wrapped)
        else:
            builder.Add(length, length2 or length, edge.wrapped, side.wrapped)
    return _built(builder, "모따기를 만들지 못했습니다 — 길이 · 각을 줄여 보세요")


def fillet(
    part: Part, edges: Iterable[Edge], radius: float, radius_end: float, start: Vector | None
) -> Part:
    """반지름이 엣지를 따라 `radius` → `radius_end` 로 고르게 변하는 필렛."""
    builder = BRepFilletAPI_MakeFillet(part.wrapped)
    for edge in edges:
        first, last = radius, radius_end
        # 매개변수의 처음 끝이 `start` 에서 더 멀면 뒤집는다.
        if (
            start is not None
            and (edge.position_at(0) - start).length > (edge.position_at(1) - start).length
        ):
            first, last = last, first
        builder.Add(first, last, TopoDS.Edge_s(edge.wrapped))
    return _built(
        builder, "반지름이 변하는 필렛을 만들지 못했습니다 — 반지름을 줄이거나 엣지를 좁히세요"
    )


def _faces_of_edges(part: Part) -> TopTools_IndexedDataMapOfShapeListOfShape:
    found = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(part.wrapped, TopAbs_EDGE, TopAbs_FACE, found)
    return found


def _measured_side(
    edge: Edge,
    neighbours: TopTools_IndexedDataMapOfShapeListOfShape,
    reference: list[Face] | None,
) -> Face:
    """`length` 를 재는 면 — 고른 기준면 중 이 엣지에 붙은 것, 없으면 더 위를 보는 면."""
    faces = [Face(TopoDS.Face_s(one)) for one in neighbours.FindFromKey(edge.wrapped)]
    if not faces:  # pragma: no cover — 입체의 엣지는 면에 붙어 있다
        raise BlendError("엣지에 붙은 면이 없습니다")
    for face in faces:
        if reference and any(face.is_same(one) for one in reference):
            return face
    return max(faces, key=lambda one: one.normal_at(one.center()).Z)


def _built(
    builder: BRepFilletAPI_MakeChamfer | BRepFilletAPI_MakeFillet, message: str
) -> Part:
    try:
        builder.Build()
        if not builder.IsDone():
            raise BlendError(message)
        solids = []
        explorer = TopExp_Explorer(builder.Shape(), TopAbs_SOLID)
        while explorer.More():
            solids.append(Solid(TopoDS.Solid_s(explorer.Current())))
            explorer.Next()
        # `Part(solid.wrapped)` 는 부피가 0 으로 나온다(AGENTS.md) — 솔리드를 자식으로 묶는다.
        result = Part(children=solids)
    except BlendError:
        raise
    except Exception as failure:
        raise BlendError(message) from failure
    if not result.is_valid:
        raise BlendError(message)
    return result
