"""보 공진 가늠값 — 교과서 값과 맞는지, 그리고 **가늠값이라고 말하는지**."""

from __future__ import annotations

import pytest

from app.core.vibration import VibrationError, beam_frequency, thickness_for_frequency


def test_외팔보_1차는_교과서_값과_맞는다() -> None:
    """알루미늄 외팔보 길이 100 · 폭 20 · 두께 5. 교과서 식으로 411 Hz."""
    got = beam_frequency(length_mm=100, width_mm=20, thickness_mm=5)
    assert got["hz"] == pytest.approx(411, rel=0.01)
    # 양단 고정은 (4.730/1.875)² ≈ 6.36 배.
    fixed = beam_frequency(length_mm=100, width_mm=20, thickness_mm=5, support="fixed")
    assert fixed["hz"] / got["hz"] == pytest.approx(6.36, rel=0.02)
    # 폭은 1차 주파수를 바꾸지 않는다(강성 · 질량이 같은 비로 는다).
    wide = beam_frequency(length_mm=100, width_mm=40, thickness_mm=5)
    assert wide["hz"] == pytest.approx(got["hz"], rel=1e-6)


def test_끝에_질량이_붙으면_내려간다() -> None:
    bare = beam_frequency(length_mm=100, width_mm=20, thickness_mm=5)["hz"]
    loaded = beam_frequency(length_mm=100, width_mm=20, thickness_mm=5, added_mass_g=50)["hz"]
    assert loaded < bare / 2  # 보 자신(27g)보다 무거운 것이 붙었다


def test_목표_주파수를_두께로_되짚는다() -> None:
    got = thickness_for_frequency(target_hz=420, length_mm=90, width_mm=40, added_mass_g=120)
    assert got["hz"] == pytest.approx(420, rel=0.01)
    back = beam_frequency(
        length_mm=90, width_mm=40, thickness_mm=got["thickness_mm"], added_mass_g=120
    )
    assert back["hz"] == pytest.approx(420, rel=0.01)


def test_범위_밖이면_무엇을_바꿔야_하는지_말한다() -> None:
    with pytest.raises(VibrationError, match="길게 하거나"):
        thickness_for_frequency(target_hz=5, length_mm=20, width_mm=20)
    with pytest.raises(VibrationError, match="짧게 하거나"):
        thickness_for_frequency(target_hz=500_000, length_mm=200, width_mm=20)
    with pytest.raises(VibrationError, match="모르는 재료"):
        beam_frequency(length_mm=100, width_mm=20, thickness_mm=5, material="나무")


def test_가정_밖이면_경고를_붙인다() -> None:
    """짧고 두꺼운 보에서 이 식은 높게 나온다 — 말없이 숫자만 주면 안 된다."""
    stubby = beam_frequency(length_mm=20, width_mm=20, thickness_mm=10)
    assert stubby["warnings"] and "전단" in stubby["warnings"][0]
    assert "가늠값" in stubby["accuracy"]
