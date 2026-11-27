"""해석 케이스 — 공유 모델 위에 해석을 여럿(ADR 0013, 구조 정리 ①).

옛 모양(v1)은 케이스 하나다. 케이스가 하나인 v2 는 **v1 그대로** 내보내고(받는 쪽이 바뀌는 것이
없다), 여럿이면 받는 쪽이 v2 를 받기 전에는 내보내기가 까닭을 말하고 막는다. 케이스 안의 규칙은
케이스마다 v1 의 점검 그대로이고, 틀린 자리는 `cases[1].loads[0]` 처럼 케이스까지 짚는다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.core import conditions
from app.core.conditions import ConditionError, parse, resolve
from app.core.conditions.registry import analyses_with

SHARED: dict[str, Any] = {
    "units": {"system": "si"},
    "named_selections": [
        {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}},
        {"name": "윗면", "entity": "face", "select": {"what": "faces", "role": "top"}},
        {"name": "볼트 면", "entity": "face", "select": {"what": "faces", "kind": "cylinder"}},
        {
            "name": "둘째 볼트 면",
            "entity": "face",
            "select": {"what": "faces", "kind": "cylinder", "radius": 4},
        },
    ],
    "materials": [
        {
            "ref": {"source": "matnexus", "code": "S", "name": "강"},
            "apply_to": ["전체"],
            "payload": {"values": {"탄성계수": {"value": 200, "unit": "GPa"}}},
        }
    ],
    "contacts": [],
}
PRELOAD: dict[str, Any] = {
    "name": "예압",
    "target": {"solver": "calculix"},
    "analysis": {"type": "static", "large_deflection": False},
    "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
    "loads": [{"name": "누름", "type": "pressure", "on": "윗면", "magnitude": "=압력"}],
}
OUTER: dict[str, Any] = {
    "name": "외력",
    "depends_on": "예압",
    "target": {"solver": "calculix"},
    "analysis": {"type": "static"},
    "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
    "loads": [
        {
            "name": "옆 힘",
            "type": "force",
            "on": "윗면",
            "magnitude": 500,
            "direction": [1, 0, 0],
        }
    ],
}
TWO: dict[str, Any] = {**SHARED, "schema_version": 2, "cases": [PRELOAD, OUTER]}
BOLT: dict[str, Any] = {
    "name": "조임",
    "type": "bolt_pretension",
    "on": "볼트 면",
    "preload": 1000,
    "unit": "N",
}
GRAVITY: dict[str, Any] = {"name": "중력", "type": "standard_earth_gravity"}


def _v1_of(case: dict[str, Any]) -> dict[str, Any]:
    keys = ("analysis", "constraints", "loads", "initial")
    return {**SHARED, **{key: case[key] for key in keys if key in case}}


def test_케이스가_하나면_v1_그대로_내보낸다() -> None:
    one = {**SHARED, "schema_version": 2, "cases": [PRELOAD]}
    assert resolve(one, {"압력": 2}) == resolve(_v1_of(PRELOAD), {"압력": 2})
    assert resolve(one, {"압력": 2})["schema_version"] == 1
    assert "cases" not in resolve(one, {"압력": 2})
    # 옛 모양에도 `cases` 칸이 새지 않는다 — 받는 쪽이 보던 그대로.
    assert "cases" not in resolve(_v1_of(PRELOAD), {"압력": 2})
    assert "cases" not in conditions.EMPTY


def test_케이스가_여럿이면_저장은_되고_내보내기는_까닭을_말하고_막는다() -> None:
    parse(TWO)
    with pytest.raises(
        ConditionError, match=r"해석 케이스가 2개인 조건은 아직 내보낼 수 없습니다"
    ):
        resolve(TWO, {"압력": 2})


def test_v2_로_풀면_공유는_한_벌_케이스마다_풀린_칸() -> None:
    got = resolve(TWO, {"압력": 2}, cases=True)
    assert got["schema_version"] == 2
    assert not {"analysis", "constraints", "loads", "initial"} & set(got)
    first, second = got["cases"]
    assert (first["name"], first["depends_on"], first["target"]) == (
        "예압",
        "",
        {"solver": "calculix"},
    )
    assert second["depends_on"] == "예압"
    # 케이스마다 v1 과 같은 풀기 — 식 · 단위(SI 는 MPa → Pa) · 비운 방향 채우기.
    alone = resolve(_v1_of(PRELOAD), {"압력": 2})
    assert first["loads"] == alone["loads"]
    assert first["loads"][0]["magnitude"] == pytest.approx(2e6)
    assert first["analysis"] == alone["analysis"]
    assert got["materials"] == alone["materials"]
    assert got["units"] == alone["units"]


def test_케이스_안의_틀린_자리를_케이스까지_짚는다() -> None:
    bad = deepcopy(TWO)
    bad["cases"][1]["loads"][0]["on"] = "없는 면"
    with pytest.raises(ConditionError, match=r"^cases\[1\]\.loads\[0\]: 선택 그룹 ‘없는 면’"):
        parse(bad)
    psd = deepcopy(TWO)
    psd["cases"][0]["loads"].append(
        {
            "name": "흔듦",
            "type": "psd_acceleration",
            "direction": [0, 0, 1],
            "psd_table": [[20, 0.04], [2000, 0.04]],
        }
    )
    with pytest.raises(ConditionError, match=r"^cases\[0\]\.loads\[1\]: .*랜덤 진동"):
        parse(psd)
    # 모양이 틀린 것은 Pydantic 의 자리 그대로.
    shape = deepcopy(TWO)
    shape["cases"][1]["analysis"]["type"] = "모르는 해석"
    with pytest.raises(ConditionError, match=r"^cases\.1\.analysis\.type"):
        parse(shape)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda raw: raw["cases"][1].update(name="예압"),
            r"cases\[1\]: 케이스 이름 ‘예압’이\(가\) 중복",
        ),
        (
            lambda raw: raw["cases"][1].update(depends_on="없음"),
            r"앞 케이스 ‘없음’이\(가\) 없습니다",
        ),
        (
            lambda raw: raw["cases"][0].update(depends_on="외력"),
            r"이 케이스보다 뒤에 있습니다",
        ),
        (lambda raw: raw["cases"][1].update(depends_on="외력"), r"자기 자신"),
        (lambda raw: raw["cases"][1].update(target={"solver": "ansys"}), r"한 솔버가 풉니다"),
        (lambda raw: raw.update(schema_version=1), r"schema_version 2 에서만"),
        (lambda raw: raw.update(cases=[]), r"하나 이상"),
        (lambda raw: raw.update(loads=PRELOAD["loads"]), r"맨 위의 loads"),
        (
            lambda raw: raw["cases"].append({**OUTER, "name": "외력 B"}),
            r"cases\[2\]: 앞 케이스 ‘예압’ 뒤에는 이미 ‘외력’이\(가\) 있습니다 — 케이스는 "
            r"사슬로만",
        ),
        (
            lambda raw: raw["cases"][1].update(constraints=[]),
            r"cases\[1\]\.constraints: 앞 케이스 ‘예압’과\(와\) 구속이 다릅니다",
        ),
        (
            lambda raw: [one["loads"].append(BOLT) for one in raw["cases"]],
            r"cases\[1\]\.loads\[1\]: 볼트 예압 ‘조임’의 볼트\(‘볼트 면’\)는 "
            r"앞 케이스 ‘예압’에서 이미 조였습니다",
        ),
        (
            lambda raw: raw["cases"][0]["loads"].append(GRAVITY),
            r"cases\[1\]\.loads: 앞 케이스 ‘예압’에는 중력이 있고 이 케이스에는 없습니다",
        ),
        (
            lambda raw: raw["cases"][1]["loads"].append(GRAVITY),
            r"cases\[1\]\.loads: 이 케이스에만 중력이 있습니다\(앞 케이스 ‘예압’에는 없음\)",
        ),
        (
            lambda raw: [
                raw["cases"][0]["loads"].append(GRAVITY),
                raw["cases"][1]["loads"].append({**GRAVITY, "direction": [0, -1, 0]}),
            ],
            r"cases\[1\]\.loads: 중력의 방향 또는 좌표계가 앞 케이스 ‘예압’과\(와\) 다릅니다",
        ),
        (
            lambda raw: [
                raw["cases"][0]["loads"].append(GRAVITY),
                raw["cases"][1]["loads"].append({**GRAVITY, "cs": "기운 좌표계"}),
            ],
            r"중력의 방향 또는 좌표계가",
        ),
    ],
)
def test_케이스끼리의_규칙(change: Any, message: str) -> None:
    raw = deepcopy(TWO)
    change(raw)
    with pytest.raises(ConditionError, match=message):
        parse(raw)


def test_사슬은_앞의_구속을_차례와_상관없이_그대로_받고_조인_볼트는_잠근다() -> None:
    """뒤 케이스는 앞의 끝 상태에서 시작하고 하중은 이어지지 않는다 — 구속은 같게(적은
    차례는 상관없다), 중력은 같은 것을 다시 적고, 앞에서 조인 볼트는 적지 않는다. 다른 볼트는
    뒤에서 조여도 된다. 가속도는 케이스마다 달라도 된다(Mechanical 도 단계마다 끈다)."""
    raw = deepcopy(TWO)
    first, second = raw["cases"]
    side = {"name": "옆 고정", "type": "fixed_support", "on": "윗면"}
    first["constraints"].append(side)
    second["constraints"].insert(0, side)
    first["loads"] += [BOLT, GRAVITY]
    # 같은 중력 — 방향을 비운 것(-Z)과 길이만 다른 -Z 는 같다.
    second["loads"].append({**GRAVITY, "direction": [0, 0, -2]})
    third = {
        **deepcopy(second),
        "name": "다시 누름",
        "depends_on": "외력",
        "loads": [
            GRAVITY,
            {**BOLT, "name": "둘째 볼트", "on": "둘째 볼트 면"},
            {
                "name": "흔듦",
                "type": "acceleration",
                "magnitude": 9806.65,
                "direction": [1, 0, 0],
            },
        ],
    }
    raw["cases"].append(third)
    parse(raw)

    third["loads"].append(BOLT)
    with pytest.raises(
        ConditionError, match=r"cases\[2\]\.loads\[3\]: .*앞 케이스 ‘예압’에서"
    ):
        parse(raw)


def test_케이스_보기는_공유와_그_케이스의_v1_모양이다() -> None:
    views = conditions.raw_views(TWO)
    assert [name for name, _ in views] == ["예압", "외력"]
    assert views[1][1]["loads"] == OUTER["loads"]
    assert views[1][1]["named_selections"] == SHARED["named_selections"]
    assert "cases" not in views[1][1]
    assert conditions.raw_views(_v1_of(PRELOAD)) == [("", _v1_of(PRELOAD))]


def test_식_알림은_케이스마다_어느_케이스인지_말한다() -> None:
    notes = conditions.expression_notes(TWO, {})
    assert [note["where"] for note in notes] == ["케이스 ‘예압’ · 하중 ‘누름’ 크기"]
    # v1 은 그대로.
    assert [note["where"] for note in conditions.expression_notes(_v1_of(PRELOAD), {})] == [
        "하중 ‘누름’ 크기"
    ]


def test_케이스가_하나인_v2_도_고르기_인자가_그_케이스에_든다() -> None:
    one = {**SHARED, "schema_version": 2, "cases": [deepcopy(PRELOAD)]}
    target = {"group": "analysis", "field": "large_deflection"}
    made = conditions.with_choice(one, target, True)
    assert made["cases"][0]["analysis"]["large_deflection"] is True
    assert "analysis" not in made
    with pytest.raises(ConditionError, match=r"해석 케이스가 2개입니다"):
        conditions.with_choice(TWO, target, True)


# ── 「정적 → 모달」 사슬을 v1 선응력 모달로 접기(SimEngBay 와 정함, 2026-11-27) ──────────

FIXED: list[dict[str, Any]] = [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}]
SIDE: dict[str, Any] = OUTER["loads"][0]
MODAL: dict[str, Any] = {
    "name": "모달",
    "target": {"solver": "calculix"},
    "analysis": {"type": "modal", "modes": 8},
    "constraints": FIXED,
}


def _chain(*cases: dict[str, Any]) -> dict[str, Any]:
    """차례로 잇는 사슬 — 둘째부터 바로 앞 케이스 뒤."""
    out = []
    for index, case in enumerate(cases):
        one = {"target": {"solver": "calculix"}, "constraints": FIXED, **deepcopy(case)}
        one["depends_on"] = cases[index - 1]["name"] if index else ""
        out.append(one)
    return {**SHARED, "schema_version": 2, "cases": out}


def _prestressed(loads: list[dict[str, Any]]) -> dict[str, Any]:
    """같은 것을 v1 으로 적은 선응력 모달 — 픽스처 「조건_볼트예압_선응력모달」 의 꼴."""
    return {
        **SHARED,
        "analysis": {"type": "modal", "modes": 8, "prestressed": True},
        "constraints": FIXED,
        "loads": loads,
        "initial": [{"type": "prestress"}],
    }


def test_정적_뒤의_모달은_v1_선응력_모달로_접어_내보낸다() -> None:
    """뒤 케이스는 앞 정적의 끝 상태에서 시작한다 — v1 선응력 모달과 같은 뜻이다. 하중 · 구속 ·
    초기조건은 정적의 것, 해석은 모달의 것 + `prestressed`. 대상 솔버는 v1 에 없다."""
    static = {"name": "정적", "analysis": {"type": "static"}, "loads": [BOLT, SIDE]}
    two = _chain(static, MODAL)
    assert resolve(two, {}) == resolve(_prestressed([BOLT, SIDE]), {})
    assert resolve(two, {})["schema_version"] == 1
    # 환경 온도는 첫 케이스의 것이 그대로, 선응력이 뒤에 붙는다.
    room = [{"type": "environment_temperature", "value": 40}]
    warm = _chain({**static, "initial": room}, MODAL)
    assert [one["type"] for one in resolve(warm, {})["initial"]] == [
        "environment_temperature",
        "prestress",
    ]
    # 스위치(`doe_conditions_v2`)를 켜면 접지 않고 v2 그대로.
    assert resolve(two, {}, cases=True)["schema_version"] == 2


def test_예압_외력_모달_셋은_하중을_합쳐_접는다_중력은_한_번() -> None:
    """v1 은 볼트와 다른 하중이 한 벌에 있으면 ① 조임 → ② 조인 길이로 잠그고 나머지, 두
    단계로 푼다 — 「예압」 에 볼트 예압(+ 중력)뿐이면 사슬과 같은 답이다(SimEngBay)."""
    preload = {"name": "예압", "analysis": {"type": "static"}, "loads": [BOLT, GRAVITY]}
    outer = {"name": "외력", "analysis": {"type": "static"}, "loads": [SIDE, GRAVITY]}
    three = _chain(preload, outer, {**MODAL, "loads": [GRAVITY]})
    assert resolve(three, {}) == resolve(_prestressed([BOLT, GRAVITY, SIDE]), {})


def _bolt_static(loads: list[dict[str, Any]], **analysis: Any) -> dict[str, Any]:
    """같은 것을 v1 으로 적은 볼트 정적 — 픽스처 「조건_볼트예압_정적」 의 꼴(두 단계)."""
    return {
        **SHARED,
        "analysis": {"type": "static", "steps": 2, **analysis},
        "constraints": FIXED,
        "loads": loads,
    }


def test_볼트_예압_뒤의_외력은_v1_볼트_정적으로_접는다() -> None:
    """v1 의 볼트 정적이 바로 이 사슬이다 — 두 솔버 모두 ① 볼트 예압 + 중력 → ② 조인 길이로
    잠그고 나머지(SimEngBay, 2026-11-27). 하중 = 예압 + 외력(중력은 한 번), 구속 · 초기조건은
    첫 케이스의 것, 해석은 두 단계. 대변형 · 초기 부단계는 두 케이스가 같으면 그대로 싣는다."""
    preload = {"name": "예압", "analysis": {"type": "static"}, "loads": [BOLT]}
    outer = {"name": "외력", "analysis": {"type": "static"}, "loads": [SIDE]}
    assert resolve(_chain(preload, outer), {}) == resolve(_bolt_static([BOLT, SIDE]), {})
    heavy = _chain({**preload, "loads": [BOLT, GRAVITY]}, {**outer, "loads": [SIDE, GRAVITY]})
    assert resolve(heavy, {}) == resolve(_bolt_static([BOLT, GRAVITY, SIDE]), {})
    large = {"type": "static", "large_deflection": True, "substeps": 5}
    bent = _chain({**preload, "analysis": large}, {**outer, "analysis": large})
    expected = _bolt_static([BOLT, SIDE], large_deflection=True, substeps=5)
    assert resolve(bent, {}) == resolve(expected, {})
    # 스위치를 켜면 접지 않고 v2 그대로.
    assert resolve(_chain(preload, outer), {}, cases=True)["schema_version"] == 2


_STATIC = {"name": "정적", "analysis": {"type": "static"}, "loads": [BOLT, SIDE]}
_PRELOAD = {"name": "예압", "analysis": {"type": "static"}, "loads": [BOLT]}
_OUTER = {"name": "외력", "analysis": {"type": "static"}, "loads": [SIDE]}


@pytest.mark.parametrize(
    ("cases", "message"),
    [
        # 정적 둘 — 「볼트 예압 → 외력」 만 접는다.
        ((_STATIC, _OUTER), r"‘정적’에 볼트 예압 말고 다른 하중\(옆 힘\)이 있습니다"),
        (
            (_PRELOAD, {**_OUTER, "analysis": {"type": "static", "steps": 2}}),
            r"‘외력’의 해석 설정\(하중 단계 수\)은 해석 쪽이 읽지 않습니다",
        ),
        (
            ({**_PRELOAD, "analysis": {"type": "static", "solver": "direct"}}, _OUTER),
            r"‘예압’의 해석 설정\(솔버\)은",
        ),
        (
            ({**_PRELOAD, "analysis": {"type": "static", "large_deflection": True}}, _OUTER),
            r"두 케이스의 해석 설정\(대변형\)이 다릅니다",
        ),
        (
            (
                _PRELOAD,
                {**_OUTER, "initial": [{"type": "environment_temperature", "value": 30}]},
            ),
            r"‘외력’에 초기조건이 있습니다",
        ),
        ((_PRELOAD, _OUTER, {**_OUTER, "name": "또"}), r"정적이 3개입니다 — v1 정적으로는 둘"),
        (
            (
                _STATIC,
                {
                    **MODAL,
                    "analysis": {"type": "random", "modes": 8, "damping_ratio": 0.02},
                    "loads": [
                        {
                            "name": "흔듦",
                            "type": "psd_acceleration",
                            "direction": [0, 0, 1],
                            "psd_table": [[20, 0.04], [2000, 0.04]],
                        }
                    ],
                },
            ),
            r"접지 못한 까닭: ‘모달’\(랜덤 진동\(PSD\)\)의 선응력은 .*모달만 접습니다",
        ),
        (
            ({**_STATIC, "analysis": {"type": "static", "steps": 2}}, MODAL),
            r"앞 정적 ‘정적’의 해석 설정\(하중 단계 수\)은 v1 선응력 모달이 읽지 않습니다",
        ),
        (
            ({**_STATIC, "analysis": {"type": "static", "large_deflection": True}}, MODAL),
            r"해석 설정\(대변형\)",
        ),
        ((_STATIC, {**MODAL, "loads": [SIDE]}), r"모달 ‘모달’에 하중\(옆 힘\)이 있습니다"),
        (
            (
                _STATIC,
                {**MODAL, "initial": [{"type": "environment_temperature", "value": 30}]},
            ),
            r"‘모달’에 초기조건이 있습니다 — 접으면 첫 케이스 ‘정적’의 초기조건만",
        ),
        (
            ({**_PRELOAD, "loads": [BOLT, SIDE]}, {**_OUTER, "loads": []}, MODAL),
            r"‘예압’에 볼트 예압 말고 다른 하중\(옆 힘\)이 있습니다",
        ),
        (
            ({**_PRELOAD, "loads": []}, _OUTER, MODAL),
            r"‘예압’에 볼트 예압이 없습니다",
        ),
        (
            (
                _PRELOAD,
                {**_OUTER, "loads": [SIDE, {**BOLT, "name": "둘째", "on": "둘째 볼트 면"}]},
                MODAL,
            ),
            r"‘외력’에서 볼트\(둘째\)를 조입니다",
        ),
        (
            (_PRELOAD, _OUTER, {**_OUTER, "name": "또"}, MODAL),
            r"모달 앞의 정적이 3개입니다",
        ),
    ],
)
def test_v1_선응력_모달로_못_적는_사슬은_까닭을_붙여_막는다(
    cases: tuple[dict[str, Any], ...], message: str
) -> None:
    raw = _chain(*cases)
    parse(raw)  # 저장은 된다.
    blocked = r"해석 케이스가 \d개인 조건은 아직 내보낼 수 없습니다"
    with pytest.raises(ConditionError, match=blocked):
        resolve(raw, {})
    with pytest.raises(ConditionError, match=message):
        resolve(raw, {})


def test_사슬이_아니면_접지_않는다() -> None:
    """모달이 앞 케이스 없이 따로면 — 선응력이 아니다."""
    raw = _chain(_STATIC, MODAL)
    raw["cases"][1]["depends_on"] = ""
    with pytest.raises(ConditionError, match=r"따로 내보내십시오\.$"):
        resolve(raw, {})


def test_조화_응답은_선응력을_받지_않는다() -> None:
    """두 솔버 모두 받지 않는다(SimEngBay, 2026-11-27) — 칸을 내지 않고, 초기조건은 까닭과
    막는다."""
    harmonic = {
        **SHARED,
        "analysis": {"type": "harmonic", "frequency_range": [10, 100], "prestressed": True},
        "constraints": FIXED,
        "loads": [SIDE],
    }
    # 옛 값이 남아 있어도 내보내지 않는다(화면에 칸이 없다).
    assert "prestressed" not in resolve(harmonic, {})["analysis"]
    refused = r"initial\[0\]: .*조화 응답의 선응력은 해석 쪽이"
    with pytest.raises(ConditionError, match=refused):
        parse({**harmonic, "initial": [{"type": "prestress"}]})
    assert analyses_with("prestressed") == ["modal", "random"]


def test_조화_응답은_볼트_예압_회전_속도_중력을_받지_않는다() -> None:
    """가진이 아니다 — 두 솔버 모두 작업을 만들 때 막는다(SimEngBay, 2026-11-27 — 중력은
    그쪽 사용자가 정했다). 저장에서 먼저 막는다. 압력 · 힘 · 가속도는 그대로 받는다."""
    harmonic = {
        **SHARED,
        "analysis": {"type": "harmonic", "frequency_range": [10, 100]},
        "constraints": FIXED,
    }
    parse({**harmonic, "loads": [SIDE]})
    with pytest.raises(ConditionError, match=r"loads\[0\]: .*조화 응답에서는 볼트 예압을"):
        parse({**harmonic, "loads": [BOLT]})
    spin = {
        "name": "돌림",
        "type": "rotational_velocity",
        "magnitude": 100,
        "direction": [0, 0, 1],
    }
    with pytest.raises(ConditionError, match=r"loads\[1\]: .*조화 응답에서는 회전 속도를"):
        parse({**harmonic, "loads": [SIDE, spin]})
    with pytest.raises(ConditionError, match=r"loads\[0\]: .*중력을 .*가속도 하중으로"):
        parse({**harmonic, "loads": [GRAVITY, SIDE]})
