"""접촉 자리 새기기(`imprint`) — 닿는 자리를 서로의 면에 새겨 짝이 꼭 같게.

판 위의 블록: 판 윗면이 닿는 자리와 나머지로 갈리고, 양쪽 태그의 면이 넓이 · 자리가 같고
법선만 반대다. 받는 쪽(Mechanical)이 접촉 짝을 그대로 집는다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.topology import document


def _stack(block_at: list[float], *, imprint: bool = True) -> Any:
    nodes: list[dict[str, Any]] = [
        {"id": "받침판", "op": "box", "length": 100, "width": 60, "height": 5,
         "align": ["center", "center", "min"]},
        {"id": "블록", "op": "box", "length": 40, "width": 40, "height": 20, "at": block_at,
         "align": ["center", "center", "min"]},
        {"id": "조립", "op": "group", "targets": ["받침판", "블록"]},
    ]  # fmt: skip
    if imprint:
        nodes.append({"id": "새김", "op": "imprint", "target": "조립"})
    return evaluate(parse({"nodes": nodes}))


def _regions(made: Any, groups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    doc = document(
        made.shape,
        [{"name": name, "select": {"what": "faces", **rule}} for name, rule in groups.items()],
        tags=made.tags,
    )
    assert doc["unresolved"] == []
    return {
        name: [(one["area"], one["centroid"], one["normal"]) for one in faces]
        for name, faces in doc["regions"].items()
    }


def test_닿는_자리가_양쪽에_꼭_같은_짝으로_새겨진다() -> None:
    made = _stack([30, 0, 5])
    assert made.shape.is_valid and len(made.shape.solids()) == 2
    assert made.shape.volume == pytest.approx(100 * 60 * 5 + 40 * 40 * 20)
    got = _regions(
        made,
        {
            "판 쪽": {"tag": "받침판/블록"},
            "블록 쪽": {"tag": "블록/받침판"},
            "판 윗면": {"body": "받침판", "normal": [0, 0, 1]},
            "블록 아랫면": {"body": "블록", "normal": [0, 0, -1]},
        },
    )
    assert got["판 쪽"] == [(1600.0, [30.0, 0.0, 5.0], [0.0, 0.0, 1.0])]
    assert got["블록 쪽"] == [(1600.0, [30.0, 0.0, 5.0], [0.0, 0.0, -1.0])]
    # 바디로 고르는 규칙도 그대로 — 판 윗면은 닿는 자리와 나머지 둘이다.
    assert sorted(one[0] for one in got["판 윗면"]) == [1600.0, 4400.0]
    assert got["블록 아랫면"] == got["블록 쪽"]


def test_새기지_않으면_판_윗면은_통째로_하나() -> None:
    plain = _stack([30, 0, 5], imprint=False)
    got = _regions(plain, {"판 윗면": {"body": "받침판", "normal": [0, 0, 1]}})
    assert [one[0] for one in got["판 윗면"]] == [6000.0]


def test_걸쳐_있으면_닿는_만큼만() -> None:
    made = _stack([40, 0, 5])  # 블록 x 20 ~ 60, 판은 50 까지
    got = _regions(made, {"판 쪽": {"tag": "받침판/블록"}, "블록 쪽": {"tag": "블록/받침판"}})
    assert [one[0] for one in got["판 쪽"]] == [1200.0]
    assert [one[0] for one in got["블록 쪽"]] == [1200.0]


def test_겹치면_거절하고_떨어져_있으면_알린다() -> None:
    with pytest.raises(RecipeError, match="겹칩니다"):
        _stack([30, 0, 4])
    apart = _stack([30, 0, 8])
    assert apart.warnings and "닿는 바디가 없어" in apart.warnings[0]


def test_조립이_아니면_새길_것이_없다() -> None:
    with pytest.raises(RecipeError, match="조립"):
        evaluate(
            parse(
                {
                    "nodes": [
                        {"id": "b", "op": "box", "length": 10, "width": 10, "height": 10},
                        {"id": "새김", "op": "imprint", "target": "b"},
                    ]
                }
            )
        )
