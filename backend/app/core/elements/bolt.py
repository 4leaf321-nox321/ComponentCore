"""볼트 — 머리(육각 · 소켓) + 와셔 + 몸통. 부품 구멍을 지나 판에 박힌다.

치수는 ISO 비례(머리 지름 1.5d · 높이 0.65d, 소켓은 높이 1.0d)로 호칭에서 나온다 — 규격
볼트를 쓰게 되면 이 함수가 그 STEP 을 놓는 자리가 된다. 몸통은 호칭 지름 그대로(나사산 없음).
"""

from __future__ import annotations

from build123d import Cylinder, Part, Pos, RegularPolygon, extrude

from app.core.model import BoltSpec


def build_bolt(spec: BoltSpec, lift: float) -> Part:
    d = spec.nominal
    x, y, z_top = spec.position
    top = z_top + lift  # 제품 윗면(최종 좌표계) — 와셔 · 머리가 여기서 올라간다
    washer_t = 0.2 * d if spec.washer else 0.0
    head_h = d if spec.head == "socket" else 0.65 * d
    head_d = 1.5 * d

    shank_len = spec.grip + spec.engagement + washer_t
    shank: Part = Pos(x, y, top + washer_t - shank_len / 2) * Cylinder(d / 2, shank_len)
    parts: list[Part] = [shank]
    if spec.washer:
        parts.append(Pos(x, y, top + washer_t / 2) * Cylinder(d, washer_t))
    z_head = top + washer_t
    if spec.head == "socket":
        head: Part = Pos(x, y, z_head + head_h / 2) * Cylinder(head_d / 2, head_h)
        head = head - Pos(x, y, z_head + head_h) * Cylinder(0.4 * d, head_h)  # 육각 홈 자리
    else:
        hexagon = RegularPolygon(head_d / 2, 6)
        head = Pos(x, y, z_head) * extrude(hexagon, head_h)
    parts.append(head)
    bolt = parts[0]
    for one in parts[1:]:
        bolt = bolt + one
    bolt.label = spec.label
    return bolt


def build_spacer(x: float, y: float, hole_diameter: float, height: float, label: str) -> Part:
    """볼트 자리의 스페이서 — 부품을 판에서 띄울 때. 구멍보다 넉넉한 원통에 구멍을 낸 것."""
    outer = max(hole_diameter * 2.2, hole_diameter + 6)
    ring: Part = Pos(x, y, height / 2) * (
        Cylinder(outer / 2, height) - Cylinder(hole_diameter / 2, height * 2)
    )
    ring.label = label
    return ring
