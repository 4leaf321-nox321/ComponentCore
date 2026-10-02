"""구조 프레임 — 단면을 경로의 부재마다 세우고 꺾인 곳을 잇는다(`frame`).

부재 하나는 단면(지역 XY, 경계상자 가운데가 원점, 위쪽이 +Y)을 부재 방향으로 돌출한 것이다.
꺾인 곳에서는 두 부재를 그 모서리를 덮을 만큼 늘인 뒤 잇는 법대로 자른다:

- miter — 두 방향의 이등분 면에서 자른다(앞 부재는 면의 뒤쪽, 뒤 부재는 앞쪽을 남긴다).
- butt — 앞 부재가 모서리를 덮도록 지나가고, 뒤 부재는 앞 부재의 옆면에서 평평하게 시작한다
  (직각에서 꼭 맞는다 — 비스듬한 모서리는 틈 · 겹침이 조금 생긴다).
- none — 둘 다 모서리까지 늘여 겹친다(합치면 모서리가 꽉 찬다).

다른 경로의 부재에 닿는 **열린 끝**(기둥 → 틀)은 `meet: butt` 면 그 부재의 옆면까지 맞춘다 —
늘이거나 줄여서. 절단 목록(`cut_list`)은 이렇게 맞춘 부재의 자를 길이 · 각을 낸다.

늘이는 길이는 단면의 반지름(경계상자 반대각선) r 과 꺾인 각 φ 에서 정한다: 이등분 면이
단면 끝까지 닿는 거리 r · tan(φ/2). 거의 되돌아가는 꺾임(φ > 170°)은 맞댈 면이 없어 거절한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from build123d import (
    Circle,
    Keep,
    Part,
    Plane,
    Polygon,
    Pos,
    Rectangle,
    Rot,
    Shape,
    Sketch,
    Vector,
    extrude,
    split,
)

from app.core.recipe import schema as S

_TOL = 1e-6
#: 이보다 더 꺾이면(거의 되돌아가면) 맞댈 면이 없다.
_MAX_TURN = 170.0


class FrameError(ValueError):
    """사람이 읽고 고칠 수 있는 실패 — 평가기가 노드 id 를 붙인다."""


def section(profile: S.FrameProfile) -> Sketch:
    """단면 — 지역 XY, 경계상자 가운데가 원점, 위쪽이 +Y."""
    if isinstance(profile, S.TSlotProfile):
        return _t_slot(profile)
    if isinstance(profile, S.SquareTubeProfile):
        w, t = profile.width, profile.thickness
        return Rectangle(w, w) - Rectangle(w - 2 * t, w - 2 * t)
    if isinstance(profile, S.RectTubeProfile):
        w, h, t = profile.width, profile.height, profile.thickness
        return Rectangle(w, h) - Rectangle(w - 2 * t, h - 2 * t)
    if isinstance(profile, S.RoundTubeProfile):
        r, t = profile.diameter / 2, profile.thickness
        return Circle(r) - Circle(r - t)
    if isinstance(profile, S.RoundBarProfile):
        return Circle(profile.diameter / 2)
    if isinstance(profile, S.FlatBarProfile):
        return Rectangle(profile.width, profile.height)
    if isinstance(profile, S.AngleProfile):
        w, h, t = profile.width, profile.height, profile.thickness
        return _centered([(0, 0), (w, 0), (w, t), (t, t), (t, h), (0, h)], w, h)
    if isinstance(profile, S.ChannelProfile):
        w, h, t = profile.width, profile.height, profile.thickness
        points = [(0, 0), (w, 0), (w, t), (t, t), (t, h - t), (w, h - t), (w, h), (0, h)]
        return _centered(points, w, h)
    assert isinstance(profile, S.HBeamProfile)
    w, h, tw, tf = profile.width, profile.height, profile.web, profile.flange
    return (
        Pos(0, (h - tf) / 2) * Rectangle(w, tf)
        + Pos(0, -(h - tf) / 2) * Rectangle(w, tf)
        + Rectangle(tw, h - 2 * tf + 0.01)
    )


@dataclass
class Member:
    """부재 하나 — 경로의 점 사이. 늘이기(+) · 줄이기(-)와 끝의 자르는 각까지."""

    path: int
    index: int
    start: Vector
    end: Vector
    direction: Vector
    plane: Plane
    """단면이 놓이는 방향(원점 무관) — 늘일 길이를 재는 데 쓴다."""
    head: float = 0.0
    """시작 쪽으로 늘인 길이(음수면 줄인 것)."""
    tail: float = 0.0
    start_cut: float = 0.0
    """시작 끝의 자르는 각(도) — 0 이면 직각. 45° 맞대기면 꺾인 각의 절반."""
    end_cut: float = 0.0
    start_open: bool = False
    """경로 안에서 이어지지 않은 끝 — 다른 경로의 부재에 닿으면 그 옆면까지 맞춘다."""
    end_open: bool = False
    miters: list[tuple[Vector, Vector, Vector, bool]] = field(default_factory=list)
    """(모서리 점, 들어오는 방향, 나가는 방향, 앞쪽을 남기나) — 이등분 면에서 자른다."""
    solid: Shape | None = None


def frame(node: S.FrameNode) -> Part:
    solids = [one.solid for one in members(node) if one.solid is not None]
    if node.separate:
        return Part(children=solids)
    # 한 번의 불리언으로 — 하나씩 더하면 부재 수만큼 불리언이 돈다.
    whole = Part(children=[solids[0]]).fuse(*solids[1:]) if len(solids) > 1 else solids[0]
    result = whole if isinstance(whole, Part) else Part(children=list(whole.solids()))
    try:
        return result.clean()
    except Exception:  # pragma: no cover — 합친 것은 그대로 쓸 수 있다
        return result


def members(node: S.FrameNode) -> list[Member]:
    """부재들 — 경로 안의 모서리를 잇고, 다른 경로에 닿는 끝을 맞춘 뒤 입체까지."""
    shape = section(node.profile)
    box = shape.bounding_box()
    half = (box.size.X / 2, box.size.Y / 2)
    radius = math.hypot(*half)
    out: list[Member] = []
    for index, path in enumerate(node.paths):
        out += _path_members(node, index, [Vector(*one) for one in path], half, radius)
    if node.meet == "butt":
        _meet(out, half, radius)
    for one in out:
        plane = _member_plane(one.start - one.direction * one.head, one.direction, node.roll)
        length = (one.end - one.start).length + one.head + one.tail
        if length <= _TOL:
            raise FrameError(
                f"paths[{one.path}] 부재 {one.index + 1}: 맞닿는 부재에 맞추니 길이가 남지 "
                "않습니다 — 경로를 늘이세요"
            )
        solid: Shape = extrude(plane * shape, length)
        for point, incoming, outgoing, front in one.miters:
            solid = _keep(solid, point, incoming, outgoing, front=front)
        one.solid = solid
    return out


def cut_list(node: S.FrameNode) -> dict[str, Any]:
    """**절단 목록** — 부재마다 자를 길이(가장 긴 데) · 끝의 자르는 각 · 부피. 지그를 실제로
    만들 때 그대로 주문 · 재단한다. 질량은 재료 밀도 x 부피(알루미늄 2.7 · 강 7.85 g/cm³)."""
    rows = []
    for one in members(node):
        assert one.solid is not None
        along = [vertex.center().dot(one.direction) for vertex in one.solid.vertices()]
        rows.append(
            {
                "path": one.path + 1,
                "member": one.index + 1,
                "length": round(max(along) - min(along), 2),
                "start_cut": round(one.start_cut, 1),
                "end_cut": round(one.end_cut, 1),
                "volume": round(float(one.solid.volume), 1),
            }
        )
    return {
        "profile": describe_profile(node.profile),
        "section_area": round(float(section(node.profile).area), 2),
        "items": rows,
        "count": len(rows),
        "total_length": round(sum(one["length"] for one in rows), 2),
        "total_volume": round(sum(one["volume"] for one in rows), 1),
    }


def describe_profile(profile: S.FrameProfile) -> str:
    """사람이 읽는 단면 이름 — 「알루미늄 프로파일 40」 · 「각관 40x2」."""
    sizes = {
        key: value
        for key, value in profile.model_dump().items()
        if key != "type" and isinstance(value, int | float)
    }
    label = _PROFILE_NAMES.get(profile.type, profile.type)
    return f"{label} " + "x".join(f"{value:g}" for value in sizes.values())


_PROFILE_NAMES = {
    "t_slot": "알루미늄 프로파일",
    "square_tube": "각관",
    "rect_tube": "사각관",
    "round_tube": "원관",
    "round_bar": "환봉",
    "flat_bar": "평철",
    "angle": "앵글",
    "channel": "채널",
    "h_beam": "H 형강",
}


def _path_members(
    node: S.FrameNode,
    index: int,
    points: list[Vector],
    half: tuple[float, float],
    radius: float,
) -> list[Member]:
    where = f"paths[{index}]"
    closed = len(points) > 2 and (points[0] - points[-1]).length < _TOL
    if closed:
        points = points[:-1]
    segments = list(zip(points, points[1:] + ([points[0]] if closed else []), strict=False))
    for start, end in segments:
        if (end - start).length < _TOL:
            raise FrameError(f"{where}: 같은 점이 잇달아 있어 길이 0 인 부재가 됩니다")
    count = len(segments)
    out = []
    for i, (start, end) in enumerate(segments):
        direction = (end - start).normalized()
        out.append(
            Member(
                path=index,
                index=i,
                start=start,
                end=end,
                direction=direction,
                plane=_member_plane(Vector(0, 0, 0), direction, node.roll),
                start_open=i == 0 and not closed,
                end_open=i == count - 1 and not closed,
            )
        )

    def turn_at(i: int) -> float | None:
        """부재 i 의 끝에서 다음 부재로 꺾이는 각(도). 끝이 열려 있으면 None."""
        if out[i].end_open:
            return None
        j = (i + 1) % count
        turn = out[i].direction.get_angle(out[j].direction)  # build123d 는 도로 준다
        if turn > _MAX_TURN:
            raise FrameError(
                f"{where}: 점 {j} 에서 {turn:.0f}° 로 거의 되돌아갑니다 — 맞댈 면이 없습니다"
            )
        return turn

    def reach(along: Vector, other: Member, turn: float) -> float:
        """`along` 쪽으로 늘일 길이 — 이웃 부재를 덮을 만큼."""
        if node.corner == "miter":
            return radius * math.tan(math.radians(turn) / 2) + 1.0
        # 맞대기 · 겹치기 — 이웃 단면이 그 방향으로 뻗은 만큼(꺾인 각만큼 비스듬하면 더).
        return _spread(along, other.plane, half) / math.sin(math.radians(turn))

    for i, one in enumerate(out):
        turn = turn_at(i)
        if turn is None or turn < 1e-3:
            continue  # 열린 끝, 또는 곧게 이어진다 — 맞닿는 면이 곧 끝면이다
        j = (i + 1) % count
        after = out[j]
        one.tail = reach(one.direction, after, turn)
        after.head = reach(after.direction, one, turn)
        if node.corner == "butt":
            # 뒤 부재는 앞 부재의 옆면에서 평평하게 시작한다 — 앞 부재가 모서리를 덮는다.
            # 앞 부재를 빼서 깎으면 속 빈 관에서는 벽 조각이 앞 부재의 속에 남는다(실측).
            after.head = -after.head
        if node.corner == "miter":
            one.miters.append((one.end, one.direction, after.direction, False))
            after.miters.append((one.end, one.direction, after.direction, True))
            one.end_cut = after.start_cut = turn / 2
    return out


def _meet(all_members: list[Member], half: tuple[float, float], radius: float) -> None:
    """경로 안에서 이어지지 않은 끝이 **다른 경로의 부재**에 닿으면 그 옆면까지 맞춘다 —
    기둥이 틀 부재에 닿는 자리. 닿는다 = 끝점이 그 부재의 단면 안(중심선에서 단면 반지름
    이내). 모자라면 늘이고 넘치면 줄인다. 여럿에 닿으면(틀의 모서리) 가장 많이 줄이는 쪽."""
    for one in all_members:
        for at_end in (False, True):
            if not (one.end_open if at_end else one.start_open):
                continue
            point = one.end if at_end else one.start
            outward = one.direction if at_end else -one.direction
            best: float | None = None
            for other in all_members:
                if other.path == one.path or abs(outward.dot(other.direction)) > 0.99:
                    continue
                closest = _closest(point, other.start, other.end)
                if (closest - point).length > radius + _TOL:
                    continue
                shift = (closest - point).dot(outward) - _spread(outward, other.plane, half)
                best = shift if best is None else min(best, shift)
            if best is None:
                continue
            if at_end:
                one.tail += best
            else:
                one.head += best


def _spread(along: Vector, plane: Plane, half: tuple[float, float]) -> float:
    """단면이 `along` 쪽으로 뻗은 길이 — 경계상자로."""
    return abs(along.dot(plane.x_dir)) * half[0] + abs(along.dot(plane.y_dir)) * half[1]


def _closest(point: Vector, start: Vector, end: Vector) -> Vector:
    span = end - start
    t = max(0.0, min(1.0, (point - start).dot(span) / span.dot(span)))
    return start + span * t


def _keep(
    solid: Shape, point: Vector, incoming: Vector, outgoing: Vector, *, front: bool
) -> Shape:
    """이등분 면에서 잘라 한쪽을 남긴다 — 들어오는 부재는 면의 뒤쪽, 나가는 부재는 앞쪽."""
    normal = incoming + outgoing
    if normal.length < _TOL:  # pragma: no cover — _MAX_TURN 이 막는다
        return solid
    cut = Plane(origin=point, z_dir=normal.normalized())
    return split(solid, bisect_by=cut, keep=Keep.TOP if front else Keep.BOTTOM)


def _member_plane(origin: Vector, direction: Vector, roll: float) -> Plane:
    """부재의 단면 평면 — 법선이 부재 방향, 단면의 위쪽(+Y)이 +Z(부재가 서 있으면 +X)."""
    up = Vector(0, 0, 1) if abs(direction.Z) < 0.99 else Vector(1, 0, 0)
    y_dir = (up - direction * up.dot(direction)).normalized()
    x_dir = y_dir.cross(direction)
    if roll:
        # 부재 축 둘레로 — `Plane.rotated` 는 법선까지 돌려 부재 방향이 바뀐다(실측).
        turn = math.radians(roll)
        x_dir = x_dir * math.cos(turn) + y_dir * math.sin(turn)
    return Plane(origin=origin, x_dir=x_dir, z_dir=direction)


def _t_slot(profile: S.TSlotProfile) -> Sketch:
    size = float(round(profile.size))
    opening, lip, inner, depth, bore = S.T_SLOT_SERIES[int(size)]
    half = size / 2
    out: Sketch = Rectangle(size, size)
    for angle in (0, 90, 180, 270):
        mouth = Pos(0, half - lip / 2 + 0.05) * Rectangle(opening, lip + 0.1)
        cavity = Polygon(
            (-inner / 2, half - lip),
            (inner / 2, half - lip),
            (opening / 2, half - depth),
            (-opening / 2, half - depth),
        )
        out = out - Rot(0, 0, angle) * mouth - Rot(0, 0, angle) * cavity
    return out - Circle(bore / 2)


def _centered(points: list[tuple[float, float]], width: float, height: float) -> Sketch:
    return Polygon(*[(x - width / 2, y - height / 2) for x, y in points])
