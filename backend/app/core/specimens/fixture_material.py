"""시험 지그(강체)의 기본 재료 — 일반 구조용 강(2026-10-23, SimEngBay 의 요청).

해석에서는 지그도 시편과 같은 바디다. CalculiX 는 강체도 요소로 메시하므로 요소마다 재료 단면이
필요하고, Ansys 는 강체 질량을 CAD 밀도로 넣으며(MASS21), 모달 · 조화 해석에서는 지그의 질량 ·
관성이 주파수를 바꾼다. 그래서 받는 쪽은 「해석 제외」 가 아닌 모든 파트에 재료를 요구하고,
재료가 빈 지그가 있으면 그 설계점을 걸지 않는다 — 시편에 물성을 붙여도 롤러 · 노즈가 비어
막혔다.

**시편의 물성은 여전히 비워 둔다** — 시험의 대상이라 사람이 고른다. 지그는 시험 대상이 아니고
강체로 풀린다. 값은 Ansys 의 「Structural Steel」 과 같다(탄성계수 200 GPa · 푸아송비 0.3 ·
밀도 7850 kg/m³). 설치마다 MatNexus 의 재료로 바꾼다(`FIXTURE_MATERIAL_CODE` —
`modules/specimens`).

값의 모양은 MatNexus 재료와 같다 — 밀도 · 푸아송비는 칸, 탄성계수는 표준 열쇠를 단 `values[]`
줄. 받는 쪽은 `converted` 하나로 읽는다(`conditions.converted_material`, 사전 없이도 열쇠가
있다).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.core.conditions import ALL_BODIES, applied_bodies
from app.core.specimens.bending import SpecimenBuild

NAME = "일반 구조용 강(지그 기본)"
#: `materials[].ref.source` — MatNexus 에서 고른 것이 아니라 CompCore 가 붙인 기본값.
SOURCE = "compcore-default"
SUMMARY = "탄성계수 200 GPa · 푸아송비 0.3 · 밀도 7850 kg/m³"


def material(bodies: list[str]) -> dict[str, Any]:
    """`bodies` 에 붙는 기본 강재 한 줄 — 조건의 `materials[]` 항목."""
    return {
        "apply_to": list(bodies),
        "ref": {"source": SOURCE, "code": "", "material_id": "", "name": NAME},
        "payload": {
            "name": NAME,
            "density": 7850.0,
            "density_unit": "kg/m3",
            "poisson_ratio": 0.3,
            "values": [
                {
                    "property_key": "mechanical.youngs_modulus",
                    "property_name": "탄성계수",
                    "value_num": 200.0,
                    "unit": "GPa",
                    "representative": True,
                }
            ],
        },
        "deck_formats": [],
    }


def rigid_bodies(conditions: dict[str, Any] | None) -> list[str]:
    """강체로 푸는 파트(해석 제외는 뺀다) — 시험 생성기가 지그를 그렇게 적는다."""
    return [
        str(one["name"])
        for one in (conditions or {}).get("body_settings") or []
        if isinstance(one, dict)
        and one.get("name")
        and one.get("behavior") == "rigid"
        and not one.get("suppressed")
    ]


def attach(made: SpecimenBuild) -> SpecimenBuild:
    """재료가 없는 강체 지그에 기본 강재를 붙인다 — 조건이 없거나 지그가 없으면 그대로."""
    if not made.conditions:
        return made
    taken: set[str] = set()
    for one in made.conditions.get("materials") or []:
        if isinstance(one, dict):
            taken.update(applied_bodies(one.get("apply_to")))
    if ALL_BODIES in taken:
        return made
    missing = [one for one in rigid_bodies(made.conditions) if one not in taken]
    if not missing:
        return made
    conditions = {
        **made.conditions,
        "materials": [*(made.conditions.get("materials") or []), material(missing)],
    }
    return replace(
        made, conditions=conditions, notes=[*made.notes, note(missing, DEFAULT_LABEL)]
    )


#: 노트에 적는 기본 강재의 이름 — 설치가 재료를 바꿔 끼우면 이 노트를 그 재료의 것으로 바꾼다.
DEFAULT_LABEL = f"「{NAME}」({SUMMARY})"


def note(bodies: list[str], label: str) -> str:
    """사람에게 남기는 한 줄 — 어느 지그에 무엇을 붙였나."""
    return (
        f"시험 지그({' · '.join(bodies)})에는 기본 재료 {label}를 붙였습니다 — 해석에서는 "
        "강체도 재료가 있어야 합니다. 시편의 물성은 비어 있습니다."
    )
