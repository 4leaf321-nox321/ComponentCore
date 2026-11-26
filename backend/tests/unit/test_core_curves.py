"""곡선 — 이름 붙은 표 하나를 하중이 가리킨다(ADR 0013, 구조 정리 ①).

조화 응답의 주파수별 배율 · 랜덤 진동의 가속도 PSD 는 표 대신 곡선을 가리킬 수 있다. 내보낼
때는 곡선을 풀어 **표를 적은 것과 똑같이** 싣는다 — 받는 쪽은 바뀌는 것이 없다. 보간 · 단위가
그 표의 뜻과 다르면 저장에서 막는다(받는 쪽은 표를 늘 그 뜻으로 읽는다).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.core.conditions import ConditionError, parse, resolve, spec

BASE: dict[str, Any] = {
    "named_selections": [
        {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}},
    ],
    "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
}
PROFILE = [[20, 0.01], [80, 0.04], [350, 0.04], [2000, 0.007]]
PSD_CURVE: dict[str, Any] = {
    "name": "IEC 랜덤",
    "x": "frequency",
    "unit": "g^2/Hz",
    "interpolation": "loglog",
    "points": PROFILE,
}
RANDOM: dict[str, Any] = {
    **BASE,
    "curves": [PSD_CURVE],
    "loads": [
        {
            "name": "X 랜덤",
            "type": "psd_acceleration",
            "direction": [1, 0, 0],
            "curve": "IEC 랜덤",
        }
    ],
    "analysis": {"type": "random", "modes": 10, "damping_ratio": 0.02},
}
SINE: dict[str, Any] = {
    **BASE,
    "curves": [
        {"name": "스윕 배율", "x": "frequency", "points": [[100, 0.5], [800, 1], [2000, 1]]}
    ],
    "loads": [
        {
            "name": "스윕",
            "type": "acceleration",
            "magnitude": 9806.65,
            "direction": [1, 0, 0],
            "curve": "스윕 배율",
        }
    ],
    "analysis": {
        "type": "harmonic",
        "frequency_range": [200, 2000],
        "modes": 6,
        "damping_ratio": 0.02,
    },
}


def _inline(raw: dict[str, Any], field: str) -> dict[str, Any]:
    """같은 조건을 표로 적은 것 — 곡선의 점 그대로."""
    out = deepcopy(raw)
    (curve,) = out.pop("curves")
    (load,) = out["loads"]
    load.pop("curve")
    load[field] = curve["points"]
    return out


@pytest.mark.parametrize(("raw", "field"), [(RANDOM, "psd_table"), (SINE, "frequency_table")])
def test_곡선을_가리킨_하중은_표를_적은_것과_똑같이_나간다(
    raw: dict[str, Any], field: str
) -> None:
    made = resolve(raw, {})
    assert made == resolve(_inline(raw, field), {})
    assert "curves" not in made, "받는 쪽은 곡선을 모른다 — 표로 풀어 싣는다"
    assert "curve" not in made["loads"][0]


def test_곡선이_없는_조건은_곡선_칸이_새지_않는다() -> None:
    made = resolve(_inline(SINE, "frequency_table"), {})
    assert "curves" not in made
    assert all("curve" not in one for one in made["loads"])


def test_배율과_점의_식은_설계점마다_풀려_곱한다() -> None:
    raw = deepcopy(SINE)
    raw["curves"][0].update(points=[[100, "=끝"], [800, 1], [2000, 1]], scale="=레벨")
    made = resolve(raw, {"레벨": 2, "끝": 0.25})
    assert made["loads"][0]["frequency_table"] == [[100, 0.5], [800, 2.0], [2000, 2.0]]
    random = deepcopy(RANDOM)
    random["curves"][0]["scale"] = 4
    (load,) = resolve(random, {})["loads"]
    assert load["psd_table"] == [[f, v * 4] for f, v in PROFILE]
    assert load["grms"] == pytest.approx(resolve(RANDOM, {})["loads"][0]["grms"] * 2), (
        "PSD 가 4 배면 실효값은 2 배 — 풀린 표로 잰다"
    )


def test_시간_곡선은_저장은_되고_내보내기에는_실리지_않는다() -> None:
    raw = {
        **_inline(SINE, "frequency_table"),
        "curves": [{"name": "예압 곡선", "x": "time", "points": [[0, 0], [1, -1], [2, 1]]}],
    }
    assert parse(raw).curves[0].name == "예압 곡선"
    assert "curves" not in resolve(raw, {})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda raw: raw["curves"].append(deepcopy(PSD_CURVE)),
            r"curves\[1\]: 곡선 이름 ‘IEC 랜덤’이\(가\) 중복됩니다\(curves\[0\]\)",
        ),
        (
            lambda raw: raw["curves"][0].update(x="time"),
            r"curves\[0\]: .*로그-로그 보간은 주파수 곡선에만",
        ),
        (
            lambda raw: raw["curves"][0].update(points=[[20, 0.01]]),
            r"curves\[0\]: 곡선 ‘IEC 랜덤’의 점은 두 행 이상",
        ),
        (
            lambda raw: raw["curves"][0].update(points=[[80, 0.01], [20, 0.04]]),
            r"2행: 주파수는 위 행보다 커야",
        ),
        (
            lambda raw: raw["curves"][0].update(points=[[20, 0.01], [80, 0]]),
            r"2행: 값은 0보다 커야",
        ),
        (lambda raw: raw["curves"][0].update(scale=0), r"배율은 0보다 커야"),
        (
            lambda raw: raw["loads"][0].update(curve="없는 곡선"),
            r"loads\[0\]: 가속도 PSD\(기저 가진\) ‘X 랜덤’의 곡선 ‘없는 곡선’이\(가\) "
            r"없습니다",
        ),
        (
            lambda raw: raw["loads"][0].update(psd_table=PROFILE),
            r"loads\[0\]: .*가속도 PSD 표와 곡선 ‘IEC 랜덤’을\(를\) 함께 적을 수 없습니다",
        ),
        (
            lambda raw: raw["curves"][0].update(interpolation="linear"),
            r"가속도 PSD은\(는\) 로그-로그 보간입니다\(곡선 ‘IEC 랜덤’: 선형\)",
        ),
        (
            lambda raw: raw["curves"][0].update(unit=""),
            r"가속도 PSD 단위는 g\^2/Hz입니다\(곡선 ‘IEC 랜덤’: 없음\)",
        ),
    ],
)
def test_곡선과_그_쓰임의_규칙(change: Any, message: str) -> None:
    raw = deepcopy(RANDOM)
    change(raw)
    with pytest.raises(ConditionError, match=message):
        parse(raw)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda raw: raw["curves"][0].update(x="time"),
            r"주파수 곡선만 쓸 수 있습니다\(곡선 ‘스윕 배율’은\(는\) 시간 곡선\)",
        ),
        (
            lambda raw: raw["curves"][0].update(scale=-1),
            r"곡선 ‘스윕 배율’\(배율 곱\) 1행: 값은 0 이상이어야",
        ),
        (
            lambda raw: raw["curves"][0].update(points=[[300, 0.5], [2000, 1]]),
            r"주파수별 배율\(300~2000 Hz\)이 해석의 주파수 범위\(200~2000 Hz\)를 "
            r"모두 포함하지",
        ),
        (
            lambda raw: raw["loads"].append(
                {
                    "name": "조임",
                    "type": "bolt_pretension",
                    "on": "바닥",
                    "preload": 1,
                    "unit": "N",
                    "curve": "스윕 배율",
                }
            ),
            r"loads\[1\]: 볼트 예압 ‘조임’은\(는\) 곡선을 가리킬 수 없습니다",
        ),
    ],
)
def test_조화_응답의_배율_곡선은_배율_표와_같은_점검을_지난다(
    change: Any, message: str
) -> None:
    raw = deepcopy(SINE)
    change(raw)
    with pytest.raises(ConditionError, match=message):
        parse(raw)


def test_케이스의_하중도_공유_곡선을_가리키고_틀린_자리는_케이스까지_짚는다() -> None:
    case = {key: RANDOM[key] for key in ("constraints", "loads", "analysis")}
    raw = {
        "schema_version": 2,
        "named_selections": BASE["named_selections"],
        "curves": [PSD_CURVE],
        "cases": [{"name": "랜덤", **case}],
    }
    assert resolve(raw, {}) == resolve(RANDOM, {})
    raw["cases"][0]["loads"][0]["curve"] = "없는 곡선"
    with pytest.raises(ConditionError, match=r"^cases\[0\]\.loads\[0\]: .*‘없는 곡선’"):
        parse(raw)


def test_사양표가_곡선의_칸과_하중마다_채우는_표를_준다() -> None:
    table = spec()
    assert set(table["curves"]["fields"]) == {
        "name",
        "x",
        "unit",
        "interpolation",
        "points",
        "scale",
    }
    assert table["curves"]["uses"]["psd_acceleration"] == {
        "field": "psd_table",
        "interpolation": "loglog",
        "unit": "g^2/Hz",
    }
    assert table["curves"]["uses"]["force"]["field"] == "frequency_table"
    # 화면은 곡선 편집을 아직 그리지 않는다 — 하중의 칸은 숨기고 값은 지킨다.
    assert table["groups"]["loads"]["fields"]["curve"]["hidden"] is True
