"""측정값 — 형상에서 바로 나오는 값. 못 잰 것은 빈 칸이지 0 이 아니다."""

from __future__ import annotations

import pytest
from build123d import Box

from app.core.measures import MeasureError, derived, geometric, parse


def test_식은_적은_차례대로_풀고_빈_값을_부르면_빈_칸이다() -> None:
    measures = parse(
        [
            {"name": "부피", "kind": "volume"},
            {"name": "질량", "kind": "expr", "expr": "부피 * 밀도"},
            {"name": "넓이", "kind": "region_area", "region": "바닥"},
            {"name": "넓이_배", "kind": "expr", "expr": "넓이 * 2"},
        ],
        taken=set(),
        variables={"밀도"},
        regions={"바닥"},
    )
    got = derived(measures, {"밀도": 0.002}, {"부피": 1000.0, "넓이": None})
    assert got == {"부피": 1000.0, "질량": 2.0, "넓이": None, "넓이_배": None}


def test_형상에서_부피_겉넓이_크기를_잰다() -> None:
    measures = parse(
        [
            {"name": "v", "kind": "volume"},
            {"name": "a", "kind": "area"},
            {"name": "x", "kind": "size", "axis": "X"},
            {"name": "그룹없음", "kind": "region_area", "region": "바닥"},
        ],
        taken=set(),
        variables=set(),
    )
    got = geometric(Box(10, 20, 30), measures)
    assert got["v"] == pytest.approx(6000) and got["a"] == pytest.approx(2200)
    assert got["x"] == pytest.approx(10) and got["그룹없음"] is None


def test_정의가_틀리면_말한다() -> None:
    with pytest.raises(MeasureError, match="종류"):
        parse([{"name": "a", "kind": "mass"}], taken=set(), variables=set())
    with pytest.raises(MeasureError, match="겹칩니다"):
        parse([{"name": "error", "kind": "volume"}], taken=set(), variables=set())
    with pytest.raises(MeasureError, match="바디"):
        parse(
            [{"name": "a", "kind": "volume", "body": "뚜껑"}],
            taken=set(),
            variables=set(),
            bodies=["판"],
        )
