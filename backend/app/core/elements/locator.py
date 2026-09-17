"""로케이터 — 핀(구멍에 들어감) 또는 레스트(옆면에 기댐)."""

from __future__ import annotations

import contextlib

from build123d import Axis, Box, Cylinder, Part, Pos, chamfer

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


def build_locator(spec: LocatorSpec, lift: float) -> Part:
    part = _pin(spec, lift) if spec.kind == "pin" else _rest(spec, lift)
    part.label = spec.label
    return part
