"""조립 구속 — 숫자 대신 관계로 놓는다(`core/recipe/mates.py`).

잣대: 블록을 판 위에 맞대고 구멍끼리 동심으로 놓으면 블록의 자리가 손셈과 같다. 처음 자리 ·
회전이 어떻든 같은 데로 가고, 구속이 정하지 않은 쪽은 처음 자리를 지킨다. 서로 맞지 않는
구속은 몇째가 얼마나 어긋나는지 말한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.recipe import schema as S
from app.core.recipe.evaluate import RecipeError, evaluate

SOURCES: dict[str, dict[str, Any]] = {
    # 판 100 x 60 x 10(가운데가 원점 — 윗면 z = 5), (20, 15) 에 Ø8 관통.
    "plate": {
        "nodes": [
            {"id": "p", "op": "box", "length": 100, "width": 60, "height": 10},
            {"id": "h", "op": "hole", "target": "p", "diameter": 8, "at": [[20, 15]]},
        ]
    },
    # 블록 20 x 20 x 30, 가운데 Ø8 관통(Z).
    "block": {
        "nodes": [
            {"id": "b", "op": "box", "length": 20, "width": 20, "height": 30},
            {"id": "h", "op": "hole", "target": "b", "diameter": 8, "at": [[0, 0]]},
        ]
    },
}

TOUCH = {
    "type": "touch",
    "this": {"what": "faces", "role": "bottom"},
    "to": "jig",
    "select": {"what": "faces", "role": "top"},
}
HOLES = {
    "type": "concentric",
    "this": {"what": "faces", "kind": "cylinder"},
    "to": "jig",
    "select": {"what": "faces", "kind": "cylinder"},
}
SIDE = {"what": "faces", "kind": "plane", "normal": [1, 0, 0]}


def _placed(
    mates: list[dict[str, Any]],
    *,
    rotate: tuple[float, float, float] = (90, 0, 0),
    translate: tuple[float, float, float] = (50, 50, 50),
) -> tuple[Any, dict[str, Any]]:
    recipe = S.parse(
        {
            "nodes": [
                {"id": "jig", "op": "component", "source": "plate"},
                {
                    "id": "blk",
                    "op": "component",
                    "source": "block",
                    "translate": list(translate),
                    "rotate": list(rotate),
                    "mates": mates,
                },
                {"id": "all", "op": "group", "targets": ["jig", "blk"]},
            ]
        }
    )
    made = evaluate(recipe, resolve_component=SOURCES.__getitem__)
    info = next(one for one in made.nodes if one.id == "blk")
    assert info.placement is not None
    return info.bbox, info.placement


def test_맞대고_동심이면_구멍_위에_앉는다() -> None:
    box, placed = _placed([TOUCH, HOLES])
    assert box == ((10.0, 5.0, 5.0), (30.0, 25.0, 35.0))
    # 남은 것은 구멍 축 둘레 회전 하나.
    assert (placed["free_rotation"], placed["free_translation"]) == (1, 0)


@pytest.mark.parametrize("rotate", [(0, 0, 0), (90, 0, 0), (180, 0, 0), (33, -71, 12)])
def test_처음_회전이_어떻든_같은_데로(rotate: tuple[float, float, float]) -> None:
    box, placed = _placed([TOUCH, HOLES], rotate=rotate)
    # 블록의 가운데(가져온 도면의 원점)가 구멍 축 위, 바닥이 판 윗면. 축 둘레로 돈 만큼은
    # 남은 움직임이라 처음 회전을 따른다.
    assert placed["translation"] == pytest.approx([20, 15, 20], abs=1e-6)
    assert (box[0][2], box[1][2]) == pytest.approx((5, 35), abs=1e-3)


def test_구속이_정하지_않은_쪽은_처음_자리를_지킨다() -> None:
    box, placed = _placed([TOUCH])
    # 높이만 정해졌다 — 가운데 (50, 50) 은 그대로.
    assert box == ((40.0, 40.0, 5.0), (60.0, 60.0, 35.0))
    assert (placed["free_rotation"], placed["free_translation"]) == (1, 2)


def test_틈_각도_면맞춤_직각() -> None:
    box, _ = _placed([{**TOUCH, "offset": 2}, HOLES])
    assert box[0][2] == pytest.approx(7)
    angled = {"type": "angle", "angle": 30, "this": SIDE, "to": "jig", "select": SIDE}
    box, placed = _placed([TOUCH, HOLES, angled])
    assert placed["rotation"][0][0] == pytest.approx(0.866025, abs=1e-5)
    assert (placed["free_rotation"], placed["free_translation"]) == (0, 0)
    flush = {"type": "flush", "this": SIDE, "to": "jig", "select": SIDE}
    box, _ = _placed([TOUCH, flush])
    assert box[1][0] == pytest.approx(50)  # 블록의 +X 면이 판의 +X 면(x = 50)과 한 면
    square = {"type": "perpendicular", "this": SIDE, "to": "X"}
    _, placed = _placed([TOUCH, HOLES, square])
    assert abs(placed["rotation"][0][0]) == pytest.approx(0, abs=1e-6)


def test_구멍_테두리와_기준면에도_건다() -> None:
    rim = {
        "type": "concentric",
        "this": {"what": "edges", "kind": "circle", "near": [4, 0, -15]},
        "to": "jig",
        "select": {"what": "edges", "kind": "circle", "near": [24, 15, 5]},
    }
    box, _ = _placed([TOUCH, rim])
    assert box == ((10.0, 5.0, 5.0), (30.0, 25.0, 35.0))
    floor = {"type": "touch", "this": {"what": "faces", "role": "bottom"}, "to": "XY"}
    box, _ = _placed([floor], rotate=(0, 0, 0))
    assert box[0][2] == pytest.approx(0)


@pytest.mark.parametrize(
    ("mates", "said"),
    [
        ([TOUCH, {**TOUCH, "offset": 3}], "구속 2(접촉): 이전 구속과 충돌합니다(오차 3 mm)"),
        (
            [TOUCH, {**TOUCH, "type": "flush"}],
            "구속 2(동일 평면): 이전 구속과 충돌합니다(오차 180°)",
        ),
        (
            [{**HOLES, "this": {"what": "faces", "role": "bottom"}}],
            "동심 구속은 축끼리만 가능합니다",
        ),
        ([{k: v for k, v in TOUCH.items() if k != "select"}], "select가 없습니다"),
        ([{**TOUCH, "this": {"what": "faces", "kind": "plane"}}], "near로 그중 하나를"),
    ],
)
def test_맞지_않는_구속은_몇째인지_말한다(mates: list[dict[str, Any]], said: str) -> None:
    with pytest.raises(RecipeError) as caught:
        _placed(mates)
    assert caught.value.node_id == "blk"
    assert said in caught.value.message


def test_구속은_앞에_놓인_것에만() -> None:
    with pytest.raises(S.RecipeValidationError, match="앞에 없는 피처"):
        S.parse(
            {
                "nodes": [
                    {"id": "blk", "op": "component", "source": "block", "mates": [TOUCH]},
                    {"id": "jig", "op": "component", "source": "plate"},
                ]
            }
        )
    with pytest.raises(S.RecipeValidationError, match="각도 구속에는 각"):
        S.parse(
            {
                "nodes": [
                    {"id": "jig", "op": "component", "source": "plate"},
                    {
                        "id": "blk",
                        "op": "component",
                        "source": "block",
                        "mates": [{**TOUCH, "type": "angle"}],
                    },
                ]
            }
        )
