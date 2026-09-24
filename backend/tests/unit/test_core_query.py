"""찍은 자리를 **말로 되돌려 주기** — 좌표를 조건에 박지 않기 위한 장치."""

from __future__ import annotations

from typing import Any

import pytest
from build123d import Shape

from app.core.recipe import evaluate, parse
from app.core.recipe.query import find_features, select_features, selector_candidates

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
    # 하나만 집는 길도 함께 준다 — 고르는 것은 사람이다. 방향(축)으로 거른 것이 먼저다.
    assert labels["Z축 원통면 중 이 면"]["matches"] == 1
    assert labels["좌표에 가장 가까운 면"]["matches"] == 1


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
    assert 점["엣지 3개가 모이는 점 중 이 점"]["matches"] == 1
    assert 점["좌표에 가장 가까운 점"]["matches"] == 1

    엣지 = _labels({"what": "edges", "point": [0, 25, 10]})
    assert 엣지["x 방향 직선 엣지"]["matches"] == 4
    assert 엣지["x 방향 직선 엣지 중 이 엣지"]["matches"] == 1
    assert 엣지["좌표에 가장 가까운 엣지"]["matches"] == 1


def test_찍은_자리를_그대로_쓴다() -> None:
    """원통면의 `center` 는 축이 아니라 표면 위의 점이다(topology.py 실측) — 그것을 「이
    자리」 로 적어 주면 사람이 읽고 엉뚱한 좌표라고 여긴다."""
    labels = _labels({"what": "faces", "point": [-30, -15, 5]})
    assert labels["좌표에 가장 가까운 면"]["select"]["near"] == [-30, -15, 5]
    assert labels["Z축 원통면 중 이 면"]["select"]["near"] == [-30, -15, 5]


def test_자리를_안_주면_말해_준다() -> None:
    with pytest.raises(ValueError, match="point"):
        selector_candidates(_shape(), {"what": "faces"})


def test_여럿을_골라_묶으면_규칙들의_합이고_겹치면_한_번이다() -> None:
    """3D 에서 Ctrl · Shift 로 하나씩 고른 것을 한 그룹으로 — 규칙 하나로는 「바닥과 구멍
    하나」 를 말할 수 없다. 두 규칙이 같은 면을 집으면 한 번만 센다(안 그러면 하중이 두 번
    걸린다)."""
    바닥 = {"what": "faces", "role": "bottom"}
    구멍하나 = {"what": "faces", "near": [-30, -15, 5], "limit": 1}
    구멍넷 = {"what": "faces", "kind": "cylinder", "radius": 4.25}

    both = select_features(_shape(), {"any": [바닥, 구멍하나]})
    assert both["what"] == "faces" and both["total"] == 2

    # 구멍 하나는 구멍 넷 안에 있다 — 합은 다섯(바닥 + 구멍 넷)이지 여섯이 아니다.
    겹침 = select_features(_shape(), {"any": [바닥, 구멍넷, 구멍하나]})
    assert 겹침["total"] == 5
    assert len({row["index"] for row in 겹침["items"]}) == 5

    # **치수를 바꿔도** 같은 것들을 가리킨다 — 규칙마다 설계점에서 다시 풀린다.
    assert select_features(_shape(6), {"any": [바닥, 구멍하나]})["total"] == 2

    # 하나짜리는 예전 그대로다.
    assert select_features(_shape(), 바닥)["total"] == find_features(_shape(), 바닥)["total"]


def _long_plate(길이: float) -> Shape:
    """길이도 변수인 판 — 구멍은 가운데에서 ±30 에 그대로 있다."""
    recipe = {**PLATE, "params": {"두께": 10, "길이": 길이}}
    recipe["nodes"] = [{**PLATE["nodes"][0], "length": "=길이"}, PLATE["nodes"][1]]
    return evaluate(parse(recipe)).shape


def test_좌표만_쓰면_치수가_바뀔_때_딴_면을_집고_방향으로_거르면_안_헛집는다() -> None:
    """**「이 자리의 면」 이 DOE 에서 못 찾지 않나?** — 못 찾는 게 아니라 더 나쁘다: 가장
    가까운 **딴 면**을 말없이 집는다. 판 길이를 80 → 130 으로 늘리면 +X 옆면을 가리키던
    좌표에 구멍 원통면이 더 가깝다(실측 2026-09-24). 같은 종류 · 같은 방향 중 가장 가까운
    것은 그대로다."""
    picked = selector_candidates(_long_plate(80), {"what": "faces", "point": [40, 0, 5]})
    labels = {one["label"]: one for one in picked["candidates"]}
    좌표만 = labels["좌표에 가장 가까운 면"]
    방향으로 = labels["+X 방향 평면 중 이 면"]
    # 화면은 좌표만 쓰는 후보를 **기본으로 고르지 않는다** — 그러라고 알려 준다.
    assert 좌표만["stable"] is False and 방향으로["stable"] is True

    for 길이 in (80, 120, 130, 200):
        집은것 = find_features(_long_plate(길이), 방향으로["select"])["items"][0]
        assert 집은것["normal"] == [1.0, 0.0, 0.0] and 집은것["center"][0] == 길이 / 2, 길이

    헛집은것 = find_features(_long_plate(130), 좌표만["select"])["items"][0]
    assert 헛집은것["kind"] == "cylinder", "좌표만 쓰면 구멍을 집는다 — 기본이면 안 되는 까닭"
