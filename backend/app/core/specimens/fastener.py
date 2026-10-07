"""체결부 — 핀 베어링(ASTM D5961)과 체결구 뽑힘(ASTM D7332) 시편 · 해석 조건.

좌표: 판의 길이 X · 폭 Y · 두께 Z, XY 가운데가 원점, 아랫면이 z=0.

- **핀 베어링**: 구멍이 오른쪽 끝에서 `끝_거리` 에 있다. 핀(강체)이 구멍을 지나 위아래로
  튀어나오고, 오른쪽(가까운 끝 쪽)으로 옮겨 구멍 가장자리를 민다 — 이중 전단 지그의 근사.
  왼쪽 끝은 그립 자리(`coupon`)로 고정. 핀과 구멍은 마찰 접촉.
- **뽑힘**: 판 한가운데 구멍에 머리 달린 체결구. 판의 둘레를 위아래 고리(받침 · 누름판)로
  물고 — 고리는 스케치 고리로 면을 나눈 자리 — 체결구를 아래로 당긴다. 머리 아랫면과 판
  윗면은 마찰 접촉, 몸통과 구멍은 닿지 않는다(틈새 끼움).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.specimens import coupon
from app.core.specimens.bending import SpecimenBuild

if TYPE_CHECKING:
    from app.core.specimens.presets import FastenerPreset, FastenerSpecimen

SPECIMEN = "시편"
PIN = "핀"
BOLT = "체결구"
#: 핀이 판 위아래로 튀어나온 길이 · 체결구 몸통이 판 아래로 나온 길이(mm).
PIN_OUT = 5.0
SHANK_OUT = 10.0
BEARING_ONLY = ("edge_distance", "grip_length")
PULL_ONLY = ("head_diameter", "head_height", "support_diameter")


def check(family: str, size: FastenerSpecimen) -> None:
    margin = coupon.MARGIN
    own, other = (
        (BEARING_ONLY, PULL_ONLY) if family == "bearing" else (PULL_ONLY, BEARING_ONLY)
    )
    missing = [name for name in own if getattr(size, name) is None]
    if missing:
        raise ValueError(f"이 시편에는 {', '.join(missing)}이(가) 필요합니다.")
    extra = [name for name in other if getattr(size, name) is not None]
    if extra:
        raise ValueError(f"이 시편에는 {', '.join(extra)}을(를) 지정하지 않습니다.")
    if size.hole_diameter >= size.width - 4 * margin:
        raise ValueError(
            f"구멍 지름({size.hole_diameter:g})이 폭({size.width:g})보다 충분히 작아야 합니다."
        )
    if family == "bearing":
        assert size.edge_distance is not None and size.grip_length is not None
        if size.edge_distance <= size.hole_diameter / 2 + margin:
            raise ValueError(
                f"끝 거리({size.edge_distance:g})가 구멍 반지름"
                f"({size.hole_diameter / 2:g})보다 커야 합니다."
            )
        reach = size.length - size.edge_distance - size.hole_diameter / 2
        if size.grip_length >= reach - margin:
            raise ValueError(
                f"그립 길이({size.grip_length:g})가 구멍까지({reach:g} mm) 닿습니다."
            )
        return
    assert size.head_diameter is not None and size.support_diameter is not None
    if size.head_diameter <= size.hole_diameter + 2 * margin:
        raise ValueError(
            f"머리 지름({size.head_diameter:g})이 구멍 지름({size.hole_diameter:g})보다 커야 "
            "합니다."
        )
    if size.support_diameter <= size.head_diameter + 2 * margin:
        raise ValueError(
            f"받침 고리 안지름({size.support_diameter:g})이 머리 지름({size.head_diameter:g})"
            "보다 커야 합니다."
        )
    outer = min(size.length, size.width) - 2
    if size.support_diameter >= outer - 2 * margin:
        raise ValueError(
            f"받침 고리 안지름({size.support_diameter:g})이 판({outer + 2:g} mm) 안에 "
            "들어가지 않습니다."
        )


def build(
    preset: FastenerPreset, *, fixture: bool = True, conditions: bool = True
) -> SpecimenBuild:
    size = preset.specimen
    notes = coupon.review(preset.verified, preset.source)
    params: dict[str, Any] = {
        "길이": size.length,
        "폭": size.width,
        "두께": size.thickness,
        "구멍_지름": size.hole_diameter,
    }
    bearing = preset.family == "bearing"
    if bearing:
        params["끝_거리"] = size.edge_distance
        spot: list[Any] = ["=길이 / 2 - 끝_거리", 0]
    else:
        spot = [0, 0]
    body = f"{SPECIMEN}_몸통" if fixture else SPECIMEN
    nodes: list[dict[str, Any]] = [
        {
            "id": f"{SPECIMEN}_판",
            "op": "box",
            "label": "시편",
            "length": "=길이",
            "width": "=폭",
            "height": "=두께",
            "align": ["center", "center", "min"],
        },
        {
            "id": body,
            "op": "hole",
            "label": "구멍",
            "target": f"{SPECIMEN}_판",
            "at": [spot],
            "diameter": "=구멍_지름",
        },
    ]
    if bearing:
        params["핀_돌출"] = PIN_OUT
        others = [
            {
                "id": PIN,
                "op": "cylinder",
                "label": "핀",
                "radius": "=구멍_지름 / 2",
                "height": "=두께 + 2 * 핀_돌출",
                "axis": "Z",
                "at": [*spot, "=-핀_돌출"],
                "align": ["center", "center", "min"],
            }
        ]
        partner = PIN
    else:
        params.update(
            {
                "머리_지름": size.head_diameter,
                "머리_높이": size.head_height,
                "몸통_돌출": SHANK_OUT,
            }
        )
        others = [
            {
                "id": f"{BOLT}_머리",
                "op": "cylinder",
                "label": "체결구 머리",
                "radius": "=머리_지름 / 2",
                "height": "=머리_높이",
                "axis": "Z",
                "at": [0, 0, "=두께"],
                "align": ["center", "center", "min"],
            },
            {
                "id": f"{BOLT}_몸통",
                "op": "cylinder",
                "label": "체결구 몸통",
                "radius": "=구멍_지름 / 2",
                "height": "=두께 + 몸통_돌출",
                "axis": "Z",
                "at": [0, 0, "=-몸통_돌출"],
                "align": ["center", "center", "min"],
            },
            {
                "id": BOLT,
                "op": "union",
                "label": "체결구",
                "targets": [f"{BOLT}_머리", f"{BOLT}_몸통"],
            },
        ]
        partner = BOLT
    if fixture:
        margin = coupon.MARGIN
        if bearing:
            params["그립_길이"] = size.grip_length
            grip_size = [f"=그립_길이 - {margin:g}", f"=폭 - {2 * margin:g}"]
            x = f"=-(길이 / 2 - (그립_길이 + {margin:g}) / 2)"
            patches = [
                coupon.patch("그립_위", "top", [x, 0, "=두께"], grip_size, "그립 자리"),
                coupon.patch("그립_아래", "bottom", [x, 0, 0], grip_size, "그립 자리"),
            ]
            notes.append(
                "그립은 바디로 그리지 않고, 왼쪽 끝의 윗면과 아랫면을 물린 자리로 "
                "표시했습니다. 핀은 강체입니다(이중 전단 지그의 근사)."
            )
        else:
            params["받침_지름"] = size.support_diameter
            nodes.append(
                {
                    "id": "받침_고리",
                    "op": "sketch",
                    "label": "받침 고리",
                    "shapes": [
                        {"type": "circle", "radius": "=min(길이, 폭) / 2 - 1"},
                        {"type": "circle", "radius": "=받침_지름 / 2", "mode": "cut"},
                    ],
                }
            )
            # 고리는 사각 · 원 패치로 안 된다 — 구멍 뚫린 스케치로 나눈다(위아래 같은 스케치).
            ring = {"op": "divide_face", "shape": "sketch", "sketch": "받침_고리"}
            patches = [
                {**ring, "label": "받침 고리", "on": {"role": "bottom"}, "tag": "받침"},
                {**ring, "label": "누름 고리", "on": {"role": "top"}, "tag": "누름판"},
            ]
            notes.append(
                "지그는 바디로 그리지 않고, 판 둘레의 윗면 · 아랫면 고리를 물린 자리로 "
                "표시했습니다. 체결구의 물성을 따로 지정하십시오."
            )
        nodes += coupon.chain(body, SPECIMEN, patches)
    nodes += others
    nodes.append(
        {
            "id": "핀_베어링" if bearing else "뽑힘",
            "op": "group",
            "label": "핀 베어링" if bearing else "체결구 뽑힘",
            "targets": [SPECIMEN, partner],
        }
    )
    with_conditions = fixture and conditions
    if with_conditions:
        params["당김"] = preset.analysis.displacement
        params["마찰계수"] = preset.analysis.friction
        notes.append(
            f"{'핀을 가까운 끝 쪽으로' if bearing else '체결구를 아래로'} "
            f"{preset.analysis.displacement:g} mm 옮깁니다(해석 기본값이며 규격의 판정 기준이 "
            "아닙니다). 시편의 물성을 지정하십시오."
        )
    recipe = {"version": 1, "params": params, "nodes": nodes}
    rules = None
    if with_conditions:
        large = preset.analysis.large_deflection
        rules = _bearing(large) if bearing else _pull_through(size.thickness, large)
    return SpecimenBuild(recipe=recipe, conditions=rules, notes=notes)


def _contact(name: str, source: str, target: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": "frictional",
        "source": source,
        "target": target,
        "friction": "=마찰계수",
        "behavior": "asymmetric",
        "interface_treatment": "adjust_to_touch",
    }


def _rigid_move(on: str, x: Any, z: Any) -> dict[str, Any]:
    return {
        "name": f"{on} 이동",
        "type": "remote_displacement",
        "on": on,
        "behavior": "rigid",
        "x": x,
        "y": 0,
        "z": z,
        "rx": 0,
        "ry": 0,
        "rz": 0,
    }


def _bearing(large_deflection: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "named_selections": [
            {
                "name": "고정 그립",
                "entity": "face",
                "select": coupon.tagged("그립_위", "그립_아래"),
            },
            {
                "name": "구멍면",
                "entity": "face",
                "select": {"what": "faces", "body": SPECIMEN, "kind": "cylinder"},
            },
            {
                "name": "핀 옆면",
                "entity": "face",
                "select": {"what": "faces", "body": PIN, "kind": "cylinder"},
            },
            {
                "name": "핀 끝면",
                "entity": "face",
                "select": {"what": "faces", "body": PIN, "kind": "plane"},
            },
        ],
        "constraints": [
            {"name": "그립 고정", "type": "fixed_support", "on": "고정 그립"},
            _rigid_move("핀 끝면", "=당김", 0),
        ],
        "contacts": [_contact("핀-구멍", "핀 옆면", "구멍면")],
        "analysis": {"type": "static", "large_deflection": large_deflection},
        "body_settings": [{"name": PIN, "behavior": "rigid"}],
    }


def _pull_through(thickness: float, large_deflection: bool) -> dict[str, Any]:
    under = {"what": "faces", "body": BOLT, "normal": [0, 0, -1]}
    return {
        "schema_version": 1,
        "named_selections": [
            {"name": "받침 고리", "entity": "face", "select": coupon.tagged("받침")},
            {"name": "누름 고리", "entity": "face", "select": coupon.tagged("누름판")},
            {
                "name": "머리 아랫면",
                "entity": "face",
                "select": {**under, "near": [0, 0, thickness]},
            },
            {
                "name": "판 윗면",
                "entity": "face",
                "select": {"what": "faces", "body": SPECIMEN, "normal": [0, 0, 1]},
            },
            {
                "name": "체결구 끝면",
                "entity": "face",
                "select": {**under, "near": [0, 0, -SHANK_OUT]},
            },
        ],
        "constraints": [
            {"name": "받침 고정", "type": "fixed_support", "on": "받침 고리"},
            {"name": "누름판 고정", "type": "fixed_support", "on": "누름 고리"},
            _rigid_move("체결구 끝면", 0, "=-당김"),
        ],
        "contacts": [_contact("머리-판", "머리 아랫면", "판 윗면")],
        "analysis": {"type": "static", "large_deflection": large_deflection},
    }
