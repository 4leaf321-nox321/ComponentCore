"""판 굽히기(`bend`) — 펼친 판을 접고 감는다. 치수는 손으로 셈한 값과 맞춰 본다.

정확도의 잣대: `k_factor` 0.5 면 중립면이 두께의 가운데라, 반지름 방향 옆벽으로 감은 판의
부피가 펼친 판과 **정확히** 같다. 근사로 감았다면 여기서 어긋난다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.query import find_features
from app.core.recipe.schema import RecipeValidationError

T = 2.0
LENGTH = 100.0
WIDTH = 40.0
HOLE = 5.0


def _plate(bends: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """100 x 40 x 2 판, x 0 ~ 100 · y 가운데. 구멍 하나가 x=45 에 있다(첫 굽힘 구간 안)."""
    return {
        "params": extra.pop("params", {}),
        "nodes": [
            {
                "id": "전개",
                "op": "sketch",
                "shapes": [
                    {
                        "type": "rect",
                        "width": LENGTH,
                        "height": WIDTH,
                        "align": ["min", "center"],
                    },
                    {"type": "circle", "radius": HOLE, "at": [45, 0], "mode": "cut"},
                ],
            },
            {"id": "판", "op": "extrude", "sketch": "전개", "distance": T},
            {"id": "굽힘", "op": "bend", "target": "판", "bends": bends, **extra},
        ],
    }


def _volume(shape: Any) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props, 1e-9, False)
    return float(props.Mass())


FLAT = LENGTH * WIDTH * T - math.pi * HOLE**2 * T


def _bbox(raw: dict[str, Any]) -> tuple[Any, list[float], list[float]]:
    """평가 결과와 바운딩 박스의 (x, y, z) 최소 · 최대."""
    made = evaluate(parse(raw))
    box = made.shape.bounding_box()
    return made, list(box.min.to_tuple()), list(box.max.to_tuple())


def test_위로_90도_접으면_치수와_부피가_맞다() -> None:
    radius, at = 5.0, 40.0
    made, low, high = _bbox(_plate([{"at": at, "radius": radius, "angle": 90}]))
    assert made.shape.is_valid and len(made.shape.solids()) == 1
    # 구멍이 굽힘 구간에 걸려 있어도 부피는 펼친 판 그대로 — 정확히 감았다.
    assert _volume(made.shape) == pytest.approx(FLAT, rel=1e-7)
    zone = (radius + T / 2) * math.pi / 2
    assert high[0] == pytest.approx(at + radius + T, abs=1e-4)  # 바깥 면이 축에서 R + t
    assert high[2] == pytest.approx(T + radius + (LENGTH - at - zone), abs=1e-4)
    assert low[2] == pytest.approx(0, abs=1e-4)


def test_아래로_접으면_거울이다() -> None:
    radius, at = 5.0, 40.0
    _, low, high = _bbox(_plate([{"at": at, "radius": radius, "toward": "down"}]))
    zone = (radius + T / 2) * math.pi / 2
    assert high[2] == pytest.approx(T, abs=1e-4)
    assert low[2] == pytest.approx(-(radius + (LENGTH - at - zone)), abs=1e-4)
    assert high[0] == pytest.approx(at + radius + T, abs=1e-4)


def test_굽힘면은_원통면이다_안쪽_R_바깥_R_더하기_t() -> None:
    made = evaluate(parse(_plate([{"at": 20, "radius": 4}])))
    found = find_features(made.shape, {"what": "faces", "kind": "cylinder"})
    radii = sorted({round(float(one["radius"]), 3) for one in found["items"]})
    assert radii == sorted([4.0, 4.0 + T, HOLE])  # 굽힘 안 · 밖, 그리고 평평한 데 남은 구멍


def test_두_번_접으면_U_채널() -> None:
    radius = 3.0
    made, low, high = _bbox(
        _plate([{"at": 30, "radius": radius}, {"at": 60, "radius": radius}])
    )
    zone = (radius + T / 2) * math.pi / 2
    rise = 60 - (30 + zone)  # 세운 판의 평평한 길이
    back = LENGTH - (60 + zone)  # 다시 누운 판이 되돌아오는 길이
    assert _volume(made.shape) == pytest.approx(FLAT, rel=1e-7)
    assert high[2] == pytest.approx(T + radius + rise + radius + T, abs=1e-4)
    # 세운 판의 안쪽 면이 x = 30 + R, 둘째 굽힘 축은 거기서 R 안쪽(x = 30). 되돌아온 판은
    # 그 축에서 back 만큼 간다.
    assert low[0] == pytest.approx(30 - back, abs=1e-4)


def test_끝까지_감으면_반원통() -> None:
    radius = 10.0
    neutral = radius + T / 2
    length = math.pi * neutral  # 반 바퀴 길이
    raw = {
        "nodes": [
            {"id": "판", "op": "box", "length": length, "width": 30, "height": T,
             "align": ["min", "center", "min"]},
            {"id": "감기", "op": "bend", "target": "판",
             "bends": [{"at": 0, "radius": radius, "until": "end"}]},
        ]
    }  # fmt: skip
    made, low, high = _bbox(raw)
    assert _volume(made.shape) == pytest.approx(length * 30 * T, rel=1e-7)
    assert high[0] == pytest.approx(radius + T, abs=1e-4)
    assert high[2] == pytest.approx(2 * (radius + T), abs=1e-4)
    assert low[0] == pytest.approx(0, abs=1e-4)


def test_중립면_위치가_펼친_길이를_정한다() -> None:
    radius, at, k = 5.0, 40.0, 0.3
    _, _, high = _bbox(_plate([{"at": at, "radius": radius}], k_factor=k))
    zone = (radius + k * T) * math.pi / 2
    assert high[2] == pytest.approx(T + radius + (LENGTH - at - zone), abs=1e-4)


def test_도면_변수로_훑을_수_있다() -> None:
    raw = _plate([{"at": "=자리", "radius": "=R", "angle": "=각"}])
    raw["params"] = {"자리": 40, "R": 5, "각": 45}
    made = evaluate(parse(raw))
    assert made.shape.is_valid and _volume(made.shape) == pytest.approx(FLAT, rel=1e-7)


def test_선_판은_Y_쪽이_위다() -> None:
    raw = {
        "nodes": [
            {"id": "s", "op": "sketch", "plane": {"name": "XZ"},
             "shapes": [
                 {"type": "rect", "width": 60, "height": 20, "align": ["min", "center"]}
             ]},
            {"id": "판", "op": "extrude", "sketch": "s", "distance": T},
            {"id": "굽힘", "op": "bend", "target": "판", "bends": [{"at": 30, "radius": 3}]},
        ]
    }  # fmt: skip
    _, low, high = _bbox(raw)
    assert high[1] > 20 and low[1] == pytest.approx(-T, abs=1e-4)


def test_굽힌_뒤에_필렛_구멍을_더한다() -> None:
    raw = _plate([{"at": 40, "radius": 5}])
    raw["nodes"].append(
        {"id": "둥글", "op": "fillet", "target": "굽힘", "edges": "all", "radius": 0.5}
    )
    made = evaluate(parse(raw))
    assert made.shape.is_valid and _volume(made.shape) < FLAT


def _box_then(
    *nodes: dict[str, Any], bends: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "판", "op": "box", "length": 80, "width": 30, "height": 3,
             "align": ["min", "center", "min"]},
            *nodes,
            {"id": "굽힘", "op": "bend", "target": nodes[-1]["id"] if nodes else "판",
             "bends": bends or [{"at": 40, "radius": 4}]},
        ]
    }  # fmt: skip


@pytest.mark.parametrize(
    ("raw", "words"),
    [
        (
            _box_then(
                {
                    "id": "홈",
                    "op": "box",
                    "length": 10,
                    "width": 10,
                    "height": 2,
                    "at": [20, 0, 2],
                    "align": ["center", "center", "min"],
                },
                {"id": "파기", "op": "cut", "target": "판", "tools": ["홈"]},
            ),
            "두께가 균일한 판이 아닙니다",
        ),
        (
            _box_then(
                {"id": "깎기", "op": "chamfer", "target": "판", "edges": "all", "length": 0.5}
            ),
            "굽힌 뒤에",
        ),
        (_box_then(bends=[{"at": 90, "radius": 4}]), "판의 범위\\(0 ~ 80\\) 안의 값이어야"),
        (
            _box_then(bends=[{"at": 70, "radius": 10, "angle": 180}]),
            "판 끝\\(80\\)을 넘습니다",
        ),
        (
            _box_then(bends=[{"at": 20, "radius": 10}, {"at": 25, "radius": 3}]),
            "이전 굽힘이",
        ),
        (_box_then(bends=[{"at": 1, "radius": 3, "until": "end"}]), "한 바퀴를"),
    ],
)
def test_굽힐_수_없으면_왜인지_말한다(raw: dict[str, Any], words: str) -> None:
    with pytest.raises(RecipeError, match=words) as failure:
        evaluate(parse(raw))
    assert failure.value.node_id == "굽힘"


def test_판_위의_방향이어야_한다() -> None:
    raw = _box_then()
    raw["nodes"][-1]["along"] = [0, 0, 1]
    with pytest.raises(RecipeError, match="판 위의 방향"):
        evaluate(parse(raw))


@pytest.mark.parametrize(
    ("bends", "words"),
    [
        ([{"at": 40, "radius": 4}, {"at": 20, "radius": 4}], "이전 굽힘"),
        (
            [{"at": 20, "radius": 4, "until": "end"}, {"at": 60, "radius": 4}],
            "마지막 굽힘에만",
        ),
        ([{"at": 20, "radius": 4, "angle": 360}], "360"),
    ],
)
def test_굽힘_목록의_모양(bends: list[dict[str, Any]], words: str) -> None:
    with pytest.raises(RecipeValidationError, match=words):
        parse(_box_then(bends=bends))


def _box_net(shapes: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """상자 전개도 — 바탕 100 x 60, 네 변에 깊이 20 의 날개(판 두께 2)."""
    return {
        "nodes": [
            {"id": "s", "op": "sketch", "shapes": shapes},
            {"id": "p", "op": "extrude", "sketch": "s", "distance": T},
            {
                "id": "b",
                "op": "bend",
                "target": "p",
                "along": [1, 0, 0],
                "bends": [{"at": 50, "radius": 2, "angle": 90}],
                "also": [
                    {"along": [-1, 0, 0], "bends": [{"at": 50, "radius": 2, "angle": 90}]},
                    {"along": [0, 1, 0], "bends": [{"at": 30, "radius": 2, "angle": 90}]},
                    {"along": [0, -1, 0], "bends": [{"at": 30, "radius": 2, "angle": 90}]},
                ],
                **extra,
            },
        ]
    }


CROSS = [
    {"type": "rect", "width": 140, "height": 60, "at": [0, 0]},
    {"type": "rect", "width": 100, "height": 100, "at": [0, 0]},
]
CROSS_AREA = 140 * 60 + 100 * 100 - 100 * 60


def test_네_방향으로_접으면_상자() -> None:
    made, low, high = _bbox(_box_net(CROSS))
    assert len(made.shape.solids()) == 1 and made.shape.is_valid
    assert _volume(made.shape) == pytest.approx(CROSS_AREA * T, rel=1e-6)
    # 바탕 100 x 60 에 날개 두께 2 + 안쪽 R 2 가 양쪽으로. 날개 높이 = R + t + (20 - 굽힘 호).
    assert [h - lo for h, lo in zip(high, low, strict=True)] == pytest.approx(
        [108, 68, 2 + T + 20 - 3 * math.pi / 2], abs=1e-3
    )


def test_모서리가_겹치면_거절하거나_따낸다() -> None:
    full = [{"type": "rect", "width": 140, "height": 100, "at": [0, 0]}]
    with pytest.raises(RecipeError, match="모서리에서 겹칩니다"):
        evaluate(parse(_box_net(full)))
    made = evaluate(parse(_box_net(full, corner_relief=True)))
    # 네 모서리(20 x 20)를 따내면 십자 전개도와 같은 상자다.
    assert _volume(made.shape) == pytest.approx(CROSS_AREA * T, rel=1e-6)


def test_상자도_전개도로_되돌아간다() -> None:
    from app.core.recipe.unfold import unfold

    raw = _box_net(CROSS)
    groups = raw["nodes"][2]["also"]
    groups[1]["bends"][0]["toward"] = "down"  # 한 날개는 아래로
    groups[2]["bends"] = [  # 한 날개는 두 번(45° 씩)
        {"at": 30, "radius": 3, "angle": 45},
        {"at": 40, "radius": 2, "angle": 45},
    ]
    flat = unfold(evaluate(parse(raw)).shape)
    assert flat.summary()["size"] == pytest.approx([140, 100], abs=1e-3)
    assert flat.summary()["area"] == pytest.approx(CROSS_AREA, rel=1e-6)
    assert len(flat.bends) == 5
