"""DOE 엔진 — 조합 · LHS · 시드."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.doe import (
    DoeError,
    build_points,
    count,
    latin_hypercube,
    levels,
    parse_factors,
)

FACTORS: list[dict[str, Any]] = [
    {"name": "두께", "mode": "range", "start": 4, "end": 12, "steps": 5},
    {"name": "길이", "mode": "list", "values": [80, 100]},
    {"name": "폭", "mode": "fixed", "value": 40},
]


def test_구간은_고르게_나누고_고정은_조합에_안_들어간다() -> None:
    factors = parse_factors(FACTORS)
    assert levels(factors[0]) == [4.0, 6.0, 8.0, 10.0, 12.0]
    assert count(factors, "factorial", 0) == 10  # 5 단계 곱하기 2 값, 고정은 곱하지 않는다
    rows = build_points(factors, method="factorial")
    assert len(rows) == 10
    assert all(row["폭"] == 40 for row in rows)  # 고정 치수는 모든 점에서 같다
    assert {row["두께"] for row in rows} == {4.0, 6.0, 8.0, 10.0, 12.0}


def test_LHS_는_시드로_같은_표를_다시_만든다() -> None:
    """해석 결과와 형상을 잇지 못하면 DOE 를 다시 돌려야 한다 — 재현이 곧 값이다."""
    factors = parse_factors(FACTORS)
    first = build_points(factors, method="lhs", samples=12, seed=7)
    again = build_points(factors, method="lhs", samples=12, seed=7)
    other = build_points(factors, method="lhs", samples=12, seed=8)
    assert first == again
    assert first != other
    assert len(first) == 12
    assert all(4.0 <= row["두께"] <= 12.0 for row in first)


def test_LHS_는_구간마다_하나씩_고른다() -> None:
    rows = latin_hypercube(2, 10, seed=3)
    for dimension in (0, 1):
        buckets = sorted(int(row[dimension] * 10) for row in rows)
        assert buckets == list(range(10))  # 열마다 열 칸을 하나씩


def test_너무_많으면_미리_막는다() -> None:
    many = [
        {"name": f"x{i}", "mode": "range", "start": 1, "end": 5, "steps": 5} for i in range(4)
    ]
    factors = parse_factors(many)
    assert count(factors, "factorial", 0) == 625
    with pytest.raises(DoeError, match="625 개입니다"):
        build_points(factors, method="factorial")


def test_틀린_인자는_이름을_짚어_말한다() -> None:
    with pytest.raises(DoeError, match="바꿔 볼 치수를 하나는"):
        parse_factors([{"name": "두께", "mode": "fixed", "value": 5}])
    with pytest.raises(DoeError, match="'두께': 값 목록이 비었습니다"):
        parse_factors([{"name": "두께", "mode": "list", "values": []}])
    with pytest.raises(DoeError, match="두 번"):
        parse_factors([FACTORS[0], FACTORS[0]])
    with pytest.raises(DoeError, match="숫자가 아닙니다"):
        parse_factors([{"name": "두께", "mode": "range", "start": "많이", "end": 5}])


def test_구간_값은_가공_단위로_맞추고_겹치면_하나만() -> None:
    from app.core.doe import levels, parse_factors, snap

    assert snap(6.333333, 0.1) == 6.3
    assert snap(6.35, 0.1) == 6.4
    assert snap(6.26, 0.5) == 6.5
    fine = parse_factors([{"name": "t", "mode": "range", "start": 6, "end": 6.2, "steps": 5}])
    assert levels(fine[0]) == [6.0, 6.1, 6.2]  # 5단계를 0.1 단위로 맞추면 셋만 남는다
    coarse = parse_factors(
        [{"name": "t", "mode": "range", "start": 6, "end": 7, "steps": 4, "resolution": 0.5}]
    )
    assert levels(coarse[0]) == [6.0, 6.5, 7.0]
    listed = parse_factors([{"name": "t", "mode": "list", "values": [4.04, 8.06]}])
    assert levels(listed[0]) == [4.0, 8.1]
