"""소성 — ② 비선형 정적의 재료 모델(SimEngBay 와 정함, 2026-11-27).

이선형(σy · Et)과 다선형(진응력 대 진소성변형률 표)만, 손으로 적는다(MatNexus 카드에서 받는
길은 방향 · 판이 정해진 뒤). 해석 케이스에서만 쓰고 v1 길은 막는다. 능력표는 정적에서 재료
모델로 거른다.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.core.conditions import ConditionError, parse, resolve
from app.core.conditions.capabilities import notes, read
from app.core.conditions.model import views

FIXTURE = Path(__file__).parents[1] / "fixtures" / "simengbay" / "capabilities.json"
RAW: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))

STEEL: dict[str, Any] = {
    "ref": {"source": "matnexus", "code": "S", "name": "강"},
    "apply_to": ["전체"],
    "payload": {"values": {"탄성계수": {"value": 200, "unit": "GPa"}}},
}
BILINEAR: dict[str, Any] = {
    **STEEL,
    "model": "bilinear_isotropic",
    "plastic": {"yield_stress": 250, "tangent_modulus": 2000},
}
MULTILINEAR: dict[str, Any] = {
    **STEEL,
    "model": "multilinear_isotropic",
    "plastic": {"table": [[0, 250], [0.01, 270], [0.05, 300]]},
}
FIXED: dict[str, Any] = {"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}
PULL: dict[str, Any] = {
    "name": "당김",
    "type": "force",
    "on": "윗면",
    "magnitude": 28000,
    "direction": [0, 0, 1],
}


def _case(
    material: dict[str, Any], *more: dict[str, Any], system: str = "mm_n_tonne"
) -> dict[str, Any]:
    return deepcopy(
        {
            "schema_version": 2,
            "units": {"system": system},
            "named_selections": [
                {
                    "name": "바닥",
                    "entity": "face",
                    "select": {"what": "faces", "role": "bottom"},
                },
                {"name": "윗면", "entity": "face", "select": {"what": "faces", "role": "top"}},
            ],
            "materials": [material],
            "cases": [
                {
                    "name": "당기기",
                    "analysis": {"type": "static"},
                    "constraints": [FIXED],
                    "loads": [PULL],
                },
                *more,
            ],
        }
    )


@pytest.mark.parametrize("material", [BILINEAR, MULTILINEAR])
def test_이선형과_다선형을_저장한다(material: dict[str, Any]) -> None:
    got = parse(_case(material))
    assert got.materials[0].model == material["model"]


@pytest.mark.parametrize(
    ("material", "message"),
    [
        (
            {**STEEL, "plastic": {"yield_stress": 250}},
            r"선형 탄성이라 소성 값을 쓰지 않습니다",
        ),
        ({**BILINEAR, "plastic": None}, r"이선형 소성\(등방 경화\) 값이 없습니다"),
        ({**BILINEAR, "plastic": {"tangent_modulus": 2000}}, r"항복응력이\(가\) 없습니다"),
        (
            {**BILINEAR, "plastic": {"yield_stress": 250, "tangent_modulus": -1}},
            r"접선계수은\(는\) 0 이상이어야",
        ),
        (
            {
                **BILINEAR,
                "plastic": {"yield_stress": 250, "tangent_modulus": 0, "table": [[0, 1]]},
            },
            r"이선형이라 표를 쓰지 않습니다",
        ),
        (
            {**MULTILINEAR, "plastic": {"table": [[0, 250]]}},
            r"2 ~ 5000행이어야 합니다\(지금 1행\)",
        ),
        (
            {**MULTILINEAR, "plastic": {"table": [[0.001, 250], [0.01, 270]]}},
            r"첫 행의 소성 변형률은 0이어야",
        ),
        (
            {**MULTILINEAR, "plastic": {"table": [[0, 250], [0.01, 240]]}},
            r"2행: 응력이 위 행보다 작습니다\. 연화는 받지 않습니다",
        ),
        (
            {**MULTILINEAR, "plastic": {"table": [[0, 250], [0, 260]]}},
            r"2행: 소성 변형률은 위 행보다 커야",
        ),
        (
            {
                **MULTILINEAR,
                "plastic": {"yield_stress": 250, "table": [[0, 250], [0.01, 260]]},
            },
            r"다선형이라 항복응력 · 접선계수 대신",
        ),
    ],
)
def test_소성_값이_모델과_맞는지_본다(material: dict[str, Any], message: str) -> None:
    with pytest.raises(ConditionError, match=r"^materials\[0\]: 재료 ‘강’.*" + message):
        parse(_case(material))


def test_식으로_적은_표는_설계점마다_풀린다() -> None:
    raw = _case({**MULTILINEAR, "plastic": {"table": [[0, "=항복"], [0.02, "=항복 * 1.2"]]}})
    parse(raw)
    out = resolve(raw, {"항복": 250}, cases=True)
    assert out["materials"][0]["plastic"]["table"] == [[0, 250.0], [0.02, 300.0]]


def test_케이스가_없는_조건에는_소성을_쓰지_않는다() -> None:
    v1 = {
        "named_selections": [
            {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
        ],
        "materials": [BILINEAR],
        "analysis": {"type": "static"},
        "constraints": [FIXED],
    }
    with pytest.raises(
        ConditionError,
        match=r"^materials\[0\]: 재료 ‘강’의 소성은\(는\) 해석 케이스에서 지정합니다",
    ):
        parse(v1)


def test_v1_길은_막고_v2_는_응력을_내보내기_계로_옮겨_낸다() -> None:
    with pytest.raises(
        ConditionError, match=r"재료 ‘강’의 소성은\(는\) 해석 쪽\(SimEngBay\)이"
    ):
        resolve(_case(BILINEAR), {})
    out = resolve(_case(BILINEAR, system="si"), {}, cases=True)
    assert out["schema_version"] == 2
    (material,) = out["materials"]
    assert material["model"] == "bilinear_isotropic"
    assert material["plastic"] == {
        "yield_stress": 250e6,
        "tangent_modulus": 2000e6,
        "source": "manual",
        "stress_unit": "Pa",
    }
    table = resolve(_case(MULTILINEAR), {}, cases=True)["materials"][0]["plastic"]
    assert table["table"] == [[0, 250.0], [0.01, 270.0], [0.05, 300.0]]
    assert table["stress_unit"] == "MPa"
    # 선형 탄성은 지금까지와 같다 — 칸이 실리지 않는다.
    plain = resolve({**_case(STEEL), "schema_version": 2}, {})
    assert not {"model", "plastic"} & set(plain["materials"][0])


def test_소성_재료가_있으면_정적_뒤에_모드_해석을_잇지_않는다() -> None:
    modal = {
        "name": "모달",
        "depends_on": "당기기",
        "analysis": {"type": "modal", "modes": 6},
        "constraints": [FIXED],
    }
    with pytest.raises(
        ConditionError,
        match=r"^cases\[1\]: 재료 ‘강’의 소성이\(가\) 있는 조건에서는 정적 뒤에 모달, "
        r"랜덤 진동",
    ):
        parse(_case(BILINEAR, modal))
    # 따로 둔 모달은 된다 — 탄성 값으로 푼다.
    parse(_case(BILINEAR, {**modal, "depends_on": ""}))
    parse(_case(STEEL, modal))


def test_출력_요청에_등가_소성_변형률을_적는다() -> None:
    raw = _case(BILINEAR)
    raw["cases"][0]["analysis"]["outputs"] = {
        "quantities": ["displacement", "stress", "equivalent_plastic_strain", "reaction"]
    }
    out = resolve(raw, {}, cases=True)
    assert "equivalent_plastic_strain" in out["cases"][0]["analysis"]["outputs"]["quantities"]


def _notes(
    raw: dict[str, Any], tables: list[dict[str, Any]], index: int = 0
) -> list[dict[str, Any]]:
    raw = deepcopy(raw)
    for one in raw["cases"]:
        one["target"] = {"solver": "calculix"}
    seen = views(parse(raw))
    return notes(seen[index][1], read(tables), "calculix")


def test_능력표는_정적에서_재료_모델로_거른다() -> None:
    raw = _case(MULTILINEAR)
    raw["cases"][0]["target"] = {"solver": "calculix"}
    with pytest.raises(
        ConditionError,
        match=r"^materials\[0\]: 재료 ‘강’의 다선형 소성\(등방 경화\)을\(를\) 대상 솔버 "
        r"‘calculix’의 정적 구조 해석에서 받지 않습니다",
    ):
        parse(raw, capabilities=read(RAW))
    later = deepcopy(RAW)
    later[0]["analyses"]["static"]["materials"] += [
        "bilinear_isotropic",
        "multilinear_isotropic",
    ]
    parse(raw, capabilities=read(later))
    # 모드 해석은 소성을 읽지 않는다 — 막지 않고 탄성으로 푼다고 알린다.
    modal = {"name": "모달", "analysis": {"type": "modal", "modes": 6}, "constraints": [FIXED]}
    got = _notes(_case(MULTILINEAR, modal), RAW, index=1)
    assert {
        "level": "info",
        "where": "재료 ‘강’",
        "text": "모달(고유진동) 해석에서는 다선형 소성(등방 경화) 대신 탄성 값으로 풉니다.",
    } in got
