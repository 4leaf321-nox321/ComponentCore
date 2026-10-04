"""중간면 — 두께가 한결같은 얇은 판의 가운데 면(셸 요소 해석용).

잣대: 굽힌 판의 중간면 넓이는 펼친 판(구멍 빼고)과 같다(중립면 = 가운데). 각진 판금은
꺾은선을 두께 가운데로 옮긴 길이 x 폭, 쉘 상자는 바닥 + 네 벽의 가운데 면.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core.recipe import evaluate, parse
from app.core.recipe.midsurface import MidSurfaceError, midsurface


def _mid(nodes: list[dict[str, Any]]) -> Any:
    return midsurface(evaluate(parse({"nodes": nodes})).shape)


def test_굽힌_판의_중간면은_펼친_판과_넓이가_같다() -> None:
    got = _mid(
        [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [
                    {"type": "rect", "width": 100, "height": 40, "align": ["min", "center"]},
                    {"type": "circle", "radius": 5, "at": [20, 0], "mode": "cut"},
                ],
            },
            {"id": "p", "op": "extrude", "sketch": "s", "distance": 2},
            {"id": "b", "op": "bend", "target": "p", "bends": [{"at": 40, "radius": 5}]},
        ]
    )
    summary = got.summary()
    assert summary["bodies"][0]["thickness"] == pytest.approx(2)
    assert summary["area"] == pytest.approx(100 * 40 - math.pi * 25, rel=1e-6)
    assert summary["notes"] == []
    # 면만 — 솔리드가 아니다(셸 요소가 받는 것).
    assert got.shape.solids() == [] and len(got.shape.faces()) == 3


def test_각진_판금과_쉘_상자() -> None:
    sheet = _mid(
        [
            {
                "id": "m",
                "op": "sheet_metal",
                "thickness": 2,
                "width": 40,
                "path": [[0, 30], [0, 0], [50, 0], [50, 20]],
                "bend_radius": 0,
            }
        ]
    )
    # 재료가 꺾은선 바깥에 붙는다 — 가운데 선은 1 씩 바깥: 31 + 52 + 21.
    assert sheet.summary()["area"] == pytest.approx((31 + 52 + 21) * 40, rel=1e-6)
    box = _mid(
        [
            {"id": "b", "op": "box", "length": 100, "width": 60, "height": 40},
            {"id": "s", "op": "shell", "target": "b", "thickness": 2, "open": "top"},
        ]
    )
    assert box.summary()["area"] == pytest.approx(98 * 58 + 2 * (98 + 58) * 39, rel=1e-6)


def test_두께가_곳곳에_다르면_알린다() -> None:
    ribbed = _mid(
        [
            {"id": "p", "op": "box", "length": 100, "width": 60, "height": 2},
            {"id": "r", "op": "box", "length": 100, "width": 4, "height": 10, "at": [0, 0, 5]},
            {"id": "u", "op": "union", "targets": ["p", "r"]},
        ]
    )
    assert any("두께가 위치마다 다릅니다" in one for one in ribbed.summary()["notes"])


def test_판이_아니면_거절한다() -> None:
    with pytest.raises(MidSurfaceError, match="판이 아닙니다"):
        _mid([{"id": "c", "op": "box", "length": 20, "width": 20, "height": 20}])


def _bracket_on_block(block_height: float = 40.0) -> Any:
    """판이 아닌 덩어리(지그 블록) 위의 판금 브래킷 — 조립."""
    return evaluate(
        parse(
            {
                "nodes": [
                    {"id": "블록", "op": "box", "length": 80, "width": 40,
                     "height": block_height, "align": ["min", "center", "min"]},
                    {"id": "브래킷", "op": "sheet_metal", "thickness": 2, "width": 30,
                     "path": [[10, block_height], [50, block_height], [50, block_height + 50]],
                     "bend_radius": 4, "side": "right"},
                    {"id": "조립", "op": "group", "targets": ["블록", "브래킷"]},
                ]
            }
        )
    )  # fmt: skip


def test_쉘_파트만_만들고_실패는_파트마다_남긴다() -> None:
    """판이 아닌 파트 하나가 점 전체를 오류로 만들어 쉘 브래킷의 중간면도 안 나왔다
    (SimEngBay, 2026-10-04). 이제 쉘 파트만, 실패는 그 파트에만."""
    made = _bracket_on_block()
    with pytest.raises(MidSurfaceError, match="블록"):
        midsurface(made.shape)  # 예전 그대로 — 엄격하면 블록에서 멈춘다
    only = midsurface(made.shape, ["브래킷"], strict=False)
    assert [one.name for one in only.bodies] == ["브래킷"] and only.failed == []
    loose = midsurface(made.shape, strict=False)
    assert [one.name for one in loose.bodies] == ["브래킷"]
    assert [name for name, _ in loose.failed] == ["블록"]
    summary = loose.summary()
    assert summary["failed"][0]["name"] == "블록"
    # 셸과 짝지을 손잡이 — 넓이 무게중심 · 경계상자(셸에는 이름이 없다).
    body = summary["bodies"][0]
    assert len(body["centroid"]) == 3 and body["bbox"][1][2] == pytest.approx(90.0)
    with pytest.raises(MidSurfaceError, match="없는 파트"):
        midsurface(made.shape, ["없는 파트"], strict=False)


def test_쉘_파트의_영역은_중간면의_면과_모서리로_옮긴다() -> None:
    from app.core.recipe import topology
    from app.core.recipe.midsurface import attach

    made = _bracket_on_block()
    definitions = [
        {"name": "누름", "select": {"what": "faces", "body": "브래킷", "normal": [1, 0, 0]}},
        {"name": "옆", "select": {"what": "faces", "body": "브래킷", "normal": [0, 1, 0]}},
        {"name": "블록 윗면",
         "select": {"what": "faces", "body": "블록", "normal": [0, 0, 1]}},
        {"name": "끝점", "select": {"what": "vertices", "of_face": {"body": "브래킷",
                                    "normal": [1, 0, 0]}, "near": [50, 15, 90], "limit": 1}},
    ]  # fmt: skip
    regions, _ = topology.regions(made.shape, definitions, made.tags)
    attach(regions, made.shape, midsurface(made.shape, ["브래킷"], strict=False), definitions)
    # 겉면 → 중간면의 면(원래 겉면의 바깥 법선을 둔다 — 쉘은 앞뒤가 없다).
    (face,) = regions["누름"][0]["mid"]
    assert face["face"]["normal"] == [1.0, 0.0, 0.0]
    assert face["face"]["centroid"][0] == pytest.approx(49.0)
    assert face["face"]["area"] == pytest.approx(regions["누름"][0]["area"])
    # 두께 쪽 면(ㄱ자 옆면) → 중간면의 모서리 셋(눕힌 다리 · 굽힘 · 세운 다리).
    edges = regions["옆"][0]["mid"]
    assert len(edges) == 3 and all("edge" in one for one in edges)
    assert {one["edge"].get("radius") for one in edges} == {None, 5.0}
    # 점 → 중간면 위로 내린 점(x 50 → 49).
    (point,) = regions["끝점"][0]["mid"]
    assert point["point"] == pytest.approx([49.0, 15.0, 90.0])
    # 쉘 파트가 아닌 지문에는 붙이지 않는다.
    assert "mid" not in regions["블록 윗면"][0]
