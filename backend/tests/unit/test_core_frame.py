"""구조 프레임(`frame`) — 단면을 경로의 부재마다 세우고 꺾인 곳을 잇는다.

잣대: 45° 맞대기(miter)와 맞대기(butt)로 이은 닫힌 틀의 부피는 **중심선 길이 x 단면적**이다.
겹치기(none)는 모서리마다 겹친 만큼 더 크다. 바깥 치수는 경로 + 단면 반 폭.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.frame import section
from app.core.recipe.schema import FrameNode, RecipeValidationError

SQUARE = {"type": "square_tube", "width": 40, "thickness": 2}
SQUARE_AREA = 40 * 40 - 36 * 36  # 304
LOOP = [[0, 0, 0], [500, 0, 0], [500, 300, 0], [0, 300, 0], [0, 0, 0]]


def _frame(**extra: Any) -> Any:
    node = {"id": "틀", "op": "frame", "profile": SQUARE, "paths": [LOOP], **extra}
    return evaluate(parse({"nodes": [node]}))


def _box(made: Any) -> list[float]:
    box = made.shape.bounding_box()
    return [round(v, 3) for v in (*box.min, *box.max)]


@pytest.mark.parametrize("corner", ["miter", "butt"])
def test_닫힌_틀은_중심선_길이_곱하기_단면적(corner: str) -> None:
    made = _frame(corner=corner)
    assert made.shape.is_valid and len(made.shape.solids()) == 1
    assert made.shape.volume == pytest.approx(1600 * SQUARE_AREA, rel=1e-6)
    assert _box(made) == [-20, -20, -20, 520, 320, 20]


def test_겹치기는_모서리마다_더_크다() -> None:
    made = _frame(corner="none")
    assert made.shape.volume > 1600 * SQUARE_AREA
    assert _box(made) == [-20, -20, -20, 520, 320, 20]


def test_따로_두면_부재마다_솔리드_하나() -> None:
    made = _frame(corner="butt", separate=True)
    assert len(made.shape.solids()) == 4
    assert made.shape.volume == pytest.approx(1600 * SQUARE_AREA, rel=1e-6)


def test_열린_경로의_끝은_잘리지_않는다_비스듬한_모서리도_잇는다() -> None:
    made = _frame(paths=[[[0, 0, 0], [200, 0, 0], [300, 173.205, 0]]])
    assert made.shape.is_valid and len(made.shape.solids()) == 1
    assert made.shape.volume == pytest.approx((200 + 200) * SQUARE_AREA, rel=1e-4)


def test_단면을_부재_축_둘레로_돌린다() -> None:
    angle = {"type": "angle", "width": 40, "height": 20, "thickness": 4}
    flat = _frame(profile=angle, paths=[[[0, 0, 0], [100, 0, 0]]])
    rolled = _frame(profile=angle, paths=[[[0, 0, 0], [100, 0, 0]]], roll=90)
    # 위쪽(+Z)이 높이 20 → 돌리면 폭 40 이 위로 선다. 부재는 그대로 X 를 따라간다.
    assert _box(flat) == [0, -20, -10, 100, 20, 10]
    assert _box(rolled) == [0, -10, -20, 100, 10, 20]


@pytest.mark.parametrize(
    ("profile", "area"),
    [
        ({"type": "square_tube", "width": 40, "thickness": 2}, 304.0),
        ({"type": "rect_tube", "width": 60, "height": 30, "thickness": 2}, 60 * 30 - 56 * 26),
        ({"type": "flat_bar", "width": 50, "height": 6}, 300.0),
        ({"type": "angle", "width": 40, "height": 40, "thickness": 4}, 40 * 4 + 36 * 4),
        ({"type": "channel", "width": 40, "height": 80, "thickness": 5}, 80 * 5 + 2 * 35 * 5),
        ({"type": "h_beam", "width": 100, "height": 100, "web": 6, "flange": 8}, 2104.0),
    ],
)
def test_단면적(profile: dict[str, Any], area: float) -> None:
    node = FrameNode.model_validate(
        {"id": "f", "op": "frame", "profile": profile, "paths": [[[0, 0, 0], [1, 0, 0]]]}
    )
    shape = section(node.profile)
    assert shape.area == pytest.approx(area, abs=0.05)
    middle = shape.bounding_box().center()
    assert (round(middle.X, 9), round(middle.Y, 9)) == (0, 0)  # 경계상자 가운데가 경로 위


@pytest.mark.parametrize("size", [20, 30, 40, 45])
def test_알루미늄_프로파일은_슬롯_넷과_가운데_구멍(size: int) -> None:
    node = FrameNode.model_validate(
        {
            "id": "f",
            "op": "frame",
            "profile": {"type": "t_slot", "size": size},
            "paths": [[[0, 0, 0], [1, 0, 0]]],
        }
    )
    shape = section(node.profile)
    assert len(shape.faces()) == 1  # 슬롯끼리 안 만난다 — 한 덩어리 단면
    assert len(shape.faces()[0].inner_wires()) == 1  # 가운데 구멍
    assert 0.35 * size**2 < shape.area < 0.65 * size**2


@pytest.mark.parametrize(
    ("extra", "words"),
    [
        ({"profile": {"type": "t_slot", "size": 25}}, "20, 30, 40, 45"),
        ({"profile": {"type": "square_tube", "width": 10, "thickness": 5}}, "두 배"),
        ({"paths": [[[0, 0, 0]]]}, "2개 이상"),
    ],
)
def test_단면_경로가_틀리면_말한다(extra: dict[str, Any], words: str) -> None:
    with pytest.raises(RecipeValidationError, match=words):
        parse(
            {
                "nodes": [
                    {"id": "틀", "op": "frame", "profile": SQUARE, "paths": [LOOP], **extra}
                ]
            }
        )


def test_되돌아가는_경로는_맞댈_면이_없다() -> None:
    with pytest.raises(RecipeError, match="되돌아갑니다"):
        _frame(paths=[[[0, 0, 0], [100, 0, 0], [0, 0, 1]]])


#: 600 x 400 틀(높이 300 중심선) + 바닥에서 틀 중심선까지 오는 기둥 넷.
TABLE = [
    [
        [-300, -200, 300],
        [300, -200, 300],
        [300, 200, 300],
        [-300, 200, 300],
        [-300, -200, 300],
    ],
    [[-300, -200, 0], [-300, -200, 300]],
    [[300, -200, 0], [300, -200, 300]],
    [[300, 200, 0], [300, 200, 300]],
    [[-300, 200, 0], [-300, 200, 300]],
]


def test_기둥은_틀의_밑면에서_멈춘다_그리고_절단_목록() -> None:
    from app.core.recipe.frame import cut_list

    made = _frame(paths=TABLE, corner="miter")
    loop = 2000 * SQUARE_AREA  # 중심선 2000
    posts = 4 * 280 * SQUARE_AREA  # 300 에서 틀 반 폭(20)만큼 줄었다
    assert made.shape.volume == pytest.approx(loop + posts, rel=1e-6)
    assert _box(made) == [-320, -220, 0, 320, 220, 320]

    node = FrameNode.model_validate(
        {"id": "틀", "op": "frame", "profile": SQUARE, "paths": TABLE, "corner": "miter"}
    )
    listed = cut_list(node)
    rows = [
        (one["path"], one["length"], one["start_cut"], one["end_cut"])
        for one in listed["items"]
    ]
    assert rows == [
        (1, 640.0, 45.0, 45.0),
        (1, 440.0, 45.0, 45.0),
        (1, 640.0, 45.0, 45.0),
        (1, 440.0, 45.0, 45.0),
        (2, 280.0, 0.0, 0.0),
        (3, 280.0, 0.0, 0.0),
        (4, 280.0, 0.0, 0.0),
        (5, 280.0, 0.0, 0.0),
    ]
    assert listed["profile"] == "각관 40x2" and listed["count"] == 8
    assert listed["total_volume"] == pytest.approx(loop + posts)


def test_겹치기를_고르면_기둥이_틀_속까지_들어간다() -> None:
    made = _frame(paths=TABLE, corner="miter", meet="overlap")
    assert made.shape.volume > 2000 * SQUARE_AREA + 4 * 280 * SQUARE_AREA


def test_조금_모자란_기둥은_틀까지_늘인다() -> None:
    from app.core.recipe.frame import cut_list

    node = FrameNode.model_validate(
        {
            "id": "틀",
            "op": "frame",
            "profile": SQUARE,
            "paths": [[[0, 0, 300], [600, 0, 300]], [[300, 0, 0], [300, 0, 275]]],
        }
    )
    # 틀 밑면은 280 — 끝이 그 단면 반지름 안에 들면 닿는 것으로 보고 맞춘다.
    assert [one["length"] for one in cut_list(node)["items"]] == [600.0, 280.0]
