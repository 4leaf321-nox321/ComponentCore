"""기준축 · 기준면 — 형상을 만들지 않고 회전 · 대칭 · 스케치가 기대는 축과 평면.

전에는 회전체 · 원형 패턴 · 대칭 · 회전 이동이 모두 **원점을 지나는 X · Y · Z 축 · 평면**에만
걸렸다. (50, 0) 을 지나는 축으로 돌리려면 원점으로 옮겼다가 돌리고 되돌려야 했다. 기준은 그
축 · 평면 자체를 이름 붙여 두고 가리키게 한다.

형상에서 뽑는 기준(`target` + `select`)은 **설계점마다 다시 찾는다** — 「이 구멍의 축」 ·
「윗면에서 10 띄운 면」 은 DOE 가 치수를 바꿔도 그 구멍 · 그 면을 따라간다.

평가기의 `made` 에는 형상 대신 build123d 의 `Axis` · `Plane` 이 들어간다.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from build123d import Axis, GeomType, Location, Plane, Shape, Vector
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf
from OCP.TopLoc import TopLoc_Location

from app.core.recipe import schema as S
from app.core.recipe.query import find_features

_GLOBAL_AXES = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}
_GLOBAL_PLANES = {
    "XY": Plane.XY,
    "XZ": Plane.XZ,
    "YZ": Plane.YZ,
    "YX": Plane.YX,
    "ZX": Plane.ZX,
    "ZY": Plane.ZY,
}


class DatumError(ValueError):
    """사람이 읽고 고칠 수 있는 실패 — 평가기가 노드 id 를 붙인다."""


def is_datum(value: Any) -> bool:
    return isinstance(value, Axis | Plane)


def axis(ref: str, made: dict[str, Any]) -> Axis:
    """축 칸의 값 → 축. 전역 이름이거나 앞의 기준축."""
    if ref in _GLOBAL_AXES:
        return _GLOBAL_AXES[ref]
    found = made.get(ref)
    if not isinstance(found, Axis):
        raise DatumError(f"'{ref}' 은 기준축이 아닙니다")
    return found


def plane(ref: str, made: dict[str, Any]) -> Plane:
    """평면 칸의 값(이름) → 평면. 전역 이름이거나 앞의 기준면."""
    if ref in _GLOBAL_PLANES:
        return _GLOBAL_PLANES[ref]
    found = made.get(ref)
    if not isinstance(found, Plane):
        raise DatumError(f"'{ref}' 은 기준면이 아닙니다")
    return found


def with_datums(node: Any, made: dict[str, Any]) -> Any:
    """노드의 평면 칸(`PlaneSpec`)이 기준면을 가리키면 그 원점 · 법선 · X 방향으로 바꾼 사본.
    그래서 스케치 · 자르기 · 단면 · 구배 · 구멍 · 판금이 따로 고치지 않고 기준면을 받는다."""
    updates: dict[str, Any] = {}
    for key in type(node).model_fields:
        value = getattr(node, key)
        if isinstance(value, S.PlaneSpec) and value.datum is not None:
            found = plane(value.datum, made)
            updates[key] = S.PlaneSpec(
                origin=_xyz(found.origin),
                normal=_xyz(found.z_dir),
                x_dir=_xyz(found.x_dir),
            )
    return node.model_copy(update=updates) if updates else node


def make_axis(node: S.DatumAxisNode, made: dict[str, Any]) -> Axis:
    if node.origin is not None and node.direction is not None:
        return Axis(node.origin, _direction(node.direction, "direction"))
    if node.through is not None:
        start, end = (Vector(*one) for one in node.through)
        return Axis(start, _direction(end - start, "through"))
    assert node.target is not None and node.select is not None
    shape = made[node.target]
    what, index = _picked(shape, node.select, ("faces", "edges"))
    if what == "faces":
        face = shape.faces()[index]
        if face.geom_type not in (GeomType.CYLINDER, GeomType.CONE):
            raise DatumError("select: 원통 · 원뿔면이어야 축이 있습니다")
        # 축 위의 점은 **그 면 곁으로** — OCC 가 주는 점은 원통을 만든 자리라 면에서 1 m 넘게
        # 떨어져 있기도 하다(실측: 판 구멍의 축이 z = -1220). 미리보기가 그 점에 축을 그린다.
        line = face.axis_of_rotation
        middle = face.bounding_box().center()
        foot = line.position + line.direction * (middle - line.position).dot(line.direction)
        return Axis(foot, line.direction)
    edge = shape.edges()[index]
    if edge.geom_type != GeomType.LINE:
        raise DatumError("select: 직선 엣지여야 축이 됩니다")
    return Axis(edge.position_at(0), edge.tangent_at(0))


def make_plane(
    node: S.DatumPlaneNode, made: dict[str, Any], resolve_plane: Callable[[S.PlaneSpec], Plane]
) -> Plane:
    """`resolve_plane` 은 평가기의 평면 풀이 — 이름 · 원점 · 법선을 같은 규칙으로 읽는다."""
    if node.plane is not None:
        base = resolve_plane(node.plane)
    elif node.points is not None:
        a, b, c = (Vector(*one) for one in node.points)
        normal = (b - a).cross(c - a)
        if normal.length < 1e-9:
            raise DatumError("points: 세 점이 한 줄 위에 있어 평면이 정해지지 않습니다")
        base = Plane(origin=a, x_dir=(b - a).normalized(), z_dir=normal.normalized())
    else:
        assert node.target is not None and node.select is not None
        shape = made[node.target]
        _, index = _picked(shape, {"what": "faces", **node.select}, ("faces",))
        face = shape.faces()[index]
        if face.geom_type != GeomType.PLANE:
            raise DatumError("select: 평면이어야 기준면이 됩니다")
        base = _settled(face.center(), face.normal_at(face.center()))
    if node.offset:
        base = base.offset(node.offset)
    if node.hinge is not None and node.angle:
        base = _turned(base, axis(node.hinge, made), node.angle)
    return base


def describe(name: str, value: Axis | Plane) -> dict[str, Any]:
    """미리보기가 3D 에 그릴 것 — 축은 점과 방향, 평면은 원점 · 법선 · X 방향."""
    if isinstance(value, Axis):
        return {
            "id": name,
            "kind": "axis",
            "origin": _xyz(value.position),
            "direction": _xyz(value.direction),
        }
    return {
        "id": name,
        "kind": "plane",
        "origin": _xyz(value.origin),
        "normal": _xyz(value.z_dir),
        "x_dir": _xyz(value.x_dir),
    }


def _picked(shape: Any, select: dict[str, Any], kinds: tuple[str, ...]) -> tuple[str, int]:
    """질의가 집는 **하나**. 여럿이면 어느 것인지 모르니 거절한다."""
    if not isinstance(shape, Shape) or is_datum(shape):
        raise DatumError("target: 형상이어야 합니다")
    what = str(select.get("what", "faces"))
    if what not in kinds:
        raise DatumError(f"select.what: {' · '.join(kinds)} 중 하나입니다")
    found = find_features(shape, {**select, "what": what})
    if found["total"] == 0:
        raise DatumError(f"select: 맞는 것이 없습니다 — {select}")
    if not select.get("near") and found["total"] > 1:
        raise DatumError(
            f"select: {found['total']} 개에 맞습니다 — near 로 그중 하나를 고르세요"
        )
    return what, int(found["items"][0]["index"])


def _settled(point: Vector, normal: Vector) -> Plane:
    """형상의 면에서 뽑은 평면 — 원점은 **전역 원점을 그 평면에 내린 점**, X 는 전역 X 를
    평면에 눕힌 방향(X 가 법선과 나란하면 Y).

    면의 무게중심을 원점으로 삼으면 안 된다: 그 면에 뚫린 구멍이 DOE 로 움직이면 무게중심이
    움직이고, 이 면 위에 그린 스케치가 통째로 밀린다(실측 2026-10-02: 구멍을 x=-60 으로
    옮기자 판 윗면의 하중 영역이 0.15 mm 밀렸다). 이렇게 두면 누운 면의 스케치 좌표가 곧 전역
    x · y 다."""
    normal = normal.normalized()
    origin = normal * point.dot(normal)
    across = Vector(1, 0, 0) if abs(normal.X) < 0.99 else Vector(0, 1, 0)
    x_dir = (across - normal * across.dot(normal)).normalized()
    return Plane(origin=origin, x_dir=x_dir, z_dir=normal)


def _turned(base: Plane, hinge: Axis, angle: float) -> Plane:
    turn = gp_Trsf()
    origin, direction = hinge.position, hinge.direction
    turn.SetRotation(
        gp_Ax1(
            gp_Pnt(origin.X, origin.Y, origin.Z), gp_Dir(direction.X, direction.Y, direction.Z)
        ),
        math.radians(angle),
    )
    return Plane(Location(TopLoc_Location(turn)) * base.location)


def _direction(value: Any, where: str) -> Vector:
    vector = Vector(*value) if not isinstance(value, Vector) else value
    if vector.length < 1e-9:
        raise DatumError(f"{where}: 방향의 길이가 0 입니다")
    return vector.normalized()


def _xyz(vector: Any) -> tuple[float, float, float]:
    return (round(float(vector.X), 6), round(float(vector.Y), 6), round(float(vector.Z), 6))
