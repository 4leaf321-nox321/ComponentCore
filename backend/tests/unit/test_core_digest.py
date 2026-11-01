"""치수표 — AI 가 형상을 「읽는」 길. 사람의 측정 창에 해당한다."""

from __future__ import annotations

import pytest

from app.core.recipe import evaluate, parse
from app.core.recipe.digest import digest

PLATE = {
    "params": {"L": 80},
    "nodes": [
        {
            "id": "b",
            "op": "box",
            "length": "=L",
            "width": 50,
            "height": 10,
            "align": ["min", "center", "min"],
        },
        {"id": "h", "op": "hole", "target": "b", "at": [[15, 0], [65, 0]], "diameter": 6},
        {
            "id": "p",
            "op": "cylinder",
            "radius": 4,
            "height": 20,
            "at": [40, 0, 10],
            "align": ["center", "center", "min"],
        },
        {"id": "u", "op": "union", "targets": ["h", "p"]},
    ],
}


def test_구멍을_지름과_자리와_깊이로_말한다() -> None:
    got = digest(evaluate(parse(PLATE)).shape)
    assert got["bbox"]["size"] == [80.0, 50.0, 30.0]
    holes = {(h["diameter"], tuple(h["at"][:2])): h for h in got["holes"]}
    # ⌀6 구멍 둘 — 판 두께만큼 뚫렸다. 나란한 두 구멍이 한 구멍으로 묶이면 안 된다.
    assert (6.0, (15.0, 0.0)) in holes and (6.0, (65.0, 0.0)) in holes
    assert holes[(6.0, (15.0, 0.0))]["depth"] == 10.0
    assert holes[(6.0, (15.0, 0.0))]["axis"] == [0.0, 0.0, 1.0]
    # 핀은 ⌀8 · 높이 20 으로 잡힌다(원 둘이 같은 축에 있다).
    assert (8.0, (40.0, 0.0)) in holes
    assert holes[(8.0, (40.0, 0.0))]["depth"] == 20.0


def test_면을_법선과_넓이로_말한다() -> None:
    got = digest(evaluate(parse(PLATE)).shape)
    planes = got["faces"]["planes"]
    assert planes[0]["area"] >= planes[-1]["area"]  # 큰 것부터
    bottom = next(one for one in planes if one["normal"] == [0.0, 0.0, -1.0])
    assert bottom["center"][2] == 0.0  # align min 이라 바닥이 z=0
    assert got["faces"]["curved"][0]["radius"] == 4.0  # 핀 옆면
    assert "*_total" in got["note"] or "전체는" in got["note"]


def test_질량과_관성은_무게중심_기준으로_낸다() -> None:
    """진동 · 무게 중심 잡기에 쓰는 값. 원점 기준이면 형상을 옮기기만 해도 값이 변한다."""
    from app.core.recipe.digest import mass_properties

    at_origin = evaluate(
        parse({"nodes": [{"id": "b", "op": "box", "length": 80, "width": 50, "height": 10}]})
    )
    moved = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "b",
                        "op": "box",
                        "length": 80,
                        "width": 50,
                        "height": 10,
                        "at": [500, 0, 0],
                    }
                ]
            }
        )
    )
    here = mass_properties(at_origin.shape, "aluminum")
    there = mass_properties(moved.shape, "aluminum")
    assert here["mass_g"] == pytest.approx(80 * 50 * 10 * 2.70 / 1000)  # 108 g
    assert here["inertia_g_mm2_about_com"] == there["inertia_g_mm2_about_com"]
    assert there["center_of_mass"][0] == 500.0


def test_해석에_싣는_질량은_조건의_밀도와_단위계로_낸다() -> None:
    """`mass_properties` 는 재료 이름 · g 다(AI 의 치수표). 해석에 실을 값은 조건의 물성 밀도
    (그 계의 값)로, 그 계의 단위로 낸다 — t 단위 질량을 소수 셋째 자리로 자르면 0 이 된다."""
    from app.core.recipe.digest import body_mass

    box = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "b",
                        "op": "box",
                        "length": 10,
                        "width": 20,
                        "height": 30,
                        "at": [100, 0, 0],
                        "align": ["min", "min", "min"],
                    }
                ]
            }
        )
    ).shape
    m = 10 * 20 * 30 * 7.85e-9  # t
    got = body_mass(box, 7.85e-9, "mm_n_tonne")
    assert got["mass"] == pytest.approx(m)
    assert got["center_of_mass"] == pytest.approx([105.0, 10.0, 15.0])
    ixx, iyy, izz = (
        m * (20**2 + 30**2) / 12,
        m * (10**2 + 30**2) / 12,
        m * (10**2 + 20**2) / 12,
    )
    assert got["inertia"][:3] == pytest.approx([ixx, iyy, izz])
    assert got["inertia"][3:] == pytest.approx([0, 0, 0], abs=1e-15)
    assert got["units"] == {"mass": "tonne", "length": "mm", "inertia": "tonne*mm^2"}

    # 같은 몸을 SI 로 — 밀도는 kg/m³, 길이는 m. t·mm² → kg·m² 는 1e3 · 1e-6 = 1e-3 배다.
    si = body_mass(box, 7850.0, "si")
    assert si["mass"] == pytest.approx(m * 1e3)
    assert si["center_of_mass"] == pytest.approx([0.105, 0.010, 0.015])
    assert si["inertia"][:3] == pytest.approx([v * 1e-3 for v in got["inertia"][:3]])
    assert si["units"]["inertia"] == "kg*m^2"


def test_곱관성은_관성_텐서의_부호다() -> None:
    """L 자(60 x 10 가로 + 10 x 50 세로, 두께 10)를 손으로 셈하면 ∫(x-x̄)(y-ȳ) dm 이 음수다
    (질량이 무게중심의 2 · 4 사분면에 있다). 관성 텐서의 Ixy 는 그 반대 부호 — 양수다."""
    from app.core.recipe.digest import body_mass

    shape = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "가로",
                        "op": "box",
                        "length": 60,
                        "width": 10,
                        "height": 10,
                        "align": ["min", "min", "min"],
                    },
                    {
                        "id": "세로",
                        "op": "box",
                        "length": 10,
                        "width": 50,
                        "height": 10,
                        "at": [0, 10, 0],
                        "align": ["min", "min", "min"],
                    },
                    {"id": "엘", "op": "union", "targets": ["가로", "세로"]},
                ]
            }
        )
    ).shape
    got = body_mass(shape, 7.85e-9, "mm_n_tonne")
    # 손셈: ∫(x-x̄)(y-ȳ) dm = -16056.818 g·mm² = -0.016056818 t·mm²
    assert got["inertia"][3] == pytest.approx(0.016056818, rel=1e-6)
    assert got["inertia"][4:] == pytest.approx([0, 0], abs=1e-12)
