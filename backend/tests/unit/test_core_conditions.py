"""해석 조건 — 솔버를 모르는 중립 표현. 틀린 자리를 짚고, 식을 설계점마다 푼다."""

from __future__ import annotations

from typing import Any

import pytest

from app.core import conditions
from app.core.conditions import ConditionError, parse, resolve, spec

FULL: dict[str, Any] = {
    "named_selections": [
        {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}},
        {
            "name": "볼트구멍",
            "entity": "face",
            "select": {"what": "faces", "kind": "cylinder", "radius": 4.25},
        },
    ],
    "materials": [
        {
            "apply_to": "전체",
            "ref": {"source": "matnexus", "code": "M-000123", "name": "SPCC"},
            "payload": {"density": 7850.0, "density_unit": "kg/m3"},
        }
    ],
    "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
    "loads": [
        {
            "name": "볼트",
            "type": "bolt_pretension",
            "on": "볼트구멍",
            "preload": "=토크계수 * 8000",
            "unit": "N",
        },
        {"name": "중력", "type": "standard_earth_gravity", "direction": [0, 0, -1]},
    ],
    "analysis": {"type": "modal", "prestressed": True, "modes": 6},
}


def test_한_벌을_읽고_되돌려_준다() -> None:
    got = parse(FULL)
    assert [one.name for one in got.named_selections] == ["바닥", "볼트구멍"]
    assert got.analysis.type == "modal" and got.analysis.modes == 6
    # 물성은 **해석하지 않는다** — 받은 것을 그대로 들고 있는다.
    assert got.materials[0].payload["density_unit"] == "kg/m3"
    # 단위계는 **이름 하나**다 — 낱낱이 적게 두면 닫히지 않는 계(`mm·kg·s·N`)를 적을 수
    # 있고, 그런 것은 아무도 안 볼 때까지 조용하다가 어느 날 10⁶ 배 틀린다.
    assert got.units.system == "mm_n_tonne"


def test_없는_이름표를_가리키면_지금_말한다() -> None:
    """내보낸 뒤 해석 쪽에서 0 개를 집으면 **하중 없는 해석**이 끝까지 돈다."""
    with pytest.raises(ConditionError, match="이름표가 없습니다"):
        parse(
            {**FULL, "constraints": [{"name": "고정", "type": "fixed_support", "on": "옆면"}]}
        )
    # 있는 이름을 함께 알려 준다 — 오타를 그 자리에서 고치게.
    try:
        parse(
            {**FULL, "constraints": [{"name": "고정", "type": "fixed_support", "on": "옆면"}]}
        )
    except ConditionError as failure:
        assert "바닥" in str(failure) and "볼트구멍" in str(failure)


def test_이름표가_겹치면_막는다() -> None:
    doubled = [FULL["named_selections"][0], FULL["named_selections"][0]]
    with pytest.raises(ConditionError, match="겹칩니다"):
        parse({**FULL, "named_selections": doubled, "constraints": [], "loads": []})


def test_모르는_종류는_자리를_짚어_말한다() -> None:
    with pytest.raises(ConditionError, match=r"loads\.0\.type"):
        parse({**FULL, "loads": [{"name": "x", "type": "춤추기", "on": "바닥"}]})


def test_식은_설계점마다_풀린다() -> None:
    """**받는 쪽은 식을 풀 수 없다.** 점마다 풀린 값을 내보내야 한다."""
    got = resolve(FULL, {"토크계수": 0.9})
    assert got["loads"][0]["preload"] == 7200.0
    # 안 푼 원본은 그대로다 — 스터디의 conditions.json 은 식을 들고 있다.
    assert FULL["loads"][0]["preload"] == "=토크계수 * 8000"

    다른점 = resolve(FULL, {"토크계수": 0.5})
    assert 다른점["loads"][0]["preload"] == 4000.0


def test_모르는_변수를_쓰면_말해_준다() -> None:
    with pytest.raises(ConditionError, match="식을 풀지 못했습니다"):
        resolve(FULL, {"다른이름": 1})


def test_사양표가_화면과_AI_가_쓸_만큼_말해_준다() -> None:
    """종류를 더할 때 화면을 고치지 않으려면, 칸 목록이 서버에서 와야 한다."""
    got = spec()
    assert set(got["groups"]) == {
        "constraints",
        "loads",
        "contacts",
        "initial",
        "mesh_hints",
    }
    assert "bolt_pretension" in got["groups"]["loads"]["types"]
    assert "fixed_support" in got["groups"]["constraints"]["types"]
    assert "on" in got["groups"]["loads"]["fields"]
    assert got["entities"] == ["face", "edge", "vertex", "body"]


def test_물성은_원본_옆에_변환값을_나란히_싣는다() -> None:
    """**MatNexus 가 한 계로 주지 않는다**(2026-09-24 실측): 밀도만 `tonne/mm3` 이고 나머지
    `value_si` 는 진짜 SI 다. 우리 STEP 은 mm 이라 해석은 mm·tonne·s 로 푸는데, 그대로
    넘기면 밀도는 맞고 **탄성계수가 10⁶ 배 틀린다** — 결과가 안 나오는 게 아니라 그럴듯한
    값이 나오고 틀린다.

    그래서 값을 그 계로 옮겨 **원본 옆에** 놓는다. 원본은 안 건드린다 — 감사할 때는 원본,
    풀 때는 변환값이다.
    """
    raw = {
        "units": {"system": "mm_n_tonne"},
        "materials": [
            {
                "payload": {
                    "density": 2.68e-09,
                    "density_unit": "tonne/mm3",
                    "declared_properties": [
                        {
                            "item": "탄성계수",
                            "si_unit": "Pa",
                            "points": [{"temperature_C": 22, "value_si": 7.0e10}],
                        },
                        {
                            "item": "비열",
                            "si_unit": "J/(kg.K)",
                            "points": [{"temperature_C": 22, "value_si": 880.0}],
                        },
                    ],
                }
            }
        ],
    }
    got = conditions.resolve(raw, {})

    # 선언이 **닫힌 계 전부**를 편다 — 받는 쪽이 제멋대로 가정하지 않게.
    assert got["units"]["system"] == "mm_n_tonne"
    assert got["units"]["stress"] == "MPa" and got["units"]["mass"] == "tonne"

    made = got["materials"][0]["converted"]
    assert made["density"] == pytest.approx(2.68e-09)
    한 = {one["item"]: one for one in made["properties"]}
    assert 한["탄성계수"]["unit"] == "MPa"
    assert 한["탄성계수"]["points"][0]["value"] == pytest.approx(70000.0)
    # 비열은 길이가 제곱으로 들어가 10⁶ 배 — 「응력이니까 10⁶」 같은 눈대중으로는 안 나온다.
    assert 한["비열"]["points"][0]["value"] == pytest.approx(8.8e8)

    # **원본은 그대로다.** 이것이 감사의 정본이다.
    payload = got["materials"][0]["payload"]
    assert payload["density"] == 2.68e-09
    assert payload["declared_properties"][0]["points"][0]["value_si"] == 7.0e10


def test_SI_를_고르면_밀도가_제자리를_찾는다() -> None:
    raw = {
        "units": {"system": "si"},
        "materials": [{"payload": {"density": 7.93e-09, "density_unit": "tonne/mm3"}}],
    }
    got = conditions.resolve(raw, {})
    assert got["units"]["stress"] == "Pa"
    assert got["materials"][0]["converted"]["density"] == pytest.approx(7930.0)
    assert got["materials"][0]["converted"]["density_unit"] == "kg/m3"


def test_못_바꾼_것은_못_바꿨다고_적는다() -> None:
    """조용히 원래 값을 남기면 받는 쪽이 그것을 **새 단위인 줄 알고** 그대로 푼다."""
    raw = {
        "materials": [
            {
                "payload": {
                    "density": 1.0,
                    "density_unit": "furlong/fortnight",
                    "declared_properties": [
                        {"item": "이상한것", "si_unit": "그램", "points": [{"value_si": 3.0}]}
                    ],
                }
            }
        ]
    }
    made = conditions.resolve(raw, {})["materials"][0]["converted"]
    assert made["density"] == 1.0, "짐작해서 바꾸지 않는다"
    assert "밀도(furlong/fortnight)" in made["unconverted"]
    assert any("이상한것" in one for one in made["unconverted"])


def test_없는_바디에_물성을_붙이면_막는다() -> None:
    """물성을 없는 바디에 붙이면 해석이 그 바디를 **맨몸으로** 푼다 — 값이 안 나오는 게
    아니라 기본값으로 풀려 그럴듯한 답이 나온다. 이름표를 가리킬 때와 같은 까닭이다."""
    raw = {"materials": [{"apply_to": ["기둥"], "payload": {}}]}
    # 바디를 안 주면 검사하지 않는다 — 도면을 못 만드는 자리에서 저장이 막히면 안 된다.
    assert parse(raw).materials[0].apply_to == ["기둥"]

    parse(raw, ["바닥판", "기둥"])  # 있으면 통과
    with pytest.raises(ConditionError) as failure:
        parse(raw, ["바닥판"])
    assert "「기둥」 라는 바디가 없습니다" in str(failure.value)
    assert "있는 것: 바닥판" in str(failure.value), "무엇을 고를 수 있는지 말해 준다"

    # 「전체」 는 언제나 된다 — 모든 바디라는 뜻이다.
    parse({"materials": [{"apply_to": ["전체"], "payload": {}}]}, ["바닥판"])


def test_물성은_바디_여럿에_붙고_옛_문자열도_읽는다() -> None:
    """파트 셋에 같은 재료를 줄 때 **한 번만 담는다.** 예전(문자열 하나)에는 같은 재료를 세 번
    담아야 했고, 덱의 재료 번호도 셋이 되어 받는 쪽이 같은 재료인지 알 수 없었다."""
    raw = {"materials": [{"apply_to": ["바닥판", "기둥", "기둥"], "payload": {}}]}
    assert parse(raw, ["바닥판", "기둥"]).materials[0].apply_to == ["바닥판", "기둥"]

    # 저장된 조건 · DOE 스냅샷에는 옛 모양이 남아 있다 — 읽을 수 있어야 한다.
    assert parse({"materials": [{"apply_to": "기둥", "payload": {}}]}).materials[
        0
    ].apply_to == ["기둥"]
    # 칸을 안 주면 예전처럼 모든 바디다(부르는 쪽이 안 적었을 때의 뜻을 바꾸지 않는다).
    assert parse({"materials": [{"payload": {}}]}).materials[0].apply_to == ["전체"]
    # **빈 목록은 「아직 안 붙었다」** 다 — 담아 두고 파트마다 고르는 동안의 모양.
    assert parse({"materials": [{"apply_to": [], "payload": {}}]}).materials[0].apply_to == []


def test_바디_하나에_물성_둘은_막는다() -> None:
    """둘이면 해석 쪽이 어느 것으로 풀지 모른다 — 사람이 고른 것과 다를 수 있다."""
    둘 = {
        "materials": [
            {"apply_to": ["기둥"], "payload": {}},
            {"apply_to": ["바닥판", "기둥"], "payload": {}},
        ]
    }
    with pytest.raises(ConditionError) as failure:
        parse(둘)
    assert "「기둥」 에 물성이 둘 붙었습니다" in str(failure.value)
    assert "materials[0]" in str(failure.value), "어느 것과 겹치는지 말한다"

    # 「전체」 는 모든 바디라서, 다른 재료가 한 바디라도 가리키면 겹친다.
    with pytest.raises(ConditionError) as failure:
        parse(
            {
                "materials": [
                    {"apply_to": ["전체"], "payload": {}},
                    {"apply_to": ["기둥"], "payload": {}},
                ]
            }
        )
    assert "「기둥」 에 물성이 둘이 됩니다" in str(failure.value)

    # 담아만 둔 재료(빈 목록)는 몇 개든 겹치지 않는다.
    parse({"materials": [{"apply_to": [], "payload": {}}, {"apply_to": [], "payload": {}}]})


def test_converted_는_출처가_달라도_한_모양이다() -> None:
    """등록 재료는 밀도 · 푸아송비가 payload 의 **칸**으로 오고 문헌은 `values[]` 안에
    **줄**로 온다. 그대로 두면 받는 쪽이 출처에 따라 두 군데를 봐야 한다."""
    등록 = conditions.converted_material(
        {"density_si": 2680.0, "poisson_ratio": 0.33}, "mm_n_tonne"
    )
    문헌 = conditions.converted_material(
        {
            "values": [
                {"property_key": "physical.density", "value_num": 2680.0, "unit": "kg/m^3"},
                {
                    "property_key": "mechanical.poisson_ratio",
                    "value_num": 0.33,
                    "unit": "1",
                },
            ]
        },
        "mm_n_tonne",
    )
    for made in (등록, 문헌):
        assert made["density"] == pytest.approx(2.68e-09)
        assert made["density_unit"] == "tonne/mm3"
        assert made["poisson_ratio"] == pytest.approx(0.33)


def test_두_창고가_같은_열쇠를_내놓는다() -> None:
    """**등록 재료의 물성 줄에는 기계가 읽을 이름이 없다**(한글 라벨 `item` 뿐). 문헌은
    `property_key` 가 있다 — 그대로 두면 받는 쪽이 출처에 따라 다른 규칙으로 「어느 것이
    영률인가」 를 풀어야 한다.

    MatNexus 물성 사전이 그 다리를 이미 들고 있다(`internal_items`). 우리가 한글 표를 따로
    만들면 그쪽이 항목을 하나 더하는 날 우리만 모른다."""
    사전 = {"탄성계수": "mechanical.youngs_modulus", "비열": "thermal.specific_heat"}
    등록 = conditions.converted_material(
        {
            "density_si": 2680.0,
            "poisson_ratio": 0.33,
            "declared_properties": [
                {"item": "탄성계수", "si_unit": "Pa", "points": [{"value_si": 7.0e10}]}
            ],
        },
        "mm_n_tonne",
        사전,
    )
    문헌 = conditions.converted_material(
        {
            "values": [
                {"property_key": "physical.density", "value_num": 2680.0, "unit": "kg/m^3"},
                {
                    "property_key": "mechanical.poisson_ratio",
                    "value_num": 0.33,
                    "unit": "1",
                },
                {
                    "property_key": "mechanical.youngs_modulus",
                    "value_num": 7.0e10,
                    "unit": "Pa",
                },
            ]
        },
        "mm_n_tonne",
        사전,
    )
    for made in (등록, 문헌):
        assert made["density_key"] == "physical.density"
        assert made["poisson_key"] == "mechanical.poisson_ratio"
        # **열쇠로 찾는다** — 그것이 이 기능의 요점이다(한글 라벨로 찾지 않는다).
        E = next(
            one for one in made["properties"] if one.get("key") == "mechanical.youngs_modulus"
        )
        assert E["points"][0]["value"] == pytest.approx(70000.0)
        # 셋이 다 있으니 해석에 바로 쓸 수 있다.
        assert "missing_structural" not in made

    # 사전이 없으면 열쇠만 없다 — 값은 그대로 나간다(열쇠는 덤이다).
    없이 = conditions.converted_material(
        {
            "declared_properties": [
                {"item": "탄성계수", "si_unit": "Pa", "points": [{"value_si": 7.0e10}]}
            ]
        },
        "mm_n_tonne",
    )
    assert "key" not in 없이["properties"][0]
    assert 없이["properties"][0]["points"][0]["value"] == pytest.approx(70000.0)


def test_해석에_빠진_것을_고를_때_말한다() -> None:
    """탄성계수 · 푸아송비 · 밀도가 없으면 해석이 **기본값(구조용 강)** 으로 푼다 — 값이 안
    나오는 게 아니라 고유진동수가 틀린 뒤에야 드러난다. 문헌 2663건 중 탄성계수를 가진 것은
    1025건뿐이다."""
    모자람 = conditions.converted_material(
        {
            "values": [
                {"property_key": "physical.density", "value_num": 2680.0, "unit": "kg/m^3"}
            ]
        },
        "mm_n_tonne",
    )
    assert 모자람["missing_structural"] == ["탄성계수", "푸아송비"]

    # **모르는 것과 없는 것은 다르다.** 목록 한 줄에는 값이 아예 안 딸려 온다(2663건을
    # 값째로 끌 수 없다) — 그때 「다 빠졌다」 고 하면 거짓말이다.
    아직 = conditions.converted_material({"name": "무언가"}, "mm_n_tonne")
    assert "missing_structural" not in 아직
