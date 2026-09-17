"""클램프 — 판 위에 선 기둥 + 제품 위로 뻗은 팔 + 윗면을 누르는 패드.

실제 토글 클램프의 형상이 아니라 **자리와 간섭을 보기 위한 대표 형상**이다. 규격 클램프를
쓰게 되면 이 함수가 그 STEP 을 불러 놓는 자리가 된다.
"""

from __future__ import annotations

import math

from build123d import Box, Cylinder, Part, Pos, Rot

from app.core.model import ClampSpec
from app.core.options import JigOptions


def build_clamp(spec: ClampSpec, lift: float, opts: JigOptions) -> Part:
    px, py, _ = spec.post_position
    x, y, z = spec.pad_position
    pad_top = z + lift  # 제품 윗면(최종 좌표계)
    arm_bottom = pad_top + opts.clamp_clearance_above
    post_h = arm_bottom + spec.arm_thickness

    post: Part = Pos(px, py, post_h / 2) * Box(
        opts.clamp_post_size, opts.clamp_post_size, post_h
    )

    dx, dy = x - px, y - py
    reach = math.hypot(dx, dy) + opts.clamp_post_size / 2
    angle = math.degrees(math.atan2(dy, dx))
    arm: Part = (
        Pos(px, py, arm_bottom + spec.arm_thickness / 2)
        * Rot(0, 0, angle)
        * Pos(reach / 2, 0, 0)
        * Box(reach, spec.arm_width, spec.arm_thickness)
    )

    pad_h = opts.clamp_clearance_above
    pad: Part = Pos(x, y, pad_top + pad_h / 2) * Cylinder(spec.pad_diameter / 2, pad_h)

    clamp = post + arm + pad
    clamp.label = spec.label
    return clamp
