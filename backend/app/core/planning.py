"""3단계 — Fixture Planning.

3-2-1 원칙의 뼈대다: 바닥을 받침 3~4 개로 받치고(Z · 두 회전), 옆을 로케이터로 잡고
(X · Y · 남은 회전), 위에서 클램프로 누른다. 여기서는 **어디에 무엇을 둘지**만 정한다 —
치수와 형상은 elements/ 가 만든다.

모든 위치는 **정규화 좌표계**(제품 바닥 z=0)다. 판 윗면은 z = -product_lift 가 아니라,
조립 단계에서 제품을 product_lift 만큼 올려 판 윗면을 z=0 으로 둔다(assembly.py).
"""

from __future__ import annotations

import math

from build123d import Face, Vector

from app.core import features as feat
from app.core.model import (
    XYZ,
    BasePlateSpec,
    ClampSpec,
    Feature,
    FixturePlan,
    LocatorSpec,
    ProductGeometry,
    SupportSpec,
)
from app.core.options import JigOptions


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
        notes.append("바닥면 모서리에 받침을 둘 수 없어 안쪽으로 들였습니다.")
    if len(picked) < 3:
        raise PlanningError(
            "바닥면에 받침 3 개를 둘 자리가 없습니다 — 바닥이 너무 좁거나 구멍이 많습니다."
        )
    return [
        SupportSpec(
            label=f"support-{index + 1}",
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
                label=f"locator-pin-{index + 1}",
                kind="pin",
                position=(hole.center[0], hole.center[1], 0.0),
                direction=(0.0, 0.0, 1.0),
                diameter=round(2 * (hole.radius - opts.locator_pin_clearance), 3),
                engagement=round(min(hole.depth * 0.8, opts.locator_pin_max_engagement), 3),
            )
        )
    return out


def _rest_locators(geometry: ProductGeometry, opts: JigOptions) -> list[LocatorSpec]:
    """옆면 레스트 — 가장 넓은 옆면에 둘, 그와 직교하는 옆면에 하나(2-1)."""
    sides = feat.side_faces(geometry)
    if not sides:
        return []
    w, d, h = opts.locator_rest_size
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
        offsets = [-span / 4, span / 4] if count == 2 and span > 3 * w else [0.0]
        for offset in offsets[:count]:
            point = center + along * offset
            # 레스트 블록의 중심은 면에서 **바깥**으로 d/2 만큼.
            block = point - inward * (d / 2)
            out.append(
                LocatorSpec(
                    label=f"locator-rest-{len(out) + 1}",
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


def _pick_locators(
    geometry: ProductGeometry, features: list[Feature], opts: JigOptions, notes: list[str]
) -> list[LocatorSpec]:
    pins = _pin_locators(features, opts)
    if len(pins) >= 2:
        notes.append(f"관통 구멍 {len(pins)} 개를 핀 로케이터로 씁니다.")
        return pins
    rests = _rest_locators(geometry, opts)
    if pins:
        notes.append("관통 구멍이 하나뿐이라 핀 하나와 옆면 레스트를 함께 씁니다.")
        return [*pins, *rests[:1]]
    if rests:
        notes.append("구멍이 없어 옆면 레스트(2-1)로 위치를 잡습니다.")
    else:
        notes.append(
            "옆면도 구멍도 없어 로케이터를 두지 못했습니다 — 받침과 클램프만 있습니다."
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
    # 변을 따라 옮긴다.
    px, py = candidates[0]
    along_y = abs(px) > half_x  # X 쪽 변에 섰으면 Y 를 따라 옮긴다
    # 판 모서리(여유 폭의 절반)까지는 나가도 된다 — 기둥은 제품이 아니라 판 위에 선다.
    limit_y, limit_x = half_y + margin / 2, half_x + margin / 2
    for k in range(1, 12):
        for sign in (1, -1):
            shift = sign * k * post / 2
            nx, ny = (px, py + shift) if along_y else (px + shift, py)
            if (abs(ny) > limit_y) if along_y else (abs(nx) > limit_x):
                continue
            if not _post_hits_rest(nx, ny, post, rests):
                return nx, ny
    return px, py


def _pick_clamps(
    geometry: ProductGeometry, locators: list[LocatorSpec], opts: JigOptions, notes: list[str]
) -> list[ClampSpec]:
    tops = feat.upward_faces(geometry)
    if not tops or opts.clamp_count <= 0:
        notes.append("윗면 평면이 없어 클램프를 두지 못했습니다.")
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
        notes.append("클램프 패드가 온전히 놓일 윗면이 없습니다.")
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
            notes.append(f"윗면이 좁아 클램프를 {len(chosen)} 개만 둡니다.")
            break
        chosen.append(best)

    if len(chosen) < opts.clamp_count and not any("클램프를" in n for n in notes):
        notes.append(
            f"클램프를 {opts.clamp_count} 개 시켰지만 패드가 놓일 자리가 {len(chosen)} "
            f"곳뿐입니다 — 구멍과 가장자리를 피한 자리가 그만큼입니다."
        )
    margin = opts.plate_margin
    post = opts.clamp_post_size
    rests = [one for one in locators if one.kind == "rest"]
    if margin / 2 < post / 2 + 1:
        notes.append("판 여유(plate_margin)가 좁아 클램프 기둥이 제품에 닿을 수 있습니다.")
    out: list[ClampSpec] = []
    for x, y, z in chosen:
        # 기둥은 패드에서 가장 가까운 제품 바깥 변에, 판 여유의 한가운데 선다.
        placed = _place_post(geometry, (x, y, z), half_x, half_y, margin, opts, rests)
        if placed is None:
            notes.append(
                f"({x:.0f}, {y:.0f}) 자리는 팔이 제품을 지나야 해서 클램프를 두지 않았습니다."
            )
            continue
        px, py = placed
        index = len(out)
        out.append(
            ClampSpec(
                label=f"clamp-{index + 1}",
                pad_position=(round(x, 3), round(y, 3), round(z, 3)),
                post_position=(round(px, 3), round(py, 3), 0.0),
                pad_diameter=opts.clamp_pad_diameter,
                arm_width=opts.clamp_arm_width,
                arm_thickness=opts.clamp_arm_thickness,
            )
        )
    return out


# --- 계획 ---------------------------------------------------------------------


def plan(geometry: ProductGeometry, features: list[Feature], opts: JigOptions) -> FixturePlan:
    notes: list[str] = []
    size = geometry.bbox.size
    plate = BasePlateSpec(
        length=round(size[0] + 2 * opts.plate_margin, 1),
        width=round(size[1] + 2 * opts.plate_margin, 1),
        thickness=opts.plate_thickness,
        mount_hole_diameter=opts.plate_mount_hole_diameter,
    )
    # 순서가 곧 우선순위다: 로케이터(구멍이 정한다) → 받침(구멍 · 핀을 피한다) →
    # 클램프(레스트를 피한다).
    locators = _pick_locators(geometry, features, opts, notes)
    supports = _pick_supports(geometry, features, opts, notes)
    clamps = _pick_clamps(geometry, locators, opts, notes)
    return FixturePlan(
        base_plate=plate,
        supports=supports,
        locators=locators,
        clamps=clamps,
        product_lift=opts.support_height,
        notes=notes,
    )


def as_vector(point: XYZ) -> Vector:
    return Vector(*point)
