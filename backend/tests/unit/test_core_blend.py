"""비대칭 모따기 · 반지름이 변하는 필렛 — 깎인 부피와 남은 면의 꼭짓점으로 맞춘다.

40 x 30 x 20 상자의 위 앞 엣지(y=0, z=20, X 를 따라 40)를 다룬다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core.recipe import evaluate, parse
from app.core.recipe.schema import RecipeValidationError

BOX: dict[str, Any] = {
    "id": "b",
    "op": "box",
    "length": 40,
    "width": 30,
    "height": 20,
    "align": ["min", "min", "min"],
}
EDGE = {"near": [[20, 0, 20]], "tolerance": 1}


def _made(node: dict[str, Any]) -> Any:
    return evaluate(parse({"nodes": [BOX, {"target": "b", "edges": EDGE, **node}]}))


def _top_corners(made: Any) -> list[tuple[float, float]]:
    """윗면(+Z 평면)의 꼭짓점 (x, y) — 모따기 · 필렛이 윗면을 어디까지 먹었나."""
    top = next(
        face
        for face in made.shape.faces()
        if face.geom_type.name == "PLANE" and face.normal_at().Z > 0.999
    )
    return sorted({(round(v.X, 3), round(v.Y, 3)) for v in top.vertices()})


def test_두_거리_모따기는_위를_보는_면에서_length() -> None:
    made = _made({"id": "c", "op": "chamfer", "length": 2, "length2": 6})
    assert made.shape.volume == pytest.approx(40 * 30 * 20 - 0.5 * 2 * 6 * 40, rel=1e-9)
    assert _top_corners(made)[0] == (0.0, 2.0)  # 윗면에서 2


def test_기준면을_고르면_그_면에서_length() -> None:
    made = _made(
        {
            "id": "c",
            "op": "chamfer",
            "length": 2,
            "length2": 6,
            "reference": {"near": [[20, 0, 10]]},
        }
    )
    assert _top_corners(made)[0] == (0.0, 6.0)  # 앞면에서 2, 윗면에서 6


def test_거리_각도_모따기() -> None:
    made = _made({"id": "c", "op": "chamfer", "length": 3, "angle": 30})
    removed = 0.5 * 3 * 3 * math.tan(math.radians(30)) * 40
    assert made.shape.volume == pytest.approx(40 * 30 * 20 - removed, rel=1e-6)
    assert _top_corners(made)[0] == (0.0, 3.0)


@pytest.mark.parametrize(("start", "at_zero"), [([0, 0, 20], 1.0), ([40, 0, 20], 5.0)])
def test_반지름이_변하는_필렛은_start_쪽_끝이_radius(
    start: list[float], at_zero: float
) -> None:
    made = _made({"id": "f", "op": "fillet", "radius": 1, "radius_end": 5, "start": start})
    # 윗면이 앞에서부터 먹힌 폭 — x=0 쪽과 x=40 쪽.
    eaten = {x: min(y for xx, y in _top_corners(made) if xx == x) for x in (0.0, 40.0)}
    assert made.shape.is_valid
    assert eaten == {0.0: at_zero, 40.0: 6.0 - at_zero}


def test_두_거리와_각을_함께_쓰지_않는다() -> None:
    with pytest.raises(RecipeValidationError, match="하나만"):
        parse(
            {
                "nodes": [
                    BOX,
                    {"id": "c", "op": "chamfer", "target": "b", "length": 2, "length2": 3,
                     "angle": 30},
                ]
            }
        )  # fmt: skip
