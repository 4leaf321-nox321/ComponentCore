"""찍은 자리를 **말로 되돌려 주기** — 좌표를 조건에 박지 않기 위한 장치."""

from __future__ import annotations

from typing import Any

import pytest
from build123d import Shape

from app.core.recipe import evaluate, parse
from app.core.recipe.query import find_features, selector_candidates

#: 볼트 구멍 넷짜리 판. 두께는 변수다.
PLATE: dict[str, Any] = {
    "params": {"두께": 10},
    "nodes": [
        {
            "id": "b",
            "op": "box",
            "length": 80,
            "width": 50,
            "height": "=두께",
            "align": ["center", "center", "min"],
        },
        {
            "id": "h",
            "op": "hole",
            "target": "b",
            "at": [[-30, -15], [30, -15], [-30, 15], [30, 15]],
            "diameter": 8.5,
        },
    ],
}


def _shape(두께: float = 10) -> Shape:
    return evaluate(parse({**PLATE, "params": {"두께": 두께}})).shape


def _labels(pick: dict[str, Any], 두께: float = 10) -> dict[str, dict[str, Any]]:
    got = selector_candidates(_shape(두께), pick)
    return {one["label"]: one for one in got["candidates"]}


def test_구멍_하나를_찍으면_넷_전부를_잡는_후보도_준다() -> None:
    """볼트 구멍은 대개 **넷을 한꺼번에** 쓴다 — 하나만 자동으로 고르면 나머지 셋이
    조용히 빠지고, 그 사실은 설계점 스무 개를 돌린 뒤에 보인다."""
    labels = _labels({"what": "faces", "point": [-30, -15, 5]})
    group = labels["반지름 4.25 원통면"]
    assert group["matches"] == 4
    assert group["select"] == {"what": "faces", "kind": "cylinder", "radius": 4.25}
    # 하나만 집는 길도 함께 준다 — 고르는 것은 사람이다.
    assert labels["이 자리의 면"]["matches"] == 1


def test_셀렉터는_치수를_바꿔도_같은_것을_가리킨다() -> None:
    """**이 장치의 존재 이유다.** 좌표로 저장하면 두께를 바꾸는 순간 그 자리에
    아무것도 없다."""
    바닥 = _labels({"what": "faces", "point": [0, 0, 0]})["bottom 면"]["select"]
    구멍 = _labels({"what": "faces", "point": [-30, -15, 5]})["반지름 4.25 원통면"]["select"]

    for 두께 in (3, 6, 10, 20):
        shape = _shape(두께)
        assert find_features(shape, 바닥)["total"] == 1, f"두께 {두께}"
        assert find_features(shape, 구멍)["total"] == 4, f"두께 {두께}"


def test_점과_엣지도_고른다() -> None:
    점 = _labels({"what": "vertices", "point": [40, 25, 10]})
    assert 점["엣지 3개가 모이는 점"]["matches"] == 8  # 상자의 꼭짓점 여덟
    assert 점["이 자리의 점"]["matches"] == 1

    엣지 = _labels({"what": "edges", "point": [0, 25, 10]})
    assert 엣지["x 방향 직선 엣지"]["matches"] == 4
    assert 엣지["이 자리의 엣지"]["matches"] == 1


def test_찍은_자리를_그대로_쓴다() -> None:
    """원통면의 `center` 는 축이 아니라 표면 위의 점이다(topology.py 실측) — 그것을 「이
    자리」 로 적어 주면 사람이 읽고 엉뚱한 좌표라고 여긴다."""
    labels = _labels({"what": "faces", "point": [-30, -15, 5]})
    assert labels["이 자리의 면"]["select"]["near"] == [-30, -15, 5]


def test_자리를_안_주면_말해_준다() -> None:
    with pytest.raises(ValueError, match="point"):
        selector_candidates(_shape(), {"what": "faces"})
