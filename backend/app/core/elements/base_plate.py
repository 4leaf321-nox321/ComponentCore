"""베이스 플레이트 — 윗면이 z=0, 네 모서리에 고정 구멍."""

from __future__ import annotations

from build123d import Box, Cylinder, Part, Pos

from app.core.model import BasePlateSpec


def build_base_plate(spec: BasePlateSpec) -> Part:
    t = spec.thickness
    plate: Part = Pos(0, 0, -t / 2) * Box(spec.length, spec.width, t)
    margin = max(spec.mount_hole_diameter, 8.0)
    dx, dy = spec.length / 2 - margin, spec.width / 2 - margin
    if dx > margin and dy > margin:
        for sx in (-1, 1):
            for sy in (-1, 1):
                plate = plate - Pos(sx * dx, sy * dy, -t / 2) * Cylinder(
                    spec.mount_hole_diameter / 2, t * 2
                )
    plate.label = "base-plate"
    return plate
