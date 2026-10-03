"""곡면 — 점 격자 · 곡선 · 테두리로 면을 세우고, 두께를 주거나 칼로 쓴다(`surfaces.py`)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.schema import RecipeValidationError

#: 말안장 — z = 0.002 (x² - y²), x -50~50 · y -40~40.
SADDLE = [
    [[x, y, 0.002 * (x * x - y * y)] for x in range(-50, 51, 25)] for y in range(-40, 41, 20)
]


def _made(*nodes: dict[str, Any], preview: bool = False) -> Any:
    return evaluate(parse({"nodes": list(nodes)}), allow_sketch=preview)


def test_점_격자를_지나는_곡면에_두께를() -> None:
    surface = {"id": "s", "op": "surface", "kind": "grid", "grid": SADDLE}
    shown = _made(surface, preview=True)
    # 곡면만으로는 미리보기에서만 보인다 — 무엇을 하면 되는지 함께.
    assert any("thicken" in one for one in shown.warnings)
    area = shown.shape.area
    assert area > 100 * 80  # 휘었으니 평면보다 넓다
    with pytest.raises(RecipeError, match="결과가 곡면입니다"):
        _made(surface)
    for side in ("front", "back", "both"):
        made = _made(
            surface, {"id": "t", "op": "thicken", "target": "s", "thickness": 3, "side": side}
        )
        assert made.shape.is_valid
        assert made.shape.volume == pytest.approx(area * 3, rel=2e-3)
    # 앞 · 뒤로 준 두께는 서로 다른 쪽에 붙는다(앞은 곡면의 법선 쪽 — 점의 차례가 정한다).
    front = _made(surface, {"id": "t", "op": "thicken", "target": "s", "thickness": 3})
    back = _made(
        surface, {"id": "t", "op": "thicken", "target": "s", "thickness": 3, "side": "back"}
    )
    assert abs(front.shape.bounding_box().max.Z - back.shape.bounding_box().max.Z) > 2


def test_곡선들을_잇고_테두리를_메운다() -> None:
    curves = [
        [[x, y, z + 10 * math.sin(x / 20)] for x in range(-50, 51, 10)]
        for y, z in ((-30, 0), (0, 5), (30, 0))
    ]
    lofted = _made(
        {"id": "s", "op": "surface", "kind": "loft", "curves": curves},
        {"id": "t", "op": "thicken", "target": "s", "thickness": 2},
    )
    assert lofted.shape.is_valid and lofted.shape.volume > 100 * 60 * 2
    filled = _made(
        {
            "id": "s",
            "op": "surface",
            "kind": "fill",
            "boundary": [[-40, -30, 0], [40, -30, 5], [40, 30, 0], [-40, 30, 5]],
            "through": [[0, 0, 12]],
            "smooth": False,
        },
        preview=True,
    )
    assert pytest.approx(12, abs=0.5) == filled.shape.bounding_box().max.Z


def test_곡면으로_블록을_가른다() -> None:
    block = {"id": "b", "op": "box", "length": 100, "width": 80, "height": 40}
    surface = {"id": "s", "op": "surface", "kind": "grid", "grid": SADDLE}
    top = _made(block, surface, {"id": "c", "op": "split", "target": "b", "tool": "s"})
    bottom = _made(
        block,
        surface,
        {"id": "c", "op": "split", "target": "b", "tool": "s", "keep": "bottom"},
    )
    assert top.shape.volume + bottom.shape.volume == pytest.approx(100 * 80 * 40, rel=1e-6)
    # 말안장이라 위아래가 다르다 — 가운데(0) 평면이 아니다.
    assert top.shape.volume != pytest.approx(bottom.shape.volume, rel=1e-3)
    with pytest.raises(RecipeError, match="곡면\\(surface\\)이 아닙니다"):
        _made(
            block,
            {"id": "k", "op": "box", "length": 1, "width": 1, "height": 1},
            {"id": "c", "op": "split", "target": "b", "tool": "k"},
        )


@pytest.mark.parametrize(
    ("surface", "words"),
    [
        ({"kind": "grid", "grid": [[[0, 0, 0], [1, 0, 0]]]}, "2 x 2"),
        ({"kind": "grid", "grid": [[[0, 0, 0], [1, 0, 0]], [[0, 1, 0]]]}, "같아야"),
        ({"kind": "loft", "curves": [[[0, 0, 0], [1, 0, 0]]]}, "곡선 둘 이상"),
        ({"kind": "fill", "boundary": [[0, 0, 0], [1, 0, 0]]}, "점 셋 이상"),
    ],
)
def test_모자란_곡면은_만들기_전에(surface: dict[str, Any], words: str) -> None:
    with pytest.raises(RecipeValidationError, match=words):
        parse({"nodes": [{"id": "s", "op": "surface", **surface}]})
