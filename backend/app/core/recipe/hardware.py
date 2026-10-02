"""표준 부품 — 너트 · 와셔 · 베어링 · 압축 스프링 · 프로파일 코너 브래킷, 그리고 **구멍에 맞춰
놓기**(`fasten`).

부품은 원점에서 +Z 로 서게 만든 뒤 `at` · `direction` 의 자리로 옮긴다. `fasten` 은 구멍을
규칙으로 찾아(구멍 축 · 끝 · 지름) 구멍마다 같은 일을 한다 — 좌표를 적지 않으니 DOE 가 구멍을
옮겨도 부품이 따라간다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from build123d import (
    Box,
    Circle,
    Cylinder,
    Helix,
    Location,
    Part,
    Plane,
    Pos,
    RegularPolygon,
    Shape,
    Vector,
    extrude,
    sweep,
)

from app.core.recipe import defeature
from app.core.recipe import schema as S
from app.core.recipe.query import select_features


class HardwareError(ValueError):
    """사람이 읽고 고칠 수 있는 실패 — 평가기가 노드 id 를 붙인다."""


def placed(shape: Shape, at: Vector, direction: Vector) -> Shape:
    """원점에서 +Z 로 선 부품을 `at` 에, +Z 가 `direction` 을 보게."""
    if direction.length < 1e-9:
        raise HardwareError("direction: 길이 0 인 방향입니다")
    return Plane(origin=at, z_dir=direction.normalized()).location * shape


def nut(thread: str) -> Part:
    across, height = S.NUTS[thread]
    major = float(thread[1:])
    body = extrude(RegularPolygon(across / 3**0.5, 6), height)
    return body - Pos(0, 0, height / 2) * Cylinder(major / 2, height * 2)


def washer(thread: str) -> Part:
    inner, outer, thickness = S.WASHERS[thread]
    return extrude(Circle(outer / 2) - Circle(inner / 2), thickness)


def bearing(designation: str) -> Part:
    inner, outer, width = S.BEARINGS[designation]
    return extrude(Circle(outer / 2) - Circle(inner / 2), width)


def spring(node: S.SpringNode) -> Part:
    pitch = (node.length - node.wire) / node.coils
    path = Helix(pitch=pitch, height=pitch * node.coils, radius=node.diameter / 2)
    start = Plane(origin=path.position_at(0), z_dir=path.tangent_at(0))
    coil = sweep(start * Circle(node.wire / 2), path, is_frenet=True)
    return Pos(0, 0, node.wire / 2) * coil


def bracket(node: S.BracketNode) -> Shape:
    leg, width, thickness, hole = S.BRACKETS[round(node.size)]
    first, second = (Vector(*one).normalized() for one in node.legs)
    # 지역 좌표: X = 첫 다리, Z = 둘째 다리. 다리는 모서리에서 두께만큼 안쪽(빈 쪽)으로 선다.
    flat = Pos(leg / 2, 0, thickness / 2) * Box(leg, width, thickness)
    up = Pos(thickness / 2, 0, leg / 2) * Box(thickness, width, leg)
    body: Part = flat + up
    at_hole = thickness + (leg - thickness) / 2
    body = body - Pos(at_hole, 0, thickness / 2) * Cylinder(hole / 2, thickness * 3)
    body = body - Pos(thickness / 2, 0, at_hole) * (
        Location((0, 0, 0), (0, 1, 0), 90) * Cylinder(hole / 2, thickness * 3)
    )
    frame = Plane(origin=Vector(*node.at), x_dir=first, z_dir=second)
    return frame.location * body


# --- 구멍에 맞춰 놓기 -----------------------------------------------------------------


@dataclass
class Hole:
    """구멍 하나 — 고른 끝(`seat`)과 그 끝에서 바깥(재료 밖)을 보는 방향, 반대쪽 끝, 깊이 ·
    지름. 카운터보어면 가장 가는 구멍의 끝이 자리다."""

    seat: Vector
    outward: Vector
    far: Vector
    depth: float
    diameter: float


def holes(part: Part, query: dict[str, object], side: str) -> list[Hole]:
    matched = {
        part.faces()[row["index"]]
        for row in select_features(part, {**query, "what": "faces"})["items"]
    }
    out: list[Hole] = []
    for (point, direction), walls in defeature.hole_walls(part).items():
        if not any(one in matched for one in walls):
            continue
        axis_point, axis = Vector(*point), Vector(*direction)
        thinnest = min(float(one.radius) for one in walls)
        core = [one for one in walls if abs(float(one.radius) - thinnest) < 1e-6]
        along = [
            (vertex.center() - axis_point).dot(axis)
            for one in core
            for vertex in one.vertices()
        ]
        low, high = axis_point + axis * min(along), axis_point + axis * max(along)
        high_is_up = _rank(high) >= _rank(low)
        take_high = high_is_up if side == "top" else not high_is_up
        seat, far = (high, low) if take_high else (low, high)
        out.append(
            Hole(
                seat=seat,
                outward=axis if take_high else -axis,
                far=far,
                depth=max(along) - min(along),
                diameter=2 * thinnest,
            )
        )
    if not out:
        raise HardwareError(f"holes: 규칙에 맞는 구멍이 없습니다 — {query}")
    return sorted(
        out, key=lambda one: (round(one.seat.X, 3), round(one.seat.Y, 3), round(one.seat.Z, 3))
    )


def thread_for(diameter: float) -> str:
    """구멍 지름에 맞는 나사 — 여유 구멍(±0.3) 또는 탭 드릴(±0.2)."""
    for name, (tap, clearance, *_rest) in S.THREADS.items():
        if abs(diameter - clearance) <= 0.3 or abs(diameter - tap) <= 0.2:
            return name
    raise HardwareError(
        f"지름 {diameter:g} 구멍에 맞는 나사(M3 ~ M12)가 없습니다 — thread 를 주세요"
    )


def fasten(part: Part, node: S.FastenNode, make_bolt: Callable[[S.BoltNode], Part]) -> Part:
    pieces: list[Shape] = []
    for one in holes(part, node.holes, node.side):
        if node.part == "pin":
            length = node.length or one.depth + one.diameter
            pin = Pos(0, 0, length / 2) * Cylinder(one.diameter / 2, length)
            pieces.append(placed(pin, one.far, one.outward))
            continue
        thread = node.thread or thread_for(one.diameter)
        if node.part == "bolt":
            bolt = make_bolt(
                S.BoltNode(
                    id="fasten",
                    op="bolt",
                    at=(0.0, 0.0, 0.0),
                    nominal=float(thread[1:]),
                    length=node.length or round(one.depth, 3),
                    head=node.head,
                    washer=node.washer,
                    down=True,
                )
            )
            pieces.append(placed(bolt, one.seat, one.outward))
        elif node.part == "nut":
            pieces.append(placed(nut(thread), one.seat, one.outward))
        else:
            pieces.append(placed(washer(thread), one.seat, one.outward))
    return Part(children=pieces)


def _rank(point: Vector) -> tuple[float, float, float]:
    """「위」 의 순서 — Z, 같으면 X, 그다음 Y."""
    return (round(point.Z, 6), round(point.X, 6), round(point.Y, 6))
