"""DOE 계획 — 제약식으로 거르기. 제약이 없으면 예전 표와 꼭 같아야 한다(시드로 다시 만든 표가
해석 결과와 이어지려면)."""

from __future__ import annotations

import pytest

from app.core.doe import DoeError, build_points, parse_constraints, parse_factors, plan
from app.core.recipe.params import ExpressionError, evaluate_condition, names_in

TWO = parse_factors(
    [
        {"name": "a", "mode": "range", "start": 0, "end": 10, "steps": 11},
        {"name": "b", "mode": "range", "start": 0, "end": 10, "steps": 11},
    ]
)


def test_제약식은_비교와_논리를_읽고_비교가_없으면_말한다() -> None:
    assert evaluate_condition("간격 > 2 * 지름", {"간격": 10, "지름": 4})
    assert not evaluate_condition("4 <= 두께 <= 12 and not 두께 == 5", {"두께": 5})
    assert evaluate_condition("a < 1 or hypot(a, b) >= 5", {"a": 3, "b": 4})
    with pytest.raises(ExpressionError, match="비교"):
        evaluate_condition("두께 * 2", {"두께": 1})
    assert names_in("hypot(a, b) > 2 * pi * c") == {"a", "b", "c"}


def test_제약이_없으면_예전_표와_같다() -> None:
    assert plan(TWO).rows == build_points(TWO, limit=200)
    lhs = plan(TWO, method="lhs", samples=30, seed=3)
    assert lhs.rows == build_points(TWO, method="lhs", samples=30, seed=3)
    assert lhs.rejected == 0 and lhs.shortfall == 0


def test_격자는_어긴_줄을_빼고_제약마다_몇_개_걸렸는지_센다() -> None:
    def check(row: dict[str, float | str]) -> list[int]:
        failed = []
        if not float(row["a"]) > float(row["b"]):
            failed.append(0)
        if float(row["a"]) > 8:
            failed.append(1)
        return failed

    got = plan(TWO, check=check, constraints=2)
    assert got.requested == 121 and got.candidates == 121
    assert all(float(r["a"]) > float(r["b"]) and float(r["a"]) <= 8 for r in got.rows)
    assert got.kept == len(got.rows) == 36
    assert got.rejected == 121 - 36 and got.hits == [66, 22]
    assert got.rejected_rows and len(got.rejected_rows) <= 300


def test_LHS_는_표본_수가_찰_때까지_더_뽑고_같은_시드면_같은_표다() -> None:
    def small(row: dict[str, float | str]) -> list[int]:
        return [] if float(row["a"]) + float(row["b"]) <= 5 else [0]

    got = plan(TWO, method="lhs", samples=30, seed=3, check=small, constraints=1)
    assert len(got.rows) == 30 and got.shortfall == 0 and got.candidates > 30
    assert all(float(r["a"]) + float(r["b"]) <= 5 for r in got.rows)
    again = plan(TWO, method="lhs", samples=30, seed=3, check=small, constraints=1)
    assert again.rows == got.rows

    # 끝내 못 채우면 숨기지 않고 말한다.
    never = plan(TWO, method="lhs", samples=10, seed=1, check=lambda _: [0], constraints=1)
    assert never.rows == [] and never.shortfall == 10


def test_제약식_목록을_다듬고_너무_많으면_말한다() -> None:
    assert parse_constraints([" a > b ", "", "  "]) == ["a > b"]
    with pytest.raises(DoeError, match="문자열"):
        parse_constraints([3])
    with pytest.raises(DoeError, match="20개"):
        parse_constraints([f"a > {i}" for i in range(21)])


THREE = parse_factors(
    [
        {"name": "a", "mode": "range", "start": 0, "end": 10, "steps": 3},
        {"name": "b", "mode": "list", "values": [1, 2, 4]},
        {"name": "c", "mode": "range", "start": 5, "end": 7, "steps": 2},
        {"name": "고정", "mode": "fixed", "value": 9},
    ]
)


def test_하나씩_바꾸기는_가운데에서_변수마다_제_값들을() -> None:
    rows = plan(THREE, method="oat").rows
    assert rows[0] == {"고정": 9.0, "a": 5.0, "b": 2.0, "c": 6.0}
    # a: 0 · 10, b: 1 · 4, c: 5 · 7 — 가운데는 한 번만.
    assert len(rows) == 1 + 2 + 2 + 2
    assert {"고정": 9.0, "a": 0.0, "b": 2.0, "c": 6.0} in rows


def test_중심_합성은_모서리_축_가운데이고_Box_Behnken_은_둘씩() -> None:
    ccd = plan(THREE, method="ccd").rows
    assert len(ccd) == 2**3 + 2 * 3 + 1
    assert {"고정": 9.0, "a": 0.0, "b": 1.0, "c": 5.0} in ccd  # 모서리
    assert {"고정": 9.0, "a": 10.0, "b": 2.0, "c": 6.0} in ccd  # 축
    bbd = plan(THREE, method="bbd").rows
    assert len(bbd) == 4 * 3 + 1
    assert {"고정": 9.0, "a": 0.0, "b": 1.0, "c": 5.0} not in bbd  # 모두 끝인 점은 없다
    unit = {"mode": "range", "start": 0, "end": 1, "steps": 2}
    two = parse_factors([{"name": "a", **unit}, {"name": "b", **unit}])
    with pytest.raises(DoeError, match="3개 이상"):
        plan(two, method="bbd")
    swap = {"name": "재료", "mode": "material", "values": ["A", "B"], "bodies": ["전체"]}
    material = parse_factors([{"name": "a", **unit}, swap])
    with pytest.raises(DoeError, match="수치 변수만"):
        plan(material, method="ccd")


def test_Sobol_은_참조_구현과_같고_이어_뽑으면_이어진다() -> None:
    from app.core.doe import sobol

    # scipy.stats.qmc.Sobol(3, scramble=False).random(4) 와 같다.
    assert sobol(3, 4) == [
        [0.0, 0.0, 0.0],
        [0.5, 0.5, 0.5],
        [0.75, 0.25, 0.25],
        [0.25, 0.75, 0.75],
    ]
    assert sobol(8, 8, seed=3)[5:] == sobol(8, 3, seed=3, start=5)
    first = plan(THREE, method="sobol", samples=8, seed=2)
    more = plan(THREE, method="sobol", samples=8, seed=2, offset=first.next_index)
    assert first.next_index == 8 and more.next_index == 16
    assert plan(THREE, method="sobol", samples=16, seed=2).rows == first.rows + more.rows
    # 제약에 걸리면 수열을 이어 더 뽑는다.
    small = plan(
        THREE,
        method="sobol",
        samples=8,
        seed=2,
        check=lambda r: [] if float(r["a"]) < 5 else [0],
        constraints=1,
    )
    assert len(small.rows) == 8 and small.next_index > 8
    assert all(float(r["a"]) < 5 for r in small.rows)
