"""기준축 · 기준면 — 원점을 지나는 X · Y · Z 말고 아무 축 · 평면에 돌리고 · 비추고 · 그린다.

치수는 손으로 셈한 값과 맞춘다. 형상에서 뽑은 기준은 치수를 바꿔도 따라가야 한다(DOE).
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.schema import RecipeValidationError


def _made(raw: dict[str, Any]) -> Any:
    return evaluate(parse(raw))


def _box(made: Any) -> tuple[list[float], list[float]]:
    box = made.shape.bounding_box()
    return [round(v, 3) for v in box.min], [round(v, 3) for v in box.max]


def test_비켜_선_축으로_돌린다() -> None:
    """x=50 을 지나는 Z 축 둘레로 — 사각형(x 55~65, 높이 20)이 반지름 5~15 고리가 된다."""
    made = _made(
        {
            "nodes": [
                {"id": "s", "op": "sketch", "plane": {"name": "XZ"},
                 "shapes": [{"type": "rect", "width": 10, "height": 20, "at": [60, 0]}]},
                {"id": "축", "op": "datum_axis", "origin": [50, 0, 0], "direction": [0, 0, 1]},
                {"id": "r", "op": "revolve", "sketch": "s", "axis": "축"},
            ]
        }
    )  # fmt: skip
    assert made.shape.volume == pytest.approx(math.pi * (15**2 - 5**2) * 20, rel=1e-6)
    low, high = _box(made)
    assert (low[0], high[0]) == (35.0, 65.0)
    assert made.datums == [
        {"id": "축", "kind": "axis", "origin": (50.0, 0.0, 0.0), "direction": (0.0, 0.0, 1.0)}
    ]


def _plate_with_hole(at: float) -> dict[str, Any]:
    """구멍 자리가 변수인 판 — 구멍 축 둘레로 핀 여섯을 돌려 세운다."""
    return {
        "params": {"자리": at},
        "nodes": [
            {"id": "판", "op": "box", "length": 100, "width": 100, "height": 5,
             "align": ["min", "min", "min"]},
            {"id": "구멍", "op": "hole", "target": "판", "at": [["=자리", 50]],
             "diameter": 20},
            {"id": "구멍축", "op": "datum_axis", "target": "구멍",
             "select": {"what": "faces", "kind": "cylinder", "radius": 10}},
            {"id": "핀", "op": "cylinder", "radius": 2, "height": 10,
             "at": ["=자리 + 15", 50, 0], "align": ["center", "center", "min"]},
            {"id": "핀들", "op": "pattern", "source": "핀", "kind": "circular", "count": 6,
             "axis": "구멍축"},
        ],
    }  # fmt: skip


@pytest.mark.parametrize("at", [40.0, 65.0])
def test_구멍의_축은_치수를_바꿔도_따라간다(at: float) -> None:
    made = _made(_plate_with_hole(at))
    centers = sorted(
        (round(solid.center().X, 3), round(solid.center().Y, 3))
        for solid in made.shape.solids()
    )
    expected = sorted(
        (
            round(at + 15 * math.cos(math.radians(60 * k)), 3),
            round(50 + 15 * math.sin(math.radians(60 * k)), 3),
        )
        for k in range(6)
    )
    assert centers == pytest.approx(expected, abs=1e-3)


def test_윗면에서_띄운_면에_스케치한다() -> None:
    """윗면(두께 h)에서 10 위 — 두께를 바꾸면 스케치도 따라 올라간다."""
    for h in (5, 12):
        made = _made(
            {
                "params": {"h": h},
                "nodes": [
                    {"id": "판", "op": "box", "length": 50, "width": 50, "height": "=h",
                     "align": ["center", "center", "min"]},
                    {"id": "위", "op": "datum_plane", "target": "판",
                     "select": {"kind": "plane", "normal": [0, 0, 1]}, "offset": 10},
                    {"id": "s", "op": "sketch", "plane": {"datum": "위"},
                     "shapes": [{"type": "circle", "radius": 5}]},
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 3},
                ],
            }
        )  # fmt: skip
        low, high = _box(made)
        assert (low[2], high[2]) == (h + 10, h + 13)


def test_기준면에_비추고_기울인_면으로_자른다() -> None:
    mirrored = _made(
        {
            "nodes": [
                {"id": "b", "op": "box", "length": 10, "width": 10, "height": 10,
                 "at": [10, 0, 0]},
                {"id": "면", "op": "datum_plane",
                 "plane": {"name": "YZ", "origin": [30, 0, 0]}},
                {"id": "m", "op": "mirror", "target": "b", "plane": "면"},
            ]
        }
    )  # fmt: skip
    low, high = _box(mirrored)
    assert (low[0], high[0]) == (5.0, 55.0)

    # XY 면을 X 축 둘레로 30° — 40 정육면체의 아래쪽을 남기면 가장 높은 데가 20 tan30.
    tilted = _made(
        {
            "nodes": [
                {"id": "b", "op": "box", "length": 40, "width": 40, "height": 40},
                {"id": "면", "op": "datum_plane", "plane": {"name": "XY"}, "hinge": "X",
                 "angle": 30},
                {"id": "c", "op": "split", "target": "b", "plane": {"datum": "면"},
                 "keep": "bottom"},
            ]
        }
    )  # fmt: skip
    assert _box(tilted)[1][2] == pytest.approx(20 * math.tan(math.radians(30)), abs=1e-3)


def test_세_점으로_기준면() -> None:
    made = _made(
        {
            "nodes": [
                {"id": "b", "op": "box", "length": 20, "width": 20, "height": 20},
                {"id": "면", "op": "datum_plane", "points": [[0, 0, 5], [1, 0, 5], [0, 1, 5]]},
                {"id": "c", "op": "split", "target": "b", "plane": {"datum": "면"}},
            ]
        }
    )  # fmt: skip
    assert _box(made)[0][2] == pytest.approx(5)


def test_회전_이동은_중심을_줄_수_있다() -> None:
    made = _made(
        {
            "nodes": [
                {"id": "b", "op": "box", "length": 20, "width": 10, "height": 10,
                 "at": [50, 0, 0]},
                {"id": "t", "op": "transform", "target": "b", "rotate": [0, 0, 90],
                 "pivot": [50, 0, 0]},
            ]
        }
    )  # fmt: skip
    low, high = _box(made)
    assert (low[0], high[0], low[1], high[1]) == (45.0, 55.0, -10.0, 10.0)


def test_기준을_막_더해도_미리보기는_그_앞의_형상이다() -> None:
    made = _made(
        {
            "nodes": [
                {"id": "b", "op": "box", "length": 10, "width": 10, "height": 10},
                {"id": "축", "op": "datum_axis", "through": [[0, 0, 0], [1, 1, 0]]},
            ]
        }
    )
    assert made.shape.volume == pytest.approx(1000)
    with pytest.raises(RecipeError, match="결과가 될 수 없습니다"):
        _made({**_made_raw_result(), "result": "축"})


def _made_raw_result() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "b", "op": "box", "length": 10, "width": 10, "height": 10},
            {"id": "축", "op": "datum_axis", "through": [[0, 0, 0], [1, 0, 0]]},
        ]
    }


@pytest.mark.parametrize(
    ("nodes", "words"),
    [
        (
            [
                {"id": "면", "op": "datum_plane", "plane": {"name": "XY"}},
                {"id": "b", "op": "box", "length": 9, "width": 9, "height": 9},
                {"id": "p", "op": "pattern", "source": "b", "kind": "circular", "count": 3,
                 "axis": "면"},
            ],
            "기준축\\(datum_axis\\)이 아닙니다",
        ),
        (
            [
                {"id": "축", "op": "datum_axis", "through": [[0, 0, 0], [1, 0, 0]]},
                {"id": "f", "op": "fillet", "target": "축", "radius": 1},
            ],
            "형상이 아닙니다",
        ),
        (
            [{"id": "축", "op": "datum_axis", "through": [[0, 0, 0], [1, 0, 0]],
              "origin": [0, 0, 0], "direction": [1, 0, 0]}],
            "중 하나로 정합니다",
        ),
        ([{"id": "면", "op": "datum_plane", "plane": {"name": "XY"}, "angle": 30}], "hinge"),
        (
            [
                {"id": "b", "op": "box", "length": 9, "width": 9, "height": 9},
                {"id": "m", "op": "mirror", "target": "b", "plane": "없는면"},
            ],
            "앞에 없는 피처",
        ),
    ],
)  # fmt: skip
def test_기준을_잘못_가리키면_어디가_왜인지_말한다(
    nodes: list[dict[str, Any]], words: str
) -> None:
    with pytest.raises(RecipeValidationError, match=words):
        parse({"nodes": nodes})


def test_형상에서_고른_것이_여럿이면_하나를_고르라고_한다() -> None:
    raw = {
        "nodes": [
            {"id": "b", "op": "box", "length": 10, "width": 10, "height": 10},
            {"id": "면", "op": "datum_plane", "target": "b", "select": {"kind": "plane"}},
        ]
    }
    with pytest.raises(RecipeError, match="6 개에 맞습니다"):
        _made(raw)
