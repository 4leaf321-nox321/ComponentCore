"""중간면 — 두께가 한결같은 얇은 판의 가운데 면(셸 요소 해석용).

잣대: 굽힌 판의 중간면 넓이는 펼친 판(구멍 빼고)과 같다(중립면 = 가운데). 각진 판금은
꺾은선을 두께 가운데로 옮긴 길이 x 폭, 쉘 상자는 바닥 + 네 벽의 가운데 면.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core.recipe import evaluate, parse
from app.core.recipe.midsurface import MidSurfaceError, midsurface


def _mid(nodes: list[dict[str, Any]]) -> Any:
    return midsurface(evaluate(parse({"nodes": nodes})).shape)


def test_굽힌_판의_중간면은_펼친_판과_넓이가_같다() -> None:
    got = _mid(
        [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [
                    {"type": "rect", "width": 100, "height": 40, "align": ["min", "center"]},
                    {"type": "circle", "radius": 5, "at": [20, 0], "mode": "cut"},
                ],
            },
            {"id": "p", "op": "extrude", "sketch": "s", "distance": 2},
            {"id": "b", "op": "bend", "target": "p", "bends": [{"at": 40, "radius": 5}]},
        ]
    )
    summary = got.summary()
    assert summary["bodies"][0]["thickness"] == pytest.approx(2)
    assert summary["area"] == pytest.approx(100 * 40 - math.pi * 25, rel=1e-6)
    assert summary["notes"] == []
    # 면만 — 솔리드가 아니다(셸 요소가 받는 것).
    assert got.shape.solids() == [] and len(got.shape.faces()) == 3


def test_각진_판금과_쉘_상자() -> None:
    sheet = _mid(
        [
            {
                "id": "m",
                "op": "sheet_metal",
                "thickness": 2,
                "width": 40,
                "path": [[0, 30], [0, 0], [50, 0], [50, 20]],
                "bend_radius": 0,
            }
        ]
    )
    # 재료가 꺾은선 바깥에 붙는다 — 가운데 선은 1 씩 바깥: 31 + 52 + 21.
    assert sheet.summary()["area"] == pytest.approx((31 + 52 + 21) * 40, rel=1e-6)
    box = _mid(
        [
            {"id": "b", "op": "box", "length": 100, "width": 60, "height": 40},
            {"id": "s", "op": "shell", "target": "b", "thickness": 2, "open": "top"},
        ]
    )
    assert box.summary()["area"] == pytest.approx(98 * 58 + 2 * (98 + 58) * 39, rel=1e-6)


def test_두께가_곳곳에_다르면_알린다() -> None:
    ribbed = _mid(
        [
            {"id": "p", "op": "box", "length": 100, "width": 60, "height": 2},
            {"id": "r", "op": "box", "length": 100, "width": 4, "height": 10, "at": [0, 0, 5]},
            {"id": "u", "op": "union", "targets": ["p", "r"]},
        ]
    )
    assert any("두께가 위치마다 다릅니다" in one for one in ribbed.summary()["notes"])


def test_판이_아니면_거절한다() -> None:
    with pytest.raises(MidSurfaceError, match="판이 아닙니다"):
        _mid([{"id": "c", "op": "box", "length": 20, "width": 20, "height": 20}])
