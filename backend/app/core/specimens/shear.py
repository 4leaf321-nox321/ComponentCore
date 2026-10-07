"""전단 — V 노치 시편(ASTM D5379 이오시페스쿠 · D7078 레일 전단)과 물림 · 해석 조건.

좌표: 길이 X · 폭 Y · 두께 Z — XY 가운데가 원점, 아랫면이 z=0. 폭의 양 가장자리 한가운데에
V 노치가 있다(벌어진 각, 뿌리 반지름 r, 깊이 d). 뿌리의 호는 양 빗변에 접한다: 반각을
h 라 하면 접점은 중심축에서 r·cos h, 가장자리에서 d - r + r·sin h 안쪽이고, 노치 입구의
반폭은 그 접점에서 빗변을 따라 가장자리까지 간 자리다.

물림(`coupon`): 노치 양쪽 반을 윗면 · 아랫면에서 문다 — 왼쪽은 고정, 오른쪽은 폭 방향(Y)으로
옮긴다. 두 물림 사이(`grip_gap`)가 전단 구간이다.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.core.specimens import coupon
from app.core.specimens.bending import SpecimenBuild

if TYPE_CHECKING:
    from app.core.specimens.presets import ShearPreset, VNotchSpecimen

SPECIMEN = "시편"
FIXED = "고정 물림"
MOVED = "가압 물림"


def mouth(size: VNotchSpecimen) -> float:
    """노치 입구의 반폭(가장자리에서) — 중심축에서 빗변이 가장자리를 만나는 자리까지."""
    half = math.radians(size.notch_angle / 2)
    r = size.notch_radius
    depth = size.notch_depth - r + r * math.sin(half)
    return r * math.cos(half) + depth * math.tan(half)


def check(size: VNotchSpecimen) -> None:
    if 2 * size.notch_depth >= size.width:
        raise ValueError(
            f"노치 깊이 둘({2 * size.notch_depth:g})이 폭({size.width:g})보다 작아야 합니다."
        )
    if size.notch_radius >= size.notch_depth:
        raise ValueError(
            f"노치 뿌리 반지름({size.notch_radius:g})이 노치 깊이({size.notch_depth:g})보다 "
            "작아야 합니다."
        )
    if size.grip_gap >= size.length - 4 * coupon.MARGIN:
        raise ValueError(
            f"물림 간격({size.grip_gap:g})이 시편 길이({size.length:g})보다 짧아야 합니다."
        )
    if size.grip_gap / 2 <= mouth(size) + coupon.MARGIN:
        raise ValueError(
            f"물림 간격({size.grip_gap:g})이 노치 입구(폭 {2 * mouth(size):.3g} mm)를 "
            "덮지 않아야 합니다 — 물림이 노치를 물면 안 됩니다."
        )


def _outline() -> dict[str, Any]:
    """노치 둘이 있는 윤곽 — 아래 가장자리를 왼쪽에서 오른쪽으로, 위 가장자리를 되돌아온다.
    뿌리의 호는 재료 쪽으로 휜다(양수 반지름)."""
    bottom_root = "=-폭 / 2 + 노치_접점_깊이"
    top_root = "=폭 / 2 - 노치_접점_깊이"
    return {
        "type": "polyline",
        "start": ["=-길이 / 2", "=-폭 / 2"],
        "segments": [
            {"to": ["=-노치_입구", "=-폭 / 2"]},
            {"to": ["=-노치_접점_x", bottom_root]},
            {"to": ["=노치_접점_x", bottom_root], "radius": "=노치_반지름"},
            {"to": ["=노치_입구", "=-폭 / 2"]},
            {"to": ["=길이 / 2", "=-폭 / 2"]},
            {"to": ["=길이 / 2", "=폭 / 2"]},
            {"to": ["=노치_입구", "=폭 / 2"]},
            {"to": ["=노치_접점_x", top_root]},
            {"to": ["=-노치_접점_x", top_root], "radius": "=노치_반지름"},
            {"to": ["=-노치_입구", "=폭 / 2"]},
            {"to": ["=-길이 / 2", "=폭 / 2"]},
        ],
    }


def build(
    preset: ShearPreset, *, fixture: bool = True, conditions: bool = True
) -> SpecimenBuild:
    size = preset.specimen
    notes = coupon.review(preset.verified, preset.source)
    params: dict[str, Any] = {
        "길이": size.length,
        "폭": size.width,
        "두께": size.thickness,
        "노치_깊이": size.notch_depth,
        "노치_각도": size.notch_angle,
        "노치_반지름": size.notch_radius,
        "노치_접점_x": "=노치_반지름 * cos(노치_각도 / 2)",
        "노치_접점_깊이": "=노치_깊이 - 노치_반지름 + 노치_반지름 * sin(노치_각도 / 2)",
        "노치_입구": "=노치_접점_x + 노치_접점_깊이 * tan(노치_각도 / 2)",
    }
    body = f"{SPECIMEN}_몸통" if fixture else SPECIMEN
    nodes: list[dict[str, Any]] = [
        {
            "id": f"{SPECIMEN}_윤곽",
            "op": "sketch",
            "label": "V 노치 시편",
            "shapes": [_outline()],
        },
        {
            "id": body,
            "op": "extrude",
            "label": "시편",
            "sketch": f"{SPECIMEN}_윤곽",
            "distance": "=두께",
        },
    ]
    notes.append("복합재이면 재료 방향(섬유 방향)을 시편 길이(X)에 맞춰 지정하십시오.")
    if not fixture:
        return SpecimenBuild(
            recipe={"version": 1, "params": params, "nodes": nodes},
            conditions=None,
            notes=notes,
        )

    params["물림_간격"] = size.grip_gap
    margin = coupon.MARGIN
    grip_size = [f"=길이 / 2 - 물림_간격 / 2 - {margin:g}", f"=폭 - {2 * margin:g}"]
    patches = []
    for index, sign in ((1, "-"), (2, "")):
        x = f"={sign}(길이 / 2 - {margin:g} + 물림_간격 / 2) / 2"
        patches += [
            coupon.patch(f"물림_{index}_위", "top", [x, 0, "=두께"], grip_size, "물림 자리"),
            coupon.patch(f"물림_{index}_아래", "bottom", [x, 0, 0], grip_size, "물림 자리"),
        ]
    nodes += coupon.chain(body, SPECIMEN, patches)
    notes.append(
        "지그는 바디로 그리지 않고, 노치 양쪽 반의 윗면과 아랫면을 물린 자리로 표시했습니다."
    )
    if not conditions:
        return SpecimenBuild(
            recipe={"version": 1, "params": params, "nodes": nodes},
            conditions=None,
            notes=notes,
        )

    params["전단_변형률"] = preset.analysis.shear_strain
    params["전단_변위"] = "=전단_변형률 * 물림_간격"
    moved = preset.analysis.shear_strain * size.grip_gap
    notes.append(
        f"왼쪽 물림을 고정하고 오른쪽 물림을 폭 방향(Y)으로 {moved:.3g} mm 옮깁니다"
        "(해석 기본값이며 규격의 판정 기준이 아닙니다). 시편의 물성을 지정하십시오."
    )
    recipe = {"version": 1, "params": params, "nodes": nodes}
    return SpecimenBuild(recipe=recipe, conditions=_conditions(), notes=notes)


def _conditions() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "named_selections": [
            {
                "name": FIXED,
                "entity": "face",
                "select": coupon.tagged("물림_1_위", "물림_1_아래"),
            },
            {
                "name": MOVED,
                "entity": "face",
                "select": coupon.tagged("물림_2_위", "물림_2_아래"),
            },
        ],
        "constraints": [
            {"name": "물림 고정", "type": "fixed_support", "on": FIXED},
            {
                "name": "물림 가압",
                "type": "displacement",
                "on": MOVED,
                "x": 0,
                "y": "=전단_변위",
                "z": 0,
            },
        ],
        "analysis": {"type": "static", "large_deflection": False},
    }
