"""받는 쪽 능력표 — 관리자가 받아 두고(복사본), 저장 · DOE 생성 · 준비 점검이 그것으로 거른다.

SimEngBay 는 `httpx.MockTransport` 로 흉내 낸다 — 응답은 그쪽이 보낸 실제 견본이다
(`tests/fixtures/simengbay/capabilities.json`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.server import capabilities_store
from app.modules.server.models import ServerSetting
from app.shared.clients import simengbay
from tests.api.conftest import Signed

FIXTURE = Path(__file__).parents[1] / "fixtures" / "simengbay" / "capabilities.json"
TABLES: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
TOKEN = "simengbay_pat_test0123"

BOX: dict[str, Any] = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 40, "height": 30}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 10},
    ]
}
GROUPS: list[dict[str, Any]] = [
    {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}},
    {"name": "윗면", "entity": "face", "select": {"what": "faces", "role": "top"}},
]
PUSH: dict[str, Any] = {
    "name": "옆 힘",
    "type": "force",
    "on": "윗면",
    "magnitude": 500,
    "direction": [1, 0, 0],
}


def _random(solver: str, *loads: dict[str, Any]) -> dict[str, Any]:
    """랜덤 진동 케이스 하나 — Ansys 는 가속도 PSD 밖의 하중을 받지 않는다."""
    return {
        "schema_version": 2,
        "named_selections": GROUPS,
        "cases": [
            {
                "name": "흔들기",
                "target": {"solver": solver},
                "analysis": {"type": "random", "damping_ratio": 0.02},
                "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
                "loads": [
                    {
                        "name": "흔듦",
                        "type": "psd_acceleration",
                        "direction": [0, 0, 1],
                        "psd_table": [[20, 0.04], [2000, 0.04]],
                    },
                    *loads,
                ],
            }
        ],
    }


Answer = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def no_copy(db: Session) -> Iterator[None]:
    """시험 DB 는 시험끼리 함께 쓴다 — 복사본 줄을 앞뒤로 지운다(다른 시험의 저장을 거르지
    않게)."""

    def clear() -> None:
        row = db.get(ServerSetting, capabilities_store.KEY)
        if row is not None:
            db.delete(row)
            db.commit()

    clear()
    yield
    db.expire_all()
    clear()


@pytest.fixture
def seb(monkeypatch: pytest.MonkeyPatch) -> Callable[[Answer], list[httpx.Request]]:
    """SimEngBay 를 흉내 낸다 — 받은 요청을 돌려준다(머리 · 경로를 본다)."""

    def use(answer: Answer) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return answer(request)

        monkeypatch.setattr(get_settings(), "simengbay_base_url", "http://seb.test/simengbay/")
        monkeypatch.setattr(get_settings(), "simengbay_token", TOKEN)
        real = simengbay._client

        def client() -> httpx.Client:
            # 실제 클라이언트(바탕 주소 · 머리) 그대로, 전송만 갈아 끼운다.
            one = real()
            one._transport = httpx.MockTransport(handler)
            return one

        monkeypatch.setattr(simengbay, "_client", client)
        return seen

    return use


def _refresh(client: TestClient, admin: Signed) -> Any:
    return client.post("/api/server/capabilities/refresh", headers=admin.headers)


def test_관리자가_받아_두면_복사본이_생긴다(
    client: TestClient,
    admin: Signed,
    member: Signed,
    seb: Callable[[Answer], list[httpx.Request]],
) -> None:
    before = client.get("/api/server/capabilities", headers=admin.headers).json()
    assert before["tables"] is None and before["fetched_at"] is None
    seen = seb(lambda _: httpx.Response(200, json=TABLES))
    got = _refresh(client, admin)
    assert got.status_code == 200, got.text
    body = got.json()
    assert [one["solver"] for one in body["tables"]] == ["calculix", "ansys"]
    assert body["tables"] == TABLES, "받은 그대로 둔다"
    assert body["source"] == "http://seb.test/simengbay" and body["fetched_at"]
    assert TOKEN not in got.text, "토큰은 화면으로 나가지 않는다"
    # 접두어 아래의 경로, 읽기 범위 PAT.
    (request,) = seen
    assert str(request.url) == "http://seb.test/simengbay/api/simulations/capabilities"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    # 사용자는 복사본(솔버 목록)을 읽는다 — 갱신은 관리자만.
    mine = client.get("/api/cad/conditions/capabilities", headers=member.headers).json()
    assert [one["solver"] for one in mine["tables"]] == ["calculix", "ansys"]
    assert _refresh(client, member).status_code == 403
    assert client.get("/api/server/capabilities", headers=member.headers).status_code == 403


@pytest.mark.parametrize(
    ("status", "error", "message"),
    [
        (401, "SEB-AUTH-0101", r"토큰이 맞지 않거나 만료 또는 폐기되었습니다.*계정의 상태"),
        (401, "SEB-AUTH-0100", r"Authorization 헤더를 전달하는지"),
        (403, "SEB-AUTH-0104", r"읽기 범위\(read\)가 없습니다"),
        (404, "", r"접두어\(예: /simengbay\)까지"),
        (500, "SEB-CORE-0001", r"HTTP 500, SEB-CORE-0001"),
    ],
)
def test_못_받으면_까닭을_말하고_있던_복사본을_둔다(
    client: TestClient,
    admin: Signed,
    seb: Callable[[Answer], list[httpx.Request]],
    status: int,
    error: str,
    message: str,
) -> None:
    seb(lambda _: httpx.Response(200, json=TABLES))
    assert _refresh(client, admin).status_code == 200
    envelope = {"error": {"code": error, "message": "…", "request_id": "r", "details": {}}}
    seb(lambda _: httpx.Response(status, json=envelope))
    failed = _refresh(client, admin)
    assert failed.status_code == 502
    assert failed.json()["error"]["code"].endswith("SERVER-0003")
    assert re.search(message, failed.json()["error"]["message"]), failed.text
    kept = client.get("/api/server/capabilities", headers=admin.headers).json()
    assert kept["tables"] == TABLES


def test_모양이_틀린_표는_두지_않는다(
    client: TestClient, admin: Signed, seb: Callable[[Answer], list[httpx.Request]]
) -> None:
    seb(lambda _: httpx.Response(200, json={"solver": "calculix"}))
    failed = _refresh(client, admin)
    assert failed.status_code == 502
    assert "약속한 모양이 아닙니다: 능력표는 배열이어야" in failed.json()["error"]["message"]
    assert (
        client.get("/api/server/capabilities", headers=admin.headers).json()["tables"] is None
    )


def test_설정이_비면_무엇이_비었는지_말한다(
    client: TestClient, admin: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "simengbay_base_url", "http://seb.test")
    monkeypatch.setattr(get_settings(), "simengbay_token", "")
    status = client.get("/api/server/capabilities", headers=admin.headers).json()
    assert not status["configured"] and "SIMENGBAY_TOKEN(토큰)" in status["missing"]
    failed = _refresh(client, admin)
    assert failed.status_code == 502 and "SIMENGBAY_TOKEN(토큰)" in failed.text


def test_저장과_DOE_생성은_대상_솔버의_표로_거른다(
    client: TestClient,
    admin: Signed,
    member: Signed,
    seb: Callable[[Answer], list[httpx.Request]],
) -> None:
    made = client.post(
        "/api/works", json={"name": "능력표", "recipe": BOX}, headers=member.headers
    )
    work = made.json()
    put = f"/api/works/{work['id']}/versions/1/conditions"
    # 복사본이 없으면 거르지 않는다 — 능력표가 생기기 전과 같다.
    assert (
        client.put(put, json={"conditions": _random("ansys", PUSH)}, headers=member.headers)
    ).status_code == 200

    seb(lambda _: httpx.Response(200, json=TABLES))
    assert _refresh(client, admin).status_code == 200
    refused = client.put(
        put, json={"conditions": _random("ansys", PUSH)}, headers=member.headers
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["message"].startswith(
        "cases[0].loads[1]: 힘 ‘옆 힘’은(는) 대상 솔버 ‘ansys’의 랜덤 진동(PSD) 해석에서 받지 "
        "않습니다"
    )
    # CalculiX 는 받는다 · 솔버를 비우거나 모르는 솔버면 거르지 않는다.
    for solver in ("calculix", "", "abaqus"):
        ok = client.put(
            put, json={"conditions": _random(solver, PUSH)}, headers=member.headers
        )
        assert ok.status_code == 200, (solver, ok.text)

    doe = client.post(
        "/api/doe",
        json={
            "name": "능력표로 막힘",
            "recipe": {**BOX, "params": {"두께": 10}},
            "conditions": _random("ansys", PUSH),
            "factors": [{"name": "두께", "mode": "list", "values": [10]}],
        },
        headers=member.headers,
    )
    assert doe.status_code == 400
    assert "대상 솔버 ‘ansys’의 랜덤 진동(PSD) 해석에서 받지 않습니다" in doe.text


def test_준비_점검은_고치는_케이스의_솔버로_알린다(
    client: TestClient,
    admin: Signed,
    member: Signed,
    seb: Callable[[Answer], list[httpx.Request]],
) -> None:
    one = _random("ansys", PUSH)
    case = one["cases"][0]
    view = {
        "named_selections": GROUPS,
        **{key: case[key] for key in ("analysis", "constraints", "loads")},
    }

    def notes(solver: str) -> list[dict[str, Any]]:
        got = client.post(
            "/api/cad/conditions/notes",
            json={"recipe": BOX, "conditions": view, "solver": solver},
            headers=member.headers,
        )
        assert got.status_code == 200, got.text
        return list(got.json()["items"])

    # 솔버가 비면 지금과 같다(식 알림만).
    assert notes("") == []
    (never,) = notes("ansys")
    assert "능력표를 아직 받지 않아" in never["text"]

    seb(lambda _: httpx.Response(200, json=TABLES))
    assert _refresh(client, admin).status_code == 200
    got = notes("ansys")
    assert got[0]["level"] == "warn" and got[0]["where"] == "힘 ‘옆 힘’"
    assert got[0]["open"] == {"kind": "item", "group": "loads", "index": 1}
    assert any(one["level"] == "info" and "X · Y · Z 축만" in one["text"] for one in got)
    # 모양이 아직 틀린 한 벌(고치는 중)이면 능력표 알림을 건너뛴다.
    view["loads"] = [{"name": "", "type": "모르는 하중"}]
    assert notes("ansys") == []


@pytest.mark.parametrize(
    ("switch", "contracts", "v2"),
    [
        ("auto", None, False),
        ("auto", ([1], [1]), False),
        ("auto", ([1, 2], [1]), False),
        ("auto", ([1, 2], [1, 2]), True),
        ("off", ([1, 2], [1, 2]), False),
        ("on", None, True),
        (True, None, True),
    ],
)
def test_v2_로_내보낼지는_이_설치의_능력표가_판_2_를_받는지로_가른다(
    client: TestClient,
    admin: Signed,
    db: Session,
    seb: Callable[[Answer], list[httpx.Request]],
    monkeypatch: pytest.MonkeyPatch,
    switch: object,
    contracts: tuple[list[int], list[int]] | None,
    v2: bool,
) -> None:
    """SimEngBay 의 판이 나와도 운영에 올리는 것은 운영자 일이라 시차가 난다 — 판 번호가 아니라
    그 설치가 실제로 받는 판(능력표의 contract)으로 가른다. 스위치는 강제로 끄고 켜는 데만."""
    from app.modules.doe.services import conditions_v2

    monkeypatch.setattr(get_settings(), "doe_conditions_v2", switch)
    if contracts is not None:
        tables = [dict(one) for one in TABLES]
        for one, contract in zip(tables, contracts, strict=True):
            one["contract"] = contract
        seb(lambda _: httpx.Response(200, json=tables))
        assert _refresh(client, admin).status_code == 200
    db.expire_all()
    assert conditions_v2(db) is v2


def test_v2_로_낼_때_대상_솔버를_비운_케이스의_단계_칸은_모든_솔버가_받아야_한다(
    client: TestClient,
    admin: Signed,
    member: Signed,
    seb: Callable[[Answer], list[httpx.Request]],
) -> None:
    tables = [{**one, "contract": [1, 2]} for one in TABLES]
    seb(lambda _: httpx.Response(200, json=tables))
    assert _refresh(client, admin).status_code == 200
    conditions = {
        "schema_version": 2,
        "named_selections": GROUPS,
        "cases": [
            {
                "name": "단계",
                "analysis": {
                    "type": "static",
                    "load_steps": [{"name": "하나"}, {"name": "둘"}],
                },
                "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
                "loads": [{**PUSH, "active_steps": [2]}],
            }
        ],
    }
    doe = client.post(
        "/api/doe",
        json={
            "name": "솔버 비운 단계",
            "recipe": {**BOX, "params": {"두께": 10}},
            "conditions": conditions,
            "factors": [{"name": "두께", "mode": "list", "values": [10]}],
        },
        headers=member.headers,
    )
    assert doe.status_code == 400
    message = doe.json()["error"]["message"]
    assert "‘하중 단계’ 칸을 아직 받지 않습니다" in message
    assert "케이스 ‘단계’은(는) 대상 솔버를 비웠으므로 해석 쪽의 모든 솔버가" in message
