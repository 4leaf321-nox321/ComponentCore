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
