"""CompCore MCP 서버 — AI 가 **내 작업**에서 부품을 그리고 지그를 만들게 하는 도구.

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
    claude mcp add --transport http compcore http://127.0.0.1:8062/mcp \\
      --header "Authorization: Bearer compcore_pat_…"
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP, Image

API_BASE = os.environ.get("PLATFORM_API_BASE", "http://127.0.0.1:8060").rstrip("/")

# SSE 를 버퍼링하는 프록시 뒤에서는 단발 JSON 응답으로(StandardPlatform 에서 실측한 함정).
_JSON_RESPONSE = os.environ.get("MCP_JSON_RESPONSE") == "1"

mcp = FastMCP(
    os.environ.get("APP_SLUG", "compcore"),
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


async def _put(ctx: Context, path: str, json_body: Any = None) -> Any:
    async with _client(60) as client:
        return _unwrap(await client.put(path, json=json_body, headers=_forward_headers(ctx)))


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
    브래킷), 그리고 사람이 저장해 둔 템플릿 목록(`saved_templates` — 내 것과 공용).
    새로 그릴 때는 템플릿에서 시작해 고치는 것이 빠르다.

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


@mcp.tool()
async def recipe_geometry(
    ctx: Context, recipe: dict[str, Any], material: str | None = None
) -> Any:
    """만든 형상의 **치수표** — 크기 · 평면(법선 · 넓이) · 원통 · **구멍(지름 · 중심 · 깊이)**.

    사람은 3D 를 보고 자를 대지만 너는 못 본다. 그러니 **그린 뒤에는 이것으로 확인한다**:
    구멍이 뜻한 자리에 뚫렸나, 바닥이 평평한가, 두께가 맞나. 제품을 기준으로 지그를 그릴 때도
    먼저 제품의 치수표를 본다(`part_geometry` · `work_geometry`).

    `material`(steel · aluminum · abs …)을 주면 **질량 · 무게중심 · 관성 모멘트**까지 낸다 —
    무게 중심을 잡거나 진동을 볼 때 쓴다."""
    return await _post(
        ctx, "/api/cad/recipe/geometry", {"recipe": recipe, "material": material}
    )


@mcp.tool()
async def recipe_views(
    ctx: Context,
    recipe: dict[str, Any],
    views: list[str] | None = None,
    width: int = 640,
) -> Any:
    """도면을 **그림으로 본다** — iso · front · top · right 의 은선 투영(보이는 선 실선, 가려진
    선 점선). 네가 그린 것이 뜻대로인지 눈으로 확인하는 유일한 길이다. `recipe_check` 통과 뒤,
    저장 전에 본다. 답은 이미지들과 한 줄 설명."""
    got = await _post(
        ctx,
        "/api/cad/recipe/views",
        {"recipe": recipe, "views": views or ["iso", "front", "top", "right"], "width": width},
    )
    if not isinstance(got, dict) or "error" in got:
        return got
    out: list[Any] = []
    for name, one in got["views"].items():
        out.append(f"[{name}]")
        out.append(Image(data=base64.b64decode(one["png_base64"]), format="png"))
    return out


@mcp.tool()
async def recipe_find(ctx: Context, recipe: dict[str, Any], query: dict[str, Any]) -> Any:
    """말로 고른 **엣지 · 면의 좌표** — 좌표를 짐작하지 않는다. query 예:
    - 윗면 테두리 엣지: `{"what":"edges","of_face_role":"top","kind":"line"}`
    - 지름 8 구멍의 위 원: `{"kind":"circle","radius":4,"near":[20,10,12]}`
    - 옆면들: `{"what":"faces","role":"side"}`
    칸: what(edges|faces) · kind · role(top|bottom|side|step|underside) · of_face_role ·
    axis(x|y|z) · radius · min_length · max_length · near · limit. 답의 `midpoint`(엣지) ·
    `center`(면)를 fillet/chamfer 의 `near`, 스케치의 `plane` 에 그대로 쓴다."""
    return await _post(ctx, "/api/cad/recipe/find", {"recipe": recipe, "query": query})


@mcp.tool()
async def recipe_selectors(ctx: Context, recipe: dict[str, Any], pick: dict[str, Any]) -> Any:
    """찍은 자리를 **말로 되돌려 받는다** — 「아래쪽 면」 · 「반지름 4.25 원통면(4개)」.

    `pick` 은 `{"what": "faces"|"edges"|"vertices", "point": [x, y, z]}`. 답의 후보마다
    `select`(셀렉터)와 `matches`(지금 몇 개에 맞나)가 있다.

    **좌표를 그대로 조건에 박지 마라.** 실험계획이 치수를 바꾸면 그 자리에 아무것도 없다.
    이 셀렉터를 영역 이름표 · 조건에 쓰면 설계점마다 다시 풀린다."""
    return await _post(ctx, "/api/cad/recipe/selectors", {"recipe": recipe, "pick": pick})


@mcp.tool()
async def recipe_measure(
    ctx: Context, recipe: dict[str, Any], a: dict[str, Any], b: dict[str, Any]
) -> Any:
    """둘 사이를 **잰다** — 거리(축별 차) · 평면끼리 각도 · 평행이면 간격 · 점과 평면의 수직
    거리. 선택자: `{"point":[x,y,z]}` · `{"hole_near":[…]}`(구멍 중심 · 지름) ·
    `{"face_near":[…]}` · `{"edge_near":[…]}`. 예: 두께 = 윗면과 바닥면의 gap,
    구멍 간 거리 = 두 hole_near."""
    return await _post(ctx, "/api/cad/recipe/measure", {"recipe": recipe, "a": a, "b": b})


@mcp.tool()
async def patch_work(
    ctx: Context, work_id: str, ops: list[dict[str, Any]], note: str = ""
) -> Any:
    """작업의 현재 도면을 **연산 몇 개로 고쳐 새 버전**으로 — 레시피 전체를 되보내지 않는다.
    연산: `set_param{name,value}` · `remove_param{name}` · `add_node{node,before?}` ·
    `set_field{id,field,value}`(value null 이면 칸 지움) ·
    `remove_node{id}`(가리키는 것이 있으면 거절) · `move_node{id,before?}` ·
    `rename_node{id,new_id}`(가리키는 곳도 따라감).
    고친 도면이 틀리면 저장하지 않고 문제와 고친 레시피를 돌려준다. 끝나면 평가 요약."""
    version = await _post(
        ctx, f"/api/works/{work_id}/patch", {"ops": ops, "note": note or "AI 가 부분 수정"}
    )
    if not isinstance(version, dict) or "error" in version:
        return version
    evaluation = await _wait_job(ctx, version.get("job"))
    return {
        "work_id": work_id,
        "version": version.get("number"),
        "recipe": version.get("recipe"),
        "evaluation": _slim_job(evaluation),
    }


@mcp.tool()
async def place_on(
    ctx: Context,
    work_id: str,
    mover: str,
    onto: str,
    face: str = "top",
    offset: float = 0.0,
    align: str = "center",
    note: str = "",
) -> Any:
    """조립에서 구성품 `mover` 를 `onto` 의 면에 **얹는다** — 「지그 윗면에 부품 바닥을」.
    `face` 는 top|bottom|+x|-x|+y|-y, `offset` 은 띄우는 거리, `align` 은 나머지 두 축(center|
    min|max). 경계 상자로 맞추므로 닿는 면이 평면일 때 정확하다. translate 를 계산해
    새 버전으로 저장하고 값을 돌려준다. 부품 + 생성된 지그는 `assemble_jig_on_part` 가
    더 정확하다."""
    got = await _get(ctx, f"/api/works/{work_id}")
    if not isinstance(got, dict) or "error" in got:
        return got
    current = got.get("current") or {}
    placed = await _post(
        ctx,
        "/api/cad/recipe/place",
        {
            "recipe": current.get("recipe"),
            "mover": mover,
            "onto": onto,
            "face": face,
            "offset": offset,
            "align": align,
        },
    )
    if not isinstance(placed, dict) or "error" in placed:
        return placed
    if placed["problems"]:
        return {"error": "놓은 뒤 도면이 틀립니다", "problems": placed["problems"]}
    saved = await save_version(
        ctx, work_id, placed["recipe"], note or f"{mover} 를 {onto} 의 {face} 에 얹음"
    )
    return {**saved, "translate": placed["translate"]}


@mcp.tool()
async def recipe_interference(
    ctx: Context, recipe: dict[str, Any], tolerance: float | None = None
) -> Any:
    """조립(group)의 **구성품끼리 겹치는가** — 모든 쌍의 겹침 부피(mm³). `ok` 가 False 면
    `items` 에 어느 것과 어느 것이 얼마나 겹치는지 있다. 허용치(기본 0.5 mm³) 이하는 닿은 것.

    조립을 저장하기 전, 그리고 지그를 고친 뒤(받침을 옮기거나 튜닝부를 붙인 뒤) 부른다 — 서버는
    겹친 채로도 저장해 주므로 네가 봐야 한다. DOE 설계점에는 서버가 점마다 붙여 준다
    (`doe_points` 의 `interference`)."""
    return await _post(
        ctx, "/api/cad/recipe/interference", {"recipe": recipe, "tolerance": tolerance}
    )


@mcp.tool()
async def sweep_parameter(
    ctx: Context,
    recipe: dict[str, Any],
    param: str,
    values: list[float],
    material: str | None = None,
) -> Any:
    """치수 하나를 값마다 바꿔 만들어 보고 **치수표를 나란히** 받는다(한 번에 40개까지).

    「연결부는 그대로 두고 두께만 바꿔 가며 고른다」 가 이 한 번으로 된다 — 질량 · 관성 ·
    크기가 어떻게 달라지는지 보고 고른다. 연결부를 이루는 칸에는 그 치수를 **쓰지 않아야**
    안 변한다."""
    return await _post(
        ctx,
        "/api/cad/recipe/sweep",
        {"recipe": recipe, "param": param, "values": values, "material": material},
    )


@mcp.tool()
async def beam_frequency(
    ctx: Context,
    length_mm: float,
    width_mm: float,
    thickness_mm: float | None = None,
    target_hz: float | None = None,
    material: str = "aluminum",
    support: str = "cantilever",
    added_mass_g: float = 0,
) -> Any:
    """납작한 보의 1차 굽힘 공진 **가늠값**, 또는 목표 주파수를 내는 **두께**.

    지그를 세트의 공진에 맞출 때 쓴다: 붙는 부품 무게를 `added_mass_g` 로 주고 목표 Hz 를 주면
    두께가 나온다 → 그 두께로 레시피를 그려 `sweep_parameter` 로 질량을 확인한다.

    **해석이 아니다.** 균일 직사각형 보 · 완전 고정 가정의 닫힌 식이라 ±10% 는 흔하고, 물림이
    무르면 실제는 더 낮다. 응답의 `accuracy` · `warnings` 를 사용자에게 그대로 전한다."""
    return await _post(
        ctx,
        "/api/cad/beam-frequency",
        {
            "length_mm": length_mm,
            "width_mm": width_mm,
            "thickness_mm": thickness_mm,
            "target_hz": target_hz,
            "material": material,
            "support": support,
            "added_mass_g": added_mass_g,
        },
    )


@mcp.tool()
async def conditions_schema(ctx: Context) -> Any:
    """해석 조건에 **어떤 칸이 있는가** — 구속 · 하중 · 접촉 · 초기조건 · 메시 힌트의 종류와
    칸 목록. 조건을 쓰기 전에 이것을 읽어라(레시피 전에 `recipe_schema` 를 읽는 것과 같다)."""
    return await _get(ctx, "/api/cad/conditions/schema")


@mcp.tool()
async def set_conditions(
    ctx: Context, work_id: str, conditions: dict[str, Any], number: int | None = None
) -> Any:
    """작업 버전에 **해석 조건**을 붙인다 — 경계 · 하중 · 접촉 · 초기조건 · 해석 설정 · 물성.

    **조건은 면을 직접 가리키지 않는다.** `named_selections` 에 이름표를 만들고(셀렉터는
    `recipe_selectors` 로 받는다) 조건은 그 이름만 가리킨다. 좌표를 박으면 실험계획이 치수를
    바꾸는 순간 그 자리에 아무것도 없다.

    숫자 칸에는 레시피와 **같은 식**을 쓸 수 있다(`"=압력"`) — 변수는 레시피의 `params` 다.
    그 변수를 실험계획으로 훑으면 형상과 하중이 함께 움직인다.

    새 버전을 만들지 않는다 — 도면이 안 바뀌었으니까. `number` 를 안 주면 현재 버전."""
    if number is None:
        got = await _get(ctx, f"/api/works/{work_id}")
        if not isinstance(got, dict) or "error" in got:
            return got
        number = got["current_version"]
    return await _put(
        ctx, f"/api/works/{work_id}/versions/{number}/conditions", {"conditions": conditions}
    )


@mcp.tool()
async def doe_preview(
    ctx: Context,
    factors: list[dict[str, Any]],
    method: str = "factorial",
    samples: int = 20,
    seed: int = 1,
) -> Any:
    """**만들기 전에** 설계점이 몇 개인지 센다. 격자는 곱으로 늘어난다 —
    인자 넷에 5단계면 625개.

    인자 하나는 `{"name": "두께", "mode": "range", "start": 4, "end": 12, "steps": 5}` 또는
    `{"mode": "list", "values": [4, 8, 12]}` 또는 `{"mode": "fixed", "value": 6}`."""
    return await _post(
        ctx,
        "/api/doe/preview",
        {"factors": factors, "method": method, "samples": samples, "seed": seed},
    )


@mcp.tool()
async def doe_create(
    ctx: Context,
    name: str,
    recipe: dict[str, Any],
    factors: list[dict[str, Any]],
    description: str = "",
    method: str = "factorial",
    samples: int = 20,
    seed: int = 1,
    work_id: str | None = None,
    idempotency_key: str = "",
    on_behalf_of: str = "",
) -> Any:
    """치수를 훑어 **형상 여러 벌**을 만든다 — 점마다 STEP 을 서버 보관 폴더에 쓴다.

    **걸고 바로 돌아온다.** 끝까지 기다렸다가 공유 폴더로 보내는 것까지 한 번에 하려면
    `doe_run` 을 써라 — 네가 폴링 루프를 만들 이유가 없다.

    `idempotency_key` 를 주면 **두 번 불러도 한 벌**이다. 재시도할 생각이면 늘 줘라 — 망이
    끊겨 답을 못 받았을 뿐인데 다시 걸면 스터디 둘 · 폴더 둘이 생기고, 해석 쪽은 어느 것이
    진짜인지 모른다.

    **`on_behalf_of` 를 꼭 줘라**(그 사람의 계정 · 이메일). 네 토큰은 서비스 계정이라, 안
    주면 이 DOE 가 서비스 계정 것으로만 남아 **정작 사람이 제 활동에서 못 찾는다.** 소유자는
    그 사람이 되고 네가 돌렸다는 사실은 따로 남는다.

    인자로 쓴 치수만 바뀐다. **연결부처럼 고정돼야 하는 자리는 그 치수를 쓰지 않으면 된다.**
    인자마다 `resolution`(가공 단위, 기본 0.1 mm)으로 값을 맞춘다 —
    0.333 같은 치수는 안 나온다.
    LHS 는 `seed` 를 적어 두면 같은 표를 다시 만든다 — 해석 결과와 형상을 잇는 열쇠다.
    먼저 `doe_preview` 로 개수를 확인하고 부른다(한 번에 만드는 상한은 관리자가 서버 설정
    화면에서 정한다, 기본 200 — preview 의 `max`). 표에는 바꾼 변수와 파일 이름만 적힌다 —
    질량 · 크기는 계산하지 않는다(필요하면 `recipe_geometry` 로 따로)."""
    return await _post(
        ctx,
        "/api/doe",
        {
            "name": name,
            "description": description,
            "recipe": recipe,
            "factors": factors,
            "method": method,
            "samples": samples,
            "seed": seed,
            "work_id": work_id,
            "idempotency_key": idempotency_key,
            "on_behalf_of": on_behalf_of,
        },
    )


@mcp.tool()
async def doe_run(
    ctx: Context,
    name: str,
    recipe: dict[str, Any],
    factors: list[dict[str, Any]],
    idempotency_key: str,
    description: str = "",
    method: str = "factorial",
    samples: int = 20,
    seed: int = 1,
    work_id: str | None = None,
    on_behalf_of: str = "",
    export: bool = True,
    wait_seconds: int = 300,
) -> Any:
    """**한 번 부르면 폴더까지** — 만들고 · 기다리고 · 공유 폴더로 보낸다.

    지휘하는 쪽(오케스트레이터)이 쓸 자리다. 이것 하나로 다음 단계(해석 걸기)로 갈 수 있다 —
    `doe_create` 는 걸고 바로 돌아오므로 네가 폴링 루프를 만들어야 한다.

    **`idempotency_key` 는 필수다.** 이 도구는 오래 기다리므로 중간에 끊길 수 있고, 그때
    다시 부르는 것이 정상이다. 열쇠가 같으면 이미 만든 것을 이어서 본다 — 없으면 끊길
    때마다 스터디가 하나씩 는다.

    답: `folder`(해석이 여는 경로 — 아직 못 보냈으면 None) · `points` · `done` · `failed` ·
    `job`. **안 끝나도 답은 온다**(`wait_seconds` 가 다 되면 그때 상태로). 그 경우 보내지
    않으니 — 만들다 만 폴더를 해석이 읽으면 안 된다 — `doe_status` 로 끝을 보고
    `doe_export` 를 부른다.

    **`on_behalf_of` 를 꼭 줘라**(그 사람의 계정 · 이메일) — 안 주면 사람이 제 활동에서 이
    DOE 를 못 찾는다. `export=false` 면 만들기만 한다(조건만 바꿔 가며 쌓아 둘 때).
    """
    query = f"?wait_seconds={wait_seconds}&export={'true' if export else 'false'}"
    got = await _post(
        ctx,
        f"/api/doe/run{query}",
        {
            "name": name,
            "description": description,
            "recipe": recipe,
            "factors": factors,
            "method": method,
            "samples": samples,
            "seed": seed,
            "work_id": work_id,
            "idempotency_key": idempotency_key,
            "on_behalf_of": on_behalf_of,
        },
    )
    if not isinstance(got, dict) or "error" in got:
        return got
    return {
        "study_id": got["id"],
        "name": got["name"],
        "owner": got.get("owner_name"),
        "folder": got["export_dir_windows"] or None,
        "files_ready": got.get("local_ready", True),
        "points": got["point_count"],
        "done": got["done"],
        "failed": got["failed"],
        "job": _slim_job(got.get("job")),
    }


@mcp.tool()
async def doe_status(ctx: Context, study_id: str) -> Any:
    """**진행만** — 끝났나 · 몇 점 됐나 · 폴더는 어디인가. 설계점 표는 안 준다.

    `doe_points` 는 설계점 200줄을 통째로 준다. 「끝났나」 만 보려고 그것을 되풀이해 받지
    마라 — 여기는 세는 것만 한다.

    `files_ready` 가 거짓이면 보관 기한이 지나 파일이 치워진 것이다(`doe_rerun` 으로 되살린다).
    """
    return await _get(ctx, f"/api/doe/{study_id}/status")


@mcp.tool()
async def doe_wait(ctx: Context, study_id: str, seconds: int = 30) -> Any:
    """끝날 때까지 **기다려 준다**(한 번에 최대 2분). 끝났든 시간이 다 됐든 지금 상태를 준다.

    `doe_run` 을 썼는데 시간 안에 안 끝났을 때 이어서 기다리는 자리다. `waited_out` 이 참이면
    아직 도는 중이니 다시 부르면 된다 — 1초마다 `doe_status` 를 두드리지 마라.
    """
    return await _post(ctx, f"/api/doe/{study_id}/wait?seconds={seconds}", None)


@mcp.tool()
async def doe_points(ctx: Context, study_id: str) -> Any:
    """만들어진 설계점 표 — 바꾼 변수 값 · STEP · **점 파일**(영역 · 풀린 조건) · 실패 사유,
    **공유 폴더 경로**(`folder`, 아직 안 보냈으면 None — `doe_export` 로 보낸다).

    해석 **결과는 여기 없다** — 이 플랫폼은 형상 · 영역 · 조건 · 설계점을 만들어 넘기고,
    결과와 설계점 고르기는 해석 플랫폼이 한다."""
    got = await _get(ctx, f"/api/doe/{study_id}")
    if not isinstance(got, dict) or "error" in got:
        return got
    return {
        "study_id": got["id"],
        "name": got["name"],
        "folder": got["export_dir_windows"] or None,
        "exported_at": got.get("exported_at"),
        # 서버 보관 폴더에 파일이 남아 있나. False 면 보관 기한이 지나 치워진 것이라
        # `doe_export` 가 막힌다 — `doe_rerun` 으로 먼저 되살린다.
        "files_ready": got.get("local_ready", True),
        "method": got["method"],
        "seed": got["seed"],
        "points_total": got["point_count"],
        "done": got["done"],
        "failed": got["failed"],
        "job": _slim_job(got.get("job")),
        "points": [
            {
                "number": one["number"],
                "params": one["params"],
                "status": one["status"],
                "interference": one.get("interference"),
                "step_file": one["step_file"],
                "point_file": one.get("point_file"),
                "error": one["error"],
            }
            for one in got.get("points", [])
        ],
    }


@mcp.tool()
async def doe_rerun(ctx: Context, study_id: str, only: str = "all") -> Any:
    """**다시 만들기** — 스냅샷으로 설계점 파일(STEP · 점 파일)을 되살린다. 같은 스터디다.

    언제 부르나:

    - `doe_points` 의 `files_ready` 가 False 일 때. 보관 기한이 지나 파일이 치워진 것이고,
      그 상태로는 `doe_export` 가 막힌다. 이것을 먼저 부르고 끝나면 보낸다.
    - 실패한 점을 한 번 더 해 볼 때 — `only="failed"`.

    **같은 재료로 같은 것이 나온다**(레시피 · 인자 · 시드 · 조건이 스냅샷으로 박혀 있다).
    범위를 고쳐 다시 돌리는 것은 이것이 아니다 — 그건 `doe_create` 로 새 스터디다.

    작업을 걸고 **바로** 돌아온다. 끝났는지는 `doe_points` 의 `job` 으로 본다."""
    if only not in ("all", "failed"):
        return {"error": "only 는 all 또는 failed 입니다."}
    got = await _post(ctx, f"/api/doe/{study_id}/rerun?only={only}", None)
    if not isinstance(got, dict) or "error" in got:
        return got
    return {
        "study_id": got["id"],
        "name": got["name"],
        "only": only,
        "points_total": got["point_count"],
        "job": _slim_job(got.get("job")),
    }


@mcp.tool()
async def doe_export(ctx: Context, study_id: str) -> Any:
    """만들어진 설계점(STEP · manifest.csv)을 **공유 폴더로 보낸다** — 해석은 그때부터 읽는다.

    만들기는 서버 보관 폴더에 먼저 하고, 다 끝난 뒤 보낸다(반쪽짜리 표를 해석이 읽지 않게).
    다시 부르면 같은 폴더에 덮어쓴다. 답의 `folder` 가 해석 쪽이 여는 경로(F:\\…)다."""
    got = await _post(ctx, f"/api/doe/{study_id}/export", None)
    if not isinstance(got, dict) or "error" in got:
        return got
    return {
        "study_id": got["id"],
        "folder": got["export_dir_windows"],
        "exported_at": got["exported_at"],
    }


@mcp.tool()
async def doe_release(ctx: Context, study_id: str) -> Any:
    """해석이 **다 읽었다** — 공유 폴더를 먼저 치워도 된다고 알린다.

    「성공했다」 가 아니라 **「더 안 읽는다」** 는 뜻이다. 실패해서 다시 돌릴 생각이면 부르지
    마라 — 알린 폴더는 보관 기한을 기다리지 않고 치워진다.

    치워지는 것은 **공유 폴더의 사본뿐**이다. 레시피 · 설계점 · 조건은 남아서 `doe_export` 를
    다시 부르면 같은 폴더가 다시 선다."""
    return await _post(ctx, f"/api/doe/{study_id}/release", None)


@mcp.tool()
async def doe_keep(ctx: Context, study_id: str, keep: bool = True) -> Any:
    """**영구보관** — 보관 기한이 지나도 **두 폴더를 다 남긴다.**

    공유 폴더(기본 30일)와 서버 보관 폴더(기본 180일) 모두에 걸린다 — 한쪽만 켜게 하면
    나머지가 조용히 사라지는 날이 온다. 기한은 기본값이고 이것이 예외다.

    「이건 남겨야 한다」 를 아는 사람(또는 너)이 켠다. 안 켜도 잃는 것은 파일뿐이고
    `doe_rerun` 이 되살리지만, 수천 점이면 그 시간이 아깝다."""
    flag = "true" if keep else "false"
    return await _post(ctx, f"/api/doe/{study_id}/keep?keep={flag}", None)


@mcp.tool()
async def doe_studies(
    ctx: Context, work_id: str | None = None, limit: int = 20, scope: str = "mine"
) -> Any:
    """실험계획 목록 — 무엇을 언제 훑었나.

    `scope="mine"`(기본) 은 네 토큰의 계정 것, `"all"` 은 **공개된 것까지**. 남이 이미 같은
    훑기를 돌았는지 보려면 `all` 로 찾아라 — 같은 것을 다시 도는 것이 가장 큰 낭비다."""
    query: dict[str, Any] = {"limit": limit, "scope": scope}
    if work_id:
        query["work_id"] = work_id
    page = await _get(ctx, "/api/doe", query)
    if isinstance(page, dict) and "items" in page:
        return {"total": page["total"], "studies": page["items"]}
    return page


@mcp.tool()
async def work_geometry(ctx: Context, work_id: str, number: int | None = None) -> Any:
    """내 작업(제품)의 치수표와 레시피, 그리고 **STEP 작업물 id**.

    그 id 를 `{"op": "import_step", "file": "<id>"}` 에 넣으면 **제품 형상 자체를 지그 레시피
    안에 불러올 수 있다** — 제품을 여유만큼 키워(`offset`) 블록에서 빼면 곧 포켓이다."""
    base = f"/api/works/{work_id}"
    path = base if number is None else f"{base}/versions/{number}"
    got = await _get(ctx, path)
    if not isinstance(got, dict) or "error" in got:
        return got
    version = got if number is not None else got.get("current")
    return await _with_geometry(ctx, version, {"work_id": work_id})


@mcp.tool()
async def part_geometry(ctx: Context, part_id: str, number: int | None = None) -> Any:
    """부품 카탈로그의 제품 — 치수표 · 레시피 · **STEP 작업물 id**.

    **지그 설계는 보통 여기서 시작한다**: 부품을 고르고 치수표를 읽어 받침 · 핀 · 클램프 자리를
    정한다. 자동 설계는 `copy_part_to_work` → `run_jig`, 손으로 그리려면 STEP 을 불러와
    (`import_step`) 빼고 더한다."""
    path = f"/api/parts/{part_id}" if number is None else f"/api/parts/{part_id}/versions"
    got = await _get(ctx, path)
    if not isinstance(got, dict) or "error" in got:
        return got
    version = got.get("current")
    if number is not None and isinstance(got, list):  # pragma: no cover - 방어
        version = next((v for v in got if v.get("number") == number), None)
    return await _with_geometry(ctx, version, {"part_id": part_id, "name": got.get("name")})


async def _with_geometry(ctx: Context, version: Any, head: dict[str, Any]) -> Any:
    """버전 하나를 레시피 · 치수표 · STEP id 로 묶는다."""
    if not isinstance(version, dict) or "recipe" not in version:
        return {**head, "error": "평가된 버전이 없습니다 — 먼저 저장하고 평가를 기다리세요."}
    geometry = await _post(ctx, "/api/cad/recipe/geometry", {"recipe": version["recipe"]})
    job = _slim_job(version.get("job"))
    artifacts = job.get("artifacts", []) if isinstance(job, dict) else []
    step = next((a["id"] for a in artifacts if a.get("kind") == "model_step"), None)
    return {
        **head,
        "number": version.get("number"),
        "recipe": version["recipe"],
        "geometry": geometry,
        "step_artifact_id": step,
        "how_to_use_step": (
            '{"op": "import_step", "file": "<step_artifact_id>"} 로 이 형상을 다른 레시피에서 '
            "불러온다 — 제품을 지그 안에 두고 빼는 방식."
        ),
    }


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
async def search(ctx: Context, query: str, limit: int = 10) -> Any:
    """이름 · 설명으로 **한꺼번에 찾는다** — 내 작업(부품 · 지그 · 조립) · 공용 부품 ·
    공용 지그 · 템플릿. 사용자가 「센서 브래킷」 「진동」 처럼 말하면 목록을 다 훑지 말고
    이것부터. 답의 id 를 `work:<id>` · `part:<id>` · `jig:<id>` 로 다른 도구에 넘긴다."""
    works, parts, jigs, templates = await asyncio.gather(
        _get(ctx, "/api/works", {"q": query, "limit": limit}),
        _get(ctx, "/api/parts", {"q": query, "limit": limit}),
        _get(ctx, "/api/jigs", {"q": query, "limit": limit}),
        _get(ctx, "/api/templates", {"q": query, "limit": limit}),
    )

    def rows(page: Any, kind: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        if not isinstance(page, dict) or "items" not in page:
            return []
        return [{"kind": kind, **{f: one.get(f) for f in fields}} for one in page["items"]]

    return {
        "query": query,
        "works": rows(works, "work", ("id", "name", "kind", "current_version", "tags")),
        "parts": rows(parts, "part", ("id", "name", "current_version")),
        "jigs": rows(jigs, "jig", ("id", "name", "current_version", "part_name")),
        "templates": rows(templates, "template", ("id", "name", "mine")),
    }


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
    ctx: Context,
    name: str,
    recipe: dict[str, Any],
    description: str = "",
    note: str = "",
    kind: str = "part",
    jig_for_part_id: str | None = None,
) -> Any:
    """새 작업을 만든다(첫 버전 = 이 레시피, 출처 "ai"). 평가가 끝날 때까지 기다려 요약을
    돌려준다. **`recipe_check` 를 통과한 레시피만 넣는다.**

    `kind` 는 **무엇을 그렸나**다: `part`(제품 · 부품) 또는 `jig`(지그). 그리는 방법은 같고,
    종류가 **어느 카탈로그로 올라가는지**와 덤으로 쓰는 도구를 정한다(부품엔 지그 생성기,
    지그엔 잡는 부품). 지그를 그렸으면 `kind="jig"` 로 만들고 `jig_for_part_id` 로 어느 부품을
    잡는지 이어 둔다 — 승격할 때 그대로 따라간다."""
    work = await _post(
        ctx,
        "/api/works",
        {
            "name": name,
            "description": description,
            "recipe": recipe,
            "source": "ai",
            "note": note or "AI 가 만듦",
            "kind": kind,
            "jig_for_part_id": jig_for_part_id,
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
async def jig_preview(ctx: Context, source: str, options: dict[str, Any] | None = None) -> Any:
    """부품에서 지그를 **만들기 전에** 어떻게 놓이는지 본다 — 계획(받침 · 위치 핀/받침대 ·
    클램프 자리) · 간섭 · 부품 크기. 작업도 파일도 안 생긴다. 옵션을 바꿔 가며 몇 번 보고
    `run_jig` 로 만든다. 메시는 크니 돌려주지 않는다."""
    got = await _post(
        ctx, "/api/works/jig-from-part/preview", {"source": source, "options": options or {}}
    )
    if isinstance(got, dict) and "mesh" in got:
        return {k: v for k, v in got.items() if k != "mesh"}
    return got


@mcp.tool()
async def run_jig(
    ctx: Context,
    source: str,
    options: dict[str, Any] | None = None,
    name: str | None = None,
) -> Any:
    """부품에서 **지그 작업을 생성**한다. `source` 는 `work:<내 부품 작업 id>` 또는
    `part:<공용 부품 id>`. `options.kind` 가 형식이다(`jig_options` 로 기본값과 칸 이름):
    - `clamped`(기본) 판 · 받침 · 위치 핀 · 클램프 — 3-2-1 원칙의 고정구
    - `bolted` 부품의 수직 관통 구멍으로 볼트를 넣어 판에 조인다 — 진동 · 충격 시험
      (`bolt_max_count` · `bolt_head` hex|socket · `bolt_washer` · `bolt_spacer_height`)
    - `bending` 3점 굽힘 — 긴 변으로 스팬(`bending_span_ratio` 또는 `bending_span`), 롤러 둘 +
      로딩 노즈
    - `drop` 낙하 · 충격 자세 — `drop_orientation`(bottom|top|+x|-x|+y|-y|edge|corner) 이
      아래를 보게 놓고 바닥 · `drop_impactor`(none|ball|pen)
    먼저 `jig_preview` 로 계획 · 간섭을 보고 부른다.

    지그 작업이 새로 생기고(kind=jig, 잡는 부품이 이어진다), 결과가 **변수 있는 레시피**로 그
    첫 버전이 된 채로 돌아온다 — `판_두께` · `받침_높이` · `스팬` 같은 변수가 이미 있어
    `assemble_jig_on_part` → `doe_create` 로 바로 훑고, `patch_work` 로 받침을 옮기거나
    튜닝부를 붙인다.
    간섭이 있으면 `job.summary.interference.items` 와 계획의 notes 를 읽고 옵션을 고쳐 다시
    만든다(새 지그 작업이 또 생긴다 — 지난 것은 사용자가 내 작업에서 지운다)."""
    made = await _post(
        ctx,
        "/api/works/jig-from-part",
        {"source": source, "options": options or {}, "name": name},
    )
    if not isinstance(made, dict) or "error" in made:
        return made
    work_id = made["work"]["id"]
    job = await _wait_job(ctx, made["job"])
    out: dict[str, Any] = {
        "work_id": work_id,
        "name": made["work"]["name"],
        "job": _slim_job(job),
    }
    if isinstance(job, dict) and job.get("status") == "done":
        adopted = await _post(ctx, f"/api/works/{work_id}/jig-runs/{job['id']}/adopt", None)
        if isinstance(adopted, dict) and "number" in adopted:
            out["version"] = adopted["number"]
    return out


@mcp.tool()
async def assemble_jig_on_part(
    ctx: Context, part_source: str, jig_work_id: str, name: str | None = None
) -> Any:
    """부품과 지그를 **맞는 자리에** 놓은 **조립 작업**을 만든다 — 좌표 계산을 네가 안 한다.

    `part_source` 는 `work:<내 부품 작업 id>` 또는 `part:<공용 부품 id>`, `jig_work_id` 는 지그
    작업(kind=jig). 생성기(`run_jig`)로 만든 지그는 그 좌표계(부품 XY 중심이 원점, 판 윗면이
    z=0, 부품은 받침 높이만큼 뜸)로 정확히 놓고(`placement.mode="generated"`), 손으로 그린
    지그는 윗면에 얹어 어림한다(`"guessed"` — 사용자에게 확인을 받아라). 부품 높이는 변수
    `부품_높이` 로 들어가 있어 그대로 `doe_create(work_id=<조립>)` 로 훑을 수 있다. 다른 변수를
    심으려면 `get_work` → 레시피를 고쳐 `save_version`."""
    got = await _post(
        ctx,
        "/api/works/assemble",
        {"part_source": part_source, "jig_work_id": jig_work_id, "name": name},
    )
    if not isinstance(got, dict) or "error" in got:
        return got
    work = got["work"]
    return {
        "work_id": work["id"],
        "name": work["name"],
        "kind": work["kind"],
        "version": work.get("current_version"),
        "placement": got["placement"],
        "recipe": (work.get("current") or {}).get("recipe"),
    }


@mcp.tool()
async def list_jig_runs(ctx: Context, work_id: str) -> Any:
    """지그 작업의 생성 기록(최근 것부터) — 계획 · 간섭 검사 결과를 되짚을 때."""
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
async def promote_jig_recipe(
    ctx: Context,
    work_id: str,
    name: str | None = None,
    note: str = "",
    part_id: str | None = None,
) -> Any:
    """지그 작업의 현재 버전을 **지그 카탈로그**로. **사용자가 시킬 때만.**

    지그 작업은 두 길로 생긴다: (1) `run_jig` 가 부품에서 만들어 주는 것, (2) 사람 · AI 가 빈
    화면에서 **그리는** 것. 어느 쪽이든 올리는 길은 이것 하나다. `part_id` 를 주면 어느 부품의
    지그인지 이어진다(생성한 것은 이미 이어져 있다)."""
    return await _post(
        ctx,
        f"/api/works/{work_id}/promote/jig-recipe",
        {"name": name, "note": note, "part_id": part_id},
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
