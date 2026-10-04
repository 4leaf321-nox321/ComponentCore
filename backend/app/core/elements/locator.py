"""로케이터 — 핀(바닥 구멍) · 레스트(옆면에 기댐) · 측면 핀(옆 구멍에 가로로 들어감)."""

from __future__ import annotations

import contextlib

from build123d import Axis, Box, Cylinder, Part, Pos, Rot, chamfer

from app.core.model import LocatorSpec


def _pin(spec: LocatorSpec, lift: float) -> Part:
    assert spec.diameter is not None and spec.engagement is not None
    x, y, _ = spec.position
    height = lift + spec.engagement
    pin: Part = Pos(x, y, height / 2) * Cylinder(spec.diameter / 2, height)
    top = pin.edges().sort_by(Axis.Z)[-1]
    with contextlib.suppress(Exception):  # 들어갈 때 걸리지 않게 — 실패하면 모따기 없이
        pin = chamfer(top, min(0.8, spec.diameter / 5))
    return pin


def _rest(spec: LocatorSpec, lift: float) -> Part:
    assert spec.size is not None
    w, d, h = spec.size
    x, y, z = spec.position
    ix, iy, _ = spec.direction
    # 블록의 긴 변(w)이 면을 따라, 짧은 변(d)이 면에 수직. 방향이 X 축이면 90° 돌린다.
    length, depth = (d, w) if abs(ix) > abs(iy) else (w, d)
    # 판 윗면(z=0)에서부터 세운다 — 옆면과 닿는 높이(z+lift)까지 채워야 붙어 있다.
    top = z + lift + h / 2
    block: Part = Pos(x, y, top / 2) * Box(length, depth, top)
    return block


def side_pin_layout(spec: LocatorSpec) -> dict[str, float]:
    """측면 핀의 치수 — 요소와 레시피(`jig_recipe`)가 **같은 수**를 쓰게 한 곳에서 잰다.

    블록은 입구 바깥에 `d` 만큼 판 위에 서고(긴 변 `w` 가 옆면을 따라), 핀은 블록 가운데서
    구멍 안 `engagement` 까지 간다. 높이(z)는 제품 좌표계 — 받침 높이를 더해 쓴다."""
    assert spec.diameter is not None and spec.engagement is not None and spec.size is not None
    w, d, _ = spec.size
    x, y, z = spec.position
    ix, iy, _ = spec.direction
    along_x = abs(ix) > abs(iy)
    mid = (
        spec.engagement / 2 - d / 4
    )  # 입구에서 안쪽으로 — 블록 가운데(-d/2) ~ 끝(+engagement)
    return {
        "block_x": x - ix * d / 2,
        "block_y": y - iy * d / 2,
        "block_sx": d if along_x else w,
        "block_sy": w if along_x else d,
        "block_top": z + spec.diameter,
        "pin_x": x + ix * mid,
        "pin_y": y + iy * mid,
        "pin_z": z,
        "pin_length": spec.engagement + d / 2,
        "pin_radius": spec.diameter / 2,
        "along_x": 1.0 if along_x else 0.0,
    }


def _side_pin(spec: LocatorSpec, lift: float) -> Part:
    one = side_pin_layout(spec)
    top = one["block_top"] + lift
    block: Part = Pos(one["block_x"], one["block_y"], top / 2) * Box(
        one["block_sx"], one["block_sy"], top
    )
    turn = Rot(0, 90, 0) if one["along_x"] else Rot(90, 0, 0)
    pin: Part = (
        Pos(one["pin_x"], one["pin_y"], one["pin_z"] + lift)
        * turn
        * Cylinder(one["pin_radius"], one["pin_length"])
    )
    return block + pin


def build_locator(spec: LocatorSpec, lift: float) -> Part:
    if spec.kind == "pin":
        part = _pin(spec, lift)
    elif spec.kind == "side_pin":
        part = _side_pin(spec, lift)
    else:
        part = _rest(spec, lift)
    part.label = spec.label
    return part
