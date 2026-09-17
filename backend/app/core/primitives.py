"""제품 파일이 없어도 그릴 수 있는 기본 CAD.

두 곳이 쓴다 — CAD 작업대(화면에서 치수를 넣어 STEP 을 받는 자리)와, 제품 STEP 을 안 올린
지그 프로젝트(이 중 하나를 제품으로 삼아 파이프라인을 돌린다). 스펙은 JSON 한 벌이라
화면 · API · CLI 가 같은 말을 쓴다.

    {"kind": "box", "length": 80, "width": 50, "height": 20}
    {"kind": "cylinder", "radius": 25, "height": 40}
    {"kind": "plate_with_holes", "length": 100, "width": 60, "thickness": 12,
     "hole_diameter": 8, "hole_margin": 10}
    {"kind": "bracket", "length": 80, "width": 50, "height": 40, "thickness": 8,
     "hole_diameter": 6}
"""

from __future__ import annotations

import contextlib
from typing import Any

from build123d import Axis, Box, Cylinder, Part, Pos, fillet

KINDS = ("box", "cylinder", "plate_with_holes", "bracket")


class PrimitiveError(ValueError):
    """스펙이 틀렸다. 메시지는 화면에 그대로 나간다."""


def _num(
    spec: dict[str, Any], key: str, default: float | None = None, *, minimum: float = 0.1
) -> float:
    raw = spec.get(key, default)
    if raw is None:
        raise PrimitiveError(f"{key} 가 필요합니다")
    try:
        value = float(raw)
    except (TypeError, ValueError) as failure:
        raise PrimitiveError(f"{key} 는 숫자여야 합니다") from failure
    if value < minimum:
        raise PrimitiveError(f"{key} 는 {minimum} 이상이어야 합니다")
    return value


def box(spec: dict[str, Any]) -> Part:
    return Box(_num(spec, "length"), _num(spec, "width"), _num(spec, "height"))


def cylinder(spec: dict[str, Any]) -> Part:
    return Cylinder(_num(spec, "radius"), _num(spec, "height"))


def plate_with_holes(spec: dict[str, Any]) -> Part:
    """네 모서리에 관통 구멍이 있는 판 — 핀 로케이터 시험에 알맞다."""
    length = _num(spec, "length")
    width = _num(spec, "width")
    thickness = _num(spec, "thickness")
    hole_d = _num(spec, "hole_diameter", 8.0)
    margin = _num(spec, "hole_margin", 10.0)
    if 2 * margin >= min(length, width):
        raise PrimitiveError("hole_margin 이 너무 큽니다 — 구멍이 판 밖으로 나갑니다")
    part: Part = Box(length, width, thickness)
    dx, dy = length / 2 - margin, width / 2 - margin
    for sx in (-1, 1):
        for sy in (-1, 1):
            part = part - Pos(sx * dx, sy * dy, 0) * Cylinder(hole_d / 2, thickness * 2)
    return part


def bracket(spec: dict[str, Any]) -> Part:
    """L 자 브래킷 — 바닥판 + 세운 벽, 바닥판에 구멍 둘. 옆면 · 윗면 · 구멍이 다 있어서
    받침 · 로케이터 · 클램프가 전부 자리를 잡는 **기본 시연 제품**이다."""
    length = _num(spec, "length", 80.0)
    width = _num(spec, "width", 50.0)
    height = _num(spec, "height", 40.0)
    thickness = _num(spec, "thickness", 8.0)
    hole_d = _num(spec, "hole_diameter", 6.0)
    if thickness >= min(width, height):
        raise PrimitiveError("thickness 가 너무 큽니다")

    base = Box(length, width, thickness)
    wall = Pos(0, -(width - thickness) / 2, (height - thickness) / 2) * Box(
        length, thickness, height
    )
    part: Part = base + wall
    # 바닥판에 구멍 둘 — 벽 반대쪽으로 치우쳐서.
    hole_y = width / 2 - (width - thickness) / 3
    for sx in (-1, 1):
        part = part - Pos(sx * length / 3, hole_y, 0) * Cylinder(hole_d / 2, height * 2)
    # 바닥판 바깥 모서리(수직 엣지)를 둥글려 "진짜 부품" 느낌을 낸다.
    vertical = part.edges().filter_by(Axis.Z).sort_by(Axis.Y)[-2:]
    # 치수가 극단이면 필렛이 실패한다 — 필렛 없는 브래킷도 제품이다.
    with contextlib.suppress(Exception):
        part = fillet(vertical, min(6.0, width / 6))
    return part


_BUILDERS = {
    "box": box,
    "cylinder": cylinder,
    "plate_with_holes": plate_with_holes,
    "bracket": bracket,
}


def build(spec: dict[str, Any]) -> Part:
    kind = str(spec.get("kind", ""))
    builder = _BUILDERS.get(kind)
    if builder is None:
        raise PrimitiveError(f"모르는 종류입니다: {kind!r} (가능: {', '.join(KINDS)})")
    part = builder(spec)
    part.label = kind
    return part


def demo_product() -> Part:
    """제품 STEP 이 없을 때 파이프라인이 쓰는 기본 제품."""
    return build({"kind": "bracket"})
