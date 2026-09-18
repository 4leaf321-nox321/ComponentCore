"""AutoJigGenerator MCP 서버 — AI 가 **내 작업**에서 부품을 그리고 지그를 만들게 하는 도구.

플랫폼이 AI 를 부르지 않는다. AI(Claude Code · Claude Desktop · 다른 클라이언트)가 이 서버를
도구로 물고, 사용자의 **개인 토큰(PAT)** 으로 백엔드에 붙는다 — 검증도 권한도 백엔드가 한다.
여기에 규칙을 두면 「MCP 로는 되는데 화면에서는 안 되는」 상태가 생기고, 그때 어느 쪽이 맞는지
알 방법이 없다.

## 도구가 몇 개뿐인 이유

도구 목록이 길수록 모델은 엉뚱한 것을 고른다. 도구는 「작업 흐름」 단위로 고정하고, **무엇을
만들 수 있는가**(피처 종류 · 칸)는 `recipe_schema` 와 `get_guide` 가 말한다 — 동적인 것은
도구가 아니라 스키마다.

## AI 의 자기 수정 루프

`recipe_check` 가 레시피를 **실제로 만들어 본다.** 실패하면 어느 피처가 왜인지가 돌아오고,
AI 는 그것을 읽고 고쳐 다시 부른다. 통과한 레시피만 `save_version` 으로 저장한다 — 저장은 늘
**내 작업의 새 버전**(출처 "ai")이고, 사람이 화면에서 보고 승격한다.

실행:
    PLATFORM_API_BASE=http://127.0.0.1:8061 ./venv/bin/python server.py
    # streamable-http, 기본 127.0.0.1:8062/mcp

Claude Code 등록(사용자별 토큰 — 화면의 「내 정보」 에서 발급):
    claude mcp add --transport http autojig http://127.0.0.1:8062/mcp \\
      --header "Authorization: Bearer autojig_pat_…"
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP

API_BASE = os.environ.get("PLATFORM_API_BASE", "http://127.0.0.1:8060").rstrip("/")

# SSE 를 버퍼링하는 프록시 뒤에서는 단발 JSON 응답으로(StandardPlatform 에서 실측한 함정).
_JSON_RESPONSE = os.environ.get("MCP_JSON_RESPONSE") == "1"

mcp = FastMCP(
    os.environ.get("APP_SLUG", "autojig"),
    json_response=_JSON_RESPONSE,
    instructions=(
        "부품을 레시피(연산 트리 JSON)로 그리고 지그를 만드는 플랫폼. "
        "**`get_guide` 를 먼저 부른다** — 레시피의 규칙과 작업 순서가 거기 있다. "
        "레시피는 `recipe_check` 로 만들어 본 뒤에만 `save_version` 으로 저장한다. "
        "저장은 사용자의 내 작업에 새 버전으로 들어가고, 승격(부품 · 지그 카탈로그)은 "
        "사람이 판단할 일이니 `promote_*` 는 사용자가 시킬 때만."
    ),
)

#: 시험이 갈아 끼우는 자리 — 진짜 앱(ASGI)을 여기로 붙인다. 운영에서는 None(실제 네트워크).
_TRANSPORT: httpx.AsyncBaseTransport | None = None

#: 작업(평가 · 지그 생성)이 끝나기를 기다리는 최대 시간(초).
_WAIT_SECONDS = float(os.environ.get("MCP_JOB_WAIT", "90"))


def _forward_headers(ctx: Context) -> dict[str, str]:
    """들어온 MCP HTTP 요청의 인증 헤더를 백엔드로 — **사용자의 토큰으로** 동작한다."""
    headers: dict[str, str] = {}
    req = getattr(getattr(ctx, "request_context", None), "request", None)
    if req is not None:
        value = req.headers.get("authorization")
        if value:
            headers["Authorization"] = value
    return headers


def _unwrap(response: httpx.Response) -> Any:
    """백엔드 응답 언래핑. 오류 봉투는 {error, details} 로 — **서버의 말을 그대로 전한다.**"""
    if response.status_code < 400 and not response.content:
        return {"ok": True, "message": "완료"}
    try:
        body = response.json()
    except ValueError:
        return {
            "error": f"HTTP {response.status_code} (non-JSON)",
            "status": response.status_code,
        }
    if response.status_code >= 400:
        error = body.get("error") if isinstance(body, dict) else None
        if not isinstance(error, dict):
            return {"error": f"HTTP {response.status_code}", "status": response.status_code}
        label = error.get("code") or response.status_code
        out: dict[str, Any] = {"error": f"[{label}] {error.get('message') or ''}"}
        if error.get("details"):
            out["details"] = error["details"]
        return out
    return body


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=API_BASE, timeout=timeout, transport=_TRANSPORT)


async def _get(ctx: Context, path: str, params: dict[str, Any] | None = None) -> Any:
    async with _client(60) as client:
        return _unwrap(await client.get(path, params=params, headers=_forward_headers(ctx)))


async def _post(ctx: Context, path: str, json_body: Any = None) -> Any:
    async with _client(120) as client:
        return _unwrap(await client.post(path, json=json_body, headers=_forward_headers(ctx)))


async def _wait_job(ctx: Context, job: Any) -> Any:
    """작업(Job)이 끝날 때까지 폴링한다. 도구 하나가 「걸고 결과까지」 를 돌려줘야 AI 가 한
    번에 읽는다 — 작업 id 만 주면 다음 도구 호출을 또 낸다."""
    if not isinstance(job, dict) or "id" not in job:
        return job
    deadline = asyncio.get_event_loop().time() + _WAIT_SECONDS
    current = job
    while current.get("status") in ("queued", "running"):
        if asyncio.get_event_loop().time() > deadline:
            current["note"] = (
                f"{_WAIT_SECONDS:.0f}초 안에 안 끝났습니다 — get_job 으로 다시 보세요."
            )
            return current
        await asyncio.sleep(1.0)
        current = await _get(ctx, f"/api/jobs/{job['id']}")
        # 오류 봉투는 {"error": "..."} 뿐이고 작업 응답은 `"error": null` 칸을 **늘** 든다 —
        # `"error" in current` 로 가르면 running 인 작업을 오류로 잘못 읽는다(실측).
        if not isinstance(current, dict) or "kind" not in current:
            return current
    return current


def _slim_job(job: Any) -> Any:
    """작업 응답에서 AI 가 읽을 것만 — 요약 · 오류 · 작업물 종류. 삼각형 같은 큰 것은 없다."""
    if not isinstance(job, dict) or "status" not in job:
        return job
    return {
        "job_id": job.get("id"),
        "kind": job.get("kind"),
        "status": job.get("status"),
        "error": job.get("error"),
        "summary": job.get("summary"),
        "artifacts": [
            {"kind": a.get("kind"), "id": a.get("id"), "filename": a.get("filename")}
            for a in job.get("artifacts", [])
        ],
        "note": job.get("note"),
    }


def _slim_version(version: Any) -> Any:
    if not isinstance(version, dict) or "recipe" not in version:
        return version
    return {
        "number": version.get("number"),
        "source": version.get("source"),
        "note": version.get("note"),
        "recipe": version.get("recipe"),
        "evaluation": _slim_job(version.get("job")),
        "promoted_part_id": version.get("promoted_part_id"),
        "promoted_part_version": version.get("promoted_part_version"),
    }


# --------------------------------------------------------------------------- #
# 가이드 — 서버가 쥔다. 로컬에 본문을 두면 사람마다 복사 시점이 달라 낡는다.
# --------------------------------------------------------------------------- #
_GUIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guide", "GUIDE.md")


def _guide_sections() -> tuple[str, dict[str, str]]:
    try:
        with open(_GUIDE_PATH, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return "", {}
    version = ""
    found = re.search(r"^<!--\s*version:\s*(\S+)\s*-->", text, re.M)
    if found:
        version = found.group(1)
    out: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        match = re.match(r"^##\s+(\S+)", line)
        if match:
            current = match.group(1).strip().lower()
            out[current] = []
        elif current:
            out[current].append(line)
    return version, {key: "\n".join(lines).strip() for key, lines in out.items()}


@mcp.tool()
async def get_guide(ctx: Context, topic: str | None = None) -> dict[str, Any]:
    """**시작하기 전에 먼저 부른다.** 레시피가 무엇이고 어떤 순서로 도구를 쓰는지가 여기 있다.

    `topic` 없이 부르면 overview. 세부가 필요하면 그때 주제를 지정한다:
      - `recipe`   피처 종류 · 좌표계 · 자주 하는 실수
      - `workflow` 그리기 → 검증 → 저장 → 지그 → 승격의 순서
      - `jig`      지그 생성 옵션과 결과 읽는 법"""
    del ctx
    version, sections = _guide_sections()
    if not sections:
        return {
            "error": "가이드를 읽을 수 없습니다(서버 설치 문제). 도구 설명만으로 진행하세요."
        }
    if topic:
        key = topic.strip().lower()
        if key not in sections:
            return {"error": f"그런 주제가 없습니다: {topic}", "topics": sorted(sections)}
        return {"guide_version": version, "topic": key, "content": sections[key]}
    return {
        "guide_version": version,
        "topic": "overview",
        "content": sections.get("overview", ""),
        "more_topics": [t for t in sections if t != "overview"],
    }


# --------------------------------------------------------------------------- #
# 레시피
# --------------------------------------------------------------------------- #
@mcp.tool()
async def recipe_schema(ctx: Context) -> Any:
    """레시피의 **피처 종류와 칸**(JSON Schema), 내장 템플릿 넷(상자 · 원기둥 · 구멍판 · L
    브래킷), 그리고 사람이 저장해 둔 템플릿 목록(`saved_templates` — 내 것과 공용). 새로 그릴 때는
    템플릿에서 시작해 고치는 것이 빠르다.

    저장 템플릿의 **레시피 본문은 여기 없다**(목록이 무거워진다) — `template_recipe(id)` 로
    받는다."""
    schema = await _get(ctx, "/api/cad/recipe/schema")
    saved = await _get(ctx, "/api/templates?limit=50")
    if isinstance(schema, dict) and isinstance(saved, dict):
        schema["saved_templates"] = [
            {
                "id": t["id"],
                "name": t["name"],
                "description": t["description"],
                "where": "내 것" if t["mine"] else f"공용 · {t['owner_name']}",
                "node_count": t["node_count"],
            }
            for t in saved.get("items", [])
        ]
    return schema


@mcp.tool()
async def template_recipe(ctx: Context, template_id: str) -> Any:
    """저장된 템플릿의 **레시피 본문**. `recipe_schema` 의 `saved_templates` 에서 고른 id 로
    받아서, 치수를 고쳐 `create_work` · `save_version` 에 넣는다."""
    return await _get(ctx, f"/api/templates/{template_id}")


@mcp.tool()
async def save_template(
    ctx: Context,
    name: str,
    recipe: dict[str, Any],
    description: str = "",
    shared: bool = False,
) -> Any:
    """지금 레시피를 **템플릿으로 저장**한다 — 다음에 그릴 때의 출발점. `shared` 를 켜면 공용
    자리에 놓여 누구나 고른다(고치는 것은 만든 사람뿐).

    한 번 쓰고 말 것은 저장하지 않는다. 치수만 바꿔 되풀이해 쓸 모양일 때만."""
    return await _post(
        ctx,
        "/api/templates",
        {"name": name, "description": description, "recipe": recipe, "is_shared": shared},
    )


@mcp.tool()
async def recipe_check(ctx: Context, recipe: dict[str, Any]) -> Any:
    """레시피를 **실제로 만들어 본다.** 통과하면 크기 · 부피 · 면 수 · 노드별 요약이, 실패하면
    어느 피처가 왜인지가 돌아온다. **저장 전에 반드시 이것을 통과시킨다** — 실패 메시지를 읽고
    고쳐 다시 부른다(필렛이 크다 · 앞에 없는 노드 · 스케치가 결과 등)."""
    problems = await _post(ctx, "/api/cad/recipe/check", {"recipe": recipe})
    if isinstance(problems, dict) and problems.get("problems"):
        return {"ok": False, "problems": problems["problems"]}
    info = await _post(ctx, "/api/cad/recipe/info", {"recipe": recipe})
    if isinstance(info, dict) and "error" in info:
        return {"ok": False, **info}
    return {"ok": True, "summary": info.get("summary") if isinstance(info, dict) else info}


# --------------------------------------------------------------------------- #
# 내 작업
# --------------------------------------------------------------------------- #
@mcp.tool()
async def list_works(ctx: Context, limit: int = 50) -> Any:
    """사용자의 내 작업 목록(이름 · 현재 버전 · 지그 생성 횟수 · 승격 여부)."""
    page = await _get(ctx, "/api/works", {"limit": limit})
    if isinstance(page, dict) and "items" in page:
        return {
            "total": page["total"],
            "works": [
                {
                    "work_id": w["id"],
                    "name": w["name"],
                    "description": w["description"],
                    "current_version": w["current_version"],
                    "jig_runs": w["jig_run_count"],
                    "promoted_part_id": w["promoted_part_id"],
                    "promoted_jig_id": w["promoted_jig_id"],
                }
                for w in page["items"]
            ],
        }
    return page


@mcp.tool()
async def get_work(ctx: Context, work_id: str) -> Any:
    """작업 하나 — 현재 버전의 레시피와 평가 요약, 지그 옵션. 고칠 때는 이 레시피를 받아
    바꾼다."""
    work = await _get(ctx, f"/api/works/{work_id}")
    if not isinstance(work, dict) or "error" in work:
        return work
    return {
        "work_id": work["id"],
        "name": work["name"],
        "description": work["description"],
        "current_version": work["current_version"],
        "current": _slim_version(work.get("current")),
        "jig_options": work.get("jig_options"),
        "jig_runs": work.get("jig_run_count"),
        "promoted_part_id": work.get("promoted_part_id"),
        "promoted_jig_id": work.get("promoted_jig_id"),
    }


@mcp.tool()
async def list_versions(ctx: Context, work_id: str) -> Any:
    """작업의 버전 이력(번호 · 출처 · 메모 · 평가 상태). 레시피 본문은 `get_version` 으로."""
    versions = await _get(ctx, f"/api/works/{work_id}/versions")
    if isinstance(versions, list):
        # **리스트를 그대로 돌려주지 않는다.** FastMCP 는 리스트를 항목마다 다른 content 로
        # 쪼개 클라이언트가 첫 항목만 JSON 으로 읽게 된다(실측). 늘 dict 하나로 감싼다.
        return {
            "versions": [
                {
                    "number": v["number"],
                    "source": v["source"],
                    "note": v["note"],
                    "status": (v.get("job") or {}).get("status"),
                    "promoted_part_version": v.get("promoted_part_version"),
                }
                for v in versions
            ]
        }
    return versions


@mcp.tool()
async def get_version(ctx: Context, work_id: str, number: int) -> Any:
    """특정 버전의 레시피와 평가 요약."""
    return _slim_version(await _get(ctx, f"/api/works/{work_id}/versions/{number}"))


@mcp.tool()
async def create_work(
    ctx: Context, name: str, recipe: dict[str, Any], description: str = "", note: str = ""
) -> Any:
    """새 작업을 만든다(첫 버전 = 이 레시피, 출처 "ai"). 평가가 끝날 때까지 기다려 요약을
    돌려준다. **`recipe_check` 를 통과한 레시피만 넣는다.**"""
    work = await _post(
        ctx,
        "/api/works",
        {
            "name": name,
            "description": description,
            "recipe": recipe,
            "source": "ai",
            "note": note or "AI 가 만듦",
        },
    )
    if not isinstance(work, dict) or "error" in work:
        return work
    current = work.get("current") or {}
    evaluation = await _wait_job(ctx, current.get("job"))
    return {
        "work_id": work["id"],
        "name": work["name"],
        "version": current.get("number"),
        "evaluation": _slim_job(evaluation),
    }


@mcp.tool()
async def save_version(
    ctx: Context, work_id: str, recipe: dict[str, Any], note: str = ""
) -> Any:
    """작업에 **새 버전**을 저장한다(출처 "ai"). 옛 버전은 그대로 남고 사람이 화면에서 되돌릴
    수 있다. 평가가 끝날 때까지 기다려 요약을 돌려준다. `note` 에 무엇을 바꿨는지 한 줄
    적는다."""
    version = await _post(
        ctx,
        f"/api/works/{work_id}/versions",
        {"recipe": recipe, "source": "ai", "note": note or "AI 가 고침"},
    )
    if not isinstance(version, dict) or "error" in version:
        return version
    evaluation = await _wait_job(ctx, version.get("job"))
    return {
        "work_id": work_id,
        "version": version.get("number"),
        "evaluation": _slim_job(evaluation),
    }


@mcp.tool()
async def restore_version(ctx: Context, work_id: str, number: int) -> Any:
    """옛 버전의 레시피로 새 버전을 만든다(되돌리기)."""
    version = await _post(ctx, f"/api/works/{work_id}/versions/{number}/restore")
    if not isinstance(version, dict) or "error" in version:
        return version
    return {"work_id": work_id, "version": version.get("number"), "restored_from": number}


# --------------------------------------------------------------------------- #
# 지그
# --------------------------------------------------------------------------- #
@mcp.tool()
async def jig_options(ctx: Context) -> Any:
    """지그 생성 옵션의 기본값(판 여유 · 받침 수 · 클램프 수 …). `run_jig` 에 일부만 넘겨도
    된다."""
    return await _get(ctx, "/api/works/jig-options")


@mcp.tool()
async def run_jig(ctx: Context, work_id: str, options: dict[str, Any] | None = None) -> Any:
    """작업의 **현재 부품(버전)**을 제품으로 지그를 만든다. 끝날 때까지 기다려 계획(받침 ·
    로케이터 · 클램프) · 간섭 검사 · 단계별 시간을 돌려준다. 간섭이 있으면 계획의 notes 와
    interference.items 를 읽고 부품이나 옵션을 고쳐 다시 만든다."""
    job = await _post(ctx, f"/api/works/{work_id}/jig-runs", {"options": options or {}})
    return _slim_job(await _wait_job(ctx, job))


@mcp.tool()
async def list_jig_runs(ctx: Context, work_id: str) -> Any:
    """작업의 지그 생성 기록(최근 것부터). 승격할 것을 고를 때 job_id 를 여기서 얻는다."""
    runs = await _get(ctx, f"/api/works/{work_id}/jig-runs")
    if isinstance(runs, list):
        return {
            "runs": [
                {
                    "job_id": r["id"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "interference_ok": (
                        (r.get("summary") or {}).get("interference") or {}
                    ).get("ok"),
                    "error": r.get("error"),
                }
                for r in runs
            ]
        }
    return runs


@mcp.tool()
async def get_job(ctx: Context, job_id: str) -> Any:
    """작업(평가 · 지그 생성) 하나의 상태와 요약."""
    return _slim_job(await _get(ctx, f"/api/jobs/{job_id}"))


# --------------------------------------------------------------------------- #
# 승격 · 카탈로그
# --------------------------------------------------------------------------- #
@mcp.tool()
async def promote_part(
    ctx: Context, work_id: str, name: str | None = None, note: str = ""
) -> Any:
    """현재 부품 버전을 **부품 카탈로그**에 올린다(누구나 본다, 불변). **사용자가 시킬
    때만.**"""
    return await _post(ctx, f"/api/works/{work_id}/promote/part", {"name": name, "note": note})


@mcp.tool()
async def promote_jig(
    ctx: Context, work_id: str, job_id: str, name: str | None = None, note: str = ""
) -> Any:
    """지그 생성 결과 하나를 **지그 카탈로그**에 올린다. 제품(그때의 부품 버전)이 카탈로그에
    없으면 함께 올린다. **사용자가 시킬 때만.**"""
    return await _post(
        ctx,
        f"/api/works/{work_id}/promote/jig",
        {"job_id": job_id, "name": name, "note": note, "promote_product": True},
    )


@mcp.tool()
async def list_parts(ctx: Context, limit: int = 50) -> Any:
    """부품 카탈로그(누구나 보는 것). 고치려면 `copy_part_to_work` 로 내 공간에 복사한다."""
    page = await _get(ctx, "/api/parts", {"limit": limit})
    if isinstance(page, dict) and "items" in page:
        return {"total": page["total"], "parts": page["items"]}
    return page


@mcp.tool()
async def get_part(ctx: Context, part_id: str) -> Any:
    """부품 하나 — 현재 버전의 레시피와 요약."""
    part = await _get(ctx, f"/api/parts/{part_id}")
    if not isinstance(part, dict) or "error" in part:
        return part
    current = part.get("current") or {}
    return {
        "part_id": part["id"],
        "name": part["name"],
        "description": part["description"],
        "current_version": part["current_version"],
        "jig_count": part.get("jig_count"),
        "recipe": current.get("recipe"),
        "evaluation": _slim_job(current.get("job")),
    }


@mcp.tool()
async def copy_part_to_work(ctx: Context, part_id: str, name: str | None = None) -> Any:
    """부품의 레시피로 내 작업을 새로 만든다 — 남의 부품을 고치는 유일한 길."""
    work = await _post(ctx, f"/api/parts/{part_id}/copy-to-work", {"name": name})
    if not isinstance(work, dict) or "error" in work:
        return work
    return {"work_id": work["id"], "name": work["name"], "version": work["current_version"]}


@mcp.tool()
async def list_jigs(ctx: Context, part_id: str | None = None, limit: int = 50) -> Any:
    """지그 카탈로그. `part_id` 를 주면 그 부품의 지그만."""
    params: dict[str, Any] = {"limit": limit}
    if part_id:
        params["part_id"] = part_id
    page = await _get(ctx, "/api/jigs", params)
    if isinstance(page, dict) and "items" in page:
        return {"total": page["total"], "jigs": page["items"]}
    return page


@mcp.tool()
async def get_jig(ctx: Context, jig_id: str) -> Any:
    """지그 하나 — 어느 부품 버전의 지그인지, 계획과 간섭 요약."""
    jig = await _get(ctx, f"/api/jigs/{jig_id}")
    if not isinstance(jig, dict) or "error" in jig:
        return jig
    current = jig.get("current") or {}
    return {
        "jig_id": jig["id"],
        "name": jig["name"],
        "part_id": jig.get("part_id"),
        "part_name": jig.get("part_name"),
        "part_version": current.get("part_version"),
        "current_version": jig["current_version"],
        "options": current.get("options"),
        "summary": current.get("summary"),
    }


if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    mcp.settings.host = host
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8062"))
    if host not in ("127.0.0.1", "localhost", "::1"):
        # FastMCP 는 localhost 로 고정된 DNS rebinding 보호를 켠다 — 다른 주소로 열면 421 이
        # 난다. 허용 Host 를 주거나(권장) 보호를 끈다(사내망 · 방화벽 뒤).
        from mcp.server.transport_security import TransportSecuritySettings

        allowed = [
            h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()
        ]
        mcp.settings.transport_security = (
            TransportSecuritySettings(
                enable_dns_rebinding_protection=True, allowed_hosts=allowed, allowed_origins=[]
            )
            if allowed
            else TransportSecuritySettings(enable_dns_rebinding_protection=False)
        )
    mcp.run(transport="streamable-http")
