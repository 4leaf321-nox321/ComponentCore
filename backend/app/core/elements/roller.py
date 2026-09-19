"""3점 굽힘 — 지지 롤러(받침대 위에 눕힌 원기둥)와 로딩 노즈(위에서 누르는 원기둥 + 줄기)."""

from __future__ import annotations

from build123d import Box, Cylinder, Part, Pos, Rot

from app.core.model import NoseSpec, RollerSpec


def _lying(x: float, y: float, z: float, diameter: float, length: float, along: str) -> Part:
    """축이 수평으로 눕힌 원기둥 — along 이 x 면 X 축, y 면 Y 축."""
    rot = Rot(0, 90, 0) if along == "x" else Rot(90, 0, 0)
    return Pos(x, y, z) * rot * Cylinder(diameter / 2, length)


def build_roller(spec: RollerSpec, lift: float) -> Part:
    x, y, z_axis = spec.position
    z = z_axis + lift  # 최종 좌표계의 축 높이
    r = spec.diameter / 2
    roller = _lying(x, y, z, spec.diameter, spec.length, spec.along)
    # 받침대 — 판 윗면(z=0)에서 축 높이까지, 롤러 지름만큼 두껍게.
    if z > 0.5:
        size = (
            (spec.diameter, spec.length) if spec.along == "y" else (spec.length, spec.diameter)
        )
        pedestal: Part = Pos(x, y, z / 2) * Box(size[0], size[1], z)
        roller = roller + pedestal
    del r
    roller.label = spec.label
    return roller


def build_nose(spec: NoseSpec, lift: float) -> Part:
    x, y, z_axis = spec.position
    z = z_axis + lift
    nose = _lying(x, y, z, spec.diameter, spec.length, spec.along)
    stem: Part = Pos(x, y, z + spec.stem_height / 2) * Box(
        spec.diameter, spec.diameter, spec.stem_height
    )
    nose = nose + stem
    nose.label = "로딩 노즈"
    return nose
