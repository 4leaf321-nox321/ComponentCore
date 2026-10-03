"""비틀기 · 테이퍼(`deform`) — 축을 따라 단면을 돌리고 줄인다.

잣대: 비틀기는 단면을 돌릴 뿐이라 부피가 그대로다. 테이퍼(끝 배율 k, 선형)는 부피가
A · L · (1 + (k-1) + (k-1)²/3) 이다. 곡면을 NURBS 로 근사하므로 이 둘에서 어긋남을 본다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from app.core.recipe import evaluate, parse
from app.core.recipe.schema import RecipeValidationError

BAR = {
    "id": "b",
    "op": "box",
    "length": 40,
    "width": 10,
    "height": 100,
    "align": ["center", "center", "min"],
}


def _made(deform: dict[str, Any], *base: dict[str, Any]) -> Any:
    nodes = list(base or (BAR,))
    raw = {"nodes": [*nodes, {"id": "d", "op": "deform", "target": nodes[-1]["id"], **deform}]}
    made = evaluate(parse(raw))
    assert made.shape.is_valid and len(made.shape.solids()) == 1
    return made.shape


def _volume(shape: Any) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props, 1e-9, False)
    return float(props.Mass())


def _taper(k: float) -> float:
    return 1 + (k - 1) + (k - 1) ** 2 / 3


@pytest.mark.parametrize("twist", [90, 180, -45])
def test_비틀어도_부피는_그대로(twist: float) -> None:
    shape = _made({"twist": twist})
    assert _volume(shape) == pytest.approx(40 * 10 * 100, rel=1e-5)
    box = shape.bounding_box()
    assert pytest.approx(100) == box.size.Z
    if abs(twist) >= 90:
        # 40 x 10 단면이 90° 넘게 돌면 X · Y 로 대각선(41.23)까지 쓴다.
        assert pytest.approx(math.hypot(40, 10), abs=0.05) == box.size.X


def test_테이퍼는_끝을_줄인다() -> None:
    shape = _made({"taper": 0.5})
    assert _volume(shape) == pytest.approx(40 * 10 * 100 * _taper(0.5), rel=1e-6)
    top = max(shape.faces(), key=lambda face: face.center().Z)
    assert top.area == pytest.approx(20 * 5, rel=1e-6)


def test_구멍난_판을_비틀고_줄인다() -> None:
    plate = {**BAR, "width": 20}
    hole = {
        "id": "h",
        "op": "hole",
        "target": "b",
        "diameter": 8,
        "at": [[10, 0]],
        "plane": {"origin": [0, 0, 100], "normal": [0, 0, 1]},
    }
    shape = _made({"twist": 90, "taper": 0.7}, plate, hole)
    flat = 40 * 20 * 100 - math.pi * 16 * 100
    assert _volume(shape) == pytest.approx(flat * _taper(0.7), rel=1e-5)


def test_구간을_정하면_그_앞은_그대로_그_뒤는_끝의_변형대로() -> None:
    shape = _made({"twist": 90, "start": 20, "end": 80})
    assert _volume(shape) == pytest.approx(40000, rel=1e-5)
    # 아래 20 은 그대로(40 x 10, X 로 길다), 위 20 은 90° 돌아 Y 로 길다.
    bottom = min(shape.faces(), key=lambda face: face.center().Z)
    top = max(shape.faces(), key=lambda face: face.center().Z)
    low, high = bottom.bounding_box().size, top.bounding_box().size
    assert pytest.approx((40, 10), abs=1e-3) == (low.X, low.Y)
    assert pytest.approx((10, 40), abs=1e-3) == (high.X, high.Y)


def test_기준축을_따라_띠를_비튼다() -> None:
    strip = {
        "id": "s",
        "op": "box",
        "length": 200,
        "width": 20,
        "height": 4,
        "align": ["min", "center", "center"],
    }
    axis = {"id": "ax", "op": "datum_axis", "origin": [0, 0, 0], "direction": [1, 0, 0]}
    raw = {
        "nodes": [
            strip,
            axis,
            {"id": "d", "op": "deform", "target": "s", "axis": "ax", "twist": 90},
        ]
    }
    made = evaluate(parse(raw))
    assert _volume(made.shape) == pytest.approx(200 * 20 * 4, rel=1e-5)
    end = max(made.shape.faces(), key=lambda face: face.center().X)
    assert pytest.approx(20, abs=1e-3) == end.bounding_box().size.Z  # 끝은 세워졌다


def test_바꿀_것이_없거나_구간이_틀리면_말한다() -> None:
    with pytest.raises(RecipeValidationError, match="twist · taper 중 하나"):
        parse({"nodes": [BAR, {"id": "d", "op": "deform", "target": "b"}]})
    with pytest.raises(RecipeValidationError, match="start 보다 커야"):
        parse(
            {
                "nodes": [
                    BAR,
                    {
                        "id": "d",
                        "op": "deform",
                        "target": "b",
                        "twist": 9,
                        "start": 5,
                        "end": 5,
                    },
                ]
            }
        )
    # 없는 기준축 — 레시피 검사에서 먼저 걸린다.
    with pytest.raises(RecipeValidationError, match="앞에 없는 피처"):
        parse(
            {
                "nodes": [
                    BAR,
                    {"id": "d", "op": "deform", "target": "b", "axis": "no", "twist": 9},
                ]
            }
        )
