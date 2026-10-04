"""판 펴기(`unfold`) — 굽힌 판을 전개도로. 잣대는 셋이다:

1. **굽혔다 편 판은 처음 판과 같다**(`bend` 와 같은 k) — 크기 · 넓이 · 구멍.
2. 판금(`sheet_metal`)의 전개 길이는 손으로 셈한 값(안쪽 길이 + 중립면 호)과 같다.
3. k = 0.5 면 중립면이 두께의 가운데라 **전개도 넓이 · 두께 = 굽힌 판의 부피**다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from build123d import Box, Pos
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.unfold import UnfoldError, unfold

T, LENGTH, WIDTH, HOLE = 2.0, 100.0, 40.0, 5.0
FLAT_AREA = LENGTH * WIDTH - math.pi * HOLE**2 - math.pi * 3**2


def _bent(bends: list[dict[str, Any]], **extra: Any) -> Any:
    """100 x 40 x 2 판 — 구멍 하나는 첫 굽힘 구간(x=45)에, 하나는 평평한 곳(10, 10)에."""
    return evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {
                                "type": "rect",
                                "width": LENGTH,
                                "height": WIDTH,
                                "align": ["min", "center"],
                            },
                            {"type": "circle", "radius": HOLE, "at": [45, 0], "mode": "cut"},
                            {"type": "circle", "radius": 3, "at": [10, 10], "mode": "cut"},
                        ],
                    },
                    {"id": "p", "op": "extrude", "sketch": "s", "distance": T},
                    {"id": "b", "op": "bend", "target": "p", "bends": bends, **extra},
                ]
            }
        )
    ).shape


def _volume(shape: Any) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props, 1e-9, False)
    return float(props.Mass())


@pytest.mark.parametrize(
    "bends",
    [
        [{"at": 40, "radius": 5, "angle": 90}],
        [{"at": 30, "radius": 3, "angle": 90}, {"at": 60, "radius": 3, "angle": 90}],
        [{"at": 40, "radius": 5, "angle": 135, "toward": "down"}],
    ],
)
def test_굽혔다_편_판은_처음_판과_같다(bends: list[dict[str, Any]]) -> None:
    got = unfold(_bent(bends))
    summary = got.summary()
    assert summary["thickness"] == pytest.approx(T)
    assert summary["size"] == pytest.approx([LENGTH, WIDTH], abs=1e-3)
    # 굽힘 구간의 구멍은 경계를 점으로 옮겨 근사한다 — 넓이가 아주 조금 다를 수 있다.
    assert summary["area"] == pytest.approx(FLAT_AREA, rel=2e-5)
    assert len(summary["bends"]) == len(bends)
    for found, asked in zip(summary["bends"], bends, strict=True):
        assert found["angle"] == pytest.approx(asked["angle"])
        assert found["radius"] == pytest.approx(asked["radius"])
    # 펼친 판은 XY 위, 두께만큼 섰다.
    box = got.solid.bounding_box()
    assert pytest.approx((0, T)) == (box.min.Z, box.max.Z)
    assert len(got.face.inner_wires()) == 2  # 구멍 둘이 따라왔다


@pytest.mark.parametrize(
    ("path", "side", "radius", "length"),
    [
        # 꺾은선이 안쪽 선(left) — 안쪽 길이 30 · 40, 중립면 호 (r + t/2)·π/2.
        ([[0, 30], [0, 0], [40, 0]], "left", 4, 30 - 4 + 40 - 4 + (4 + 1) * math.pi / 2),
        ([[0, 0], [0, 30], [20, 30]], "left", 3, 30 - 3 + 20 - 3 + (3 + 1) * math.pi / 2),
        # 바깥 선(right) — 꺾은선이 바깥 면이라 r + t 로 돌고, 안쪽 반지름은 그대로 r
        # (2026-10-04 전에는 r - t 였다).
        ([[0, 30], [0, 0], [40, 0]], "right", 3, 30 - 5 + 40 - 5 + (3 + 1) * math.pi / 2),
        # 각진 굽힘 — 굽힘 여유 θ·k·t.
        ([[0, 30], [0, 0], [40, 0]], "left", 0, 30 + 40 + math.pi / 2 * 0.5 * 2),
        ([[0, 30], [0, 0], [40, 0], [40, 25]], "left", 0, 95 + 2 * math.pi / 2 * 0.5 * 2),
    ],
)
def test_판금의_전개_길이는_손셈과_같다(
    path: list[list[float]], side: str, radius: float, length: float
) -> None:
    shape = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "m",
                        "op": "sheet_metal",
                        "thickness": 2,
                        "width": 40,
                        "path": path,
                        "bend_radius": radius,
                        "side": side,
                    }
                ]
            }
        )
    ).shape
    got = unfold(shape).summary()
    assert got["size"] == pytest.approx([length, 40.0], abs=1e-3)
    if radius > 0:
        # k = 0.5 — 전개도 넓이 · 두께가 굽힌 판의 부피다.
        assert got["area"] * 2 == pytest.approx(_volume(shape), rel=1e-6)


def test_각진_판금은_두께가_한결같다() -> None:
    """make_brake_formed 는 각진 모서리를 비스듬히 잘랐다(t=2 ㄱ자 부피 4080) — 우리가
    세운다."""
    for side, volume in (("left", 5760), ("right", 5440)):
        shape = evaluate(
            parse(
                {
                    "nodes": [
                        {
                            "id": "m",
                            "op": "sheet_metal",
                            "thickness": 2,
                            "width": 40,
                            "path": [[0, 30], [0, 0], [40, 0]],
                            "side": side,
                        }
                    ]
                }
            )
        ).shape
        assert _volume(shape) == pytest.approx(volume)
        box = shape.bounding_box()
        assert pytest.approx((-20, 20)) == (
            box.min.Y,
            box.max.Y,
        )  # 폭의 가운데 — 도는 방향과 무관


def test_뒤집으면_굽힘의_위아래가_바뀐다() -> None:
    shape = _bent([{"at": 40, "radius": 5, "angle": 90}])
    up = unfold(shape).summary()["bends"][0]["direction"]
    down = unfold(shape, flip=True).summary()["bends"][0]["direction"]
    assert {up, down} == {"up", "down"}


def test_펼_수_없으면_말한다() -> None:
    with pytest.raises(UnfoldError, match="솔리드 1개"):
        unfold(Box(10, 10, 10) + Pos(50, 0, 0) * Box(10, 10, 10))


def test_레시피의_펴기_노드() -> None:
    made = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "m",
                        "op": "sheet_metal",
                        "thickness": 2,
                        "width": 40,
                        "path": [[0, 30], [0, 0], [40, 0]],
                        "bend_radius": 4,
                    },
                    {"id": "펼침", "op": "unfold", "target": "m"},
                ]
            }
        )
    )
    size = made.summary()["bbox"]["size"]
    assert size == pytest.approx([30 - 4 + 40 - 4 + 5 * math.pi / 2, 40, 2], abs=1e-3)
    with pytest.raises(RecipeError, match="전개할 수"):
        evaluate(
            parse(
                {
                    "nodes": [
                        {"id": "a", "op": "box", "length": 10, "width": 10, "height": 10},
                        {
                            "id": "b",
                            "op": "box",
                            "length": 10,
                            "width": 10,
                            "height": 10,
                            "at": [30, 0, 0],
                        },
                        {"id": "g", "op": "group", "targets": ["a", "b"]},
                        {"id": "f", "op": "unfold", "target": "g"},
                    ]
                }
            )
        )


def test_가져온_STEP_도_같게_편다(tmp_path: Any) -> None:
    """고객이 준 판금 STEP 을 펴는 것이 이 기능의 큰 쓰임이다 — STEP 을 지나도 같아야 한다."""
    from build123d import import_step

    from app.core import export

    shape = _bent([{"at": 40, "radius": 5, "angle": 90}])
    path = export.write_step(shape, tmp_path / "판.step")
    back = import_step(str(path))
    assert unfold(back).summary()["size"] == pytest.approx(unfold(shape).summary()["size"])
    assert unfold(back).summary()["area"] == pytest.approx(unfold(shape).summary()["area"])
