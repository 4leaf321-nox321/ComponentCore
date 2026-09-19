"""MCP 도구를 **진짜 앱에 붙여** 본다 — AI 가 밟는 루프 그대로.

`mcp_server/server.py` 는 `mcp` 패키지를 쓰는데 그것을 백엔드 환경에 깔면 시험의 HTTP 스택이
바뀐다(StandardPlatform 에서 실측). 가짜 `mcp` 를 끼워 도구 함수만 꺼내고, 도구가 부르는
httpx 를 이 프로세스 안의 앱(ASGI)으로 돌린다 — 라우터 · 권한 · 검증이 통째로 돈다.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from collections.abc import Callable, Coroutine, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from tests.api.conftest import Signed

SERVER_PY = Path(__file__).resolve().parents[3] / "mcp_server" / "server.py"


class _FakeFastMCP:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.settings = SimpleNamespace()

    def tool(self) -> Callable[[Any], Any]:
        return lambda function: function


def _load_server() -> Any:
    fake = types.ModuleType("mcp.server.fastmcp")
    fake.FastMCP = _FakeFastMCP  # type: ignore[attr-defined]
    fake.Context = object  # type: ignore[attr-defined]
    for name in ("mcp", "mcp.server"):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules["mcp.server.fastmcp"] = fake
    spec = importlib.util.spec_from_file_location("mcp_server_under_test", SERVER_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = _load_server()


def _ctx(token: str) -> Any:
    request = SimpleNamespace(headers={"authorization": f"Bearer {token}"})
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


class Bot:
    """PAT 하나로 도구를 부르는 손 — **사람 세션이 아니라 기계 자격이다.**"""

    def __init__(self, token: str) -> None:
        self.ctx = _ctx(token)

    def call(
        self, tool: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kw: Any
    ) -> Any:
        return asyncio.run(tool(self.ctx, *args, **kw))


@pytest.fixture(autouse=True)
def _asgi_transport() -> Iterator[None]:
    server._TRANSPORT = httpx.ASGITransport(app=fastapi_app)
    server.API_BASE = "http://testserver"
    server._WAIT_SECONDS = 5
    yield
    server._TRANSPORT = None


@pytest.fixture
def bot(client: TestClient, member: Signed) -> Bot:
    made = client.post(
        "/api/auth/tokens",
        json={"name": "Claude Code", "scopes": ["read", "write"]},
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    return Bot(str(made.json()["token"]))


@pytest.fixture
def reader(client: TestClient, member: Signed) -> Bot:
    made = client.post(
        "/api/auth/tokens", json={"name": "읽기만", "scopes": ["read"]}, headers=member.headers
    )
    return Bot(str(made.json()["token"]))


def test_AI_의_루프_가이드_검증_저장_지그_승격(
    bot: Bot, client: TestClient, member: Signed
) -> None:
    guide = bot.call(server.get_guide)
    assert guide["topic"] == "overview"

    schema = bot.call(server.recipe_schema)
    plate = schema["templates"]["plate_with_holes"]

    # 1) 틀린 레시피 — 어느 노드가 왜인지 돌아온다.
    broken = {
        "nodes": [
            *plate["nodes"],
            {"id": "f", "op": "fillet", "target": "holes", "edges": "all", "radius": 100},
        ]
    }
    check = bot.call(server.recipe_check, broken)
    assert check["ok"] is False
    assert check["details"]["node_id"] == "f" and "반지름" in check["error"]

    # 2) 고쳐서 통과.
    fixed = {
        "nodes": [
            *plate["nodes"],
            {"id": "f", "op": "fillet", "target": "holes", "edges": "vertical", "radius": 3},
        ]
    }
    check = bot.call(server.recipe_check, fixed)
    assert check["ok"] is True and check["summary"]["face_count"] > 10

    # 3) 내 작업에 저장 — 출처 ai, 평가까지 기다린다(JOBS_INLINE 이라 바로 끝난다).
    made = bot.call(server.create_work, "AI 구멍판", fixed, note="모서리 R3")
    assert "error" not in made, made
    assert made["version"] == 1 and made["evaluation"]["status"] == "done"
    work_id = made["work_id"]
    work = bot.call(server.get_work, work_id)
    assert work["current"]["source"] == "ai" and work["current"]["note"] == "모서리 R3"

    # 사람 화면에서도 같은 작업이 보인다 — 같은 사람의 내 작업이다.
    seen = client.get(f"/api/works/{work_id}", headers=member.headers).json()
    assert seen["current"]["source"] == "ai"

    # 4) 새 버전 — 두께를 바꾼다.
    thicker = {
        "nodes": [n if n["id"] != "plate" else {**n, "distance": 20} for n in fixed["nodes"]]
    }
    saved = bot.call(server.save_version, work_id, thicker, note="두께 20")
    assert saved["version"] == 2 and saved["evaluation"]["summary"]["bbox"]["size"][2] == 20
    assert [v["number"] for v in bot.call(server.list_versions, work_id)["versions"]] == [2, 1]

    # 5) 부품에서 지그 생성 — 지그 작업이 생기고 결과가 그 첫 버전이 된 채로 돌아온다.
    jig = bot.call(server.run_jig, f"work:{work_id}", {"support_count": 3})
    assert "error" not in jig, jig
    assert jig["job"]["status"] == "done" and jig["version"] == 1
    assert jig["job"]["summary"]["interference"]["ok"] is True
    assert {one["kind"] for one in jig["job"]["summary"]["plan"]["locators"]} == {"pin"}
    runs = bot.call(server.list_jig_runs, jig["work_id"])["runs"]
    assert runs[0]["job_id"] == jig["job"]["job_id"] and runs[0]["interference_ok"] is True

    # 5b) 부품 + 지그를 맞는 자리에 놓은 조립 — 좌표를 AI 가 계산하지 않는다.
    assembled = bot.call(server.assemble_jig_on_part, f"work:{work_id}", jig["work_id"])
    assert "error" not in assembled, assembled
    assert assembled["kind"] == "assembly" and assembled["placement"]["mode"] == "generated"
    assert assembled["recipe"]["nodes"][0]["translate"][2] == "=부품_높이"

    # 6) 승격(사용자가 시켰다고 치자) — 부품을 올리고, 지그는 도면 길로 올린다.
    part_up = bot.call(server.promote_part, work_id, note="AI 가 그린 부품")
    assert "error" not in part_up, part_up
    promoted = bot.call(
        server.promote_jig_recipe,
        jig["work_id"],
        note="AI 가 만든 지그",
        part_id=part_up["part_id"],
    )
    assert "error" not in promoted, promoted
    part = bot.call(server.get_part, part_up["part_id"])
    assert part["current_version"] == 1 and part["jig_count"] == 1
    catalog = bot.call(server.get_jig, promoted["jig_id"])
    assert catalog["part_version"] == 1

    # 7) 카탈로그에서 내 공간으로 복사.
    copied = bot.call(server.copy_part_to_work, part_up["part_id"])
    assert copied["version"] == 1 and copied["work_id"] != work_id


def test_읽기_토큰은_저장을_못_한다(reader: Bot) -> None:
    schema = reader.call(server.recipe_schema)
    box = schema["templates"]["box"]
    # 검증 · 미리보기는 POST 지만 아무것도 안 바꾼다 — 읽기 토큰으로 되어야 AI 가 그려 본다.
    assert reader.call(server.recipe_check, box)["ok"] is True
    denied = reader.call(server.create_work, "x", box)
    assert "error" in denied and "AJG-AUTH-0106" in denied["error"]
