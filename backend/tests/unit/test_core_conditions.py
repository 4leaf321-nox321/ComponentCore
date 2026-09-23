"""해석 조건 — 솔버를 모르는 중립 표현. 틀린 자리를 짚고, 식을 설계점마다 푼다."""

from __future__ import annotations

from typing import Any

import pytest

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
            "payload": {"density": 7850.0, "density_unit": "kg/m^3"},
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
    assert got.materials[0].payload["density_unit"] == "kg/m^3"
    assert got.units.length == "mm"


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
