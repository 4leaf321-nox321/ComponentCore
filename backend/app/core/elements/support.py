"""받침(Support) — 판에서 제품 바닥까지 올라오는 원기둥. 윗면이 제품 바닥과 **닿는다**."""

from __future__ import annotations

from build123d import Cylinder, Part, Pos

from app.core.model import SupportSpec


def build_support(spec: SupportSpec, lift: float) -> Part:
    x, y, _ = spec.position
    height = lift  # 판 윗면(z=0)에서 제품 바닥(z=lift)까지
    part: Part = Pos(x, y, height / 2) * Cylinder(spec.diameter / 2, height)
    part.label = spec.label
    return part
