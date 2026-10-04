"""면 지우기 — 작은 구멍 · 필렛이나 고른 면을 없애고 이웃 면을 늘려 막는다(`defeature`).

해석 전에 형상을 단순하게 만드는 일이다. 반지름 0.5 필렛 하나가 그 둘레의 메시를 촘촘하게
만들어 요소 수를 몇 배로 늘리고, 볼트 자리가 아닌 작은 구멍은 결과에 거의 영향이 없는데
메시 품질만 떨어뜨린다. 피처 이력이 없는 가져온 STEP 은 이것 말고 고칠 길이 없다.

OCC 의 `BRepAlgoAPI_Defeaturing` 이 「이 면들을 지우고 이웃 면을 늘려 메워라」 를 한다. 여기서
하는 일은 **무엇을 지울지 가려내는 것**이다:

- 구멍 — 축을 향하는(재료가 바깥인) 원통면이 **한 바퀴**를 이루는 것. 반쪽 면 둘로 나뉜 구멍은
  합쳐 센다. 같은 축의 원뿔면(카운터싱크)과 턱(동심원으로만 둘린 평면 — 카운터보어)도 함께.
- 필렛 — **한 바퀴가 안 되는** 원통면 조각 · 토러스(모서리가 만나는 곳) · 구(세 필렛의 꼭짓점).
  한 바퀴가 안 되는 원통면은 볼록한 것(바깥 모서리)도 오목한 것(안쪽 모서리)도 필렛이다.
"""

from __future__ import annotations

import math
from collections import defaultdict

from build123d import Face, GeomType, Part, Solid, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing
from OCP.BRepTools import BRepTools
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_ListOfShape

#: 한 바퀴(2π)로 볼 오차 — 반쪽 면 둘의 합이 수치 오차로 조금 모자랄 수 있다.
_FULL_TURN = 2 * math.pi - 1e-3
_TOL = 1e-4


class DefeatureError(ValueError):
    """사람이 읽고 고칠 수 있는 실패 — 평가기가 노드 id 를 붙인다."""


def holes(part: Part, below: float) -> list[Face]:
    """지름이 `below` 보다 작은 구멍의 면들 — 벽, 같은 축의 원뿔(카운터싱크)과
    턱(카운터보어)."""
    walls = hole_walls(part)
    out: list[Face] = []
    for (axis_point, direction), faces in walls.items():
        diameter = 2 * min(_radius(one) for one in faces)
        if diameter >= below:
            continue
        out += faces
        out += _coaxial_extras(part, axis_point, direction, exclude=faces)
    return _unique(out)


def fillets(part: Part, below: float) -> list[Face]:
    """반지름이 `below` 보다 작은 필렛 면 — 한 바퀴가 안 되는 원통 조각 · 토러스 · 구."""
    # 면은 부를 때마다 새 파이썬 객체다 — 같은 면인지는 OCC 의 동일성(해시 · is_same)으로 본다.
    in_holes = {one for faces in hole_walls(part).values() for one in faces}
    out: list[Face] = []
    for face in part.faces():
        kind = face.geom_type
        if kind == GeomType.CYLINDER:
            if face in in_holes or _span(face) >= _FULL_TURN:
                continue
            if _radius(face) < below:
                out.append(face)
        elif kind == GeomType.TORUS:
            if BRepAdaptor_Surface(face.wrapped).Torus().MinorRadius() < below:
                out.append(face)
        elif kind == GeomType.SPHERE and _radius(face) < below:
            out.append(face)
    return out


def remove(part: Part, faces: list[Face]) -> tuple[Part, int]:
    """면들을 지우고 이웃 면을 늘려 메운다 — (결과, **못 지우고 남긴 면 수**).

    OCC 는 이어진 면 무리를 피처 하나로 보고 메우는데, 무리가 끝면 둘레를 다 두르면(ㄴ자의
    모든 모서리를 둥글린 것) **경계상자로 메워 버린다**(실측 2026-10-02: 6424 mm³ ㄴ자 →
    24000 상자). 오류도 내지 않는다. 그래서 결과가 그럴듯한지 부피로 보고, 아니면 이어진
    무리마다 따로 해 보아 되는 무리만 지운다. 안 되는 무리는 남기고 그 수를 돌려준다 —
    부르는 쪽이 경고한다."""
    faces = _unique(faces)
    if not faces:
        return part, 0
    whole = _attempt(part, faces)
    if whole is not None:
        return whole, 0
    doable: list[Face] = []
    for group in _groups(faces):
        if _attempt(part, group) is not None:
            doable += group
    if not doable:
        return part, len(faces)
    result = _attempt(part, doable)
    if result is None:  # pragma: no cover — 따로는 되는데 함께는 안 되는 경우
        return part, len(faces)
    return result, len(faces) - len(doable)


def _attempt(part: Part, faces: list[Face]) -> Part | None:
    """한 번 해 본다. 실패하거나 그럴듯하지 않으면 None."""
    try:
        result = _defeatured(part, faces)
    except DefeatureError:
        return None
    # 지운 면들의 경계상자를 다 합친 것보다 부피가 크게 바뀌었으면 엉뚱하게 메운 것이다 —
    # 필렛 · 구멍을 메워 바뀌는 부피는 그 면의 경계상자 안에 든다.
    room = sum(_box_volume(one) for one in faces) * 1.2 + 1e-6
    if not result.is_valid or abs(result.volume - part.volume) > room:
        return None
    return result


def _groups(faces: list[Face]) -> list[list[Face]]:
    """엣지를 나눠 가진 면끼리 한 무리."""
    parent = list(range(len(faces)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = [set(one.edges()) for one in faces]
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            if edges[i] & edges[j]:
                parent[root(i)] = root(j)
    out: dict[int, list[Face]] = defaultdict(list)
    for i, face in enumerate(faces):
        out[root(i)].append(face)
    return list(out.values())


def _box_volume(face: Face) -> float:
    size = face.bounding_box().size
    return float(size.X * size.Y * size.Z)


def _defeatured(part: Part, faces: list[Face]) -> Part:
    listed = TopTools_ListOfShape()
    for face in faces:
        listed.Append(face.wrapped)
    algo = BRepAlgoAPI_Defeaturing()
    algo.SetShape(part.wrapped)
    algo.AddFacesToRemove(listed)
    algo.SetRunParallel(False)
    algo.SetToFillHistory(False)
    algo.Build()
    if not algo.IsDone():
        raise DefeatureError(
            f"면 {len(faces)}개를 제거하고 메우지 못했습니다. 인접 면을 연장하여 메울 수 "
            "없는 위치입니다. 제거할 면을 줄이거나 해당 피처를 생성한 노드를 수정하십시오."
        )
    solids = []
    explorer = TopExp_Explorer(algo.Shape(), TopAbs_SOLID)
    while explorer.More():
        solids.append(Solid(TopoDS.Solid_s(explorer.Current())))
        explorer.Next()
    if not solids:
        raise DefeatureError("면을 제거한 결과 솔리드가 남지 않았습니다.")
    return Part(children=solids)


# --- 가려내기 -------------------------------------------------------------------------


def hole_walls(part: Part) -> dict[tuple[tuple[float, ...], tuple[float, ...]], list[Face]]:
    """(축 위의 점, 축 방향) → 그 구멍의 벽 원통면들. **한 바퀴**를 이루는 것만."""
    groups: dict[tuple[tuple[float, ...], tuple[float, ...]], list[Face]] = defaultdict(list)
    for face in part.faces():
        if face.geom_type != GeomType.CYLINDER or not _faces_axis(face):
            continue
        groups[_axis_key(face)].append(face)
    out = {}
    for key, faces in groups.items():
        # 같은 축 · 같은 반지름끼리 — 카운터보어는 반지름이 다른 둘이 같은 축에 있다.
        by_radius: dict[float, list[Face]] = defaultdict(list)
        for one in faces:
            by_radius[round(_radius(one), 4)].append(one)
        walls = [one for same in by_radius.values() if _turns(same) for one in same]
        if walls:
            out[key] = walls
    return out


def _coaxial_extras(
    part: Part,
    axis_point: tuple[float, ...],
    direction: tuple[float, ...],
    exclude: list[Face],
) -> list[Face]:
    """구멍과 같은 축의 원뿔면(카운터싱크)과 턱 — 동심원으로만 둘린 평면(카운터보어)."""
    point, axis = Vector(*axis_point), Vector(*direction)
    out: list[Face] = []
    for face in part.faces():
        if any(face.is_same(one) for one in exclude):
            continue
        if face.geom_type == GeomType.CONE and _axis_key(face) == (axis_point, direction):
            out.append(face)
        elif (
            face.geom_type == GeomType.PLANE
            and abs(abs(face.normal_at().dot(axis)) - 1) < 1e-6
        ):
            edges = face.edges()
            if edges and all(
                edge.geom_type == GeomType.CIRCLE and _on_axis(edge.arc_center, point, axis)
                for edge in edges
            ):
                out.append(face)
    return out


def _faces_axis(face: Face) -> bool:
    """바깥 법선이 축을 향하나 — 재료가 원통 밖에 있다(구멍 · 오목한 모서리)."""
    axis = face.axis_of_rotation
    point = face.position_at(0.5, 0.5)
    normal = face.normal_at(0.5, 0.5)
    offset = point - axis.position
    radial = offset - axis.direction * offset.dot(axis.direction)
    return radial.length > _TOL and normal.dot(radial) < 0


def _turns(faces: list[Face]) -> bool:
    return sum(_span(one) for one in faces) >= _FULL_TURN


def _span(face: Face) -> float:
    u_min, u_max, _, _ = BRepTools.UVBounds_s(face.wrapped)
    return float(u_max - u_min)


def _radius(face: Face) -> float:
    return float(face.radius)


def _axis_key(face: Face) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """축을 하나로 부르는 열쇠 — 방향은 부호를 맞추고, 점은 원점에서 가장 가까운 축 위의 점."""
    axis = face.axis_of_rotation
    direction = axis.direction.normalized()
    for value in (direction.Z, direction.Y, direction.X):
        if abs(value) > 1e-9:
            direction = direction if value > 0 else -direction
            break
    origin = axis.position - direction * axis.position.dot(direction)
    return (_rounded(origin), _rounded(direction))


def _on_axis(point: Vector, axis_point: Vector, direction: Vector) -> bool:
    offset = point - axis_point
    return (offset - direction * offset.dot(direction)).length < 1e-3


def _rounded(vector: Vector) -> tuple[float, ...]:
    return tuple(round(float(value), 3) + 0.0 for value in (vector.X, vector.Y, vector.Z))


def _unique(faces: list[Face]) -> list[Face]:
    out: list[Face] = []
    for face in faces:
        if not any(face.is_same(one) for one in out):
            out.append(face)
    return out
