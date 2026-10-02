"""표준 부품 · 구멍에 맞춰 놓기 — 표의 치수, 놓인 자리, 구멍을 따라가는가."""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.schema import RecipeValidationError


def _made(*nodes: dict[str, Any], params: dict[str, float] | None = None) -> Any:
    return evaluate(parse({"params": params or {}, "nodes": list(nodes)}))


def _box(made: Any) -> list[float]:
    box = made.shape.bounding_box()
    return [round(v, 2) for v in (*box.min, *box.max)]


def test_너트_와셔_베어링은_표의_치수로_방향_쪽에_쌓인다() -> None:
    nut = _made({"id": "n", "op": "nut", "at": [0, 0, 10], "thread": "M6"})
    assert _box(nut) == [-5.77, -5.0, 10.0, 5.77, 5.0, 15.2]  # 맞변 10, 높이 5.2
    washer = _made({"id": "w", "op": "washer", "at": [0, 0, 0], "thread": "M8",
                    "direction": [0, 0, -1]})  # fmt: skip
    assert _box(washer) == [-8.0, -8.0, -1.6, 8.0, 8.0, 0.0]
    assert washer.shape.volume == pytest.approx(math.pi * (8**2 - 4.2**2) * 1.6, rel=1e-6)
    bearing = _made({"id": "b", "op": "bearing", "at": [0, 0, 0], "designation": "6204",
                     "direction": [1, 0, 0]})  # fmt: skip
    assert _box(bearing) == [0.0, -23.5, -23.5, 14.0, 23.5, 23.5]


def test_스프링은_자유_길이와_지름대로() -> None:
    made = _made(
        {"id": "s", "op": "spring", "wire": 2, "diameter": 16, "length": 50, "coils": 8}
    )
    low, high = _box(made)[:3], _box(made)[3:]
    assert high[2] - low[2] == pytest.approx(50, abs=0.05)
    assert high[0] == pytest.approx(9, abs=0.05)  # 평균 반지름 8 + 선 반지름 1


def test_코너_브래킷은_두_다리를_따라() -> None:
    made = _made({"id": "k", "op": "bracket", "at": [10, 0, 0], "size": 40,
                  "legs": [[0, 1, 0], [0, 0, 1]]})  # fmt: skip
    assert _box(made) == [-9.0, 0.0, 0.0, 29.0, 38.0, 38.0]


#: 120 x 80 x 10 판 — M6 여유 구멍 넷, M8 카운터보어 하나, 핀 구멍 Ø6 하나.
PLATE: list[dict[str, Any]] = [
    {"id": "판", "op": "box", "length": 120, "width": 80, "height": "=두께",
     "align": ["center", "center", "min"]},
    {"id": "구멍", "op": "hole", "target": "판",
     "at": [[-40, -25], [40, -25], [-40, 25], [40, 25]], "thread": "M6"},
    {"id": "자리", "op": "hole", "target": "구멍", "at": [["=자리_x", 0]],
     "kind": "counterbore", "thread": "M8"},
    {"id": "핀구멍", "op": "hole", "target": "자리", "at": [[0, 30]], "diameter": 6},
]  # fmt: skip


def _plate(*more: dict[str, Any], 두께: float = 10, 자리_x: float = 0) -> Any:
    return _made(*PLATE, *more, params={"두께": 두께, "자리_x": 자리_x})


def test_M6_구멍마다_볼트_머리가_위에_몸통은_구멍_깊이() -> None:
    made = _plate({"id": "볼트", "op": "fasten", "target": "핀구멍", "washer": True,
                   "holes": {"kind": "cylinder", "radius": 3.3}})  # fmt: skip
    assert len(made.shape.solids()) == 4
    # 판 위 10 + 와셔 1.2 + 소켓 머리 6 = 17.2, 몸통은 판 바닥(0)까지.
    assert _box(made)[2] == pytest.approx(0) and _box(made)[5] == pytest.approx(17.2)


def test_너트는_아래_끝에_쌓인다() -> None:
    made = _plate({"id": "너트", "op": "fasten", "target": "핀구멍", "part": "nut",
                   "side": "bottom",
                   "holes": {"kind": "cylinder", "radius": 3.3}})  # fmt: skip
    assert len(made.shape.solids()) == 4
    assert (_box(made)[2], _box(made)[5]) == (-5.2, 0.0)


@pytest.mark.parametrize(("두께", "자리_x"), [(10.0, 0.0), (14.0, -20.0)])
def test_카운터보어_볼트는_턱에_앉고_구멍을_따라간다(두께: float, 자리_x: float) -> None:
    made = _plate(
        {"id": "볼트", "op": "fasten", "target": "핀구멍",
         "holes": {"kind": "cylinder", "radius": 4.5}},
        두께=두께, 자리_x=자리_x,
    )  # fmt: skip
    box = _box(made)
    # M8 카운터보어 깊이 9 — 턱은 윗면에서 9 아래, 소켓 머리(8)가 그 위에 앉아 윗면보다 1 낮다.
    assert box[5] == pytest.approx(두께 - 1)
    assert (box[0] + box[3]) / 2 == pytest.approx(자리_x)


def test_핀은_반대쪽_끝에서_들어가_지름만큼_나온다() -> None:
    made = _plate({"id": "핀", "op": "fasten", "target": "핀구멍", "part": "pin",
                   "holes": {"kind": "cylinder", "radius": 3}})  # fmt: skip
    assert _box(made) == [-3.0, 27.0, 0.0, 3.0, 33.0, 16.0]


def test_맞는_나사가_없으면_말한다() -> None:
    with pytest.raises(RecipeError, match="thread 를 주세요"):
        _plate({"id": "볼트", "op": "fasten", "target": "핀구멍", "part": "bolt"})


@pytest.mark.parametrize(
    "node",
    [
        {"id": "n", "op": "nut", "at": [0, 0, 0], "thread": "M7"},
        {"id": "b", "op": "bearing", "at": [0, 0, 0], "designation": "9999"},
        {"id": "s", "op": "spring", "wire": 2, "diameter": 16, "length": 20, "coils": 10},
        {"id": "k", "op": "bracket", "at": [0, 0, 0], "legs": [[1, 0, 0], [1, 1, 0]]},
    ],
)
def test_표에_없거나_맞지_않으면_말한다(node: dict[str, Any]) -> None:
    with pytest.raises(RecipeValidationError):
        parse({"nodes": [node]})
