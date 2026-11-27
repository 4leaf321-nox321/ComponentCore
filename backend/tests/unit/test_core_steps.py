"""하중 단계 — ② 비선형 정적(SimEngBay 와 정함, 2026-11-27).

해석 케이스에서만 쓰고, v1 으로 나가는 길은 막고, v2 에서는 케이스가 하나여도 v2 로 낸다.
쓰지 않는 한 벌의 내보내기는 지금과 같다(② 칸이 실리지 않는다).
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.core.conditions import ConditionError, parse, resolve
from app.core.conditions.capabilities import notes, read
from app.core.conditions.model import views
from app.core.conditions.steps import step_to_time

FIXTURE = Path(__file__).parents[1] / "fixtures" / "simengbay" / "capabilities.json"
RAW: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))

SHARED: dict[str, Any] = {
    "units": {"system": "mm_n_tonne"},
    "named_selections": [
        {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}},
        {"name": "윗면", "entity": "face", "select": {"what": "faces", "role": "top"}},
        {"name": "볼트 면", "entity": "face", "select": {"what": "faces", "kind": "cylinder"}},
    ],
    "materials": [
        {
            "ref": {"source": "matnexus", "code": "S", "name": "강"},
            "apply_to": ["전체"],
            "payload": {"values": {"탄성계수": {"value": 200, "unit": "GPa"}}},
        }
    ],
}
FIXED: dict[str, Any] = {"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}
PUSH: dict[str, Any] = {
    "name": "옆 힘",
    "type": "force",
    "on": "윗면",
    "magnitude": 500,
    "direction": [1, 0, 0],
}
BOLT: dict[str, Any] = {
    "name": "조임",
    "type": "bolt_pretension",
    "on": "볼트 면",
    "preload": 1000,
    "unit": "N",
}
GRAVITY: dict[str, Any] = {"name": "중력", "type": "standard_earth_gravity"}
TWO_STEPS: list[dict[str, Any]] = [{"name": "예압"}, {"name": "외력"}]


def _case(*loads: dict[str, Any], **analysis: Any) -> dict[str, Any]:
    """정적 케이스 하나 — 해석 설정은 `analysis` 로 덧붙인다."""
    return deepcopy(
        {
            **SHARED,
            "schema_version": 2,
            "cases": [
                {
                    "name": "정적",
                    "analysis": {"type": "static", **analysis},
                    "constraints": [FIXED],
                    "loads": list(loads),
                }
            ],
        }
    )


#: v1 의 볼트 정적(`steps: 2`)과 같은 뜻 — 단계 둘, 볼트 [조임, 잠금], 볼트가 아닌 하중은 ②,
#: 중력은 모든 단계(SimEngBay, 2026-11-27).
BOLT_IN_STEPS = _case(
    {**BOLT, "bolt_steps": ["load", "lock"]},
    {**PUSH, "active_steps": [2]},
    GRAVITY,
    load_steps=TWO_STEPS,
)


def test_하중_단계는_해석_케이스에서만_쓴다() -> None:
    v1 = {
        **SHARED,
        "analysis": {"type": "static", "load_steps": TWO_STEPS},
        "constraints": [FIXED],
        "loads": [PUSH],
    }
    with pytest.raises(
        ConditionError,
        match=r"^analysis: 해석 설정 ‘하중 단계’은\(는\) 해석 케이스에서 지정합니다",
    ):
        parse(v1)
    parse(BOLT_IN_STEPS)


@pytest.mark.parametrize(
    ("analysis", "message"),
    [
        (
            {"load_steps": [{"end_time": 2}, {"end_time": 1}]},
            r"load_steps\[1\]: 끝 시간\(1 s\)은 앞 단계\(2 s\)보다 커야",
        ),
        (
            {"load_steps": [{"end_time": 2}, {}]},
            r"load_steps\[1\]: 끝 시간\(2 s\)은 앞 단계\(2 s\)보다 커야",
        ),
        (
            {"load_steps": [{"substeps": {"initial": 5, "minimum": 10}}]},
            r"최소 ≤ 처음 ≤ 최대",
        ),
        ({"load_steps": [{"substeps": {"maximum": 0}}]}, r"부단계 수는 1 이상"),
        ({"load_steps": TWO_STEPS, "steps": 2}, r"‘하중 단계 수’와 ‘초기 부단계 수’는 비워"),
        (
            {"load_steps": TWO_STEPS, "substeps": 10},
            r"‘하중 단계 수’와 ‘초기 부단계 수’는 비워",
        ),
    ],
)
def test_단계의_끝_시간과_부단계를_본다(analysis: dict[str, Any], message: str) -> None:
    with pytest.raises(ConditionError, match=message):
        parse(_case(PUSH, **analysis))


@pytest.mark.parametrize(
    ("load", "message"),
    [
        ({**GRAVITY, "active_steps": [1]}, r"중력은 모든 하중 단계에 같게 걸립니다"),
        ({**BOLT, "active_steps": [1]}, r"‘단계별 볼트 동작’으로 단계를 정합니다"),
        ({**PUSH, "active_steps": [3]}, r"적용 단계 3이\(가\) 없습니다\(하중 단계 2개\)"),
        ({**PUSH, "active_steps": [2, 1]}, r"작은 번호부터 한 번씩"),
        (
            {**PUSH, "active_steps": [2], "time_table": [[0, 0], [2, 1]]},
            r"‘시간별 배율’\(또는 곡선\)과 ‘적용 단계’를 함께 쓸 수 없습니다",
        ),
        ({**GRAVITY, "time_table": [[0, 0], [2, 1]]}, r"‘시간별 배율’은 .*에만 지정할 수"),
        (
            {**PUSH, "time_table": [[0, 0], [1, 1]]},
            r"0 s에서 시작해 마지막 하중 단계의 끝 시간\(2 s\)에서 끝나야 합니다",
        ),
        (
            {**PUSH, "time_table": [[0.5, 0], [2, 1]]},
            r"양 끝을 모두 적으십시오",
        ),
        ({**BOLT, "bolt_steps": ["load"]}, r"하중 단계 수\(2\)만큼 적어야 합니다\(지금 1\)"),
        ({**BOLT, "bolt_steps": ["lock", "load"]}, r"첫 단계에서 한 번 조이고"),
        ({**PUSH, "bolt_steps": ["load", "lock"]}, r"볼트 예압에만 지정할 수 있습니다"),
    ],
)
def test_하중의_단계_칸이_단계와_맞는지_본다(load: dict[str, Any], message: str) -> None:
    with pytest.raises(ConditionError, match=r"^cases\[0\]\.loads\[0\]: .*" + message):
        parse(_case(load, load_steps=TWO_STEPS))


def test_시간별_배율은_음수도_받는다() -> None:
    # 음의 배율은 방향을 뒤집는다 — 하중 이력에서 쓴다(밀었다가 당기기).
    parse(_case({**PUSH, "time_table": [[0, 0], [1, 1], [2, -1]]}, load_steps=TWO_STEPS))


def test_정적이_아니면_단계_칸을_쓰지_않는다() -> None:
    modal = _case(**{"type": "modal", "load_steps": TWO_STEPS})
    with pytest.raises(
        ConditionError, match=r"해석 설정 ‘하중 단계’은\(는\) 정적 구조 해석에서만 지정합니다"
    ):
        parse(modal)


def test_v1_볼트_정적과_같은_뜻의_단계_둘이_저장된다() -> None:
    got = parse(BOLT_IN_STEPS)
    case = got.cases[0]
    assert [one.bolt_steps for one in case.loads] == [["load", "lock"], [], []]
    assert [one.active_steps for one in case.loads] == [[], [2], []]


# ── 곡선 — 정적 하중의 시간 · 단계 곡선 ──────────────────────────────────────


def _curve(name: str, x: str, points: list[list[Any]], **more: Any) -> dict[str, Any]:
    return {"name": name, "x": x, "points": points, **more}


def test_시간_곡선은_정적_하중의_시간별_배율로_풀린다() -> None:
    raw = _case({**PUSH, "curve": "램프"}, load_steps=TWO_STEPS)
    raw["curves"] = [_curve("램프", "time", [[0, 0], [1, 1], [2, "=끝배율"]])]
    parse(raw)
    out = resolve(raw, {"끝배율": 0.5}, cases=True)
    (load,) = out["cases"][0]["loads"]
    assert load["time_table"] == [[0, 0], [1, 1], [2, 0.5]]
    assert "curve" not in load and "curves" not in out


def test_단계_곡선은_단계_끝_시간으로_옮겨_시간_표로_낸다() -> None:
    raw = _case(
        {**PUSH, "curve": "단계별"},
        load_steps=[{"end_time": 2}, {"end_time": 5}],
    )
    raw["curves"] = [_curve("단계별", "step", [[0, 0], [1, 1], [1.5, 1], [2, 0.25]])]
    out = resolve(raw, {}, cases=True)
    (load,) = out["cases"][0]["loads"]
    assert load["time_table"] == [[0.0, 0], [2.0, 1], [3.5, 1], [5.0, 0.25]]
    assert step_to_time([[0, 0], [2, 1]], ["=끝", 5]) == [[0, 0], [2, 1]]


@pytest.mark.parametrize(
    ("curve", "message"),
    [
        (
            _curve("주파수", "frequency", [[10, 1], [100, 1]]),
            r"시간 곡선이나 단계 곡선만 쓸 수 있습니다",
        ),
        (
            _curve("계단", "time", [[0, 0], [2, 1]], interpolation="step"),
            r"선형 보간입니다\(곡선 ‘계단’: 계단\)",
        ),
        (
            _curve("짧음", "time", [[0, 0], [1, 1]]),
            r"끝 시간\(2 s\)에서 끝나야 합니다",
        ),
        (
            _curve("단계 모자람", "step", [[0, 0], [1, 1]]),
            r"단계 0에서 시작해 마지막 단계 2에서 끝나야 합니다",
        ),
        (_curve("단위", "time", [[0, 0], [2, 1]], unit="N"), r"단위는 없음\(배율\)입니다"),
    ],
)
def test_정적_하중의_곡선은_시간_뜻에_맞아야_한다(curve: dict[str, Any], message: str) -> None:
    raw = _case({**PUSH, "curve": curve["name"]}, load_steps=TWO_STEPS)
    raw["curves"] = [curve]
    with pytest.raises(ConditionError, match=message):
        parse(raw)


def test_곡선과_적용_단계는_함께_쓰지_않는다() -> None:
    raw = _case({**PUSH, "curve": "램프", "active_steps": [2]}, load_steps=TWO_STEPS)
    raw["curves"] = [_curve("램프", "time", [[0, 0], [2, 1]])]
    with pytest.raises(ConditionError, match=r"함께 쓸 수 없습니다"):
        parse(raw)


# ── 내보내기 — v1 길은 막고, v2 는 케이스 하나여도 v2 ───────────────────────


def test_단계를_쓰지_않으면_내보내기에_단계_칸이_없다() -> None:
    out = resolve(_case(PUSH), {})
    assert out["schema_version"] == 1
    assert not {"load_steps", "convergence", "outputs"} & set(out["analysis"])
    (load,) = out["loads"]
    assert not {"time_table", "active_steps", "bolt_steps"} & set(load)


def test_v1_으로_나가는_길에서는_까닭을_말하고_막는다() -> None:
    with pytest.raises(
        ConditionError,
        match=r"^케이스 ‘정적’의 해석 설정 ‘하중 단계’, 볼트 예압 ‘조임’의 "
        r"‘단계별 볼트 동작’, 힘 ‘옆 힘’의 ‘적용 단계’은\(는\) 해석 쪽\(SimEngBay\)이 "
        r"케이스가 있는 조건",
    ):
        resolve(BOLT_IN_STEPS, {})
    # 수렴 · 출력만 써도 v1 으로는 나가지 않는다.
    with pytest.raises(ConditionError, match=r"‘수렴 제어’"):
        resolve(_case(PUSH, convergence={"max_iterations": 30}), {})


def test_단계가_든_사슬은_저장에서_막는다() -> None:
    """단계를 쓴 케이스는 다른 케이스와 잇지 않는다 — 접기 전에 저장에서 막힌다."""
    raw = deepcopy(BOLT_IN_STEPS)
    raw["cases"].append(
        {
            "name": "모달",
            "depends_on": "정적",
            "analysis": {"type": "modal", "modes": 6},
            "constraints": [FIXED],
        }
    )
    with pytest.raises(ConditionError, match=r"^cases\[0\]\.analysis: 해석 설정 ‘하중 단계’"):
        parse(raw)


def test_v2_에서는_케이스가_하나여도_v2_로_낸다() -> None:
    out = resolve(BOLT_IN_STEPS, {}, cases=True)
    assert out["schema_version"] == 2
    (case,) = out["cases"]
    blank = {"initial": None, "minimum": None, "maximum": None}
    assert case["analysis"]["load_steps"] == [
        {"name": "예압", "end_time": 1, "substeps": blank},
        {"name": "외력", "end_time": 2, "substeps": blank},
    ]
    assert "convergence" not in case["analysis"] and "outputs" not in case["analysis"]
    bolt, push, gravity = case["loads"]
    assert bolt["bolt_steps"] == ["load", "lock"] and "active_steps" not in bolt
    assert push["active_steps"] == [2] and "bolt_steps" not in push
    assert not {"time_table", "active_steps", "bolt_steps"} & set(gravity)
    # 단계를 쓰지 않는 케이스 하나는 v2 스위치를 켜도 지금처럼 v1.
    assert resolve(_case(PUSH), {}, cases=True)["schema_version"] == 1


def test_식으로_적은_부단계는_정수로_풀린다() -> None:
    raw = _case(
        PUSH,
        load_steps=[{"end_time": "=끝", "substeps": {"initial": "=처음", "maximum": 100}}],
        convergence={"max_iterations": "=반복"},
        outputs={"at": {"count": "=횟수"}},
    )
    out = resolve(raw, {"끝": 2, "처음": 10, "반복": 30, "횟수": 4}, cases=True)
    analysis = out["cases"][0]["analysis"]
    assert analysis["load_steps"][0]["end_time"] == 2
    assert analysis["load_steps"][0]["substeps"]["initial"] == 10
    assert isinstance(analysis["load_steps"][0]["substeps"]["initial"], int)
    assert analysis["convergence"]["max_iterations"] == 30
    assert analysis["outputs"] == {
        "quantities": ["displacement", "stress", "strain", "reaction"],
        "at": {"count": 4},
    }
    with pytest.raises(ConditionError, match=r"정수여야 합니다"):
        resolve(raw, {"끝": 2, "처음": 7.5, "반복": 30, "횟수": 4}, cases=True)


# ── 능력표 — 결과를 바꾸는 칸은 막고, 수렴 · 출력은 알림 ──────────────────────


def _notes(raw: dict[str, Any], tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw = deepcopy(raw)
    raw["cases"][0]["target"] = {"solver": "calculix"}
    ((_, view),) = views(parse(raw))
    return notes(view, read(tables), "calculix")


def test_받는_쪽이_읽지_않는_결과를_바꾸는_칸은_막는다() -> None:
    raw = deepcopy(BOLT_IN_STEPS)
    raw["cases"][0]["target"] = {"solver": "calculix"}
    with pytest.raises(
        ConditionError,
        match=r"^cases\[0\]\.analysis: 대상 솔버 ‘calculix’은\(는\) ‘하중 단계’ 칸을 "
        r"아직 받지 않습니다\(해석 쪽 능력표\)\. 받지 않으면 해석 결과가 달라지므로",
    ):
        parse(raw, capabilities=read(RAW))
    got = _notes(BOLT_IN_STEPS, RAW)
    assert [(one["level"], one["where"]) for one in got if one["level"] == "warn"] == [
        ("warn", "해석 설정 ‘하중 단계’"),
        ("warn", "볼트 예압 ‘조임’"),
        ("warn", "힘 ‘옆 힘’"),
    ]


def test_받는_쪽이_단계_칸을_읽게_되면_막지_않는다() -> None:
    later = deepcopy(RAW)
    static = later[0]["analyses"]["static"]["fields"]
    static["analysis"] += ["load_steps", "convergence"]
    static["loads"] += ["time_table", "active_steps", "bolt_steps"]
    raw = deepcopy(BOLT_IN_STEPS)
    raw["cases"][0]["target"] = {"solver": "calculix"}
    parse(raw, capabilities=read(later))
    # 수렴 · 출력은 읽지 않아도 답이 같다 — 알림이다.
    output = _case(PUSH, load_steps=TWO_STEPS, outputs={"at": "all"})
    got = _notes(output, later)
    assert [(one["level"], one["where"]) for one in got] == [("info", "해석 설정 ‘출력 요청’")]


def test_곡선이_채운_시간별_배율도_능력표로_거른다() -> None:
    raw = _case({**PUSH, "curve": "램프"}, load_steps=TWO_STEPS)
    raw["curves"] = [_curve("램프", "time", [[0, 0], [2, 1]])]
    got = _notes(raw, RAW)
    assert any(
        one["where"] == "힘 ‘옆 힘’" and "‘시간별 배율’ 칸을" in one["text"] for one in got
    )


def test_화면이_비운_목록_칸은_빈_목록으로_읽는다() -> None:
    """화면은 종류를 바꿀 때 감춘 칸을 사양표의 기본값(없으면 null)으로 되돌린다 — 목록 칸의
    null 이 저장을 막으면 안 된다. 사양표에도 기본값 [] 를 싣는다."""
    raw = _case({**PUSH, "active_steps": None, "bolt_steps": None}, load_steps=None)
    (load,) = parse(raw).cases[0].loads
    assert (load.active_steps, load.bolt_steps) == ([], [])
    out = resolve(raw, {})
    assert out["schema_version"] == 1 and "load_steps" not in out["analysis"]
    from app.core.conditions import spec

    fields = spec()["groups"]["loads"]["fields"]
    assert (fields["active_steps"]["default"], fields["bolt_steps"]["default"]) == ([], [])


def test_대상_솔버를_비운_케이스의_단계_칸은_모든_솔버가_받아야_내보낸다() -> None:
    """받는 쪽이 솔버를 고르므로 결과를 바꾸는 칸은 복사본의 모든 솔버가 읽어야 한다 — 받는
    쪽은 모르는 칸을 말없이 버린다. 대상 솔버를 지정한 케이스는 저장할 때 그 솔버의 표로
    거른다."""
    from app.core.conditions import check_untargeted

    raw = _case(PUSH, load_steps=TWO_STEPS)
    with pytest.raises(
        ConditionError,
        match=r"^cases\[0\]\.analysis: 대상 솔버 ‘calculix’은\(는\) ‘하중 단계’ 칸을 "
        r"아직 받지 않습니다\(해석 쪽 능력표\)\. 케이스 ‘정적’은\(는\) 대상 솔버를 비웠으므로",
    ):
        check_untargeted(parse(raw), read(RAW))
    calculix_only = deepcopy(RAW)
    calculix_only[0]["analyses"]["static"]["fields"]["analysis"].append("load_steps")
    with pytest.raises(ConditionError, match=r"대상 솔버 ‘ansys’"):
        check_untargeted(parse(raw), read(calculix_only))
    both = deepcopy(calculix_only)
    both[1]["analyses"]["static"]["fields"]["analysis"].append("load_steps")
    check_untargeted(parse(raw), read(both))
    # 대상 솔버를 지정한 케이스는 여기서 보지 않는다.
    targeted = deepcopy(raw)
    targeted["cases"][0]["target"] = {"solver": "calculix"}
    check_untargeted(parse(targeted), read(RAW))


def test_하중_단계는_다른_케이스와_잇지_않은_정적_케이스에서만_쓴다() -> None:
    """받는 쪽 첫 판은 사슬 안의 어느 케이스든(앞 케이스 자신 포함) ② 칸을 쓰면 작업을 만들
    때 막는다(SimEngBay, 2026-11-28) — 저장에서 먼저 막는다. 수렴 · 출력은 결과를 바꾸지 않으니
    막지 않는다."""
    raw = _case(PUSH)
    follower = {
        "name": "뒤",
        "depends_on": "정적",
        "analysis": {"type": "static", "load_steps": TWO_STEPS},
        "constraints": [FIXED],
        "loads": [PUSH],
    }
    raw["cases"].append(follower)
    with pytest.raises(
        ConditionError,
        match=r"^cases\[1\]\.analysis: 해석 설정 ‘하중 단계’은\(는\) 다른 케이스와 잇지 않은 "
        r"정적 케이스에서만",
    ):
        parse(raw)
    timed = deepcopy(raw)
    timed["cases"][1]["analysis"] = {"type": "static"}
    timed["cases"][1]["loads"] = [{**PUSH, "time_table": [[0, 0], [1, 1]]}]
    with pytest.raises(
        ConditionError, match=r"^cases\[1\]\.loads\[0\]: 힘 ‘옆 힘’의 ‘시간별 배율’"
    ):
        parse(timed)
    # 뒤 케이스를 거느린 앞 케이스도 막는다.
    leader = deepcopy(raw)
    leader["cases"][0]["analysis"] = {"type": "static", "load_steps": TWO_STEPS}
    leader["cases"][1]["analysis"] = {"type": "static"}
    with pytest.raises(
        ConditionError, match=r"^cases\[0\]\.analysis: .*케이스 ‘정적’을\(를\)"
    ):
        parse(leader)
    quiet = deepcopy(raw)
    quiet["cases"][1]["analysis"] = {"type": "static", "convergence": {"max_iterations": 30}}
    parse(quiet)
    # 잇지 않은 케이스는 쓴다 — 같은 조건 안의 다른 사슬과도 상관없다.
    alone = deepcopy(raw)
    alone["cases"][1] = {**follower, "name": "따로", "depends_on": ""}
    parse(alone)
