"""단위 환산 — **여기가 틀리면 해석이 그럴듯하게 틀린다.**

손으로 확인한 값으로 못 박는다. 밀도만 맞고 탄성계수가 10⁶ 배 틀린 결과는 사람이 눈으로
잡기 어렵다 — 그래서 시험이 잡아야 한다.
"""

from __future__ import annotations

import pytest

from app.core import units


def test_ANSYS_mm_tonne_s_의_교과서_값과_맞는다() -> None:
    """FE 에서 mm 로 풀 때 쓰는 값들. ANSYS 단위계 표에 나오는 그대로다."""
    # 강: 7850 kg/m³ → 7.85e-9 tonne/mm³
    made, name, ok = units.convert(7850.0, "kg/m3", "mm_n_tonne")
    assert ok and name == "tonne/mm3"
    assert made == pytest.approx(7.85e-9)

    # 탄성계수 206 GPa → 206000 MPa. **여기가 10⁶ 배 틀리던 자리다.**
    made, name, ok = units.convert(2.06e11, "Pa", "mm_n_tonne")
    assert ok and name == "MPa"
    assert made == pytest.approx(206000.0)

    # 비열 880 J/(kg·K) → 8.8e8 mJ/(tonne·K). 길이가 제곱으로 들어가 10⁶ 배가 된다 —
    # 「응력이니까 10⁶」 같은 눈대중이 아니라 **차원으로** 풀어야 나오는 값이다.
    made, name, ok = units.convert(880.0, "J/(kg.K)", "mm_n_tonne")
    assert ok and name == "mJ/(tonne.K)"
    assert made == pytest.approx(8.8e8)

    # 열전도율 237 W/(m·K) → mm·t·s 에서도 **숫자가 같다**(mW/(mm·K)).
    made, name, ok = units.convert(237.0, "W/(m.K)", "mm_n_tonne")
    assert ok and name == "mW/(mm.K)"
    assert made == pytest.approx(237.0)

    # 선팽창계수는 온도만 걸려 있어 그대로.
    made, _, ok = units.convert(2.38e-5, "1/K", "mm_n_tonne")
    assert ok and made == pytest.approx(2.38e-5)


def test_SI_로_가면_MatNexus_의_밀도가_제자리를_찾는다() -> None:
    """MatNexus 는 밀도만 `tonne/mm3` 로 준다 — SI 를 고르면 그것도 맞춰 준다."""
    made, name, ok = units.convert(7.93e-9, "tonne/mm3", "si")
    assert ok and name == "kg/m3"
    assert made == pytest.approx(7930.0)
    # 나머지 `value_si` 는 SI 에서 그대로다.
    assert units.convert(2.06e11, "Pa", "si")[0] == pytest.approx(2.06e11)


def test_모르는_단위는_건드리지_않고_그_사실을_말한다() -> None:
    """짐작해서 바꾸면 **틀린 값이 맞는 얼굴로** 나간다. 그대로 두고 거짓을 준다."""
    made, name, ok = units.convert(12.0, "furlong/fortnight", "mm_n_tonne")
    assert made == 12.0 and name == "furlong/fortnight" and ok is False


def test_돌아오면_제자리다() -> None:
    """어느 계로 갔다 와도 같은 값 — 배수를 손으로 적다 틀리는 것을 잡는다."""
    for value, unit in ((7850.0, "kg/m3"), (2.06e11, "Pa"), (880.0, "J/(kg.K)")):
        there, name, ok = units.convert(value, unit, "mm_n_tonne")
        assert ok
        back, _, ok = units.convert(there, name, "si")
        assert ok
        # SI 이름으로 되돌린 값이 원래 SI 값과 같다.
        assert back == pytest.approx(value, rel=1e-12)


def test_선언은_닫히는_계만_말한다() -> None:
    """`mm · kg · s · N` 은 **닫히지 않는다**(그 계의 힘은 mN, 응력은 kPa 다). 기본 셋만
    적고 나머지를 계산하므로 그런 조합을 아예 적을 수 없다."""
    said = units.declaration("mm_n_tonne")
    assert said["system"] == "mm_n_tonne"
    assert (said["length"], said["mass"], said["force"], said["stress"]) == (
        "mm",
        "tonne",
        "N",
        "MPa",
    )
    assert units.declaration("si")["stress"] == "Pa"
    # 모르는 계를 달라고 하면 기본으로 — 빈 선언을 주면 받는 쪽이 제멋대로 가정한다.
    assert units.declaration("없는계")["system"] == units.DEFAULT_SYSTEM


def test_mm_kg_s_는_힘이_mN_이다() -> None:
    """MatNexus 가 내 계산을 바로잡아 줬다(2026-09-24): `mm·kg·s` 의 힘은 μN 이 아니라
    **mN**(kg·mm/s² = 10⁻³ N)이고 응력은 kPa 다.

    요점은 그대로다 — `mm · kg · s · N` 은 **앞뒤가 안 맞는 조합**이고, 낱낱이 적게 두면
    그런 것을 적을 수 있다. 그래서 고를 수 있는 것은 계 이름뿐이다."""
    assert set(units.SYSTEMS) == {"mm_n_tonne", "si"}
    # 우리가 내주는 계는 둘 다 힘이 N 이다 — 닫혀 있다는 뜻이다.
    for key in units.SYSTEMS:
        assert units.declaration(key)["force"] == "N"


def test_카드에_나오는_단위도_안다() -> None:
    """**재료 API 에는 여섯 종만 나오지만 물성 카드에는 열한 종이 나온다**(MatNexus 가
    알려 줬다). 여섯으로 굳혀 두면 점탄성이나 속도별 카드를 받는 날 조용히 지나간다."""
    for one in ("K", "s", "1/s", "Hz", "Pa.s"):
        assert one in units.KNOWN, one
    # 점도는 계에 따라 이름이 바뀐다 — Pa·s → N·s/mm²(그쪽 기호표와 같다).
    made, name, ok = units.convert(1000.0, "Pa.s", "mm_n_tonne")
    assert ok and name == "N.s/mm2" and made == pytest.approx(1e-3)


def test_계가_다시_이름_짓지_않는_것은_들어온_기호를_둔다() -> None:
    """`Hz` 를 `1/s` 로 바꿔 내보내고 있었다 — 값은 같아도 **그쪽이 쓴 말을 우리가 바꾼
    것**이라, 되돌아온 파일이 원본과 안 맞는다. 드리프트 검사가 잡았다."""
    assert units.convert(50.0, "Hz", "mm_n_tonne")[1] == "Hz"
    assert units.convert(50.0, "1/s", "mm_n_tonne")[1] == "1/s"
    # 계가 실제로 다시 이름 짓는 것은 바뀐다.
    assert units.convert(1.0, "Pa", "mm_n_tonne")[1] == "MPa"
    assert units.convert(1.0, "W/(m.K)", "mm_n_tonne")[1] == "mW/(mm.K)"
