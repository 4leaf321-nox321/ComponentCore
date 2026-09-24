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
