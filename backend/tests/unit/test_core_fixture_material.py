"""시험 지그(강체)에는 기본 강재가 붙는다 — 해석은 지그도 바디라 재료가 있어야 한다(SimEngBay,
2026-10-23). 시편의 물성은 비워 둔다(시험의 대상이라 사람이 고른다).
"""

from __future__ import annotations

import pytest

from app.core import conditions as model
from app.core import specimens
from app.core.specimens import Preset, fixture_material


def _preset(preset_id: str) -> Preset:
    found = specimens.find_builtin(preset_id)
    assert found is not None
    return found


def test_굽힘_지그에_기본_강재가_붙고_시편은_비어_있다() -> None:
    made = specimens.build(_preset("iso-178"))
    assert made.conditions is not None
    materials = made.conditions["materials"]
    assert [(one["apply_to"], one["ref"]["source"]) for one in materials] == [
        (["롤러_1", "롤러_2", "로딩_노즈"], "compcore-default")
    ]
    assert any("기본 재료" in one and "시편의 물성은 비어" in one for one in made.notes)
    # 조건 검사를 지나고, 받는 쪽이 읽는 `converted` 에 표준 열쇠로 셋이 다 있다.
    parsed = model.parse(made.conditions)
    assert parsed.materials[0].apply_to == ["롤러_1", "롤러_2", "로딩_노즈"]
    converted = model.converted_material(materials[0]["payload"], "si")
    assert model.missing_structural(converted) == []
    assert converted["density"] == pytest.approx(7850.0)
    assert converted["poisson_ratio"] == pytest.approx(0.3)
    assert converted["properties"][0]["points"][0]["value"] == pytest.approx(200e9)
    # 남은 것은 시편 하나 — 사람이 고를 자리.
    names = ["시편", "롤러_1", "롤러_2", "로딩_노즈"]
    assert model.unmaterialed(made.conditions, names) == ["시편"]


def test_핀_베어링의_핀도_강체라_강재가_붙는다() -> None:
    """체결구 뽑힘(D7332)의 체결구는 시험 대상이라 비워 둔다 — 강체가 아니다."""
    pin = specimens.build(_preset("astm-d5961-a"))
    assert pin.conditions is not None
    assert [one["apply_to"] for one in pin.conditions["materials"]] == [["핀"]]
    pulled = specimens.build(_preset("astm-d7332-example"))
    assert not (pulled.conditions or {}).get("materials")


def test_지그가_없거나_조건이_없으면_안_붙인다() -> None:
    preset = _preset("iso-178")
    bare = specimens.build(preset, fixture=False)
    assert not (bare.conditions or {}).get("materials")
    none = specimens.build(preset, conditions=False)
    assert not none.conditions


def test_이미_재료가_있으면_건드리지_않는다() -> None:
    preset = _preset("iso-178")
    made = specimens.build(preset)
    assert made.conditions is not None
    whole = {**made.conditions, "materials": [{"apply_to": ["전체"], "payload": {}}]}
    again = fixture_material.attach(specimens.SpecimenBuild(made.recipe, whole, []))
    assert again.conditions == whole and again.notes == []


def test_재료_없는_파트는_해석_제외를_빼고_센다() -> None:
    raw = {
        "materials": [{"apply_to": ["판"], "payload": {}}],
        "body_settings": [{"name": "명판", "suppressed": True}],
    }
    assert model.unmaterialed(raw, ["판", "명판", "받침"]) == ["받침"]
    assert model.unmaterialed({"materials": [{"apply_to": "전체"}]}, ["판", "받침"]) == []
    assert model.unmaterialed(None, ["판"]) == ["판"]
