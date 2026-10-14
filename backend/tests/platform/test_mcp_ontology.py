"""기준정보(온톨로지) MCP 도구를 **진짜 앱에 붙여** 본다 — AI 가 밟는 루프 그대로(ADR 0008).

도구는 `mcp_server/ontology.py`(SP 에서 옮긴 것)와 `ontology_links.py`(CompCore 의 것)에 있다.
`tests/api/test_mcp_tools.py` 가 불러 둔 서버를 쓰고, 도구가 부르는 httpx 를 이 프로세스 안의
앱(ASGI)으로 돌린다 — 라우터 · 권한 · 검증이 통째로 돈다. 데이터 작업은 워커를 이 프로세스에서
돌린다(`work_until`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app as fastapi_app
from app.modules.accounts.models import User
from app.modules.parts.models import Part
from tests.api.test_mcp_tools import Bot
from tests.api.test_mcp_tools import server as mcp_server
from tests.platform.conftest import Signed, work_until

#: 서버가 불러 둔 옆 파일들 — 옮긴 도구(`ontology`)와 CompCore 의 칸 도구(`ontology_links`).
tools = mcp_server.ontology
links = mcp_server.ontology_links


@pytest.fixture(autouse=True)
def _asgi_transport() -> Iterator[None]:
    tools._TRANSPORT = httpx.ASGITransport(app=fastapi_app)
    tools.API_BASE = "http://testserver"
    yield
    tools._TRANSPORT = None


@pytest.fixture
def ai(client: TestClient, admin: Signed) -> Bot:
    """시스템 관리자의 토큰 — 정의를 바꾸는 일이라."""
    made = client.post(
        "/api/auth/tokens",
        json={"name": "Claude Code", "scopes": ["read", "write"]},
        headers=admin.headers,
    )
    assert made.status_code == 201, made.text
    return Bot(str(made.json()["token"]))


def _uniq(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:6]}"


def test_정의를_만들고_객체를_넣고_부품에_잇는다(ai: Bot, admin: Signed, db: Session) -> None:
    klass, parts, classed = _uniq("klass"), _uniq("ccpart"), _uniq("classed")
    schema = {
        "types": [
            {"slug": klass, "label": "부품 분류", "key_policy": "required"},
            {
                "slug": parts,
                "label": "CompCore 부품",
                "kind_class": "system",
                "system_source": "part",
            },
        ],
        "relation_types": [
            {
                "slug": classed,
                "label": "분류",
                "inverse_label": "분류된 부품",
                "cardinality": "many_to_one",
                "src_type_slugs": [parts],
                "dst_type_slugs": [klass],
            }
        ],
    }
    # 1) 정의 — 미리 보기가 기본이다.
    plan = ai.call(tools.ontology_import, schema)
    assert plan["applied"] is False, plan
    done = ai.call(tools.ontology_import, schema, apply=True)
    assert done["applied"] is True and done["errors"] == [], done
    known = ai.call(tools.ontology_schema)
    assert {klass, parts} <= {one["slug"] for one in known["types"]}

    # 2) 객체 여러 행 — 계획 작업 → 사람 확인 → 적용(`task_apply`).
    rows = [{"key": "HG", "label": "힌지"}, {"key": "BR", "label": "브래킷"}]
    planned = ai.call(tools.objects_import, klass, rows, workspace_slug=admin.workspace)
    job_id = planned["job_id"]
    work_until(db, uuid.UUID(job_id))
    status = ai.call(tools.task_status, job_id, wait_seconds=0)
    assert status["status"] == "done" and "task_apply" in status["next"], status
    applying = ai.call(tools.task_apply, job_id, wait_seconds=0)
    work_until(db, uuid.UUID(applying["job_id"]))
    applied = ai.call(tools.task_status, applying["job_id"], wait_seconds=0)
    assert applied["result"]["applied"] is True, applied

    # 3) 이름은 해소하고 쓴다.
    hinge = ai.call(tools.object_resolve, klass, "힌지")
    assert hinge["match"] == "exact", hinge
    found = ai.call(tools.object_search, "브래킷")
    assert any(one["type_slug"] == klass for one in found["types"]), found

    # 4) 부품의 「기준정보」 칸 — 이름 추천을 받고 잇고 뺀다.
    user = db.scalar(select(User).where(User.email == admin.email))
    assert user is not None
    part = Part(name="P5 플립 힌지 브래킷", owner_id=user.id, folder="")
    db.add(part)
    db.commit()
    card = ai.call(links.ontology_links, "part", str(part.id))
    row = next(one for one in card["rows"] if one["relation"] == classed)
    assert row["label"] == "분류" and row["single"] is True
    assert {one["label"] for one in row["suggestions"]} <= {"힌지", "브래킷"}
    linked = ai.call(links.ontology_link, "part", str(part.id), classed, hinge["object"]["id"])
    row = next(one for one in linked["rows"] if one["relation"] == classed)
    assert [one["label"] for one in row["items"]] == ["힌지"]
    # 기준정보 쪽에서도 보인다 — 방향은 관계 정의대로(부품 → 분류).
    side = ai.call(tools.object_references, klass, hinge["object"]["id"])
    assert "error" not in side, side
    cut = ai.call(links.ontology_unlink, "part", str(part.id), row["items"][0]["link_id"])
    row = next(one for one in cut["rows"] if one["relation"] == classed)
    assert row["items"] == []


def test_데이터_작업_목록과_내_권한(ai: Bot) -> None:
    """두 도구는 경로만 바뀌었다(`/api/tasks` · `/api/auth/me`) — 붙는지만 본다."""
    listed: Any = ai.call(tools.tasks_list)
    assert "error" not in listed, listed
    me = ai.call(tools.whoami)
    assert me["is_system_admin"] is True and "memberships" in me
