"""가진 프로파일 — 조화 응답의 주파수별 배율 · 위상, 랜덤 진동의 가속도 PSD(2026-11-17).

진동 시험 규격은 사인 스윕(주파수마다 진폭)과 랜덤(주파수마다 g²/Hz)으로 적힌다. 조건이 그것을
그대로 받아 **풀린 값 그대로** 내보내는지, 그리고 받는 쪽이 짐작해야 하는 빈틈(표 밖의 주파수 ·
감쇠 없음 · 가진할 지지가 없음)을 저장할 때 막는지 본다.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import pytest

from app.core import conditions
from app.core.conditions import ConditionError, parse, psd_grms, resolve, spec

BASE: dict[str, Any] = {
    "named_selections": [
        {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}},
        {"name": "윗면", "entity": "face", "select": {"what": "faces", "role": "top"}},
    ],
    "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
}

#: 사인 스윕 — 기저를 1 g(9806.65 mm/s²)로, 200 Hz 에서는 그 절반으로 흔든다.
SINE: dict[str, Any] = {
    **BASE,
    "loads": [
        {
            "name": "스윕",
            "type": "acceleration",
            "magnitude": 9806.65,
            "direction": [1, 0, 0],
            "frequency_table": [[100, 0.5], [800, 1], [2000, 1]],
        }
    ],
    "analysis": {
        "type": "harmonic",
        "frequency_range": [200, 2000],
        "modes": 6,
        "damping_ratio": 0.02,
    },
}

#: 랜덤 — IEC 60068-2-64 꼴(오르막 · 평평 · 내리막).
PROFILE = [[20, 0.01], [80, 0.04], [350, 0.04], [2000, 0.007]]
RANDOM: dict[str, Any] = {
    **BASE,
    "loads": [
        {
            "name": "X 랜덤",
            "type": "psd_acceleration",
            "direction": [1, 0, 0],
            "psd_table": PROFILE,
        }
    ],
    "analysis": {"type": "random", "modes": 10, "damping_ratio": 0.02},
}


def test_사인_스윕은_배율_표와_위상을_그대로_싣고_비운_위상은_0_이다() -> None:
    made = resolve(SINE, {})
    (load,) = made["loads"]
    assert load["frequency_table"] == [[100, 0.5], [800, 1], [2000, 1]]
    assert load["phase"] == 0.0, "조화 응답에서 비운 위상은 받는 쪽이 짐작하지 않게 0 으로"
    # SI 로 내보내도 배율 · 주파수 · 위상은 그대로 — 크기만 계를 따른다.
    si = resolve(
        {**SINE, "units": {"system": "si"}, "loads": [{**SINE["loads"][0], "phase": 30}]}, {}
    )
    (load,) = si["loads"]
    assert load["magnitude"] == pytest.approx(9.80665)
    assert load["frequency_table"] == [[100, 0.5], [800, 1], [2000, 1]]
    assert load["phase"] == 30
    # 조화 응답이 아니면 위상을 채우지 않는다(쓰이지 않는 칸에 값을 만들지 않는다).
    static = resolve({**SINE, "analysis": {"type": "static"}}, {})
    assert static["loads"][0]["phase"] is None


def test_배율_표의_식은_설계점마다_풀린다() -> None:
    raw = {
        **SINE,
        "loads": [{**SINE["loads"][0], "frequency_table": [[100, "=배율"], [2000, 1]]}],
    }
    parse(raw)
    assert resolve(raw, {"배율": 0.25})["loads"][0]["frequency_table"] == [
        [100, 0.25],
        [2000, 1],
    ]


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ([[200, 1]], "두 행 이상"),
        ([[200, 1], [200, 2]], "위 행보다 커야"),
        ([[300, 1], [200, 2]], "위 행보다 커야"),
        ([[-1, 1], [2000, 1]], "0 이상이어야"),
        ([[100, 1], [2000, -1]], "값은 0 이상이어야"),
        ([[100, 1, 3], [2000, 1]], "두 칸이어야"),
        ([[100, ""], [2000, 1]], "빈칸이 있습니다"),
    ],
)
def test_배율_표가_틀리면_몇_행이_왜인지_말한다(table: list[list[Any]], message: str) -> None:
    raw = {**SINE, "loads": [{**SINE["loads"][0], "frequency_table": table}]}
    with pytest.raises(ConditionError, match=message):
        parse(raw)


def test_배율_표는_해석의_주파수_범위를_다_덮어야_한다() -> None:
    """표 밖을 0 으로 읽을지 끝값으로 읽을지 솔버마다 다르다 — 짐작하게 두지 않는다."""
    short = {**SINE, "loads": [{**SINE["loads"][0], "frequency_table": [[300, 1], [2000, 1]]}]}
    with pytest.raises(ConditionError, match=r"300~2000 Hz.*200~2000 Hz"):
        parse(short)


def test_랜덤_진동은_PSD_를_g2_Hz_로_싣고_실효값을_함께_준다() -> None:
    for system in ("mm_n_tonne", "si"):
        made = resolve({**RANDOM, "units": {"system": system}}, {})
        (load,) = made["loads"]
        assert load["unit"] == "g^2/Hz", "어느 계로 내보내든 g²/Hz"
        assert load["psd_table"] == PROFILE
        assert load["grms"] == pytest.approx(_numeric_grms(PROFILE), rel=1e-4)
        assert made["analysis"]["type"] == "random"
        assert made["analysis"]["damping_ratio"] == 0.02
        assert "solution_intervals" not in made["analysis"], "조화 응답의 칸은 싣지 않는다"


def test_실효값은_로그_로그_면적이다() -> None:
    # 평평한 0.04 g²/Hz, 20 ~ 2000 Hz → √(0.04 * 1980).
    assert psd_grms([[20, 0.04], [2000, 0.04]]) == pytest.approx(math.sqrt(0.04 * 1980))
    # 기울기 -1(-3 dB/oct) — 면적이 P·f·ln(f2/f1).
    assert psd_grms([[100, 0.1], [1000, 0.01]]) == pytest.approx(
        math.sqrt(0.1 * 100 * math.log(10))
    )
    assert psd_grms(PROFILE) == pytest.approx(_numeric_grms(PROFILE), rel=1e-4)
    assert psd_grms([[20, "=a"], [2000, 0.04]]) is None, "식이 남아 있으면 모른다"


def test_랜덤_진동에_빠진_것을_저장할_때_말한다() -> None:
    no_psd = {**RANDOM, "loads": []}
    with pytest.raises(ConditionError, match="가속도 PSD"):
        parse(no_psd)
    no_support = {**RANDOM, "constraints": []}
    with pytest.raises(ConditionError, match="고정 지지’이\\(가\\) 하나 이상"):
        parse(no_support)
    no_damping = {**RANDOM, "analysis": {"type": "random", "modes": 10}}
    with pytest.raises(ConditionError, match="감쇠비가 필요"):
        parse(no_damping)
    no_modes = {**RANDOM, "analysis": {"type": "random", "modes": 0, "damping_ratio": 0.02}}
    with pytest.raises(ConditionError, match="모드 수"):
        parse(no_modes)
    # PSD 는 로그라 0 을 못 쓴다.
    zero = {**RANDOM, "loads": [{**RANDOM["loads"][0], "psd_table": [[20, 0], [2000, 0.04]]}]}
    with pytest.raises(ConditionError, match="0보다 커야"):
        parse(zero)
    empty = {**RANDOM, "loads": [{**RANDOM["loads"][0], "psd_table": None}]}
    with pytest.raises(ConditionError, match="PSD 표가 없습니다"):
        parse(empty)


def test_가속도_PSD_는_랜덤_진동에서만_쓴다() -> None:
    elsewhere = {**RANDOM, "analysis": {"type": "modal", "modes": 6}}
    with pytest.raises(ConditionError, match=r"loads\[0\]: .*랜덤 진동\(PSD\) 해석에서만"):
        parse(elsewhere)


def test_사양표가_표_칸과_해석_종류에_따른_칸을_알린다() -> None:
    table = spec()
    loads = table["groups"]["loads"]
    fields = loads["fields"]
    assert fields["frequency_table"]["analysis_only"] == ["harmonic"]
    assert [one["title"] for one in fields["frequency_table"]["table"]["columns"]] == [
        "주파수",
        "배율",
    ]
    assert fields["psd_table"]["table"]["grms"] is True
    assert fields["psd_table"]["only_for"] == ["psd_acceleration"]
    # 기저 가진은 선택 그룹이 아니라 고정 지지 전부를 흔든다 — 크기 칸도 없다(표가 크기다).
    assert "psd_acceleration" not in fields["on"]["only_for"]
    assert "psd_acceleration" not in fields["magnitude"]["only_for"]
    assert "psd_acceleration" in loads["notes"]
    analysis = table["analysis"]
    assert analysis["properties"]["type"]["labels"]["random"] == "랜덤 진동(PSD)"
    assert "random" in analysis["notes"]
    assert "random" in analysis["properties"]["damping_ratio"]["only_for"]


def test_랜덤_진동에서도_접촉이_어떻게_풀리는지_알린다() -> None:
    from app.core import contact_check

    raw = {
        "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
        "contacts": [{"name": "이음", "type": "frictional", "source": "a", "target": "b"}],
        "analysis": {"type": "random"},
    }
    (note,) = contact_check.eigen_notes(raw, {"바닥": {"판"}, "a": {"판"}, "b": {"블록"}})
    assert "랜덤 진동" in note["text"]


def _numeric_grms(table: list[list[float]]) -> float:
    """로그 간격으로 잘게 나눈 사다리꼴 — 닫힌 식과 따로 맞춰 본다."""
    area = 0.0
    for (f1, p1), (f2, p2) in itertools.pairwise(table):
        slope = math.log(p2 / p1) / math.log(f2 / f1)
        steps = 20000
        for i in range(steps):
            a = f1 * (f2 / f1) ** (i / steps)
            b = f1 * (f2 / f1) ** ((i + 1) / steps)
            pa, pb = p1 * (a / f1) ** slope, p1 * (b / f1) ** slope
            area += (pa + pb) / 2 * (b - a)
    return math.sqrt(area)


def test_사인_스윕_픽스처의_조건이_저장된다() -> None:
    """화면이 싣는 모양 그대로 — 표 · 위상이 있는 하중과 해석이 함께 통과한다."""
    parse({**SINE, "loads": [{**SINE["loads"][0], "phase": 45}]})
    parse(RANDOM)
    assert conditions.PSD_UNIT == "g^2/Hz"
