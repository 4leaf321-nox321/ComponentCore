"""레시피 부분 수정 · 면 기준 놓기 — 순수 함수."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.recipe.patch import PatchError, apply, place_on

RECIPE: dict[str, Any] = {
    "params": {"두께": 6},
    "nodes": [
        {"id": "판", "op": "box", "length": 80, "width": 50, "height": "=두께"},
        {"id": "구멍", "op": "hole", "target": "판", "diameter": 8, "at": [[20, 10]]},
    ],
}


def test_연산_몇_개로_고치고_원본은_두지_않는다() -> None:
    made = apply(
        RECIPE,
        [
            {"op": "set_param", "name": "두께", "value": 8},
            {"op": "set_param", "name": "구멍", "value": 10},
            {"op": "set_field", "id": "구멍", "field": "diameter", "value": "=구멍"},
            {
                "op": "add_node",
                "node": {"id": "모따기", "op": "chamfer", "target": "구멍", "length": 1},
            },
            {"op": "rename_node", "id": "판", "new_id": "바닥판"},
        ],
    )
    assert made["params"] == {"두께": 8, "구멍": 10}
    assert [n["id"] for n in made["nodes"]] == ["바닥판", "구멍", "모따기"]
    assert made["nodes"][1]["target"] == "바닥판"  # 가리키는 곳도 따라 바뀐다
    assert made["nodes"][1]["diameter"] == "=구멍"
    assert RECIPE["nodes"][0]["id"] == "판"  # 원본 그대로


def test_가리키는_것이_있으면_못_지우고_이유를_말한다() -> None:
    with pytest.raises(PatchError, match="구멍 가 가리킵니다"):
        apply(RECIPE, [{"op": "remove_node", "id": "판"}])
    made = apply(RECIPE, [{"op": "remove_node", "id": "구멍"}])
    assert [n["id"] for n in made["nodes"]] == ["판"]
    with pytest.raises(PatchError, match="없습니다"):
        apply(RECIPE, [{"op": "set_field", "id": "없음", "field": "x", "value": 1}])
    with pytest.raises(PatchError, match="모르는 연산"):
        apply(RECIPE, [{"op": "explode"}])


def test_면_기준_놓기는_상자로_맞춘다() -> None:
    jig = ((-60.0, -40.0, -15.0), (60.0, 40.0, 0.0))  # 판 윗면 z=0
    part = ((0.0, 0.0, 0.0), (80.0, 50.0, 12.0))  # 원점에서 그린 부품, 아직 안 옮김
    assert place_on(part, [0, 0, 0], jig, face="top") == [-40.0, -25.0, 0.0]
    assert place_on(part, [0, 0, 0], jig, face="top", offset=25) == [-40.0, -25.0, 25.0]
    assert place_on(part, [0, 0, 0], jig, face="+x", align="min") == [60.0, -40.0, -15.0]
    # 이미 옮겨 둔 것(translate 가 반영된 상자)은 그만큼 더한다.
    moved = ((10.0, 10.0, 30.0), (90.0, 60.0, 42.0))
    assert place_on(moved, [10, 10, 30], jig, face="top") == [-40.0, -25.0, 0.0]
    with pytest.raises(PatchError, match="face"):
        place_on(part, [0, 0, 0], jig, face="side")
