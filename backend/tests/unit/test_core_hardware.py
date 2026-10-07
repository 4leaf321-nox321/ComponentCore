"""표준 부품 · 구멍에 맞춰 놓기 — 표의 치수, 놓인 자리, 구멍을 따라가는가."""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core import fasteners
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
    # 판 위 10 + 와셔 1.6(ISO 7089 M6) + 소켓 머리 6(ISO 4762) = 17.6, 몸통은 판 바닥(0)까지.
    assert _box(made)[2] == pytest.approx(0) and _box(made)[5] == pytest.approx(17.6)


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
    with pytest.raises(RecipeError, match="thread를 지정하십시오"):
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


def _bolt(nominal: float, head: str) -> list[float]:
    """구멍 없이 놓은 볼트 하나 — 머리가 앉는 면은 z=0, 몸통은 아래로 20."""
    return _box(_made({"id": "b", "op": "bolt", "at": [0, 0, 0], "nominal": nominal,
                       "length": 20, "head": head}))  # fmt: skip


@pytest.mark.parametrize(
    ("nominal", "head", "across", "corner", "height"),
    [
        (6, "hex", 10.0, 11.55, 4.0),  # ISO 4017 — 맞변 10, 머리 높이 4
        (24, "hex", 36.0, 41.57, 15.0),
        (6, "socket", 10.0, 10.0, 6.0),  # ISO 4762 — 머리 지름 10, 높이 6
        (1.6, "socket", 3.0, 3.0, 1.6),
    ],
)
def test_볼트_머리는_규격_치수다(
    nominal: float, head: str, across: float, corner: float, height: float
) -> None:
    """전에는 비례(머리 지름 1.5d)로 그려 M6 육각의 맞변이 7.8 이었다(2026-10-08)."""
    box = _bolt(nominal, head)
    assert (box[3] - box[0], box[4] - box[1]) == pytest.approx((corner, across), abs=0.02)
    assert (box[2], box[5]) == pytest.approx((-20, height))


def test_표에_없는_호칭은_예전_비례로_그린다() -> None:
    box = _bolt(7, "hex")  # 맞변 1.5 x 7 x √3/2 = 9.09, 높이 0.65 x 7 = 4.55
    assert box[4] - box[1] == pytest.approx(9.09, abs=0.02)
    assert box[5] == pytest.approx(4.55)


@pytest.mark.parametrize(
    ("diameter", "thread"),
    [
        (1.6, "M2"),  # M2 탭 드릴 — M1.6 의 여유 구멍(1.8)보다 가깝다
        (1.8, "M1.6"),
        (3.3, "M4"),  # M4 탭 드릴 — 전에는 표 순서대로 M3(여유 3.4)이 먼저 걸렸다
        (3.4, "M3"),
        (6.6, "M6"),
        (21.0, "M24"),
        (26.0, "M24"),
        (30.0, None),
    ],
)
def test_구멍_지름에_가장_가까운_나사를_고른다(diameter: float, thread: str | None) -> None:
    assert fasteners.thread_for(diameter) == thread


def test_나사_표는_M1_6_부터_M24_까지_같은_호칭을_든다() -> None:
    names = list(fasteners.THREADS)
    assert names[0] == "M1.6" and names[-1] == "M24" and len(names) == 14
    for table in (fasteners.PITCHES, fasteners.SOCKET_HEADS, fasteners.HEX_HEADS,
                  fasteners.NUTS, fasteners.WASHERS):  # fmt: skip
        assert list(table) == names
    nut = _made({"id": "n", "op": "nut", "at": [0, 0, 0], "thread": "M20"})
    assert _box(nut)[4] - _box(nut)[1] == pytest.approx(30.0)  # 전에는 M20 을 거절했다
