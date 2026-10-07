"""접착 이음 — 단일 겹치기 시편(ASTM D1002 · D5868, ISO 4587)과 그립 · 해석 조건.

좌표: 길이 X · 폭 Y · 두께 Z. 겹친 구간의 가운데가 x=0, 아래 피착재의 아랫면이 z=0. 바디는
셋이다 — 아래 피착재(왼쪽으로 뻗는다), 접착층(겹친 구간), 위 피착재(오른쪽으로 뻗는다).
접착층과 피착재는 본드 접촉으로 붙는다 — 접착층에 접착제의 물성을 따로 준다.

그립은 바디로 그리지 않는다(`coupon`) — 아래 피착재의 왼쪽 끝을 고정하고 위 피착재의 오른쪽
끝을 X 로 당긴다. 실제 시험은 심(shim)으로 하중선을 맞추지만, 여기서는 두 그립 모두 Z 를
막는다(편심에 따른 휨은 그대로 남는다).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.specimens import coupon
from app.core.specimens.bending import SpecimenBuild

if TYPE_CHECKING:
    from app.core.specimens.presets import LapPreset

LOWER = "피착재_1"
ADHESIVE = "접착층"
UPPER = "피착재_2"
FIXED = "고정 그립"
PULLED = "당김 그립"


def _faces(body: str, z: int) -> dict[str, Any]:
    return {"what": "faces", "body": body, "normal": [0, 0, z]}


def build(
    preset: LapPreset, *, fixture: bool = True, conditions: bool = True
) -> SpecimenBuild:
    size = preset.specimen
    notes = coupon.review(preset.verified, preset.source)
    params: dict[str, Any] = {
        "길이": size.length,
        "폭": size.width,
        "두께": size.thickness,
        "겹침": size.overlap,
        "접착_두께": size.bondline,
    }

    def plate(node_id: str, label: str, align: str, at: list[Any]) -> dict[str, Any]:
        return {
            "id": node_id,
            "op": "box",
            "label": label,
            "length": "=길이",
            "width": "=폭",
            "height": "=두께",
            "at": at,
            "align": [align, "center", "min"],
        }

    lower = f"{LOWER}_몸통" if fixture else LOWER
    upper = f"{UPPER}_몸통" if fixture else UPPER
    nodes: list[dict[str, Any]] = [
        plate(lower, "아래 피착재", "max", ["=겹침 / 2", 0, 0]),
        {
            "id": ADHESIVE,
            "op": "box",
            "label": "접착층",
            "length": "=겹침",
            "width": "=폭",
            "height": "=접착_두께",
            "at": [0, 0, "=두께"],
            "align": ["center", "center", "min"],
        },
        plate(upper, "위 피착재", "min", ["=-겹침 / 2", 0, "=두께 + 접착_두께"]),
    ]
    if fixture:
        params["그립_길이"] = size.grip_length
        margin = coupon.MARGIN
        grip_size = [f"=그립_길이 - {margin:g}", f"=폭 - {2 * margin:g}"]
        # 아래 피착재의 왼쪽 끝 · 위 피착재의 오른쪽 끝 — 끝에서 그립 길이만큼.
        reach = f"길이 - 겹침 / 2 - (그립_길이 + {margin:g}) / 2"
        top = "=2 * 두께 + 접착_두께"
        nodes += coupon.chain(
            lower,
            LOWER,
            [
                coupon.patch(
                    "그립_1_위", "top", [f"=-({reach})", 0, "=두께"], grip_size, "그립"
                ),
                coupon.patch(
                    "그립_1_아래", "bottom", [f"=-({reach})", 0, 0], grip_size, "그립"
                ),
            ],
        )
        nodes += coupon.chain(
            upper,
            UPPER,
            [
                coupon.patch("그립_2_위", "top", [f"={reach}", 0, top], grip_size, "그립"),
                coupon.patch(
                    "그립_2_아래",
                    "bottom",
                    [f"={reach}", 0, "=두께 + 접착_두께"],
                    grip_size,
                    "그립",
                ),
            ],
        )
        notes.append(
            "그립은 바디로 그리지 않고, 피착재 끝의 윗면과 아랫면을 그립 길이만큼 나눠 물린 "
            "자리로 표시했습니다."
        )
    nodes.append(
        {
            "id": "겹치기_이음",
            "op": "group",
            "label": "겹치기 이음",
            "targets": [LOWER, ADHESIVE, UPPER],
        }
    )
    with_conditions = fixture and conditions
    if with_conditions:
        params["당김"] = preset.analysis.displacement
        notes.append(
            f"아래 피착재의 왼쪽 끝을 고정하고 위 피착재의 오른쪽 끝을 "
            f"{preset.analysis.displacement:g} mm 당깁니다(해석 기본값이며 규격의 판정 기준이 "
            "아닙니다). 피착재와 접착층의 물성을 각각 지정하십시오."
        )
    recipe = {"version": 1, "params": params, "nodes": nodes}
    return SpecimenBuild(
        recipe=recipe,
        conditions=_conditions(preset.analysis.large_deflection) if with_conditions else None,
        notes=notes,
    )


def _conditions(large_deflection: bool) -> dict[str, Any]:
    bonded = {"type": "bonded"}
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
            {"name": "접착층 아랫면", "entity": "face", "select": _faces(ADHESIVE, -1)},
            {"name": "접착층 윗면", "entity": "face", "select": _faces(ADHESIVE, 1)},
            {"name": "아래 피착재 윗면", "entity": "face", "select": _faces(LOWER, 1)},
            {"name": "위 피착재 아랫면", "entity": "face", "select": _faces(UPPER, -1)},
        ],
        "constraints": [
            {"name": "그립 고정", "type": "fixed_support", "on": FIXED},
            {
                "name": "그립 당김",
                "type": "displacement",
                "on": PULLED,
                "x": "=당김",
                "y": 0,
                "z": 0,
            },
        ],
        "contacts": [
            {
                "name": "접착층-아래 피착재",
                "source": "접착층 아랫면",
                "target": "아래 피착재 윗면",
                **bonded,
            },
            {
                "name": "접착층-위 피착재",
                "source": "접착층 윗면",
                "target": "위 피착재 아랫면",
                **bonded,
            },
        ],
        "analysis": {"type": "static", "large_deflection": large_deflection},
    }
