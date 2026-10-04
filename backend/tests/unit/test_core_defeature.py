"""면 지우기(`defeature`) — 작은 구멍 · 필렛을 지우고 이웃 면을 늘려 메운다.

부피로 맞춘다: 지운 것을 메우면 그만큼 부피가 돌아온다. OCC 가 엉뚱하게 메운 것(경계상자로)은
지우지 않고 남기며 경고한다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core.recipe import evaluate, parse
from app.core.recipe.query import find_features
from app.core.recipe.schema import RecipeValidationError

#: 80 x 50 x 10 판 — 수직 모서리 R3, 작은 구멍 Ø4 둘, 큰 구멍 Ø20, M5 카운터보어 · 카운터싱크.
PLATE: list[dict[str, Any]] = [
    {"id": "b", "op": "box", "length": 80, "width": 50, "height": 10,
     "align": ["center", "center", "min"]},
    {"id": "f", "op": "fillet", "target": "b", "edges": "vertical", "radius": 3},
    {"id": "h", "op": "hole", "target": "f", "at": [[-30, -15], [30, -15]], "diameter": 4},
    {"id": "big", "op": "hole", "target": "h", "at": [[0, 0]], "diameter": 20},
    {"id": "cb", "op": "hole", "target": "big", "at": [[-30, 15]], "kind": "counterbore",
     "thread": "M5"},
    {"id": "cs", "op": "hole", "target": "cb", "at": [[30, 15]], "kind": "countersink",
     "thread": "M5"},
]  # fmt: skip

BOX = 80 * 50 * 10
BIG_HOLE = math.pi * 10**2 * 10
CORNERS = 4 * (3**2 - math.pi * 3**2 / 4) * 10


def _made(*more: dict[str, Any]) -> Any:
    return evaluate(parse({"nodes": [*PLATE, *more]}))


def _kinds(made: Any) -> set[str]:
    return {face.geom_type.name for face in made.shape.faces()}


def test_작은_구멍을_지운다_카운터보어_카운터싱크까지() -> None:
    made = _made({"id": "d", "op": "defeature", "target": "cs", "holes_below": 8})
    # 남은 것: 둥근 모서리와 큰 구멍뿐 — 원뿔(카운터싱크)도 사라졌다.
    assert made.shape.volume == pytest.approx(BOX - CORNERS - BIG_HOLE, rel=1e-6)
    assert "CONE" not in _kinds(made)
    assert made.warnings == []


def test_작은_필렛을_지운다() -> None:
    before = _made().shape.volume
    made = _made({"id": "d", "op": "defeature", "target": "cs", "fillets_below": 5})
    assert made.shape.volume == pytest.approx(before + CORNERS, rel=1e-6)


def test_둘_다_지우면_큰_구멍만_남은_상자() -> None:
    made = _made(
        {"id": "d", "op": "defeature", "target": "cs", "holes_below": 8, "fillets_below": 5}
    )
    assert made.shape.volume == pytest.approx(BOX - BIG_HOLE, rel=1e-6)
    assert len(made.shape.faces()) == 7  # 상자 여섯 + 큰 구멍 하나


def test_3D_에서_고른_면을_지운다() -> None:
    wall = find_features(_made().shape, {"what": "faces", "kind": "cylinder", "radius": 10})
    point = wall["items"][0]["center"]
    before = _made().shape.volume
    made = _made({"id": "d", "op": "defeature", "target": "cs", "faces": {"near": [point]}})
    assert made.shape.volume == pytest.approx(before + BIG_HOLE, rel=1e-6)


@pytest.mark.parametrize(("diameter", "kept"), [(4.0, False), (10.0, True)])
def test_DOE_가_구멍을_키우면_기준을_넘은_점에서는_남는다(diameter: float, kept: bool) -> None:
    raw = {
        "params": {"지름": diameter},
        "nodes": [
            {"id": "b", "op": "box", "length": 40, "width": 40, "height": 5},
            {"id": "h", "op": "hole", "target": "b", "at": [[0, 0]], "diameter": "=지름"},
            {"id": "d", "op": "defeature", "target": "h", "holes_below": 6},
        ],
    }
    made = evaluate(parse(raw))
    assert ("CYLINDER" in _kinds(made)) is kept


def _l_block(edges: Any) -> list[dict[str, Any]]:
    return [
        {"id": "s", "op": "sketch", "plane": {"name": "XZ"},
         "shapes": [{"type": "polyline", "start": [0, 0], "segments": [
             {"to": [40, 0]}, {"to": [40, 5]}, {"to": [5, 5]}, {"to": [5, 30]},
             {"to": [0, 30]}]}]},
        {"id": "e", "op": "extrude", "sketch": "s", "distance": 20},
        {"id": "f", "op": "fillet", "target": "e", "edges": edges, "radius": 1},
        {"id": "d", "op": "defeature", "target": "f", "fillets_below": 3},
    ]  # fmt: skip


def test_메울_수_없는_필렛_고리는_남기고_경고한다() -> None:
    """ㄴ자의 모든 모서리를 둥글리면 필렛이 끝면 둘레를 다 두른다 — OCC 는 그것을 지우면
    **경계상자로** 메워 버린다(6424 → 24000, 실측). 그런 결과는 쓰지 않는다."""
    made = evaluate(parse({"nodes": _l_block("all")}))
    assert made.shape.volume == pytest.approx(6424.45, abs=0.1)
    assert len(made.warnings) == 1 and "30개" in made.warnings[0]

    # 한 방향의 모서리만 둥글렸으면 지운다 — 날카로운 ㄴ자(325 mm² x 20)로 돌아온다.
    near = {"near": [[5, -10, 5], [40, -10, 5], [0, -10, 30], [5, -10, 30]], "tolerance": 2}
    made = evaluate(parse({"nodes": _l_block(near)}))
    assert made.shape.volume == pytest.approx(325 * 20, rel=1e-6)
    assert made.warnings == []


@pytest.mark.parametrize(
    ("extra", "words"),
    [({}, "하나 이상을 지정해야"), ({"faces": "top"}, "3D 뷰에서 선택한 위치")],
)
def test_무엇을_지울지_없으면_말한다(extra: dict[str, Any], words: str) -> None:
    with pytest.raises(RecipeValidationError, match=words):
        parse({"nodes": [*PLATE, {"id": "d", "op": "defeature", "target": "cs", **extra}]})
