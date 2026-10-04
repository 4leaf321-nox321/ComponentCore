"""스케치 구속 — 점을 대충 두고 관계와 치수를 적으면 풀이가 맞춘다(`sketch_solver.py`)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe import schema as S
from app.core.recipe.schema import RecipeValidationError
from app.core.recipe.sketch_solver import SketchSolveError, solve

ROUGH = {"a": [1, -2], "b": [55, 3], "c": [58, 37], "d": [-3, 44]}


def _loop(names: list[str]) -> list[dict[str, str]]:
    return [{"from": a, "to": b} for a, b in zip(names, names[1:] + names[:1], strict=True)]


def _shape(points: dict[str, Any], segments: list[Any], constraints: list[Any]) -> Any:
    return {
        "type": "constrained",
        "points": points,
        "segments": segments,
        "constraints": constraints,
    }


BOXY = [
    {"type": "horizontal", "segments": [0]},
    {"type": "vertical", "segments": [1]},
    {"type": "horizontal", "segments": [2]},
    {"type": "vertical", "segments": [3]},
]


def _solve(shape: dict[str, Any]) -> Any:
    return solve(S.ConstrainedShape.model_validate(shape))


def test_대충_그린_네모를_치수로_맞춘다() -> None:
    shape = _shape(
        ROUGH,
        _loop(["a", "b", "c", "d"]),
        [
            {"type": "fix", "points": ["a"], "at": [0, 0]},
            *BOXY,
            {"type": "length", "segments": [0], "value": 60},
            {"type": "length", "segments": [1], "value": "=높이"},
        ],
    )
    raw = {
        "params": {"높이": 40},
        "nodes": [
            {"id": "s", "op": "sketch", "shapes": [shape]},
            {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
        ],
    }
    assert evaluate(parse(raw)).shape.volume == pytest.approx(60 * 40 * 5)
    solved = solve(parse(raw).nodes[0].shapes[0])  # type: ignore[union-attr, arg-type]
    assert solved.points["c"] == pytest.approx((60, 40), abs=1e-6)
    assert solved.free == 0
    # 변수를 바꾸면 따라간다 — 실험계획이 훑는 길.
    taller = {**raw, "params": {"높이": 25}}
    assert evaluate(parse(taller)).shape.volume == pytest.approx(60 * 25 * 5)


def test_덜_정하면_남은_움직임을_센다() -> None:
    # 고정도 길이도 없다 — 옮기기 둘 + 가로 · 세로 크기 둘.
    assert _solve(_shape(ROUGH, _loop(["a", "b", "c", "d"]), BOXY)).free == 4


def test_호를_두_선에_접하게_반지름으로() -> None:
    points = {
        "a": [0, 0],
        "b": [80, 0],
        "c": [80, 10],
        "d": [22, 10],
        "o": [22, 22],
        "e": [10, 23],
        "f": [10, 60],
        "g": [0, 60],
    }
    segments = [
        {"from": "a", "to": "b"},
        {"from": "b", "to": "c"},
        {"from": "c", "to": "d"},
        {"from": "d", "to": "e", "center": "o", "ccw": False},
        {"from": "e", "to": "f"},
        {"from": "f", "to": "g"},
        {"from": "g", "to": "a"},
    ]
    constraints = [
        {"type": "fix", "points": ["a"]},
        {"type": "horizontal", "segments": [0]},
        {"type": "vertical", "segments": [1]},
        {"type": "horizontal", "segments": [2]},
        {"type": "vertical", "segments": [4]},
        {"type": "horizontal", "segments": [5]},
        {"type": "vertical", "segments": [6]},
        {"type": "length", "segments": [0], "value": 80},
        {"type": "length", "segments": [6], "value": 60},
        {"type": "dy", "points": ["b", "c"], "value": 10},
        {"type": "dx", "points": ["g", "f"], "value": 10},
        {"type": "radius", "segments": [3], "value": 12},
        {"type": "tangent", "segments": [2, 3]},
        {"type": "tangent", "segments": [3, 4]},
    ]
    shape = _shape(points, segments, constraints)
    solved = _solve(shape)
    assert solved.free == 0
    assert solved.points["e"] == pytest.approx((10, 22), abs=1e-6)  # 닿는 점에 정확히
    raw = {
        "nodes": [
            {"id": "s", "op": "sketch", "shapes": [shape]},
            {"id": "e", "op": "extrude", "sketch": "s", "distance": 1},
        ]
    }
    area = 80 * 10 + 10 * 50 + (12 * 12 - math.pi * 144 / 4)
    assert evaluate(parse(raw)).shape.volume == pytest.approx(area, rel=1e-6)


def test_각은_선_사이_그린_쪽에_가깝게() -> None:
    shape = _shape(
        {"a": [0, 0], "b": [100, 0], "c": [80, 30], "d": [15, 32]},
        _loop(["a", "b", "c", "d"]),
        [
            {"type": "fix", "points": ["a"]},
            {"type": "horizontal", "segments": [0]},
            {"type": "length", "segments": [0], "value": 100},
            # 구간 3 은 d → a 방향이지만 「a 에서 60°」 로 읽힌다(그린 모양이 그쪽이다).
            {"type": "angle", "segments": [0, 3], "value": 60},
            {"type": "parallel", "segments": [0, 2]},
            {"type": "equal", "segments": [1, 3]},
            {"type": "dy", "points": ["a", "d"], "value": 30},
        ],
    )
    solved = _solve(shape)
    assert solved.points["d"] == pytest.approx((30 / math.tan(math.radians(60)), 30), abs=1e-6)
    assert solved.points["c"] == pytest.approx(
        (100 - 30 / math.tan(math.radians(60)), 30), abs=1e-6
    )


def test_맞지_않는_구속은_몇째인지_말한다() -> None:
    shape = _shape(
        ROUGH,
        _loop(["a", "b", "c", "d"]),
        [
            *BOXY,
            {"type": "length", "segments": [0], "value": 60},
            {"type": "length", "segments": [2], "value": 50},  # 네모의 마주 보는 변은 같다
        ],
    )
    with pytest.raises(SketchSolveError, match=r"구속 6\(길이\): 이전 구속과 충돌합니다"):
        _solve(shape)
    raw = {"nodes": [{"id": "s", "op": "sketch", "shapes": [shape]}]}
    with pytest.raises(RecipeError, match="구속 6"):
        evaluate(parse(raw), allow_sketch=True)


@pytest.mark.parametrize(
    ("segments", "constraints", "words"),
    [
        ([{"from": "a", "to": "b"}, {"from": "c", "to": "a"}], [], "다음 구간의 from"),
        (_loop(["a", "b", "c"]), [{"type": "length", "segments": [0]}], r"값\(value\)이 필요"),
        (_loop(["a", "b", "c"]), [{"type": "fix", "points": ["z"]}], "존재하지 않는 점 .z."),
        (_loop(["a", "b", "c"]), [{"type": "radius", "segments": [0], "value": 3}], "호"),
    ],
)
def test_틀린_구속은_만들기_전에_막는다(
    segments: list[Any], constraints: list[Any], words: str
) -> None:
    shape = _shape({"a": [0, 0], "b": [10, 0], "c": [0, 10]}, segments, constraints)
    with pytest.raises(RecipeValidationError, match=words):
        parse({"nodes": [{"id": "s", "op": "sketch", "shapes": [shape]}]})
