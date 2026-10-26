"""기준정보(온톨로지) 도구가 CompCore 의 서버에 **제대로 붙었나** — SP 에서 옮긴 시험
(`test_ontology_sp.py`)이 못 보는 CompCore 의 몫(ADR 0008).

    cd mcp_server && ./venv/bin/python -m pytest tests
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import ontology
import server

#: SP 에서 옮긴 도구 72 — 이름을 바꾼 것(`object_search` · `task_*` · `ontology_guide`) 포함.
LINK_TOOLS = {"ontology_links", "ontology_link", "ontology_unlink", "ontology_link_defaults"}
SP_TOOLS = {fn.__name__ for fn in ontology._TOOLS} - LINK_TOOLS


def _ctx(authorization: str | None = "Bearer t") -> Any:
    headers = {"authorization": authorization} if authorization else {}
    return SimpleNamespace(
        request_context=SimpleNamespace(request=SimpleNamespace(headers=headers))
    )


def _serve(handler: Any) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    ontology._TRANSPORT = httpx.MockTransport(respond)
    return seen


def test_옮긴_도구가_다_붙고_이름이_겹치지_않는다() -> None:
    """CompCore 의 도구 + 옮긴 72 + 기준정보 칸 4. 이름이 겹치면 뒤에 붙은 것이 앞의 것을
    **조용히 덮는다** — 작업 · 부품 찾기 `search` 가 객체 찾기로 바뀌는 식으로."""
    assert len(SP_TOOLS) == 72
    listed = {one.name for one in asyncio.run(server.mcp.list_tools())}
    assert listed >= SP_TOOLS | LINK_TOOLS
    own = listed - SP_TOOLS - LINK_TOOLS
    assert {"search", "get_guide", "get_job", "cancel_job"} <= own  # CompCore 의 것은 그대로
    assert len(listed) == len(own) + len(SP_TOOLS) + len(LINK_TOOLS)
    # 들이지 않은 것 — 그 API 가 CompCore 에 없다.
    assert (
        not {"platform_profile", "extensions_schema", "extension_call", "job_status"} & listed
    )


def test_기동_블록보다_앞에서_붙인다() -> None:
    """`mcp.run()` 은 블로킹이다 — 그 뒤의 등록은 운영(`python server.py`)에서 안 붙는다.
    시험은 모듈을 import 하므로 `list_tools` 로는 못 잡는다 — **소스의 순서**를 본다(SP 가
    겪은 것)."""
    source = Path(server.__file__).read_text(encoding="utf-8")
    boot = source.index('if __name__ == "__main__":')
    assert source.index("ontology.register(mcp)") < boot
    assert "@mcp.tool()" not in source[boot:]


def test_안내문이_기준정보_도구를_가리킨다() -> None:
    assert ontology.INSTRUCTIONS in str(server.mcp.instructions)
    assert "ontology_guide" in ontology.INSTRUCTIONS


def test_기준정보_칸은_부품과_지그의_경로로_간다() -> None:
    seen = _serve(lambda _r: httpx.Response(200, json={"type_slug": "cc_part", "rows": []}))
    asyncio.run(ontology_links_call("ontology_links", "part", "p1"))
    asyncio.run(ontology_links_call("ontology_link", "part", "p1", "uses_part", "m5"))
    asyncio.run(ontology_links_call("ontology_unlink", "jig", "j1", "l9"))
    assert [(one.method, one.url.path) for one in seen] == [
        ("GET", "/api/parts/p1/ontology"),
        ("POST", "/api/parts/p1/ontology/links"),
        ("DELETE", "/api/jigs/j1/ontology/links/l9"),
    ]
    assert json.loads(seen[1].content) == {"relation": "uses_part", "object_id": "m5"}
    assert seen[0].headers["authorization"] == "Bearer t"

    # 모르는 종류는 부르지 않는다 — 짐작한 경로로 가면 404 가 「없는 부품」 으로 읽힌다.
    before = len(seen)
    got = asyncio.run(ontology_links_call("ontology_links", "work", "w1"))
    assert "error" in got and len(seen) == before


def test_기본_관계는_보기와_만들기가_한_도구다() -> None:
    seen = _serve(lambda _r: httpx.Response(200, json=[]))
    asyncio.run(ontology_links_call("ontology_link_defaults"))
    asyncio.run(ontology_links_call("ontology_link_defaults", True))
    assert [(one.method, one.url.path) for one in seen] == [
        ("GET", "/api/ontology/link-defaults"),
        ("POST", "/api/ontology/link-defaults"),
    ]


async def ontology_links_call(name: str, *args: Any) -> Any:
    import ontology_links

    return await getattr(ontology_links, name)(_ctx(), *args)


def test_안내서는_옮긴_이름만_말한다() -> None:
    """빼거나 바꾼 도구를 안내서가 가리키면 AI 는 없는 도구를 부른다."""
    version, sections = ontology._guide_sections()
    assert version and "overview" in sections
    text = Path(ontology._GUIDE_PATH).read_text(encoding="utf-8")
    for gone in (
        "platform_profile",
        "extensions_schema",
        "extension_call",
        "job_status",
        "get_guide",
    ):
        assert gone not in text, gone
    assert "ontology_links" in sections["overview"]
    assert "정본은 SP" in sections["platforms"]
    overview = asyncio.run(ontology.ontology_guide(_ctx(None)))
    assert overview["topic"] == "overview" and "extensions" not in overview["more_topics"]
