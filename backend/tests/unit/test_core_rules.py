"""규칙으로 고른 엣지 · 면 — 위치로 고르면 DOE 가 치수를 바꿀 때 그 자리에 없어 실패한다.

실측(2026-10-02): 판 두께를 12 → 16 으로 훑자 위치(`near`)로 고른 모따기 엣지를 못 찾았다.
`{"query": …}` 는 설계점마다 다시 찾는다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.query import find_features


def _plate(t: float, *more: dict[str, Any]) -> Any:
    """100 x 60 x t 판 위에 30 x 30 x 20 블록, 판 구석에 지름 10 구멍."""
    return evaluate(
        parse(
            {
                "params": {"t": t},
                "nodes": [
                    {"id": "판", "op": "box", "length": 100, "width": 60, "height": "=t",
                     "align": ["center", "center", "min"]},
                    {"id": "블록", "op": "box", "length": 30, "width": 30, "height": 20,
                     "at": [0, 0, "=t"], "align": ["center", "center", "min"]},
                    {"id": "합", "op": "union", "targets": ["판", "블록"]},
                    {"id": "구멍", "op": "hole", "target": "합", "at": [[35, 0]],
                     "diameter": 10},
                    *more,
                ],
            }
        )
    )  # fmt: skip


BASE = {t: 100 * 60 * t + 30 * 30 * 20 - math.pi * 25 * t for t in (12.0, 16.0)}


@pytest.mark.parametrize("t", [12.0, 16.0])
def test_구멍의_위_원을_규칙으로_모따기(t: float) -> None:
    """위치로 적은 엣지(z = 12)는 두께 16 에서 없다 — 규칙(지름 10 원 중 위의 것)은 있다."""
    rule = {"query": {"kind": "circle", "radius": 5, "near": [35, 5, 100]}}
    made = _plate(
        t, {"id": "c", "op": "chamfer", "target": "구멍", "length": 1, "edges": rule}
    )
    # 모따기 한 바퀴: 원뿔대 고리의 단면 ½·1·1 을 반지름 5.33 둘레로 돌린 것만큼 줄어든다.
    removed = 0.5 * 1 * 1 * 2 * math.pi * (5 + 1 / 3)
    assert made.shape.volume == pytest.approx(BASE[t] - removed, rel=1e-6)


def test_위치로_고르면_두께를_바꿀_때_못_찾는다() -> None:
    # 두께 12 에서 3D 로 누른 자리 그대로 — 그 엣지의 가운데 점.
    rim = find_features(_plate(12.0).shape, {"what": "edges", "kind": "circle", "radius": 5})
    top = max(rim["items"], key=lambda one: one["midpoint"][2])
    near = {"near": [top["midpoint"]], "tolerance": 1}
    _plate(12.0, {"id": "c", "op": "chamfer", "target": "구멍", "length": 1, "edges": near})
    with pytest.raises(RecipeError, match="찾았습니다"):
        _plate(
            16.0, {"id": "c", "op": "chamfer", "target": "구멍", "length": 1, "edges": near}
        )


@pytest.mark.parametrize("t", [12.0, 16.0])
def test_면의_테두리를_규칙으로_필렛(t: float) -> None:
    """블록 윗면(가장 높은 +Z 평면)의 둘레 넷을 둥글린다 — 윗면이 줄어든 만큼 보인다."""
    rim = {"query": {"of_face": {"normal": [0, 0, 1], "near": [0, 0, 1000]}}}
    made = _plate(t, {"id": "f", "op": "fillet", "target": "구멍", "radius": 2, "edges": rim})
    top = find_features(
        made.shape, {"what": "faces", "normal": [0, 0, 1], "near": [0, 0, 1000]}
    )
    assert top["items"][0]["center"][2] == pytest.approx(t + 20)
    # 위 둘레 넷만 둥글리면 윗면의 평평한 데는 한 변이 2 x 2 줄어든 정사각형이다.
    assert top["items"][0]["area"] == pytest.approx(26 * 26, rel=1e-6)


def test_쉘의_열린_면도_규칙으로() -> None:
    made = evaluate(
        parse(
            {
                "nodes": [
                    {"id": "b", "op": "box", "length": 40, "width": 30, "height": 20},
                    {"id": "s", "op": "shell", "target": "b", "thickness": 2,
                     "open": {"query": {"normal": [0, 0, 1]}}},
                ]
            }
        )
    )  # fmt: skip
    assert made.shape.volume == pytest.approx(40 * 30 * 20 - 36 * 26 * 18, rel=1e-6)


def test_면의_꼭짓점도_고른다() -> None:
    made = _plate(12.0)
    corners = find_features(
        made.shape,
        {"what": "vertices", "of_face": {"normal": [0, 0, 1], "near": [0, 0, 1000]}},
    )
    assert corners["total"] == 4


def test_규칙에_맞는_것이_없으면_말한다() -> None:
    with pytest.raises(RecipeError, match="엣지가 없습니다"):
        _plate(12.0, {"id": "f", "op": "fillet", "target": "구멍", "radius": 1,
                      "edges": {"query": {"kind": "circle", "radius": 99}}})  # fmt: skip
