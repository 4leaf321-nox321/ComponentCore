"""받는 쪽 능력표로 거르기 — 막는 것은 해석 종류 · 항목 종류뿐, 칸과 note 는 알림(설계 5장).

견본은 SimEngBay 가 보낸 `GET /api/simulations/capabilities` 의 실제 응답이다
(`tests/fixtures/simengbay/capabilities.json` — v0.36.0 에서 연 그대로, 바뀐 것은
`receiver_version` 하나). 대상 솔버가 정해진 케이스(v2)만 거른다.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.core.conditions import ConditionError, parse
from app.core.conditions import capabilities as caps
from app.core.conditions.capabilities import CapabilityError, Table, notes, read
from app.core.conditions.model import views

FIXTURE = Path(__file__).parents[1] / "fixtures" / "simengbay" / "capabilities.json"
RAW: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
TABLES = read(RAW)

SHARED: dict[str, Any] = {
    "units": {"system": "si"},
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
SHAKE: dict[str, Any] = {
    "name": "흔듦",
    "type": "psd_acceleration",
    "direction": [0, 0, 1],
    "psd_table": [[20, 0.04], [2000, 0.04]],
}
BOLT: dict[str, Any] = {
    "name": "조임",
    "type": "bolt_pretension",
    "on": "볼트 면",
    "preload": 1000,
    "unit": "N",
}


def _random(solver: str, *loads: dict[str, Any]) -> dict[str, Any]:
    case = {
        "name": "흔들기",
        "target": {"solver": solver},
        "analysis": {"type": "random", "damping_ratio": 0.02},
        "constraints": [FIXED],
        "loads": [SHAKE, *loads],
    }
    return deepcopy({**SHARED, "schema_version": 2, "cases": [case]})


def _static(solver: str, *loads: dict[str, Any], **analysis: Any) -> dict[str, Any]:
    case = {
        "name": "정적",
        "target": {"solver": solver},
        "analysis": {"type": "static", **analysis},
        "constraints": [FIXED],
        "loads": list(loads),
    }
    return deepcopy({**SHARED, "schema_version": 2, "cases": [case]})


def _notes(raw: dict[str, Any], tables: list[Table] | None = TABLES) -> list[dict[str, Any]]:
    conditions = parse(raw)
    ((_, view),) = views(conditions)
    return notes(view, tables, conditions.cases[0].target.solver)


# ── 견본 ──────────────────────────────────────────────────────────────────────


def test_견본은_합의한_응답_그대로다() -> None:
    # 합의할 때(v0.35.0 개발 트리)의 지문 — 연 판에서 바뀐 것은 받는 쪽 판 번호 하나다.
    agreed = deepcopy(RAW)
    for one in agreed:
        assert one["receiver_version"] == "v0.36.0"
        one["receiver_version"] = "v0.35.0"
    dump = json.dumps(agreed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(dump.encode()).hexdigest() == (
        "4f179012929fca445a70a444a074cda16fac793ce79e97902b0fc23cac4a5790"
    )
    assert [(one.solver, one.version) for one in TABLES] == [
        ("calculix", None),
        ("ansys", "2025 R2"),
    ]
    assert all(
        set(one.analyses) == {"modal", "static", "harmonic", "random"} for one in TABLES
    )


def test_항목은_이름이거나_이름과_안내다() -> None:
    static = caps.table_for(TABLES, "calculix")
    assert static is not None
    loads = static.analyses["static"].loads or []
    assert loads[0].name == "pressure" and loads[0].note == ""
    bolt = next(one for one in loads if one.name == "bolt_pretension")
    assert bolt.note


def test_모르는_키는_버리고_읽는다() -> None:
    # v2 판에서 붙을 것(`follows` · `contract` [1, 2])과 아무 키나 더해도 깨지지 않는다.
    more = deepcopy(RAW)
    more[0]["contract"] = [1, 2]
    more[0]["somewhere"] = {"new": True}
    more[0]["analyses"]["modal"]["follows"] = ["static"]
    more[0]["analyses"]["modal"]["loads"][0]["severity"] = "info"
    got = read(more)
    assert got[0].contract == [1, 2]
    assert got[0].analyses["modal"].loads == TABLES[0].analyses["modal"].loads


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"solver": "calculix"}, r"배열이어야"),
        ([{"receiver": "simengbay"}], r"^\[0\]\.solver: "),
        (
            [{"solver": "x", "analyses": {"modal": {"loads": [{"note": "이름 없음"}]}}}],
            r"^\[0\]",
        ),
        ([{"solver": "calculix"}, {"solver": "calculix"}], r"calculix의 능력표가 둘 이상"),
    ],
)
def test_모양이_틀린_표는_자리를_짚어_막는다(raw: Any, message: str) -> None:
    with pytest.raises(CapabilityError, match=message):
        read(raw)


# ── 막는 것 — 해석 종류 · 항목 종류 ─────────────────────────────────────────────


def test_표에_없는_항목_종류는_저장할_때_막는다() -> None:
    # Ansys 랜덤 진동은 가속도 PSD 만 받는다(선응력이 없다) — 힘은 받는 쪽이 거절한다.
    with pytest.raises(
        ConditionError,
        match=r"^cases\[0\]\.loads\[1\]: 힘 ‘옆 힘’은\(는\) 대상 솔버 ‘ansys’의 "
        r"랜덤 진동\(PSD\) 해석에서 받지 않습니다\(해석 쪽 능력표\)\. 대상 솔버를 바꾸거나",
    ):
        parse(_random("ansys", PUSH), capabilities=TABLES)
    # CalculiX 는 받는다(선응력의 앞 정적에 걸 때 — note).
    parse(_random("calculix", PUSH), capabilities=TABLES)


def test_표에_없는_해석_종류는_막는다() -> None:
    thermal = {
        **SHARED,
        "schema_version": 2,
        "cases": [
            {"name": "열", "target": {"solver": "calculix"}, "analysis": {"type": "thermal"}}
        ],
    }
    parse(thermal)
    with pytest.raises(
        ConditionError,
        match=r"^cases\[0\]\.analysis: 대상 솔버 ‘calculix’은\(는\) 열 해석을 받지 않습니다",
    ):
        parse(thermal, capabilities=TABLES)


def test_공유_칸인_접촉은_어느_케이스에서_걸렸는지_말한다() -> None:
    narrow = deepcopy(RAW)
    narrow[0]["analyses"]["static"]["contacts"] = ["bonded"]
    raw = _static("calculix")
    raw["contacts"] = [
        {"name": "미끄럼", "type": "frictionless", "source": "윗면", "target": "바닥"}
    ]
    with pytest.raises(
        ConditionError,
        match=r"^contacts\[0\]: 케이스 ‘정적’에서 마찰 없음 ‘미끄럼’은\(는\) "
        r"대상 솔버 ‘calculix’의",
    ):
        parse(raw, capabilities=read(narrow))


@pytest.mark.parametrize(
    "raw",
    [
        # 대상 솔버가 비면 거르지 않는다 — 받는 쪽이 고른다.
        _random("", PUSH),
        # 복사본에 없는 솔버는 막지 않는다.
        _random("abaqus", PUSH),
        # v1 조건은 거르지 않는다(대상 솔버가 없다).
        {
            **SHARED,
            "analysis": {"type": "thermal"},
        },
    ],
)
def test_대상_솔버가_없거나_모르면_거르지_않는다(raw: dict[str, Any]) -> None:
    parse(raw, capabilities=TABLES)


def test_복사본이_없으면_거르지_않는다() -> None:
    parse(_random("ansys", PUSH))
    parse(_random("ansys", PUSH), capabilities=None)


# ── 알림 — 읽지 않는 칸 · 안내 ───────────────────────────────────────────────


def test_읽지_않는_칸에_기본값이_아닌_값이면_알린다() -> None:
    # 정적의 `steps` 는 받는 쪽이 읽지 않는다 — 막지 않고 알린다(SimEngBay, 2026-11-27).
    raw = _static("calculix", PUSH, steps=2)
    parse(raw, capabilities=TABLES)
    got = _notes(raw)
    assert {
        "level": "info",
        "where": "해석 설정 ‘하중 단계 수’",
        "text": "대상 솔버 ‘calculix’은(는) 이 칸을 읽지 않습니다(해석 쪽 능력표). 적은 값은 "
        "해석에 반영되지 않습니다.",
    } in got
    # 기본값이면 말하지 않는다 — 솔버(`program_controlled`) · 단계 1.
    assert _notes(_static("calculix", PUSH)) == []


def test_하중의_읽지_않는_칸은_항목마다_모아_알린다() -> None:
    narrow = deepcopy(RAW)
    narrow[1]["analyses"]["static"]["fields"]["loads"].remove("direction")
    got = _notes(_static("ansys", PUSH), read(narrow))
    assert got == [
        {
            "level": "info",
            "where": "힘 ‘옆 힘’",
            "text": "대상 솔버 ‘ansys’은(는) ‘방향’ 칸을 읽지 않습니다(해석 쪽 능력표). 적은 "
            "값은 해석에 반영되지 않습니다.",
            "open": {"kind": "item", "group": "loads", "index": 0},
        }
    ]


def test_하중의_곡선은_CompCore_쪽_칸이라_거르지_않는다() -> None:
    # 곡선은 내보낼 때 하중 안의 표로 풀려 받는 쪽에 가지 않는다.
    raw = _random("ansys")
    shake = raw["cases"][0]["loads"][0]
    del shake["psd_table"]
    shake["curve"] = "규격"
    raw["curves"] = [
        {
            "name": "규격",
            "x": "frequency",
            "unit": "g^2/Hz",
            "interpolation": "loglog",
            "points": [[20, 0.04], [2000, 0.04]],
        }
    ]
    # 남는 것은 그 종류의 안내(「X · Y · Z 축만」) 하나 — 읽지 않는 칸 알림이 없다.
    (only,) = _notes(raw)
    assert only["text"].startswith("대상 솔버 ‘ansys’ 안내: ")


def test_안내가_달린_항목은_종류마다_한_줄로_알린다() -> None:
    second = {**BOLT, "name": "둘째 조임"}
    got = _notes(_static("calculix", BOLT, second))
    note = next(one for one in RAW[0]["analyses"]["static"]["loads"] if isinstance(one, dict))
    assert got == [
        {
            "level": "info",
            "where": "볼트 예압 ‘조임’, ‘둘째 조임’",
            "text": f"대상 솔버 ‘calculix’ 안내: {note['note']}",
            "open": {"kind": "item", "group": "loads", "index": 0},
        }
    ]


def test_막을_것은_준비_점검에_경고로_먼저_보인다() -> None:
    got = _notes(_random("ansys", PUSH))
    assert got[0]["level"] == "warn"
    assert got[0]["where"] == "힘 ‘옆 힘’"
    assert got[0]["open"] == {"kind": "item", "group": "loads", "index": 1}


def test_솔버가_비면_알림이_없고_표가_없으면_확인하지_않았다고_말한다() -> None:
    assert _notes(_random("", PUSH)) == []
    (unknown,) = _notes(_random("abaqus", PUSH))
    assert unknown["level"] == "info"
    assert "‘abaqus’이(가) 없어 받는 항목을 확인하지 않았습니다" in unknown["text"]
    (never,) = _notes(_random("ansys", PUSH), None)
    assert "능력표를 아직 받지 않아" in never["text"]


# ── SimEngBay v0.37.0 — 판 2 를 받는 첫 판 ───────────────────────────────────────


def _fingerprint(tables: list[dict[str, Any]]) -> str:
    dump = json.dumps(tables, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(dump.encode()).hexdigest()


def _bare(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """받는 **종류**가 바뀌었나는 판 칸을 빼고 잰다 — 솔버의 판(`version` — 운영의 ccx -v ·
    ANSYS_VERSION)과 받는 쪽의 판(`receiver_version` — 패치 판만 올라가도 바뀐다)은 받는 것이
    같아도 달라진다(SimEngBay, 2026-11-28)."""
    return [
        {k: v for k, v in one.items() if k not in ("version", "receiver_version")}
        for one in tables
    ]


#: v0.37.0 태그(97698ea)의 코드에서 뽑은 응답(SimEngBay, 2026-11-27). v0.36.0 견본과 다른 것은
#: `contract` [1, 2] · `receiver_version` · 해석마다 `follows` · note 문구다. 칸 · 종류는 같다.
V037: list[dict[str, Any]] = json.loads(
    (FIXTURE.parent / "capabilities_v037.json").read_text(encoding="utf-8")
)


def test_v037_견본은_받은_그대로다() -> None:
    assert (
        _fingerprint(V037)
        == "b68d2f8b203844dc28d78d74900a49efde66816fab15e435ec397be6999cf86f"
    )
    assert (
        _fingerprint(_bare(V037))
        == "ab26c097929f3e1a202e2e2621721b1e05390dc814b923419b3adb034f85c0fd"
    )
    tables = read(V037)
    assert [(one.solver, one.receiver_version, one.contract) for one in tables] == [
        ("calculix", "v0.37.0", [1, 2]),
        ("ansys", "v0.37.0", [1, 2]),
    ]
    # `follows` 는 아직 읽지 않는다 — 버리고 읽어도 나머지가 v0.36.0 과 같은 꼴이다.
    for new, old in zip(tables, TABLES, strict=True):
        assert set(new.analyses) == set(old.analyses)
        for kind in new.analyses:
            mine, theirs = new.analyses[kind], old.analyses[kind]
            for group in ("constraints", "loads", "contacts", "initial", "materials"):
                names = [one.name for one in mine.listed(group) or []]
                assert names == [one.name for one in theirs.listed(group) or []], (kind, group)
            assert {k: [one.name for one in v] for k, v in mine.fields.items()} == {
                k: [one.name for one in v] for k, v in theirs.fields.items()
            }


def test_v037_은_사슬은_받고_단계_칸과_소성은_아직_막는다() -> None:
    tables = read(V037)
    assert all(2 in one.contract for one in tables)
    steps = deepcopy(_static("calculix", PUSH))
    steps["cases"][0]["analysis"]["load_steps"] = [{"name": "하나"}, {"name": "둘"}]
    with pytest.raises(ConditionError, match=r"‘하중 단계’ 칸을 아직 받지 않습니다"):
        parse(steps, capabilities=tables)
    # 단계 칸이 없는 정적은 그대로 저장된다.
    parse(_static("calculix", PUSH), capabilities=tables)


# ── SimEngBay v0.38.0 — ② 하중 단계 · 소성을 받는 판 ────────────────────────────────

#: v0.38.0 태그(4c1532c)의 코드에서 뽑은 응답(SimEngBay, 2026-11-28). v0.37.0 견본과 다른 것은
#: 정적의 단계 칸 넷(`load_steps` · `time_table` · `active_steps` · `bolt_steps`), 정적의 소성
#: 재료 둘, note 둘(CalculiX 모멘트 · 두 솔버의 볼트 예압), `receiver_version` 이다.
V038: list[dict[str, Any]] = json.loads(
    (FIXTURE.parent / "capabilities_v038.json").read_text(encoding="utf-8")
)
STAGED_BOLT: dict[str, Any] = {**BOLT, "bolt_steps": ["load", "lock"]}
STAGED_PUSH: dict[str, Any] = {**PUSH, "active_steps": [2]}
TWO_STEPS: list[dict[str, Any]] = [{"name": "예압"}, {"name": "외력"}]


def test_v038_견본은_받은_그대로다() -> None:
    assert (
        _fingerprint(V038)
        == "a02101bcc1b8f61220649d84a9a60e329af1ed0ef40629902921ac87d762e92f"
    )
    # 패치 판(v0.38.1)으로 다시 올라가도 받는 종류가 같으면 이 지문은 그대로다. 후보
    # (6a95e4b6…)와 다른 것은 볼트 예압 note 의 문구 하나다(‘하중 단계’ 를 감쌌다).
    assert (
        _fingerprint(_bare(V038))
        == "1e7b5df974799970b6305b358e9227f42bb2162a3cbb0efcd5bd97058044a4d9"
    )
    tables = read(V038)
    assert [
        (one.solver, one.version, one.receiver_version, one.contract) for one in tables
    ] == [
        ("calculix", None, "v0.38.0", [1, 2]),
        ("ansys", "2025 R2", "v0.38.0", [1, 2]),
    ]
    for table in tables:
        static = table.analyses["static"]
        assert "load_steps" in [one.name for one in static.fields["analysis"]]
        assert {"time_table", "active_steps", "bolt_steps"} <= {
            one.name for one in static.fields["loads"]
        }
        materials = [one.name for one in static.listed("materials") or []]
        assert {"bilinear_isotropic", "multilinear_isotropic"} <= set(materials)
        # 모드 해석 쪽은 그대로 탄성만 — 소성 재료는 알림을 달고 탄성 값으로 푼다.
        assert "multilinear_isotropic" not in [
            one.name for one in table.analyses["modal"].listed("materials") or []
        ]


def test_v038_은_단계_칸과_소성을_막지_않는다() -> None:
    tables = read(V038)
    for solver in ("calculix", "ansys"):
        raw = _static(solver, STAGED_BOLT, STAGED_PUSH, load_steps=TWO_STEPS)
        raw["materials"][0] |= {
            "model": "multilinear_isotropic",
            "plastic": {"table": [[0, 250], [0.01, 270], [0.05, 300]]},
        }
        parse(raw, capabilities=tables)
        got = _notes(raw, tables)
        assert [one for one in got if one["level"] == "warn"] == [], solver
        # 볼트 예압의 안내는 바뀐 문구로 — 단계를 나눴을 때 어떻게 거는지 말한다.
        (bolt,) = [one for one in got if one["where"] == "볼트 예압 ‘조임’"]
        assert "‘하중 단계’를 나누면 첫 단계에서 조이고" in bolt["text"], solver
    # 대상 솔버를 비운 케이스도 두 솔버가 다 읽으므로 내보낸다.
    from app.core.conditions import check_untargeted

    untargeted = _static("", STAGED_BOLT, STAGED_PUSH, load_steps=TWO_STEPS)
    check_untargeted(parse(untargeted), tables)
    # 다른 케이스와 잇지 않은 정적에서만 쓰는 것은 받는 쪽 판과 상관없이 그대로다.
    chained = _static("calculix", PUSH)
    chained["cases"].append(
        {
            "name": "뒤",
            "depends_on": "정적",
            "target": {"solver": "calculix"},
            "analysis": {"type": "static", "load_steps": TWO_STEPS},
            "constraints": [FIXED],
            "loads": [STAGED_PUSH],
        }
    )
    with pytest.raises(ConditionError, match=r"다른 케이스와 잇지 않은 정적 케이스에서만"):
        parse(chained, capabilities=tables)


def test_v038_의_calculix_모멘트는_큰_회전을_알린다() -> None:
    moment = {
        "name": "끝 모멘트",
        "type": "moment",
        "on": "윗면",
        "magnitude": 10,
        "direction": [0, 1, 0],
    }
    tables = read(V038)
    got = _notes(_static("calculix", moment, large_deflection=True), tables)
    assert any("약 40° 넘게 돌면" in one["text"] for one in got if one["level"] == "info")
    assert not any("40°" in one["text"] for one in _notes(_static("ansys", moment), tables))
