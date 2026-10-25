"""SP 의 MCP 서버와 안내서에서 **기준정보(온톨로지) 도구**를 CompCore 로 옮긴다(ADR 0008).

    git -C ../StandardPlatform show 6e5a773:mcp_server/server.py > /tmp/sp_server.py
    git -C ../StandardPlatform show 6e5a773:mcp_server/guide/GUIDE.md > /tmp/sp_guide.md
    git -C ../StandardPlatform show 6e5a773:mcp_server/tests/test_server.py > /tmp/sp_test.py
    python3 mcp_server/port_from_sp.py /tmp/sp_server.py /tmp/sp_guide.md /tmp/sp_test.py

`mcp_server/ontology.py` · `mcp_server/guide/ONTOLOGY.md` · `mcp_server/tests/test_ontology_sp.py`
를 **다시 쓴다** — 그 둘은 손으로 고치지
않고 이 스크립트를 고친다. 손으로 줄 번호를 박지 않는다: 최상위 덩어리로 잘라 이름으로 고르므로 SP
가 바뀌어도 같은 방법으로 다시 옮긴다. CompCore 에만 있는 도구는 `ontology_links.py` 에 둔다.
"""

# ruff: noqa: E501 — 안내서 문장을 그대로 품는 생성 스크립트다(줄을 나누면 옮긴 글이 갈린다).
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1]).read_text(encoding="utf-8")
GUIDE = Path(sys.argv[2]).read_text(encoding="utf-8")
OUT = HERE / "ontology.py"
OUT_GUIDE = HERE / "guide" / "ONTOLOGY.md"
TESTS = Path(sys.argv[3]).read_text(encoding="utf-8")
OUT_TESTS = HERE / "tests" / "test_ontology_sp.py"

lines = SRC.split("\n")

# --- 최상위 덩어리 ----------------------------------------------------------------
START = re.compile(
    r"^(@|def |async def |class |# -{5,}|# --- |#: |if __name__|[A-Za-z_][A-Za-z0-9_]*\s*[:=])"
)
chunks: list[list[str]] = []
for line in lines:
    if START.match(line):
        lead = [one for one in (chunks[-1] if chunks else []) if one.strip()]
        only_lead = bool(lead) and all(one.startswith(("@", "#: ")) for one in lead)
        if chunks and only_lead and not line.startswith(("# ---", "if __name__")):
            chunks[-1].append(line)
            continue
        chunks.append([line])
    else:
        if not chunks:
            chunks.append([])
        chunks[-1].append(line)


def name_of(chunk: list[str]) -> str:
    for one in chunk:
        m = re.match(r"^class (\w+)", one)
        if m:
            return m.group(1)
        m = re.match(r"^(?:async )?def (\w+)\(", one)
        if m:
            return m.group(1)
        m = re.match(r"^(\w+)\s*[:=]", one)
        if m:
            return m.group(1)
        if one.startswith("if __name__"):
            return "__main__"
    return ""


named = [(name_of(chunk), chunk) for chunk in chunks]
index = {name: i for i, (name, _chunk) in enumerate(named) if name}

#: 들이지 않는 것 — 사유는 ontology.py 머리에 적는다.
DROP = {
    # 설치의 자기소개(`/api/server/profile`) — CompCore 에 그 API 가 없다.
    "PROFILE_TTL",
    "PROFILE_PATH",
    "PROFILE_LIVE_PATH",
    "_SYNC_TRANSPORT",
    "_profile_cache",
    "_CACHE_MAX",
    "_CONNECTING_TOKEN",
    "SAME_TOOLS_RULE",
    "_fetch_profile",
    "profile_now",
    "identity",
    "_install_identity",
    "_RememberToken",
    "http_app",
    "platform_profile",
    "platform_profile_update",
    # 확장 모듈 기제 — CompCore 는 넣지 않는다(AGENTS.md).
    "_EXT_NAME",
    "_EXT_METHODS",
    "extensions_schema",
    "extension_call",
    # 서버 껍데기는 CompCore 의 것을 쓴다.
    "API_BASE",
    "_JSON_RESPONSE",
    "BASE_INSTRUCTIONS",
    "mcp",
    "__main__",
}

first = index["_TRACE_PATH"]
body: list[str] = []
for name, chunk in named[first:]:
    if name in DROP:
        continue
    body.extend(chunk)
text = "\n".join(body)

# 「자기소개」 를 읽던 두 자리 — 지운다.
text = text.replace(
    """    # **어느 플랫폼의 안내서인가** — 같은 안내서를 여러 플랫폼이 낸다.
    platform = await _get(ctx, PROFILE_LIVE_PATH)
    return {
        "guide_version": version,
        "topic": "overview",
        "platform": platform
        if isinstance(platform, dict) and "error" not in platform
        else None,
""",
    """    return {
        "guide_version": version,
        "topic": "overview",
""",
)
text = text.replace(
    """    me = await _get(ctx, "/api/auth/me")
    if isinstance(me, dict) and "error" not in me:
        platform = await _get(ctx, PROFILE_LIVE_PATH)
        if isinstance(platform, dict) and "error" not in platform:
            me = {**me, "platform": platform}
    return me""",
    """    return await _get(ctx, "/api/auth/me")""",
)
assert "PROFILE_LIVE_PATH" not in text, "자기소개 자리가 남았다"

# 도구 등록 — SP 는 모듈의 `mcp` 에 곧장 붙인다. 여기서는 모았다가 CompCore 의 서버에 붙인다.
text = text.replace(
    """    def wrap(fn: Any) -> Any:
        return mcp.tool()(_traced(fn))

    return wrap""",
    """    def wrap(fn: Any) -> Any:
        wrapped = _traced(fn)
        _TOOLS.append(wrapped)
        return wrapped

    return wrap""",
)

# 이름 · 경로 — CompCore 에서 겹치는 것(ADR 0008).
renames = [
    ("async def get_guide(", "async def ontology_guide("),
    ("async def search(", "async def object_search("),
    ("async def job_status(", "async def task_status("),
    ("async def job_apply(", "async def task_apply("),
    ("async def jobs_list(", "async def tasks_list("),
    ("async def job_cancel(", "async def task_cancel("),
]
for old, new in renames:
    assert text.count(old) == 1, old
    text = text.replace(old, new)
text = text.replace('"/api/jobs', '"/api/tasks').replace('f"/api/jobs', 'f"/api/tasks')
text = text.replace('"/api/search"', '"/api/object-search"')
for old, new in (
    ("job_status", "task_status"),
    ("job_apply", "task_apply"),
    ("jobs_list", "tasks_list"),
    ("job_cancel", "task_cancel"),
):
    text = re.sub(rf"\b{old}\b", new, text)
text = re.sub(r"`search\(", "`object_search(", text)
text = text.replace("get_guide(topic=", "ontology_guide(topic=")
text = text.replace('"GUIDE.md")', '"ONTOLOGY.md")')
text = text.replace('os.environ.get("MCP_PORT", "8042")', 'os.environ.get("MCP_PORT", "8062")')
text = text.replace(
    "**StandardPlatform 작업을 시작하기 전에 먼저 부른다.**",
    "**기준정보(온톨로지)를 다루기 전에 먼저 부른다.**",
)
text = text.replace(
    "      - `extensions` 이 설치에만 있는 기능(확장) — 무엇을 부를 수 있나\n", ""
)
text = text.replace(
    "      - `platforms` 같은 도구를 가진 플랫폼이 여럿일 때 — 어디에 물을지 · 자기소개\n",
    "      - `platforms` SP 와 함께 붙어 있을 때 — 어디에 물을지(정본은 SP)\n",
)

# 401 은 결과가 아니라 예외로 — HWAX 게이트웨이가 위임 토큰을 다시 받는 신호(SP ADR 0028 결정 12,
# SP 에서는 6e5a773 뒤에 고쳤다). 규칙은 `backend_errors.py` 한 곳에 두고 여기서 부른다. 업로드
# 주소의 앱 포트는 개발(+1)에서 띄우는 쪽이 알려 준다(`PLATFORM_APP_PORT`, 2026-10-25).
for old, new in (
    (
        """def _unwrap(r: httpx.Response) -> Any:
    \"\"\"백엔드 응답 언래핑. 오류 봉투 {error: {code, message, details}} 면 {error,...}.\"\"\"
    if r.status_code < 400 and not r.content:""",
        """def _unwrap(r: httpx.Response) -> Any:
    \"\"\"백엔드 응답 언래핑. 오류 봉투 {error: {code, message, details}} 면 {error,...}.

    **401 만은 예외로 올린다**(`backend_errors.rejected`) — HWAX 게이트웨이가 위임 토큰을 새로
    받아 다시 부르는 신호다(CompCore 가 더함, SP ADR 0028 결정 12).\"\"\"
    if r.status_code == 401:
        raise rejected(r)
    if r.status_code < 400 and not r.content:""",
    ),
    (
        """        response.raise_for_status()
        return response.text""",
        """        if response.status_code == 401:  # 게이트웨이의 다시 받기 신호(`_unwrap` 과 같다)
            raise rejected(response)
        response.raise_for_status()
        return response.text""",
    ),
    (
        """    if port is not None and port == int(os.environ.get("MCP_PORT", "8062")):
        port -= 2""",
        """    if port is not None and port == int(os.environ.get("MCP_PORT", "8062")):
        # 개발은 앱이 +1(8061)이라 -2 규칙이 틀린다 — 띄우는 쪽(`run.py`)이 앱 포트를 알려 준다
        # (CompCore 가 더함).
        port = int(os.environ.get("PLATFORM_APP_PORT") or port - 2)""",
    ),
):
    assert text.count(old) == 1, old[:60]
    text = text.replace(old, new)

HEADER = '''"""CompCore MCP 의 **기준정보(온톨로지) 도구** — StandardPlatform `6e5a773` 의
`mcp_server/server.py` 에서 옮겼다(ADR 0008). 도구 이름 · 설명 · 규칙은 SP 와 같고, 다른 것은
아래뿐이다:

- **이름이 겹치는 것** — CompCore 에 이미 있는 이름 · 뜻과 겹쳐 바꿨다: `search` →
  `object_search`(작업 · 부품 찾기 `search` 가 따로 있다), `job_*` → `task_*`(데이터 작업 —
  형상 작업 `get_job` · `cancel_job` 과 다르다, 경로도 `/api/tasks`), `get_guide` →
  `ontology_guide`(안내서는 `guide/ONTOLOGY.md`).
- **들이지 않은 것** — 설치의 자기소개(`platform_profile` · `platform_profile_update` ·
  접속마다 붙는 소개 — CompCore 에 `/api/server/profile` 이 없다), 확장 모듈
  (`extensions_schema` · `extension_call` — CompCore 는 그 기제를 넣지 않는다, AGENTS.md).
- **등록** — SP 는 모듈의 `mcp` 에 곧장 붙인다. 여기서는 모았다가 `register(mcp)` 가 CompCore
  의 서버에 붙인다(`server.py` 의 끝, `mcp.run()` 앞).
- **401** — 백엔드가 토큰을 거절하면 결과가 아니라 예외로 올린다
  (`backend_errors.rejected`) — HWAX 게이트웨이의 다시 받기 신호다. SP 는 `6e5a773` 뒤에 같은
  것을 고쳤다(SP ADR 0028 결정 12).

이 파일은 `port_from_sp.py` 가 SP 의 파일에서 다시 만든다 — 손으로 고치지 말고 그 스크립트를
고친다. CompCore 에만 있는 것(부품 · 지그의 「기준정보」 칸)은 `ontology_links.py`
에 따로 둔다.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import os
import re
import shlex
import time
from pathlib import PureWindowsPath
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from backend_errors import BackendUnauthorized as BackendUnauthorized  # 시험이 여기서 본다
from backend_errors import rejected
from mcp.server.fastmcp import Context, FastMCP

API_BASE = os.environ.get("PLATFORM_API_BASE", "http://127.0.0.1:8060").rstrip("/")

#: 시험이 갈아 끼우는 자리 — 진짜 앱(ASGI)이나 가짜 응답을 여기로 붙인다. 운영에서는 None.
_TRANSPORT: httpx.AsyncBaseTransport | None = None

#: `@tool()` 이 모은 도구 — `register(mcp)` 가 서버에 붙인다.
_TOOLS: list[Any] = []

#: 서버 안내문에 덧붙는 몫(SP 의 `BASE_INSTRUCTIONS` 를 줄인 것) — `server.py` 가 붙인다.
INSTRUCTIONS = (
    "**기준정보(온톨로지)** — SP 에서 받은 기준정보와 이 플랫폼의 부품 · 지그를 잇는 정의 · "
    "객체 · 관계를 읽고 쓴다. **`ontology_guide` 와 `ontology_schema` 를 먼저 부른다.** "
    "지켜야 할 셋: (1) 이름은 `object_resolve` 로 해소하고 쓴다 — `candidates` 가 오면 "
    "고르지 말고 사람에게 묻는다. (2) 0건은 「없다」 가 아니다 — 응답의 `diagnosis` 를 "
    "읽는다. (3) 바꾸거나 지울 때는 미리 보기(apply=false) 먼저 — 계획을 사람에게 보이고 "
    "판단을 받은 뒤 적용한다(`task_apply`). 부품 · 지그에 기준정보를 잇는 것은 "
    "`ontology_links` → `ontology_link`."
)


def register(mcp: FastMCP) -> None:
    """모은 도구를 서버에 붙인다 — **`mcp.run()` 보다 앞에서** 불러야 한다(그 뒤는 안
    붙는다)."""
    for fn in _TOOLS:
        mcp.tool()(fn)


'''

OUT.write_text(HEADER + text.rstrip() + "\n", encoding="utf-8")
print("tools:", len(re.findall(r"^@tool\(\)", text, re.M)))

# --- 안내서 ---------------------------------------------------------------------
guide = GUIDE
head_end = guide.index("GUIDE_VERSION:")
guide = """<!-- CompCore MCP 의 기준정보(온톨로지) 안내서 — `ontology_guide(topic)` 이 읽는다.

StandardPlatform `6e5a773` 의 `mcp_server/guide/GUIDE.md` 에서 `port_from_sp.py` 가 옮긴다 —
손으로 고치지 말고 그 스크립트를 고친다. 다른 것: 도구 이름(`object_search` · `task_*` ·
`ontology_guide`), 확장 · 자기소개 장을 뺐다, 「여러 플랫폼」 은 「SP 와 함께」 로, 정제 도구
키트(SP 의 것)는 쓰지 않는다.

주제 구분자: `<!--@ 주제이름 -->`. 순서는 상관없다. -->
""" + guide[head_end:]


def drop_section(text: str, name: str) -> str:
    start = text.index(f"<!--@ {name} -->")
    nxt = text.find("<!--@ ", start + 5)
    return text[:start] + (text[nxt:] if nxt != -1 else "")


def replace_section(text: str, name: str, body: str) -> str:
    start = text.index(f"<!--@ {name} -->")
    nxt = text.find("<!--@ ", start + 5)
    return (
        text[:start]
        + f"<!--@ {name} -->\n"
        + body.strip()
        + "\n\n"
        + (text[nxt:] if nxt != -1 else "")
    )


guide = drop_section(guide, "extensions")
guide = replace_section(
    guide,
    "platforms",
    """## SP 와 함께 붙어 있을 때 — 어디에 물을까

CompCore 의 기준정보는 **SP 에서 받은 사본**이다(데이터 소스 `sp_core` — 관리 › 데이터 소스).
SP 의 MCP 와 이 MCP 가 함께 붙어 있으면 **도구 이름이 같다**(`ontology_schema` · `objects_list`
…) — 클라이언트는 서버 이름으로 가르지만, 어디에 물을지는 네가 고른다.

- **정본은 SP 다.** 받은 타입(SP 의 기본 모델 · 부품 · 판매 모델 …)의 값을 고칠 일이면 SP 에서
  고친다 — 여기서 고친 값은 다음 동기화가 덮는다. 받는 시점만큼 늦으니 최신이 필요하면 SP 에 묻는다.
- **CompCore 에만 있는 것**은 여기에: 부품 · 지그(원 표 `cc_part` · `cc_jig`)와 그것을 기준정보에
  잇는 선(`ontology_links` · `ontology_link`). 「이 모델에 들어가는 설계 부품」 은 여기 묻는다.
- **0건은 「이 플랫폼에는 없다」** 다 — SP 에 있을 수 있다. 어디서 찾았는지 답에 함께 말한다.
- **쓰기는 어느 플랫폼인지 사람에게 말한다** — 미리 보기에 플랫폼 이름을 함께 보인다.
""",
)
guide = "\n".join(
    line
    for line in guide.split("\n")
    if "platform_profile" not in line and "extensions_schema" not in line
)
bulk_start = guide.index("**한꺼번에 많이(백필)**")
bulk_end = guide.index("### 넣은 판을 되돌린다")
guide = (
    guide[:bulk_start]
    + """**한꺼번에 많이(백필)** — `bundle_import` 에 백필 칸 넷: `preview: "plan"` · `events: "summary"` ·
`audit: "summary"` · `missing_refs: "blank"`. **행이 호출에 실리므로** 모델이 한 번에 쓸 수 있는 만큼
(수백 ~ 천 줄)이 한계다. 칸 넷은 **사용자가 백필이라고 정했을 때만** 쓴다 — 넷 다 「전부 아니면 무 ·
줄마다 기록」 을 느슨하게 한다.

수만 줄의 원천은 **여기서 넣지 않는다** — SP 에서 정제 · 적재하고(SP 의 정제 도구 키트), CompCore 는
데이터 소스(`sp_core`)로 받는다. CompCore 에는 그 키트가 없다.

"""
    + guide[bulk_end:]
)
guide = guide.replace(
    "원천을 곧바로 넣지 않는다 — `pipeline/AGENTS.md`", "원천을 곧바로 넣지 않는다"
)
guide = guide.replace(
    "<!--@ modeling -->\n",
    "<!--@ modeling -->\n> 이 장은 SP 의 모델링 규약 그대로다 — `pipeline/…` 경로는 SP 저장소의 것이다. "
    "CompCore 에서 새로 정할 것은 주로 **부품 · 지그에 잇는 관계와 그 분류**다(`ontology_links`).\n\n",
)
whoami_row = next(line for line in guide.split("\n") if line.startswith("| 내가 누구고"))
guide = guide.replace(
    whoami_row,
    whoami_row
    + "\n| **부품 · 지그에 기준정보 잇기** | `ontology_links(kind, id)` → 사람 확인 → "
    "`ontology_link(kind, id, relation, object_id)` | 줄은 관계 종류마다 선다(「적용 모델」 · "
    "「서비스 부품」). 추천은 이름의 낱말뿐 — **사람에게 보이고 잇는다.** 그 부품을 고칠 수 있는 "
    "사람만 |",
)
for old, new in (
    ("job_status", "task_status"),
    ("job_apply", "task_apply"),
    ("jobs_list", "tasks_list"),
    ("job_cancel", "task_cancel"),
    ("get_guide", "ontology_guide"),
):
    guide = re.sub(rf"\b{old}\b", new, guide)
guide = re.sub(r"`search\(", "`object_search(", guide)
guide = guide.replace("`search`", "`object_search`")
OUT_GUIDE.write_text(guide.rstrip() + "\n", encoding="utf-8")
print("guide topics:", re.findall(r"<!--@ (\w+) -->", guide))

# --- 시험 -----------------------------------------------------------------------
#: 들이지 않은 시험 — 들이지 않은 도구(자기소개 · 확장)와 SP 의 기동 순서(CompCore 는
#: `test_ontology.py` 가 본다).
DROP_TESTS = {
    "test_확장_호출은_그_확장_뿌리로만_간다",
    "test_본문은_본문_있는_메서드에만_실린다",  # extension_call 의 본문 규칙
    "test_파일을_주는_자리는_바이트를_안_흘린다",  # extension_call 의 파일 응답
    "test_기동_블록_뒤에_도구가_없다",
    "test_안내문_첫머리는_사람의_소개_지금_담긴_것_낡음을_함께_싣는다",
    "test_접속하는_사람의_토큰으로_지금_담긴_것을_세어_안내문에_싣는다",
    "test_토큰마다_짧게_붙들고_백엔드가_안_닿으면_붙들던_것으로",
    "test_whoami_와_안내서는_지금의_플랫폼을_싣는다",
    "test_자기소개_고치기는_미리_보기가_먼저고_안_보낸_칸은_그대로다",
}
DROP_TOOLS = {
    "platform_profile",
    "platform_profile_update",
    "extensions_schema",
    "extension_call",
}
TOOL_RENAMES = {
    "get_guide": "ontology_guide",
    "search": "object_search",
    "job_status": "task_status",
    "job_apply": "task_apply",
    "jobs_list": "tasks_list",
    "job_cancel": "task_cancel",
}

tlines = TESTS.split("\n")
tchunks: list[list[str]] = []
for line in tlines:
    if START.match(line):
        lead = [one for one in (tchunks[-1] if tchunks else []) if one.strip()]
        only_lead = bool(lead) and all(one.startswith(("@", "#: ")) for one in lead)
        if tchunks and only_lead:
            tchunks[-1].append(line)
            continue
        tchunks.append([line])
    else:
        if not tchunks:
            tchunks.append([])
        tchunks[-1].append(line)
kept: list[str] = []
for chunk in tchunks:
    name = name_of(chunk)
    if name in DROP_TESTS:
        continue
    kept.extend(chunk)
tests = "\n".join(kept)

# 도구 이름 목록 — 들이지 않은 것을 빼고 바꾼 이름으로.
start = tests.index("TOOLS = {")
end = tests.index("}", start)
names = re.findall(r'"([a-z_]+)"', tests[start:end])
names = [TOOL_RENAMES.get(one, one) for one in names if one not in DROP_TOOLS]
listing = "TOOLS = {\n" + "".join(f'    "{one}",\n' for one in names) + "}"
tests = tests[:start] + listing + tests[end + 1 :]

tests = tests.replace(
    "import server\n",
    "import ontology as server  # SP 의 `server` 자리 — 옮긴 도구는 여기 있다\n"
    "import server as cc_server  # CompCore 의 서버 — 거기 붙었는지 본다\n"
    "from mcp.server.fastmcp import FastMCP\n",
    1,
)
tests = tests.replace(
    """    listed = asyncio.run(server.mcp.list_tools())
    assert {one.name for one in listed} == TOOLS""",
    """    listed = asyncio.run(cc_server.mcp.list_tools())
    assert TOOLS <= {one.name for one in listed}""",
)
tests = tests.replace(
    """    listed = asyncio.run(traced.mcp.list_tools())""",
    """    fresh = FastMCP("traced")
    traced.register(fresh)
    listed = asyncio.run(fresh.list_tools())""",
)
tests = tests.replace('"/api/jobs', '"/api/tasks').replace('f"/api/jobs', 'f"/api/tasks')
tests = tests.replace('"/api/search"', '"/api/object-search"')
# 401 은 예외 — 위의 `_unwrap` 패치와 짝. SP 지금 판의 같은 시험과 같다(SP ADR 0028 결정 12).
_old_401 = """    asyncio.run(server.ontology_schema(_ctx(None)))
    assert "authorization" not in seen[0].headers"""
assert tests.count(_old_401) == 1, "토큰 시험의 401 자리가 바뀌었다"
tests = tests.replace(
    _old_401,
    """    with pytest.raises(server.BackendUnauthorized):
        asyncio.run(server.ontology_schema(_ctx(None)))
    assert "authorization" not in seen[0].headers""",
)
if "\nimport pytest\n" not in tests:
    tests = tests.replace("import httpx\n", "import httpx\nimport pytest\n", 1)
for old, new in TOOL_RENAMES.items():
    if old == "search":
        tests = tests.replace("server.search(", "server.object_search(")
        continue
    tests = re.sub(rf"\b{old}\b", new, tests)
head_end = tests.index("from __future__ import annotations")
tests = '''"""SP 의 MCP 시험을 옮긴 것 — `port_from_sp.py` 가 SP `mcp_server/tests/test_server.py`
에서 만든다(손으로 고치지 말고 그 스크립트를 고친다). 도구는 `ontology.py` 에, 등록은
CompCore 의 `server.py` 에 있다. CompCore 에만 있는 것(부품 · 지그의 기준정보 칸 · 기동
순서)은 `test_ontology.py` 가 본다.

    cd mcp_server && ./venv/bin/python -m pytest tests
"""

# ruff: noqa: E501 — SP 의 문장을 이름만 바꿔 옮긴다(바뀐 이름이 줄을 늘린다).
''' + tests[head_end:]
OUT_TESTS.write_text(tests.rstrip() + "\n", encoding="utf-8")
print("tests:", len(re.findall(r"^def test_", tests, re.M)))
