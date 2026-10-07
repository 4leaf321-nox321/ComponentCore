"""인장 — 도그본(ASTM E8 · D638, ISO 527-2) · 띠(ASTM D3039) · 구멍 띠(ASTM D5766 오픈홀)
시편과 그립 · 해석 조건.

좌표: 길이 X · 폭 Y · 두께 Z — XY 가운데가 원점, 아랫면이 z=0. 도그본은 좁은 평행부와 넓은
그립부를 반지름 R 의 호로 잇는다(호가 평행부에 접한다): 폭 차이의 절반을 h 라 하면 전이부
길이는 √(2Rh - h²). 치수가 모두 레시피 변수라 DOE 로 평행부 폭 · 반지름을 훑는다.

그립은 바디로 그리지 않는다(`coupon`) — 양 끝의 윗면 · 아랫면을 그립 길이만큼 나눠 왼쪽을
고정하고 오른쪽을 X 로 당긴다. 표점 구간도 윗면에 나눠 두어 결과에서 그 구간을 집는다.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.core.specimens import coupon
from app.core.specimens.bending import SpecimenBuild

if TYPE_CHECKING:
    from app.core.specimens.presets import TensilePreset, TensileSpecimen

SPECIMEN = "시편"
FIXED = "고정 그립"
PULLED = "당김 그립"
GAUGE = "표점 구간"


def transition(size: TensileSpecimen) -> float:
    """도그본의 전이부 길이(한쪽) — 띠면 0."""
    if size.radius is None or size.gauge_width is None:
        return 0.0
    rise = (size.width - size.gauge_width) / 2
    return math.sqrt(max(2 * size.radius * rise - rise**2, 0.0))


def check(family: str, size: TensileSpecimen) -> None:
    """치수가 서로 맞는가 — 틀리면 무엇이 왜인지 `ValueError`."""
    narrow = 2 * coupon.MARGIN
    if size.width <= narrow:
        raise ValueError(f"폭은 {narrow:g} mm보다 커야 합니다.")
    if family in ("strip", "open_hole"):
        extra = [
            name
            for name in ("gauge_width", "parallel_length", "radius")
            if getattr(size, name) is not None
        ]
        if family == "strip" and size.hole_diameter is not None:
            extra.append("hole_diameter")
        if extra:
            raise ValueError(f"띠 시편에는 {', '.join(extra)}을(를) 지정하지 않습니다.")
        free = size.length - 2 * size.grip_length
        if size.gauge_length > free - 1e-6:
            raise ValueError(
                f"표점 거리({size.gauge_length:g})가 그립 사이({free:g} mm)보다 깁니다."
            )
        if family == "open_hole":
            hole_check(size.hole_diameter, size.width, size.gauge_length)
        return
    if size.hole_diameter is not None:
        raise ValueError("도그본 시편에는 hole_diameter를 지정하지 않습니다.")
    missing = [
        name
        for name in ("gauge_width", "parallel_length", "radius")
        if getattr(size, name) is None
    ]
    if missing:
        raise ValueError(f"도그본 시편에는 {', '.join(missing)}이(가) 필요합니다.")
    assert size.gauge_width is not None and size.parallel_length is not None
    assert size.radius is not None
    if not narrow < size.gauge_width < size.width:
        raise ValueError(
            f"평행부 폭({size.gauge_width:g})은 {narrow:g} mm보다 크고 그립부 폭"
            f"({size.width:g})보다 좁아야 합니다."
        )
    rise = (size.width - size.gauge_width) / 2
    if rise > size.radius:
        raise ValueError(
            f"반지름({size.radius:g})이 폭 차이의 절반({rise:g} mm)보다 작아 평행부와 "
            "그립부를 이을 수 없습니다."
        )
    if size.gauge_length > size.parallel_length + 1e-6:
        raise ValueError(
            f"표점 거리({size.gauge_length:g})가 평행부 길이({size.parallel_length:g})보다 "
            "깁니다."
        )
    wide = (size.length - size.parallel_length - 2 * transition(size)) / 2
    if wide <= 0:
        raise ValueError(
            f"전체 길이({size.length:g})가 평행부와 전이부"
            f"({size.parallel_length + 2 * transition(size):.4g} mm)를 담지 못합니다."
        )
    if size.grip_length > wide + 1e-6:
        raise ValueError(
            f"그립 길이({size.grip_length:g})가 그립부(한쪽 {wide:.4g} mm)보다 깁니다. "
            "그립이 전이부를 물면 안 됩니다."
        )


def hole_check(hole: float | None, width: float, gauge: float) -> None:
    """구멍 띠 — 구멍이 폭 안에 들고, 표점 구간(면 나누기)이 구멍을 감싸야 한다(나눌 선이
    구멍을 가로지르면 면을 나누지 못한다)."""
    if hole is None:
        raise ValueError("구멍 띠 시편에는 hole_diameter(구멍 지름)가 필요합니다.")
    if hole >= width - 4 * coupon.MARGIN:
        raise ValueError(f"구멍 지름({hole:g})이 폭({width:g})보다 충분히 작아야 합니다.")
    if gauge <= hole + 2 * coupon.MARGIN:
        raise ValueError(f"표점 거리({gauge:g})가 구멍 지름({hole:g})보다 길어야 합니다.")


def _outline() -> dict[str, Any]:
    """도그본 윤곽 — 아래 가장자리를 왼쪽에서 오른쪽으로, 위 가장자리를 되돌아온다. 전이부의
    호는 바깥으로 휜다(양수 반지름 — 실측: 넓이가 해석식과 맞는다)."""
    half = "=-길이 / 2"
    inner = "=-평행부_길이 / 2"
    outer = "=-평행부_길이 / 2 - 전이_길이"
    return {
        "type": "polyline",
        "start": [half, "=-폭 / 2"],
        "segments": [
            {"to": [outer, "=-폭 / 2"]},
            {"to": [inner, "=-평행부_폭 / 2"], "radius": "=반지름"},
            {"to": ["=평행부_길이 / 2", "=-평행부_폭 / 2"]},
            {"to": ["=평행부_길이 / 2 + 전이_길이", "=-폭 / 2"], "radius": "=반지름"},
            {"to": ["=길이 / 2", "=-폭 / 2"]},
            {"to": ["=길이 / 2", "=폭 / 2"]},
            {"to": ["=평행부_길이 / 2 + 전이_길이", "=폭 / 2"]},
            {"to": ["=평행부_길이 / 2", "=평행부_폭 / 2"], "radius": "=반지름"},
            {"to": [inner, "=평행부_폭 / 2"]},
            {"to": [outer, "=폭 / 2"], "radius": "=반지름"},
            {"to": [half, "=폭 / 2"]},
        ],
    }


def build(
    preset: TensilePreset, *, fixture: bool = True, conditions: bool = True
) -> SpecimenBuild:
    size = preset.specimen
    dogbone = preset.family == "dogbone"
    notes = coupon.review(preset.verified, preset.source)
    params: dict[str, Any] = {"길이": size.length, "폭": size.width, "두께": size.thickness}
    body = f"{SPECIMEN}_몸통" if fixture else SPECIMEN
    nodes: list[dict[str, Any]]
    if dogbone:
        params.update(
            {
                "평행부_폭": size.gauge_width,
                "평행부_길이": size.parallel_length,
                "반지름": size.radius,
                "전이_높이": "=(폭 - 평행부_폭) / 2",
                "전이_길이": "=sqrt(2 * 반지름 * 전이_높이 - 전이_높이 ** 2)",
            }
        )
        nodes = [
            {
                "id": f"{SPECIMEN}_윤곽",
                "op": "sketch",
                "label": "도그본",
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
    else:
        holed = preset.family == "open_hole"
        nodes = [
            {
                "id": f"{SPECIMEN}_판" if holed else body,
                "op": "box",
                "label": "시편",
                "length": "=길이",
                "width": "=폭",
                "height": "=두께",
                "align": ["center", "center", "min"],
            }
        ]
        if holed:
            params["구멍_지름"] = size.hole_diameter
            nodes.append(
                {
                    "id": body,
                    "op": "hole",
                    "label": "가운데 구멍",
                    "target": f"{SPECIMEN}_판",
                    "at": [[0, 0]],
                    "diameter": "=구멍_지름",
                }
            )
        notes.append("탭은 그리지 않았습니다. 탭이 붙는 자리를 그립으로 봅니다.")
    if not fixture:
        return SpecimenBuild(
            recipe={"version": 1, "params": params, "nodes": nodes},
            conditions=None,
            notes=notes,
        )

    params["그립_길이"] = size.grip_length
    params["표점_거리"] = size.gauge_length
    margin = coupon.MARGIN
    grip_size = [f"=그립_길이 - {margin:g}", f"=폭 - {2 * margin:g}"]
    patches = []
    for index, sign in ((1, "-"), (2, "")):
        x = f"={sign}(길이 / 2 - (그립_길이 + {margin:g}) / 2)"
        patches += [
            coupon.patch(f"그립_{index}_위", "top", [x, 0, "=두께"], grip_size, "그립 자리"),
            coupon.patch(f"그립_{index}_아래", "bottom", [x, 0, 0], grip_size, "그립 자리"),
        ]
    gauge_width = "=평행부_폭" if dogbone else "=폭"
    patches.append(
        coupon.patch(
            "표점",
            "top",
            [0, 0, "=두께"],
            ["=표점_거리", f"{gauge_width} - {2 * margin:g}"],
            "표점 구간",
        )
    )
    nodes += coupon.chain(body, SPECIMEN, patches)
    notes.append(
        "그립은 바디로 그리지 않고, 양 끝의 윗면과 아랫면을 그립 길이만큼 나눠 물린 자리로 "
        "표시했습니다."
    )
    if not conditions:
        return SpecimenBuild(
            recipe={"version": 1, "params": params, "nodes": nodes},
            conditions=None,
            notes=notes,
        )

    params["변형률"] = preset.analysis.strain
    params["그립_간격"] = "=길이 - 2 * 그립_길이"
    params["늘림"] = "=변형률 * 그립_간격"
    pulled = preset.analysis.strain * (size.length - 2 * size.grip_length)
    notes.append(
        f"왼쪽 그립을 고정하고 오른쪽 그립을 그립 간격의 {preset.analysis.strain:g}배"
        f"({pulled:.3g} mm)만큼 당깁니다(해석 기본값이며 규격의 판정 기준이 아닙니다). "
        "시편의 물성을 지정하십시오."
    )
    recipe = {"version": 1, "params": params, "nodes": nodes}
    return SpecimenBuild(
        recipe=recipe,
        conditions=_conditions(preset.analysis.large_deflection),
        notes=notes,
    )


def _conditions(large_deflection: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "named_selections": [
            {
                "name": FIXED,
                "entity": "face",
                "select": coupon.tagged("그립_1_위", "그립_1_아래"),
            },
            {
                "name": PULLED,
                "entity": "face",
                "select": coupon.tagged("그립_2_위", "그립_2_아래"),
            },
            {"name": GAUGE, "entity": "face", "select": coupon.tagged("표점")},
        ],
        "constraints": [
            {"name": "그립 고정", "type": "fixed_support", "on": FIXED},
            {
                "name": "그립 당김",
                "type": "displacement",
                "on": PULLED,
                "x": "=늘림",
                "y": 0,
                "z": 0,
            },
        ],
        "analysis": {"type": "static", "large_deflection": large_deflection},
    }
