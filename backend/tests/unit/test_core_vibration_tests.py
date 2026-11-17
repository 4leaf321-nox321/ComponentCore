"""진동 시험 규격의 가진 프로파일 — 정현파의 변위 일정 구간과 랜덤 진동의 PSD(2026-11-17).

IEC 60068-2-6 의 심각도는 「변위 0.075 mm · 가속도 10 m/s², 교차 주파수 57~62 Hz」 처럼 진폭이
둘이다. 그동안은 가속도만 범위 전체에 일정하게 실어 교차 주파수 아래를 세게 흔들었다(10 Hz 에서
33 배). 이제 그 구간을 조건의 주파수별 배율 표로 싣는지, 직선으로 이은 표가 f² 곡선을 얼마나
따르는지, 그리고 랜덤 진동 규격(PSD 표)이 그대로 조건이 되는지 본다.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import pytest
from pydantic import ValidationError

from app.core import conditions, specimens
from app.core.recipe.params import resolve_params
from app.core.specimens import product
from app.core.specimens.presets import RandomPreset, VibrationPreset, VibrationSetup
from tests.unit.test_core_product_tests import PLATE, _bbox, _check

G_MM = 9806.65


def _at(table: list[list[float]], frequency: float) -> float:
    """조건의 배율 표를 받는 쪽처럼 읽는다 — 행 사이는 직선."""
    for (f1, v1), (f2, v2) in itertools.pairwise(table):
        if f1 <= frequency <= f2:
            return v1 + (v2 - v1) * (frequency - f1) / (f2 - f1)
    raise AssertionError(f"{frequency} Hz 가 표 밖이다")


def _sine(preset_id: str = "iec-60068-2-6-150-1g") -> VibrationPreset:
    preset = specimens.find_builtin(preset_id)
    assert isinstance(preset, VibrationPreset)
    return preset


def _with(preset: VibrationPreset, **setup: Any) -> VibrationPreset:
    changed = VibrationSetup(**{**preset.setup.model_dump(), **setup})
    return preset.model_copy(update={"setup": changed})


def test_교차_주파수_아래는_변위가_일정하다() -> None:
    setup = _sine().setup
    # 0.075 mm · 1 g → √(9806.65 / 0.075) / 2π.
    assert setup.crossover == pytest.approx(57.55, abs=0.01)
    table = product.sweep_table(setup)
    assert table is not None
    assert table[0][0] == 10 and table[-1] == [150, 1.0], "시험 범위를 끝까지 덮는다"
    acceleration = setup.acceleration_g * G_MM
    for frequency in (10, 12.5, 20, 33.3, 45, 57):
        exact = (2 * math.pi * frequency) ** 2 * 0.075 / acceleration
        assert _at(table, frequency) == pytest.approx(exact, rel=0.001), frequency
    for frequency in (58, 100, 150):
        assert _at(table, frequency) == pytest.approx(1.0)
    # 1/12 옥타브 이하 간격, 교차 주파수도 표의 점(받는 쪽이 꺾이는 자리를 직선으로 깎지 않게).
    below = [row[0] for row in table[:-1]]
    assert max(b / a for a, b in itertools.pairwise(below)) <= 2 ** (1 / 12) + 1e-4
    assert below[-1] == pytest.approx(setup.crossover, abs=1e-3)
    assert table[-2][1] == 1.0


def test_시험에_걸면_10_Hz_에서_변위_진폭만큼_흔든다() -> None:
    made = product.apply(_sine(), PLATE, None, bbox=_bbox(PLATE))
    _check(made)  # 조건 검사 — 표가 해석의 주파수 범위를 다 덮는다
    resolved = conditions.resolve(made.conditions, resolve_params(made.recipe))
    (load,) = resolved["loads"]
    # 10 Hz 의 가속도 = (2π · 10)² · 0.075 mm = 296 mm/s² — 일정 가속도(9807)의 1/33.
    amplitude = load["magnitude"] * _at(load["frequency_table"], 10)
    assert amplitude == pytest.approx((2 * math.pi * 10) ** 2 * 0.075, rel=1e-3)
    assert load["phase"] == 0.0
    assert any("교차 주파수 57.6 Hz" in one for one in made.notes)
    assert any("같은 비로" in one for one in made.notes), "가속도 변수를 훑을 때의 뜻을 말한다"


def test_범위가_교차_주파수_한쪽에만_있으면() -> None:
    preset = _sine()
    # 전부 아래 — 변위만 일정하고, 끝 행도 1 보다 작다.
    low = _with(preset, freq_min=5, freq_max=40)
    table = product.sweep_table(low.setup)
    assert table is not None and table[-1][0] == 40
    assert table[-1][1] == pytest.approx((40 / 57.55) ** 2, rel=1e-3)
    made = product.apply(low, PLATE, None, bbox=_bbox(PLATE))
    _check(made)
    assert any("범위 전체가 교차" in one for one in made.notes)
    # 전부 위 — 배율 표가 필요 없다.
    high = _with(preset, freq_min=100, freq_max=500)
    assert product.sweep_table(high.setup) is None
    made = product.apply(high, PLATE, None, bbox=_bbox(PLATE))
    assert "frequency_table" not in made.conditions["loads"][0]
    assert any("변위 일정 구간이 없습니다" in one for one in made.notes)


def test_변위가_없는_규격은_예전처럼_가속도만_일정하다() -> None:
    """변위 칸이 생기기 전에 복사한 사내 규격은 그대로 돈다."""
    plain = _with(_sine(), displacement_mm=None)
    assert plain.setup.crossover is None
    made = product.apply(plain, PLATE, None, bbox=_bbox(PLATE))
    _check(made)
    assert "frequency_table" not in made.conditions["loads"][0]
    assert not any("같은 비로" in one for one in made.notes)


def test_변위를_주면_0_Hz_에서_시작할_수_없다() -> None:
    with pytest.raises(ValidationError, match="0보다 커야"):
        VibrationSetup(freq_min=0, freq_max=150, acceleration_g=1, displacement_mm=0.075)


def test_랜덤_진동_규격은_PSD_표를_그대로_건다() -> None:
    preset = specimens.find_builtin("iec-60068-2-64-example-6g")
    assert isinstance(preset, RandomPreset)
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), axis="y")
    _check(made)
    (load,) = made.conditions["loads"]
    assert load == {
        "name": "랜덤 가진 (Y축)",
        "type": "psd_acceleration",
        "direction": [0, 1, 0],
        "psd_table": [[20, 0.01], [80, 0.04], [350, 0.04], [2000, 0.007]],
    }
    assert [one["type"] for one in made.conditions["constraints"]] == ["fixed_support"]
    assert any("Grms 6.06 g" in one for one in made.notes)
    assert any("3000 Hz" in one for one in made.notes), "모드가 덮어야 할 주파수를 말한다"
    resolved = conditions.resolve(made.conditions, resolve_params(made.recipe))
    assert resolved["loads"][0]["grms"] == pytest.approx(6.058, abs=1e-3)
    with pytest.raises(product.ProductTestError, match="진동 방향"):
        product.apply(preset, PLATE, None, bbox=_bbox(PLATE), axis="w")


def _random(**setup: Any) -> dict[str, Any]:
    return {
        "id": "in-house-random",
        "test": "random",
        "standard": "사내",
        "name": "사내 랜덤",
        "setup": {"psd": [[20, 0.04], [2000, 0.04]], **setup},
    }


@pytest.mark.parametrize(
    ("psd", "message"),
    [
        ([[20, 0.04]], "at least 2"),
        ([[20, 0.04], [20, 0.02]], "위 행"),
        ([[0, 0.04], [2000, 0.04]], "0보다 커야"),
        ([[20, 0.0], [2000, 0.04]], "값은 0보다"),
    ],
)
def test_PSD_표가_틀리면_몇_행이_왜인지_말한다(psd: list[list[float]], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        specimens.parse_preset(_random(psd=psd))


def test_적힌_Grms_와_표가_다르면_옮겨_적다_틀린_것이다() -> None:
    # 평평한 0.04 g²/Hz, 20 ~ 2000 Hz → √79.2 = 8.90 g.
    assert specimens.parse_preset(_random(grms=8.9))
    with pytest.raises(ValidationError, match=r"8\.9 g가 적힌 Grms 7\.7 g"):
        specimens.parse_preset(_random(grms=7.7))
