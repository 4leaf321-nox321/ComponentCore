"""충격 시험의 낙하물 — 강구, 또는 끝이 둥근 펜(원뿔)."""

from __future__ import annotations

from build123d import Cone, Part, Pos, Sphere

from app.core.model import ImpactorSpec


def build_impactor(spec: ImpactorSpec, lift: float) -> Part:
    x, y, z = spec.position
    z += lift
    if spec.kind == "pen":
        tip_r = spec.diameter / 8
        cone_h = spec.diameter * 2
        tip: Part = Pos(x, y, z + tip_r) * Sphere(tip_r)
        body: Part = Pos(x, y, z + tip_r + cone_h / 2) * Cone(spec.diameter / 2, tip_r, cone_h)
        part = tip + body
    else:
        part = Pos(x, y, z) * Sphere(spec.diameter / 2)
    part.label = "임팩터"
    return part
