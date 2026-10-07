"""압축 — 각기둥(ASTM D695, ISO 604) · 원기둥(ASTM E9) 시편은 세워서 위아래 가압판으로, 띠
(ASTM D6641, ISO 14126) · 구멍 띠(ASTM D6484 오픈홀 압축)는 눕혀서 양 끝 그립으로 누른다.

좌표: 세운 시편은 XY 가운데가 원점, 아랫면이 z=0, 길이가 Z. 눕힌 시편은 인장과 같다(길이 X ·
폭 Y · 두께 Z). 가압판은 바디로 그리지 않는다 — 아랫면을 고정하고 윗면을 아래로 옮긴다(옆으로는
막는다 — 마찰이 큰 가압판). 그립은 인장과 같이 면 나누기 자리(`coupon`).

**좌굴은 보지 않는다.** 정적 해석은 좌굴 하중을 모른다 — 띠 시편의 좌굴 방지 지그(D6484 의
지지판)도 그리지 않았다. 좌굴은 해석 쪽의 좌굴 해석이 필요하다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.specimens import coupon, tensile
from app.core.specimens.bending import SpecimenBuild

if TYPE_CHECKING:
    from app.core.specimens.presets import CompressivePreset, CompressiveSpecimen

SPECIMEN = "시편"
BASE = "아래 가압면"
PRESSED = "위 가압면"
FIXED = "고정 그립"
PUSHED = "누름 그립"


def check(family: str, size: CompressiveSpecimen) -> None:
    standing = family in ("prism", "cylinder")
    if family == "cylinder" and size.thickness is not None:
        raise ValueError("원기둥 시편에는 thickness를 지정하지 않습니다(width가 지름입니다).")
    if family != "cylinder" and size.thickness is None:
        raise ValueError("이 시편에는 thickness(두께)가 필요합니다.")
    if standing:
        extra = [name for name in ("grip_length", "hole_diameter") if getattr(size, name)]
        if extra:
            raise ValueError(
                f"가압판으로 누르는 시편에는 {', '.join(extra)}을(를) 지정하지 않습니다."
            )
        return
    if size.grip_length is None:
        raise ValueError("그립으로 누르는 시편에는 grip_length(그립 길이)가 필요합니다.")
    free = size.length - 2 * size.grip_length
    if free <= 2 * coupon.MARGIN:
        raise ValueError(
            f"그립 길이({size.grip_length:g}) 둘이 시편 길이({size.length:g})를 다 덮습니다."
        )
    if family == "strip" and size.hole_diameter is not None:
        raise ValueError("띠 시편에는 hole_diameter를 지정하지 않습니다.")
    if family == "open_hole":
        tensile.hole_check(size.hole_diameter, size.width, free)


def build(
    preset: CompressivePreset, *, fixture: bool = True, conditions: bool = True
) -> SpecimenBuild:
    size = preset.specimen
    family = preset.family
    notes = coupon.review(preset.verified, preset.source)
    params: dict[str, Any] = {"길이": size.length}
    standing = family in ("prism", "cylinder")
    body = f"{SPECIMEN}_몸통" if fixture and not standing else SPECIMEN
    nodes: list[dict[str, Any]]
    if family == "cylinder":
        params["지름"] = size.width
        nodes = [
            {
                "id": SPECIMEN,
                "op": "cylinder",
                "label": "시편",
                "radius": "=지름 / 2",
                "height": "=길이",
                "axis": "Z",
                "align": ["center", "center", "min"],
            }
        ]
    elif family == "prism":
        params.update({"폭": size.width, "두께": size.thickness})
        nodes = [
            {
                "id": SPECIMEN,
                "op": "box",
                "label": "시편",
                "length": "=폭",
                "width": "=두께",
                "height": "=길이",
                "align": ["center", "center", "min"],
            }
        ]
    else:
        params.update({"폭": size.width, "두께": size.thickness})
        holed = family == "open_hole"
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
        notes.append(
            "좌굴 방지 지그는 그리지 않았습니다. 좌굴은 정적 해석으로 보이지 않습니다."
        )
    if not fixture:
        return SpecimenBuild(
            recipe={"version": 1, "params": params, "nodes": nodes},
            conditions=None,
            notes=notes,
        )

    if standing:
        notes.append(
            "가압판은 바디로 그리지 않고, 아랫면을 고정하고 윗면을 아래로 옮깁니다(옆으로는 "
            "막습니다 — 마찰이 큰 가압판)."
        )
        free = "길이"
        pushed_length = size.length
    else:
        params["그립_길이"] = size.grip_length
        margin = coupon.MARGIN
        grip_size = [f"=그립_길이 - {margin:g}", f"=폭 - {2 * margin:g}"]
        patches = []
        for index, sign in ((1, "-"), (2, "")):
            x = f"={sign}(길이 / 2 - (그립_길이 + {margin:g}) / 2)"
            patches += [
                coupon.patch(
                    f"그립_{index}_위", "top", [x, 0, "=두께"], grip_size, "그립 자리"
                ),
                coupon.patch(
                    f"그립_{index}_아래", "bottom", [x, 0, 0], grip_size, "그립 자리"
                ),
            ]
        nodes += coupon.chain(body, SPECIMEN, patches)
        notes.append(
            "그립은 바디로 그리지 않고, 양 끝의 윗면과 아랫면을 그립 길이만큼 나눠 물린 "
            "자리로 표시했습니다."
        )
        params["자유_길이"] = "=길이 - 2 * 그립_길이"
        free = "자유_길이"
        pushed_length = size.length - 2 * (size.grip_length or 0)
    if not conditions:
        return SpecimenBuild(
            recipe={"version": 1, "params": params, "nodes": nodes},
            conditions=None,
            notes=notes,
        )

    params["변형률"] = preset.analysis.strain
    params["누름"] = f"=변형률 * {free}"
    notes.append(
        f"{'윗면' if standing else '오른쪽 그립'}을 "
        f"{preset.analysis.strain * pushed_length:.3g} mm 누릅니다(해석 기본값이며 규격의 "
        "판정 기준이 아닙니다). 시편의 물성을 지정하십시오."
    )
    recipe = {"version": 1, "params": params, "nodes": nodes}
    return SpecimenBuild(
        recipe=recipe,
        conditions=_conditions(standing, preset.analysis.large_deflection),
        notes=notes,
    )


def _conditions(standing: bool, large_deflection: bool) -> dict[str, Any]:
    if standing:
        selections = [
            {"name": BASE, "entity": "face", "select": {"what": "faces", "role": "bottom"}},
            {"name": PRESSED, "entity": "face", "select": {"what": "faces", "role": "top"}},
        ]
        fixed, moved, push = BASE, PRESSED, {"x": 0, "y": 0, "z": "=-누름"}
    else:
        selections = [
            {
                "name": FIXED,
                "entity": "face",
                "select": coupon.tagged("그립_1_위", "그립_1_아래"),
            },
            {
                "name": PUSHED,
                "entity": "face",
                "select": coupon.tagged("그립_2_위", "그립_2_아래"),
            },
        ]
        fixed, moved, push = FIXED, PUSHED, {"x": "=-누름", "y": 0, "z": 0}
    return {
        "schema_version": 1,
        "named_selections": selections,
        "constraints": [
            {"name": "받침 고정", "type": "fixed_support", "on": fixed},
            {"name": "누름", "type": "displacement", "on": moved, **push},
        ],
        "analysis": {"type": "static", "large_deflection": large_deflection},
    }
