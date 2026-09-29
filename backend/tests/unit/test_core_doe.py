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
    assert all(4.0 <= float(row["두께"]) <= 12.0 for row in first)


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


def test_재료_인자는_후보_재료를_설계점마다_하나씩_고르고_형상_값에서는_빠진다() -> None:
    from app.core.doe import material_factors, shape_values

    raw: list[dict[str, Any]] = [
        {"name": "두께", "mode": "list", "values": [5, 8]},
        {
            "name": "블록 재료",
            "mode": "material",
            "bodies": ["블록"],
            "values": ["SECC", "AL5052"],
        },
    ]
    rows = build_points(parse_factors(raw))
    assert rows == [
        {"두께": 5.0, "블록 재료": "SECC"},
        {"두께": 5.0, "블록 재료": "AL5052"},
        {"두께": 8.0, "블록 재료": "SECC"},
        {"두께": 8.0, "블록 재료": "AL5052"},
    ]
    # LHS 도 칸을 고른다.
    lhs = build_points(parse_factors(raw), method="lhs", samples=6, seed=3)
    assert {row["블록 재료"] for row in lhs} <= {"SECC", "AL5052"}
    assert material_factors(raw) == {"블록 재료": ["블록"]}
    assert shape_values(rows[1], raw) == {"두께": 5.0}


def test_재료_인자가_틀리면_이름을_짚어_말한다() -> None:
    cases = [
        ({"name": "재료", "mode": "material", "bodies": ["블록"], "values": []}, "후보 재료"),
        ({"name": "재료", "mode": "material", "values": ["A"]}, "바디"),
        ({"name": "재료", "mode": "material", "bodies": ["b"], "values": ["A", "A"]}, "두 번"),
    ]
    for one, message in cases:
        with pytest.raises(DoeError, match=message):
            parse_factors([one])


def test_고르기_배율_인자는_후보를_고르고_형상_값에서_빠진다() -> None:
    from app.core.doe import shape_values

    raw: list[dict[str, Any]] = [
        {"name": "두께", "mode": "list", "values": [5]},
        {
            "name": "접촉",
            "mode": "choice",
            "target": {"group": "contacts", "item": "블록-판", "field": "type"},
            "values": ["bonded", "frictional"],
        },
        {
            "name": "E",
            "mode": "scale",
            "bodies": ["블록"],
            "property": "탄성계수",
            "values": [0.9, 1.1],
        },
    ]
    rows = build_points(parse_factors(raw))
    assert [(row["접촉"], row["E"]) for row in rows] == [
        ("bonded", 0.9),
        ("bonded", 1.1),
        ("frictional", 0.9),
        ("frictional", 1.1),
    ]
    assert shape_values(rows[0], raw) == {"두께": 5.0}
    # 고르기 값은 글자 · 수 · 참거짓 · null — 자유(null) ↔ 고정(0) 도 훑는다.
    free: dict[str, Any] = {
        "name": "X",
        "mode": "choice",
        "target": {"group": "constraints", "item": 1, "field": "x"},
    }
    assert levels(parse_factors([{**free, "values": [None, 0]}])[0]) == [None, 0]


def test_고르기_배율_인자가_틀리면_말한다() -> None:
    target = {"group": "contacts", "item": "a", "field": "type"}
    cases: list[tuple[dict[str, Any], str]] = [
        ({"mode": "choice", "target": {**target, "group": "parts"}, "values": ["x"]}, "묶음"),
        ({"mode": "choice", "target": {**target, "item": None}, "values": ["x"]}, "항목"),
        ({"mode": "choice", "target": target, "values": []}, "후보"),
        ({"mode": "choice", "target": target, "values": ["a", "a"]}, "두 번"),
        ({"mode": "scale", "bodies": ["b"], "values": [1]}, "물성"),
        ({"mode": "scale", "property": "E", "bodies": ["b"], "values": [0]}, "0 보다"),
    ]
    for one, message in cases:
        with pytest.raises(DoeError, match=message):
            parse_factors([{"name": "인자", **one}])
