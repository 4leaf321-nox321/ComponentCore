"""DOE 엔진 — 조합 · LHS · 시드 · 걸러 보기."""

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
    passes,
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


def test_값이_없는_칸은_조건을_만족하지_않는다() -> None:
    """계산이 실패한 점이 「무게 5 kg 이하」 에 들어가면 안 된다 — 0 으로 읽히던 자리."""
    ok, why = passes({"mass_g": 120}, [{"key": "mass_g", "op": "lte", "value": 200}])
    assert ok and why is None
    ok, why = passes({"mass_g": 250}, [{"key": "mass_g", "op": "lte", "value": 200}])
    assert not ok and why is not None and "250" in why
    for empty in (None, "", "계산 실패"):
        ok, why = passes({"mass_g": empty}, [{"key": "mass_g", "op": "lte", "value": 200}])
        assert not ok and why is not None and "값이 없습니다" in why
    # 범위 · 이상
    assert passes({"v": 5}, [{"key": "v", "op": "between", "value": 1, "value2": 10}])[0]
    assert not passes({"v": 50}, [{"key": "v", "op": "between", "value": 1, "value2": 10}])[0]
    assert passes({"v": 5}, [{"key": "v", "op": "gte", "value": 5}])[0]
    # 쓰다 만 조건(값이 비었음)은 무시한다 — 표가 통째로 사라지면 안 된다
    assert passes({"v": 5}, [{"key": "v", "op": "lte", "value": None}])[0]


def test_맞서는_목표에서는_지지_않는_점만_남긴다() -> None:
    """두께를 키우면 공진은 목표에 가까워지고 무거워진다 — 합치지 않고 고르게 한다."""
    from app.core.doe import pareto, parse_objectives

    rows: list[dict[str, Any]] = [
        {"n": 1, "mass_g": 100, "hz": 300},  # 가볍지만 목표에서 멀다
        {"n": 2, "mass_g": 150, "hz": 430},  # 둘 다 어중간 — 남는다
        {"n": 3, "mass_g": 200, "hz": 440},  # 무겁지만 딱 맞는다
        {"n": 4, "mass_g": 260, "hz": 300},  # 3 보다 무겁고 4 보다 멀다 — 진다
    ]
    objectives = parse_objectives(
        [{"key": "mass_g", "goal": "min"}, {"key": "hz", "goal": "target", "target": 440}]
    )
    got = {row["n"]: row for row in pareto(rows, objectives)}
    assert [n for n, row in got.items() if row["pareto"]] == [1, 2, 3]
    assert got[4]["pareto"] is False  # 아무 면에서도 낫지 않다
    # 점수는 훑기용 — 작을수록 앞이지만 순위를 정하는 값이 아니다.
    assert got[2]["score"] is not None and got[4]["score"] > got[2]["score"]


def test_값이_없는_점은_견주지_않는다() -> None:
    from app.core.doe import pareto, parse_objectives

    rows: list[dict[str, Any]] = [
        {"n": 1, "mass_g": 100},
        {"n": 2, "mass_g": None},  # 형상이 깨진 점
    ]
    got = pareto(rows, parse_objectives([{"key": "mass_g", "goal": "min"}]))
    assert got[0]["pareto"] is True and got[0]["comparable"] is True
    assert got[1]["pareto"] is False and got[1]["comparable"] is False


def test_틀린_목표는_이름을_짚어_말한다() -> None:
    from app.core.doe import parse_objectives

    with pytest.raises(DoeError, match="목표값이 있어야"):
        parse_objectives([{"key": "hz", "goal": "target"}])
    with pytest.raises(DoeError, match="min · max · target"):
        parse_objectives([{"key": "hz", "goal": "가볍게"}])
    with pytest.raises(DoeError, match="하나는 고르세요"):
        parse_objectives([])


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
