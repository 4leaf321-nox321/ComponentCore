"""3단계 — Fixture Planning.

3-2-1 원칙의 뼈대다: 바닥을 받침 3~4 개로 받치고(Z · 두 회전), 옆을 로케이터로 잡고
(X · Y · 남은 회전), 위에서 클램프로 누른다. 여기서는 **어디에 무엇을 둘지**만 정한다 —
치수와 형상은 elements/ 가 만든다.

모든 위치는 **정규화 좌표계**(제품 바닥 z=0)다. 판 윗면은 z = -product_lift 가 아니라,
조립 단계에서 제품을 product_lift 만큼 올려 판 윗면을 z=0 으로 둔다(assembly.py).
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from build123d import Face, Vector
from pydantic import ValidationError

from app.core import fasteners, standard
from app.core import features as feat
from app.core.model import (
    XYZ,
    BasePlateSpec,
    BoltSpec,
    ClampSpec,
    Feature,
    FixturePlan,
    ImpactorSpec,
    LocatorSpec,
    NoseSpec,
    ProductGeometry,
    RollerSpec,
    SupportSpec,
)
from app.core.options import JigOptions
from app.core.specimens import bending
from app.core.specimens.presets import BendingSetup


class PlanningError(ValueError):
    """이 제품에는 지그를 계획할 수 없다. 메시지는 화면에 그대로 나간다."""


# --- 받침 ---------------------------------------------------------------------


def _inset_rectangle(face: Face, inset: float) -> list[tuple[float, float]]:
    box = face.bounding_box()
    x0, x1 = box.min.X + inset, box.max.X - inset
    y0, y1 = box.min.Y + inset, box.max.Y - inset
    if x1 <= x0 or y1 <= y0:
        cx, cy = face.center().X, face.center().Y
        return [(cx, cy)]
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _on_face(face: Face, x: float, y: float, radius: float) -> bool:
    """받침 윗면이 통째로 바닥면 안에 놓이는가 — 중심과 네 방향 끝을 본다."""
    z = face.center().Z
    probes = [(x, y)] + [
        (x + radius * math.cos(a), y + radius * math.sin(a))
        for a in (k * math.pi / 4 for k in range(8))
    ]
    return all(face.is_inside((px, py, z)) for px, py in probes)


def _bottom_holes(features: list[Feature]) -> list[tuple[float, float, float]]:
    """바닥으로 열린 구멍의 (x, y, 반지름). 받침이 구멍을 덮으면 핀과 겹치거나 허공을
    받친다."""
    return [
        (one.center[0], one.center[1], one.radius)
        for one in features
        if one.kind == "hole" and one.radius is not None and abs(one.center[2]) < 0.5
    ]


def _clear_of_holes(
    x: float, y: float, radius: float, holes: list[tuple[float, float, float]]
) -> bool:
    return all(math.dist((x, y), (hx, hy)) >= radius + hr + 1.0 for hx, hy, hr in holes)


def _nudge_inward(
    face: Face,
    x: float,
    y: float,
    radius: float,
    holes: list[tuple[float, float, float]],
) -> tuple[float, float] | None:
    """모서리가 구멍에 걸리면 바닥면 중심 쪽으로 조금씩 옮겨 본다. 못 찾으면 None."""
    cx, cy = face.center().X, face.center().Y
    dx, dy = cx - x, cy - y
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    ux, uy = dx / length, dy / length
    step = 2.0
    for k in range(1, int(length / step)):
        nx, ny = x + ux * step * k, y + uy * step * k
        if _on_face(face, nx, ny, radius) and _clear_of_holes(nx, ny, radius, holes):
            return nx, ny
    return None


def _pick_supports(
    geometry: ProductGeometry, features: list[Feature], opts: JigOptions, notes: list[str]
) -> list[SupportSpec]:
    bottom = feat.bottom_face(geometry)
    radius = opts.support_diameter / 2
    inset = max(opts.support_inset, radius + 1.0)
    corners = _inset_rectangle(bottom, inset)
    holes = _bottom_holes(features)

    wanted = 3 if opts.support_count <= 3 else 4
    if wanted == 3 and len(corners) == 4:
        # 삼각 배치 — 대각 둘과 나머지 한 변의 중점.
        (x0, y0), (x1, _), (_, y1), _ = corners
        corners = [(x0, y0), (x1, y0), ((x0 + x1) / 2, y1)]

    picked: list[tuple[float, float]] = []
    nudged = False
    for x, y in corners:
        if _on_face(bottom, x, y, radius) and _clear_of_holes(x, y, radius, holes):
            picked.append((x, y))
            continue
        moved = _nudge_inward(bottom, x, y, radius, holes)
        if moved is not None:
            picked.append(moved)
            nudged = True
    if nudged:
        notes.append("바닥면 모서리에 받침을 배치할 수 없어 안쪽으로 옮겼습니다.")
    if len(picked) < 3:
        raise PlanningError(
            "바닥면에 받침 3개를 배치할 공간이 없습니다. 바닥이 너무 좁거나 구멍이 많습니다."
        )
    return [
        SupportSpec(
            label=f"받침_{index + 1}",
            position=(round(x, 3), round(y, 3), 0.0),
            diameter=opts.support_diameter,
            height=opts.support_height,
        )
        for index, (x, y) in enumerate(picked)
    ]


# --- 로케이터 -----------------------------------------------------------------


def _farthest_pair(holes: list[Feature]) -> list[Feature]:
    if len(holes) <= 2:
        return holes
    best: tuple[float, list[Feature]] = (-1.0, holes[:2])
    for i, a in enumerate(holes):
        for b in holes[i + 1 :]:
            d = math.dist(a.center[:2], b.center[:2])
            if d > best[0]:
                best = (d, [a, b])
    return best[1]


def _pin_locators(features: list[Feature], opts: JigOptions) -> list[LocatorSpec]:
    """바닥으로 열린 수직 구멍 → 핀. 가장 멀리 떨어진 둘을 고른다(회전 구속이 가장 좋다).

    관통이 아니어도 된다 — 바닥에서 시작하면 판에서 세운 핀이 들어간다. 위에서만 열린
    구멍(center.z > 0)은 못 쓴다.
    """
    holes = [
        one
        for one in features
        if one.kind == "hole"
        and one.radius is not None
        and one.depth is not None
        and abs(one.center[2]) < 0.5
    ]
    chosen = _farthest_pair(holes)[: opts.locator_pin_max_count]
    out: list[LocatorSpec] = []
    for index, hole in enumerate(chosen):
        assert hole.radius is not None and hole.depth is not None
        out.append(
            LocatorSpec(
                label=f"위치_핀_{index + 1}",
                kind="pin",
                position=(hole.center[0], hole.center[1], 0.0),
                direction=(0.0, 0.0, 1.0),
                diameter=round(2 * (hole.radius - opts.locator_pin_clearance), 3),
                engagement=round(min(hole.depth * 0.8, opts.locator_pin_max_engagement), 3),
            )
        )
    return out


def _side_holes(features: list[Feature]) -> list[Feature]:
    """옆으로 난 구멍 중 축이 X · Y 에 나란한 것 — 측면 핀이 들어갈 수 있다."""
    return [
        one
        for one in features
        if one.kind == "hole"
        and one.role in ("side_through", "side_blind")
        and one.radius is not None
        and one.depth is not None
        and one.axis is not None
    ]


def _openings(hole: Feature) -> list[tuple[float, float, float]]:
    """옆 구멍의 두 입구(축 위, 구멍 양 끝)."""
    assert hole.axis is not None and hole.depth is not None
    i = 0 if abs(hole.axis[0]) > 0.5 else 1
    out = []
    for sign in (-1, 1):
        point = list(hole.center)
        point[i] += sign * hole.depth / 2
        out.append((point[0], point[1], point[2]))
    return out


def _covers_hole(
    face: Face, block: Vector, along: Vector, w: float, top: float, holes: list[Feature]
) -> bool:
    """옆면에 기댈 받침대 블록이 그 면의 옆 구멍 입구를 덮는가 — 덮으면 반쯤 허공을 민다."""
    center = face.center()
    normal = face.normal_at(center)
    for hole in holes:
        assert hole.radius is not None
        for x, y, z in _openings(hole):
            point = Vector(x, y, z)
            if abs((point - center).dot(normal)) > 0.5:
                continue  # 이 면의 입구가 아니다
            side = abs((point - block).dot(along))
            if side < w / 2 + hole.radius + 1.0 and z - hole.radius < top:
                return True
    return False


def _rest_locators(
    geometry: ProductGeometry, opts: JigOptions, avoid: list[Feature] | None = None
) -> list[LocatorSpec]:
    """옆면 레스트 — 가장 넓은 옆면에 둘, 그와 직교하는 옆면에 하나(2-1). 옆 구멍(`avoid`)의
    입구는 덮지 않는다 — 덮이면 그 자리를 비켜 같은 면의 다른 자리를 찾는다."""
    sides = feat.side_faces(geometry)
    if not sides:
        return []
    w, d, h = opts.locator_rest_size
    holes = avoid or []
    out: list[LocatorSpec] = []

    def place(face: Face, count: int) -> None:
        center = face.center()
        normal = face.normal_at(center)
        inward = Vector(-normal.X, -normal.Y, 0).normalized()
        along = Vector(-inward.Y, inward.X, 0)
        box = face.bounding_box()
        span = max(box.size.X, box.size.Y)
        # 레스트 높이의 절반이 제품 안에 들어가지 않게, 바닥에서 h/2 위 — 단 제품이 낮으면
        # 중간.
        z = min(h / 2, geometry.bbox.max[2] / 2)
        wide = count == 2 and span > 3 * w
        preferred = [-span / 4, span / 4] if wide else [0.0]
        spare = [-span / 3, span / 3, -span / 6, span / 6, 0.0] if span > 2 * w else []
        offsets = [
            one
            for one in [*preferred, *spare]
            if not _covers_hole(face, center + along * one, along, w, z + h / 2, holes)
        ]
        for offset in offsets[:count]:
            point = center + along * offset
            # 레스트 블록의 중심은 면에서 **바깥**으로 d/2 만큼.
            block = point - inward * (d / 2)
            out.append(
                LocatorSpec(
                    label=f"받침대_{len(out) + 1}",
                    kind="rest",
                    position=(round(block.X, 3), round(block.Y, 3), round(z, 3)),
                    direction=(round(inward.X, 3), round(inward.Y, 3), 0.0),
                    size=(w, d, h),
                )
            )

    primary = sides[0]
    place(primary, 2)
    primary_n = primary.normal_at(primary.center())
    for face in sides[1:]:
        n = face.normal_at(face.center())
        if abs(n.dot(primary_n)) < 0.2:  # 직교하는 면
            place(face, 1)
            break
    return out


def _side_pin_locators(
    geometry: ProductGeometry, features: list[Feature], opts: JigOptions
) -> list[LocatorSpec]:
    """옆 구멍 → **측면 위치 핀** 하나 — 판에 세운 블록에서 가로 핀이 구멍으로 들어간다.

    블록은 제품 바깥에 서야 하므로 입구가 제품의 **바깥 옆면**(상자 끝)에 있는 구멍만 쓴다.
    낮은 것부터 — 블록이 작고 단단하다. 하나면 된다: 핀이 두 방향과 회전을, 블록이 핀 축 방향
    한쪽을 잡고, 받침 · 클램프가 나머지를 잡는다."""
    w, d, _ = opts.locator_rest_size
    for hole in sorted(_side_holes(features), key=lambda one: one.center[2]):
        assert hole.radius is not None and hole.depth is not None and hole.axis is not None
        i = 0 if abs(hole.axis[0]) > 0.5 else 1
        low, high = _openings(hole)
        if abs(low[i] - geometry.bbox.min[i]) < 0.5:
            opening, sign = low, 1.0
        elif abs(high[i] - geometry.bbox.max[i]) < 0.5:
            opening, sign = high, -1.0
        else:
            continue  # 바깥 옆면에서 열리지 않는다 — 블록이 설 자리가 없다
        diameter = 2 * (hole.radius - opts.locator_pin_clearance)
        if diameter < 2.0:
            continue
        direction = [0.0, 0.0, 0.0]
        direction[i] = sign
        return [
            LocatorSpec(
                label="측면_핀_1",
                kind="side_pin",
                position=(round(opening[0], 3), round(opening[1], 3), round(opening[2], 3)),
                direction=(direction[0], direction[1], 0.0),
                diameter=round(diameter, 3),
                engagement=round(min(hole.depth * 0.8, opts.locator_pin_max_engagement), 3),
                size=(round(max(w, diameter * 2.5), 3), d, 0.0),
            )
        ]
    return []


def _pick_locators(
    geometry: ProductGeometry, features: list[Feature], opts: JigOptions, notes: list[str]
) -> list[LocatorSpec]:
    pins = _pin_locators(features, opts)
    if len(pins) >= 2:
        notes.append(f"관통 구멍 {len(pins)}개를 핀 로케이터로 사용합니다.")
        return pins
    side_holes = _side_holes(features)
    side = _side_pin_locators(geometry, features, opts)
    rests = _rest_locators(geometry, opts, avoid=side_holes)
    if pins and side:
        notes.append("바닥 구멍이 하나뿐이므로 핀 1개와 옆 구멍의 측면 핀을 함께 사용합니다.")
        return [*pins, *side]
    if side:
        # 측면 핀의 축과 나란한 옆면은 블록이 이미 닿는다 — 받침대는 그와 직교하는 면에 하나.
        axis = side[0].direction
        across = [
            one
            for one in rests
            if abs(one.direction[0] * axis[0] + one.direction[1] * axis[1]) < 0.2
        ]
        notes.append(
            "바닥에 구멍이 없어 옆 구멍에 측면 핀을 꽂고"
            + (
                " 직교하는 옆면 받침대로 위치를 결정합니다."
                if across
                else " 위치를 결정합니다."
            )
        )
        return [*side, *across[:1]]
    if pins:
        notes.append("관통 구멍이 하나뿐이므로 핀 1개와 옆면 레스트를 함께 사용합니다.")
        return [*pins, *rests[:1]]
    if rests:
        notes.append("구멍이 없어 옆면 레스트(2-1)로 위치를 결정합니다.")
    else:
        notes.append(
            "옆면과 구멍이 모두 없어 로케이터를 배치하지 못했습니다. 받침과 클램프만 "
            "배치합니다."
        )
    return rests


# --- 클램프 -------------------------------------------------------------------


def _post_hits_rest(px: float, py: float, post: float, rests: list[LocatorSpec]) -> bool:
    for rest in rests:
        if rest.size is None:
            continue
        w, d, _ = rest.size
        half = max(w, d) / 2 + post / 2 + 1.0
        if abs(px - rest.position[0]) < half and abs(py - rest.position[1]) < half:
            return True
    return False


def _arm_clear(
    geometry: ProductGeometry,
    pad: tuple[float, float, float],
    post: tuple[float, float],
    opts: JigOptions,
) -> bool:
    """팔이 기둥에서 패드까지 가는 길 위에 제품이 없나 — 팔 높이에서 제품 안을 지나면 관통이다.

    실측: 벽 앞의 바닥판을 누르려는 클램프의 기둥이 벽 **뒤** 에 서서 팔이 벽을 뚫고 갔다. 간섭
    검사가 잡았지만 계획이 먼저 피해야 사람이 고칠 일이 안 된다."""
    x, y, z = pad
    px, py = post
    arm_z = z + opts.clamp_clearance_above + opts.clamp_arm_thickness / 2
    steps = 12
    for k in range(1, steps):
        t = k / steps
        sx, sy = px + (x - px) * t, py + (y - py) * t
        if geometry.shape.is_inside((sx, sy, arm_z)):
            return False
    return True


def _place_post(
    geometry: ProductGeometry,
    pad: tuple[float, float, float],
    half_x: float,
    half_y: float,
    margin: float,
    opts: JigOptions,
    rests: list[LocatorSpec],
) -> tuple[float, float] | None:
    """패드에서 가장 가까운 제품 바깥 변에 기둥을 세운다. 레스트와 겹치거나 팔이 제품을 지나면
    다른 변, 그래도 안 되면 변을 따라 옮긴다. 어디도 안 되면 None — 그 패드 자리는 버린다."""
    x, y, _ = pad
    post = opts.clamp_post_size
    dx, dy = half_x - abs(x), half_y - abs(y)
    on_x_edge = (math.copysign(half_x + margin / 2, x or 1), y)
    on_y_edge = (x, math.copysign(half_y + margin / 2, y or 1))
    near = [on_x_edge, on_y_edge] if dx <= dy else [on_y_edge, on_x_edge]
    candidates = [*near, (-on_x_edge[0], y), (x, -on_y_edge[1])]

    def ok(px: float, py: float) -> bool:
        return not _post_hits_rest(px, py, post, rests) and _arm_clear(
            geometry, pad, (px, py), opts
        )

    for px, py in candidates:
        if ok(px, py):
            return px, py
    # 판 모서리(여유 폭의 절반)까지는 나가도 된다 — 기둥은 제품이 아니라 판 위에 선다.
    limit_y, limit_x = half_y + margin / 2, half_x + margin / 2
    for px, py in candidates:
        along_y = abs(px) > half_x  # X 쪽 변에 섰으면 Y 를 따라 옮긴다
        for k in range(1, 12):
            for sign in (1, -1):
                shift = sign * k * post / 2
                nx, ny = (px, py + shift) if along_y else (px + shift, py)
                if (abs(ny) > limit_y) if along_y else (abs(nx) > limit_x):
                    continue
                if ok(nx, ny):
                    return nx, ny
    return None


def _pick_clamps(
    geometry: ProductGeometry, locators: list[LocatorSpec], opts: JigOptions, notes: list[str]
) -> list[ClampSpec]:
    ups = feat.upward_faces(geometry)
    # 포켓 바닥은 뺀다 — 팔이 벽을 넘어 들어가야 하고, 바닥이 얇아 휜다.
    tops = [face for face in ups if not feat.is_pocket_floor(geometry, face)]
    if len(tops) < len(ups):
        notes.append(f"포켓 바닥 {len(ups) - len(tops)}곳은 클램프 위치에서 제외했습니다.")
    if not tops or opts.clamp_count <= 0:
        notes.append("윗면에 평면이 없어 클램프를 배치하지 못했습니다.")
        return []
    pad_r = opts.clamp_pad_diameter / 2
    size_x, size_y = geometry.bbox.size[0], geometry.bbox.size[1]
    half_x, half_y = size_x / 2, size_y / 2

    # 후보: 가장 넓은 윗면들의 들여 놓은 모서리 · 변의 중점 · 중심. 패드가 면 안에 온전히
    # 들어가야 한다. 모서리만 보면 모서리마다 구멍이 있는 부품에서 후보가 하나도 안 남는다
    # (실측).
    candidates: list[tuple[float, float, float]] = []
    for face in tops[:3]:
        z = face.center().Z
        corners = _inset_rectangle(face, pad_r + 2)
        points = [*corners, (face.center().X, face.center().Y)]
        if len(corners) == 4:
            (x0, y0), (x1, _), (_, y1), _ = corners
            points += [
                ((x0 + x1) / 2, y0),
                ((x0 + x1) / 2, y1),
                (x0, (y0 + y1) / 2),
                (x1, (y0 + y1) / 2),
            ]
        for x, y in points:
            if _on_face(face, x, y, pad_r) and (x, y, z) not in candidates:
                candidates.append((x, y, z))
    if not candidates:
        notes.append("클램프 패드를 완전히 올릴 수 있는 윗면이 없습니다.")
        return []

    # 서로 가장 멀리 떨어진 것부터 고른다 — 한쪽만 누르면 반대쪽이 들린다.
    chosen: list[tuple[float, float, float]] = [
        max(candidates, key=lambda c: abs(c[0]) + abs(c[1]))
    ]
    # 팔끼리 겹치지 않을 만큼은 떨어져야 한다 — 작은 부품에서는 클램프 하나로 줄어든다.
    apart = opts.clamp_arm_width + opts.clamp_pad_diameter
    while len(chosen) < opts.clamp_count and len(chosen) < len(candidates):
        rest = [c for c in candidates if c not in chosen]
        best = max(rest, key=lambda c: min(math.dist(c[:2], k[:2]) for k in chosen))
        if min(math.dist(best[:2], k[:2]) for k in chosen) < apart:
            notes.append(f"윗면이 좁아 클램프를 {len(chosen)}개만 배치합니다.")
            break
        chosen.append(best)

    if len(chosen) < opts.clamp_count and not any("클램프를" in n for n in notes):
        notes.append(
            f"클램프 {opts.clamp_count}개를 지정했지만 패드를 놓을 수 있는 위치가 "
            f"{len(chosen)}곳뿐입니다. 구멍과 가장자리를 피할 수 있는 위치가 그만큼입니다."
        )
    margin = opts.plate_margin
    post = opts.clamp_post_size
    # 기둥이 피할 것 — 옆면 받침대와 측면 핀의 블록.
    rests = [one for one in locators if one.kind in ("rest", "side_pin")]
    if margin / 2 < post / 2 + 1:
        notes.append("판 여유(plate_margin)가 좁아 클램프 기둥이 제품에 닿을 수 있습니다.")
    out: list[ClampSpec] = []
    for x, y, z in chosen:
        # 기둥은 패드에서 가장 가까운 제품 바깥 변에, 판 여유의 한가운데 선다.
        placed = _place_post(geometry, (x, y, z), half_x, half_y, margin, opts, rests)
        if placed is None:
            notes.append(
                f"({x:.0f}, {y:.0f}) 위치는 클램프 팔이 제품을 통과해야 하므로 클램프를 "
                "배치하지 않았습니다."
            )
            continue
        px, py = placed
        index = len(out)
        out.append(
            ClampSpec(
                label=f"클램프_{index + 1}",
                pad_position=(round(x, 3), round(y, 3), round(z, 3)),
                post_position=(round(px, 3), round(py, 3), 0.0),
                pad_diameter=opts.clamp_pad_diameter,
                arm_width=opts.clamp_arm_width,
                arm_thickness=opts.clamp_arm_thickness,
            )
        )
    return out


# --- 계획 ---------------------------------------------------------------------


def _plate(geometry: ProductGeometry, opts: JigOptions) -> BasePlateSpec:
    size = geometry.bbox.size
    return BasePlateSpec(
        length=round(size[0] + 2 * opts.plate_margin, 1),
        width=round(size[1] + 2 * opts.plate_margin, 1),
        thickness=opts.plate_thickness,
        mount_hole_diameter=opts.plate_mount_hole_diameter,
    )


def _standard_clamp(
    geometry: ProductGeometry,
    clamp: ClampSpec,
    lift: float,
    opts: JigOptions,
    avoid: list[LocatorSpec],
    taken: list[ClampSpec],
    library: list[standard.LibraryPart],
) -> ClampSpec | None:
    """토글 클램프 — 패드 자리에 패드 중심이 오도록 베이스를 놓는다. 베이스는 제품 밖(상자
    밖)에 서고, 팔이 제품을 지나지 않으며, 받침대 · 측면 핀 · 다른 클램프와 겹치지 않아야
    한다. 누르는 높이가 모자라면 베이스를 **받침 블록**에 올린다(넘치면 못 쓴다). 방향은 즉석
    클램프가 고른 쪽부터, 다음은 가까운 바깥 변 쪽."""
    x, y, z = clamp.pad_position
    px, py, _ = clamp.post_position
    half_x, half_y = geometry.bbox.size[0] / 2, geometry.bbox.size[1] / 2
    first = math.atan2(y - py, x - px)
    edges = sorted(
        [
            (half_x - x, 0.0),
            (half_x + x, math.pi),
            (half_y - y, math.pi / 2),
            (half_y + y, -math.pi / 2),
        ]
    )
    directions = [first, *(angle for _, angle in edges)]
    for item in standard.clamps(library):
        spec = item.spec
        reach, pad_h = float(spec["reach"]), float(spec["pad_height"])
        size = max(float(spec["base_length"]), float(spec["base_width"]))
        riser = lift + z - pad_h
        if riser < -0.5:
            continue  # 누르는 높이가 판보다 아래 — 이 클램프는 너무 크다
        for angle in directions:
            ux, uy = math.cos(angle), math.sin(angle)
            bx, by = x - ux * reach, y - uy * reach
            if abs(bx) - size / 2 < half_x and abs(by) - size / 2 < half_y:
                continue  # 베이스가 제품 상자 안에 걸린다
            if not _arm_clear(geometry, clamp.pad_position, (bx, by), opts):
                continue
            if _post_hits_rest(bx, by, size, avoid):
                continue
            if any(math.dist((bx, by), one.post_position[:2]) < size for one in taken):
                continue
            thread, holes = _mount_holes(spec, bx, by, angle)
            return replace(
                clamp,
                post_position=(round(bx, 3), round(by, 3), 0.0),
                pad_diameter=float(spec.get("pad_diameter", clamp.pad_diameter)),
                standard=standard.StandardRef(
                    source=item.source, kind="clamp", part_no=item.part_no, name=item.name
                ),
                angle=round(math.degrees(angle), 3),
                riser=round(max(riser, 0.0), 3),
                base_size=round(size, 3),
                mount_thread=thread,
                mount_holes=holes,
            )
    return None


def _mount_holes(
    spec: dict[str, Any], bx: float, by: float, angle: float
) -> tuple[str | None, list[tuple[float, float]]]:
    """클램프 고정 나사 — (나사, 판 위 자리). 사양의 자리는 클램프 좌표(베이스 바닥 중심이
    원점, 팔이 +X)라 베이스를 놓은 자리 · 방향으로 돌려 옮긴다. 사양에 없으면 (None, [])."""
    thread = spec.get("mount_thread")
    if not thread or thread not in fasteners.THREADS:
        return None, []
    c, s = math.cos(angle), math.sin(angle)
    return str(thread), [
        (round(bx + c * hx - s * hy, 3), round(by + s * hx + c * hy, 3))
        for hx, hy in spec.get("mount_holes") or []
    ]


def _hole_at(features: list[Feature], x: float, y: float) -> Feature | None:
    holes = [one for one in features if one.kind == "hole" and abs(one.center[2]) < 0.5]
    return min(holes, key=lambda one: math.dist(one.center[:2], (x, y)), default=None)


def _standardize(
    geometry: ProductGeometry,
    features: list[Feature],
    plan: FixturePlan,
    opts: JigOptions,
    library: list[standard.LibraryPart],
) -> FixturePlan:
    """계획의 받침 · 위치 핀 · 클램프를 **규격 부품**으로 — 맞는 것이 있는 것만. 받침이 먼저다:
    고정 높이 받침이면 받침 높이(제품이 뜨는 높이)가 그 높이가 되고, 핀 길이 · 클램프 높이가
    그것을 따른다. 바꾸지 못한 것은 즉석 도형으로 남기고 그렇다고 말한다."""
    notes = plan.notes
    lift = plan.product_lift
    supports = plan.supports
    chosen = standard.support_for(library, lift)
    if chosen is not None:
        ref, used, top = chosen
        if abs(used - lift) > 0.01:
            notes.append(
                f"규격 받침({ref.part_no})의 높이에 맞춰 받침 높이를 {used:g} mm로 했습니다."
            )
        # 받침 윗면이 바닥면 안에 놓이게 — 규격품의 윗면 지름으로 자리를 다시 잡는다.
        quiet: list[str] = []
        supports = _pick_supports(
            geometry, features, replace(opts, support_diameter=top), quiet
        )
        supports = [replace(one, standard=ref, diameter=top) for one in supports]
        lift = used
    elif any(one.kind == "support" for one in library):
        notes.append("받침 높이에 맞는 규격 받침이 없어 받침은 제작품으로 둡니다.")

    locators: list[LocatorSpec] = []
    missing_pins = 0
    for one in plan.locators:
        if one.kind != "pin" or one.diameter is None:
            locators.append(one)
            continue
        hole = _hole_at(features, one.position[0], one.position[1])
        depth = hole.depth if hole is not None and hole.depth else 0.0
        hole_d = one.diameter + 2 * opts.locator_pin_clearance
        wanted = min(depth * 0.8, opts.locator_pin_max_engagement)
        found = standard.pin_for(library, hole_d, lift, wanted, depth)
        if found is None:
            missing_pins += 1
            locators.append(one)
            continue
        ref, diameter, engagement = found
        locators.append(replace(one, standard=ref, diameter=diameter, engagement=engagement))
    if missing_pins and any(one.kind == "pin" for one in library):
        notes.append(f"구멍에 맞는 규격 위치 핀이 없어 {missing_pins}개는 제작품으로 둡니다.")

    clamps: list[ClampSpec] = []
    avoid = [one for one in locators if one.kind in ("rest", "side_pin")]
    missing_clamps = 0
    for given in plan.clamps:
        placed = (
            _standard_clamp(geometry, given, lift, opts, avoid, clamps, library)
            if standard.clamps(library)
            else None
        )
        if placed is None:
            missing_clamps += 1
        clamps.append(placed or given)
    if missing_clamps and standard.clamps(library):
        notes.append(
            f"놓을 수 있는 규격 클램프가 없어 {missing_clamps}개는 제작품으로 둡니다"
            "(도달 거리 · 누르는 높이 · 베이스 자리)."
        )

    # 베이스가 판 밖으로 나가면 판을 넓힌다 — 클램프는 판에 볼트로 선다.
    plate = plan.base_plate
    for clamp in clamps:
        if clamp.standard is None:
            continue
        bx, by, _ = clamp.post_position
        reach_x = 2 * (abs(bx) + clamp.base_size / 2 + 5.0)
        reach_y = 2 * (abs(by) + clamp.base_size / 2 + 5.0)
        if reach_x > plate.length or reach_y > plate.width:
            plate = replace(
                plate,
                length=round(max(plate.length, reach_x), 1),
                width=round(max(plate.width, reach_y), 1),
            )
    if plate is not plan.base_plate:
        notes.append("규격 클램프의 베이스가 놓이도록 바닥판을 넓혔습니다.")
    # 고정 나사의 탭 구멍 — 볼트 고정과 같이 호칭 지름으로 판을 뚫는다. 받침 블록에 올린
    # 클램프도 나사가 블록의 여유 구멍을 지나 판에 박힌다(블록 구멍은 assembly · jig_recipe).
    taps = [
        (x, y, fasteners.nominal_of(clamp.mount_thread))
        for clamp in clamps
        if clamp.standard is not None and clamp.mount_thread
        for x, y in clamp.mount_holes
    ]
    if taps:
        plate = replace(plate, holes=[*plate.holes, *taps])
    bare = sorted(
        {
            clamp.standard.part_no
            for clamp in clamps
            if clamp.standard is not None and not clamp.mount_holes
        }
    )
    if bare:
        notes.append(
            f"규격 클램프({', '.join(bare)})의 사양에 고정 나사 자리가 없어 판에 탭 구멍을 "
            "내지 않았습니다. 규격 사양에 고정 나사와 구멍 자리를 적으십시오."
        )
    return replace(
        plan,
        supports=supports,
        locators=locators,
        clamps=clamps,
        base_plate=plate,
        product_lift=lift,
        notes=notes,
    )


def _plan_clamped(
    geometry: ProductGeometry, features: list[Feature], opts: JigOptions
) -> FixturePlan:
    """판 위에 받침 · 위치 핀(또는 받침대) · 클램프 — 3-2-1 원칙의 고정구."""
    notes: list[str] = []
    # 순서가 곧 우선순위다: 로케이터(구멍이 정한다) → 받침(구멍 · 핀을 피한다) →
    # 클램프(레스트를 피한다).
    locators = _pick_locators(geometry, features, opts, notes)
    supports = _pick_supports(geometry, features, opts, notes)
    clamps = _pick_clamps(geometry, locators, opts, notes)
    slopes = [one for one in features if one.kind == "plane" and one.role.startswith("slope")]
    if slopes:
        notes.append(
            f"경사면 {len(slopes)}곳은 받침과 클램프 위치에서 제외했습니다"
            "(평면에만 배치합니다)."
        )
    return FixturePlan(
        kind="clamped",
        base_plate=_plate(geometry, opts),
        supports=supports,
        locators=locators,
        clamps=clamps,
        product_lift=opts.support_height,
        notes=notes,
    )


# --- 볼트 고정 ----------------------------------------------------------------

#: ISO 미터 호칭 — 구멍 지름에서 가장 가까운 아래 것을 고른다(6.5 구멍 → M6).
_ISO_NOMINALS = (3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 24.0)


def _nominal_for(hole_diameter: float) -> float | None:
    fitting = [d for d in _ISO_NOMINALS if d <= hole_diameter - 0.3]
    return fitting[-1] if fitting else None


def _spread(holes: list[Feature], count: int) -> list[Feature]:
    """서로 가장 멀리 떨어진 것부터 `count` 개 — 한쪽에 몰리면 반대쪽이 들린다."""
    if len(holes) <= count:
        return holes
    chosen = _farthest_pair(holes)
    while len(chosen) < count:
        rest = [h for h in holes if h not in chosen]
        chosen.append(
            max(rest, key=lambda h: min(math.dist(h.center[:2], k.center[:2]) for k in chosen))
        )
    return chosen


def _plan_bolted(
    geometry: ProductGeometry, features: list[Feature], opts: JigOptions
) -> FixturePlan:
    """부품의 수직 관통 구멍으로 볼트를 넣어 판에 조인다 — 진동 · 충격 시험의 기본 고정.

    클램프가 아니라 볼트라야 가진에서 미끄러지지 않는다. 부품은 판(또는 스페이서)에 바로 앉고,
    판에는 볼트 자리마다 탭 구멍이 난다."""
    notes: list[str] = []
    holes = [
        one
        for one in features
        if one.kind == "hole"
        and one.role == "through"
        and one.radius is not None
        and one.depth is not None
        and _nominal_for(2 * one.radius) is not None
    ]
    if not holes:
        raise PlanningError(
            "볼트를 체결할 수직 관통 구멍이 없습니다. 볼트 고정 형식은 부품의 구멍에 볼트를 "
            "체결합니다. 구멍을 추가하거나 ‘판·클램프 고정’ 형식을 사용하십시오."
        )
    chosen = _spread(holes, max(1, opts.bolt_max_count))
    if len(chosen) < 2:
        notes.append(
            "관통 구멍이 하나뿐입니다. 볼트 1개로는 부품이 회전할 수 있으므로 구멍을 "
            "추가하십시오."
        )
    lift = max(0.0, opts.bolt_spacer_height)
    bolts: list[BoltSpec] = []
    plate_holes: list[tuple[float, float, float]] = []
    for index, hole in enumerate(chosen):
        assert hole.radius is not None and hole.depth is not None
        hole_d = round(2 * hole.radius, 3)
        nominal = _nominal_for(hole_d)
        assert nominal is not None
        x, y = hole.center[0], hole.center[1]
        bolts.append(
            BoltSpec(
                label=f"볼트_{index + 1}",
                position=(x, y, round(hole.center[2] + hole.depth, 3)),
                nominal=nominal,
                hole_diameter=hole_d,
                grip=round(hole.depth + lift, 3),
                head=opts.bolt_head if opts.bolt_head in ("hex", "socket") else "hex",
                washer=opts.bolt_washer,
                engagement=round(nominal * opts.bolt_plate_engagement, 3),
            )
        )
        plate_holes.append((x, y, nominal))  # 탭 구멍 — 호칭 지름(나사산 없음)
    plate = _plate(geometry, opts)
    plate.holes = plate_holes
    if any(bolt.engagement > plate.thickness for bolt in bolts):
        notes.append(
            "판이 볼트 체결 깊이보다 얇습니다. 판 두께를 늘리거나 체결 깊이를 줄이십시오."
        )
    return FixturePlan(
        kind="bolted",
        base_plate=plate,
        supports=[],
        locators=[],
        clamps=[],
        bolts=bolts,
        product_lift=lift,
        notes=notes,
    )


# --- 굽힘(3점 · 4점) ---------------------------------------------------------


def _bending_rule(
    thickness: float, length: float, opts: JigOptions, notes: list[str]
) -> tuple[int, float, float, float, float]:
    """(점 수, 지지 간격, 하중 간격, 롤러 지름, 노즈 지름). 시험 규격의 규칙(`bending_setup`)이
    있으면 그것 — 지지 간격 = 간격비 x 부품 두께, 반지름은 두께에 따라. 시편 템플릿
    (`specimens.bending`)과 같은 함수를 쓴다. 없으면 옵션의 값 그대로."""
    if opts.bending_setup:
        try:
            setup = BendingSetup.model_validate(opts.bending_setup)
        except ValidationError as failure:
            raise PlanningError(
                f"시험 규격의 규칙이 올바르지 않습니다: {failure}"
            ) from failure
        span = bending.span_at(setup, thickness)
        load_span = bending.load_span_at(setup, span)
        roller_d = 2 * bending.radius_at(setup.support_radius, thickness)
        nose_d = 2 * bending.radius_at(setup.nose_radius, thickness)
        rule = (
            f"간격비 {setup.span.to_thickness:g} x 두께 {thickness:g}"
            if setup.span.to_thickness is not None
            else "고정 값"
        )
        notes.append(
            f"시험 규격 ‘{opts.bending_preset or '지정 규칙'}’: 지지 간격 {span:g} mm"
            f"({rule}), 롤러 지름 {roller_d:g} mm, 노즈 지름 {nose_d:g} mm."
        )
        need = span + 2 * bending.overhang_at(setup, span)
        if length < need - 1e-6:
            notes.append(
                f"부품 길이({length:.1f} mm)가 규격의 돌출을 담지 못합니다"
                f"(최소 {need:.1f} mm)."
            )
        return setup.points, span, load_span, roller_d, nose_d
    span = opts.bending_span if opts.bending_span > 0 else length * opts.bending_span_ratio
    points = 4 if int(opts.bending_points) == 4 else 3  # 화면의 고르개는 글자로 줄 수 있다
    load_span = (opts.bending_load_span or span / 3) if points == 4 else 0.0
    return points, span, load_span, opts.bending_roller_diameter, opts.bending_nose_diameter


def _plan_bending(geometry: ProductGeometry, opts: JigOptions) -> FixturePlan:
    """굽힘 — 긴 변 방향으로 스팬을 잡아 롤러 둘로 받치고, 3점이면 가운데를 노즈 하나로,
    4점이면 하중 간격의 양 끝을 노즈 둘로 누른다.

    규칙은 SpaceClaim 시절의 BendingFixture 에서 가져왔다: 스팬 방향 = 긴 변, 스팬 = 길이 x
    비율(또는 절대값), 롤러는 폭보다 조금 길게. 시험 규격을 고르면(`bending_setup`) 스팬 ·
    지름이 규격의 규칙을 따른다 — 두께는 부품의 Z 높이(노즈가 누르는 방향)다."""
    notes: list[str] = []
    sx, sy, sz = geometry.bbox.size
    along_span = "x" if sx >= sy else "y"  # 스팬이 놓이는 축
    length = sx if along_span == "x" else sy
    width = sy if along_span == "x" else sx
    points, span, load_span, roller_d, nose_d = _bending_rule(sz, length, opts, notes)
    if span <= 0 or span >= length:
        raise PlanningError(
            f"스팬({span:.1f} mm)은 부품 길이({length:.1f} mm)보다 작아야 합니다. 스팬 "
            "비율이나 값을 줄이십시오."
        )
    if points == 4 and not 0 < load_span < span:
        raise PlanningError(
            f"하중 간격({load_span:.1f} mm)은 0보다 크고 스팬({span:.1f} mm)보다 작아야 "
            "합니다."
        )
    roller_len = width + 2 * opts.bending_roller_margin
    lift = opts.support_height
    roller_along = "y" if along_span == "x" else "x"  # 롤러 축은 스팬에 수직

    def spot(offset: float, z: float) -> tuple[float, float, float]:
        x, y = (offset, 0.0) if along_span == "x" else (0.0, offset)
        return (round(x, 3), round(y, 3), round(z, 3))

    rollers = [
        RollerSpec(
            label=f"롤러_{index + 1}",
            position=spot(sign * span / 2, -roller_d / 2),
            diameter=roller_d,
            length=round(roller_len, 3),
            along=roller_along,
        )
        for index, sign in enumerate((-1, 1))
    ]
    offsets = (
        [(0.0, "로딩_노즈")]
        if points == 3
        else [(-load_span / 2, "로딩_노즈_1"), (load_span / 2, "로딩_노즈_2")]
    )
    noses = [
        NoseSpec(
            position=spot(offset, sz + nose_d / 2),
            diameter=nose_d,
            length=round(roller_len, 3),
            along=roller_along,
            stem_height=opts.bending_nose_stem_height,
            label=label,
        )
        for offset, label in offsets
    ]
    if lift < roller_d:
        notes.append(
            "받침 높이가 롤러 지름보다 작아 롤러가 판에 묻힙니다. 받침 높이를 늘리십시오."
        )
    plate = _plate(geometry, opts)
    notes.append(f"스팬 {span:.1f} mm(부품 길이 {length:.1f} mm의 {span / length:.0%}).")
    if points == 4:
        notes.append(f"4점 굽힘: 하중 간격 {load_span:.1f} mm(스팬의 {load_span / span:.0%}).")
    return FixturePlan(
        kind="bending",
        base_plate=plate,
        supports=[],
        locators=[],
        clamps=[],
        rollers=rollers,
        noses=noses,
        product_lift=lift,
        notes=notes,
    )


# --- 낙하 · 충격 ---------------------------------------------------------------


def _plan_drop(geometry: ProductGeometry, opts: JigOptions) -> FixturePlan:
    """낙하 · 충격 자세 — 부품은 이미 고른 면이 아래를 보게 돌아 있다(geometry.pose).

    바닥판은 부품 발자국 + 여유. 틈(drop_gap)만큼 띄운다 — 해석이 초기 속도로 낙하를 준다.
    임팩터를 주면 위에서 떨어지는 것(충격 시험)이 부품 윗면 가운데 위에 선다."""
    notes: list[str] = []
    sz = geometry.bbox.size[2]
    impactor = None
    if opts.drop_impactor in ("ball", "pen"):
        d = opts.drop_ball_diameter
        z = sz + opts.drop_impactor_clearance + (d / 2 if opts.drop_impactor == "ball" else 0)
        impactor = ImpactorSpec(
            kind=opts.drop_impactor, position=(0.0, 0.0, round(z, 3)), diameter=d
        )
    plate = _plate(geometry, opts)
    plate.mount_hole_diameter = 0.0  # 바닥에는 고정 구멍이 없다
    notes.append(
        f"낙하 자세: {opts.drop_orientation}이(가) 아래를 향합니다. 바닥과의 간극은 "
        f"{opts.drop_gap:g} mm입니다."
    )
    return FixturePlan(
        kind="drop",
        base_plate=plate,
        supports=[],
        locators=[],
        clamps=[],
        impactor=impactor,
        product_lift=max(0.0, opts.drop_gap),
        notes=notes,
    )


# --- 계획 ---------------------------------------------------------------------


def plan(
    geometry: ProductGeometry,
    features: list[Feature],
    opts: JigOptions,
    library: list[standard.LibraryPart] | None = None,
) -> FixturePlan:
    """형식(`opts.kind`)에 따라 다른 규칙 — 모두 같은 FixturePlan 으로 나온다. 규격 부품
    목록(`library`)이 있으면 판 · 클램프 고정의 받침 · 위치 핀 · 클램프를 그것으로 바꾼다."""
    if opts.kind == "bolted":
        return _plan_bolted(geometry, features, opts)
    if opts.kind == "bending":
        return _plan_bending(geometry, opts)
    if opts.kind == "drop":
        return _plan_drop(geometry, opts)
    if opts.kind != "clamped":
        raise PlanningError(f"알 수 없는 지그 형식입니다: {opts.kind}")
    made = _plan_clamped(geometry, features, opts)
    if library and opts.standard_parts:
        made = _standardize(geometry, features, made, opts, library)
    return made


def as_vector(point: XYZ) -> Vector:
    return Vector(*point)
