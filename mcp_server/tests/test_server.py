"""백엔드 없이 볼 수 있는 것 — 가이드 파싱 · 응답 언래핑 · 요약 줄이기."""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import server


def test_가이드에_주제가_있다() -> None:
    version, sections = server._guide_sections()
    assert version
    assert {"overview", "recipe", "workflow", "jig"} <= set(sections)
    got = asyncio.run(server.get_guide(SimpleNamespace(), None))
    assert got["topic"] == "overview" and "recipe" in got["more_topics"]
    bad = asyncio.run(server.get_guide(SimpleNamespace(), "nope"))
    assert "error" in bad


def test_말로_받은_치수를_넣을_칸을_가이드가_알려준다() -> None:
    """AI 는 이 가이드만 읽고 레시피를 쓴다 —
    좌표로 환산하지 않아도 되는 칸이 적혀 있어야 한다."""
    _, sections = server._guide_sections()
    recipe = sections["recipe"]
    for word in (
        "radius",
        "tangent",
        "measure overall|centers",
        "triangle",
        "sheet_metal",
        "`bend`",
        "until: end",
    ):
        assert word in recipe, word
    assert "via" in recipe and "사람이 캔버스에서 찍을 때" in recipe


def test_사람이_손으로_하는_일이_도구로_다_있다() -> None:
    """화면에서 되는 것은 AI 도 돼야 한다 —
    그리기 · 치수 확인 · 저장 · 지그 · 승격 · 템플릿."""
    tools = {name for name in dir(server) if not name.startswith("_")}
    needed = {
        "recipe_schema",  # 무엇을 만들 수 있나
        "recipe_check",  # 만들어 보기
        "recipe_geometry",  # 잰다 — 사람의 측정 창에 해당
        "template_recipe",
        "save_template",
        "create_work",
        "save_version",
        "restore_version",
        "work_geometry",
        "part_geometry",  # 제품을 기준으로 지그 그리기
        "copy_part_to_work",
        "copy_jig_to_work",  # 남의 지그를 내 것으로 — 조건까지
        "set_standard_part",  # 규격 사양 — 관리자
        "export_standard_parts",  # 규격 부품 묶음 — 개발 PC 에서
        "import_standard_parts",  # 운영 서버로 — 미리 보기 먼저
        "list_test_presets",  # 시험 규격 — 공개 · 사내
        "create_specimen_work",  # 규격으로 시편 · 시험 지그 · 해석 조건
        "apply_product_test",  # 제품에 정하중 · 방향 하중 · 압착 · 수압 · 가속도 · 진동 등
        "save_test_preset",  # 사내 규격 — 관리자
        "delete_test_preset",
        "jig_options",
        "run_jig",
        "promote_part",
        "sweep_parameter",  # 치수를 훑어 고르기
        "beam_frequency",  # 공진 가늠값
        "doe_preview",  # 형상 여러 벌
        "doe_create",
        "doe_points",
        "doe_export",  # 다 만든 뒤 공유 폴더로
        "assemble_jig_on_part",  # 부품 + 지그를 맞는 자리에
        "recipe_interference",  # 구성품끼리 겹치는가
        "recipe_views",  # 그림으로 본다
        "recipe_find",  # 엣지 · 면 · 점 좌표
        "recipe_selectors",  # 찍은 자리를 셀렉터로
        "recipe_cutlist",  # 프레임의 절단 목록
        "conditions_schema",  # 해석 조건의 칸
        "set_conditions",  # 해석 조건 붙이기
        "doe_release",  # 해석이 다 읽었다
        "doe_keep",  # 영구보관
        "recipe_measure",  # 재기
        "patch_work",  # 부분 수정
        "jig_check",  # 지그 요소마다 제품과의 간섭
        "place_on",  # 면에 얹기
        "search",  # 이름으로 찾기
        "promote_jig_recipe",  # 손으로 그린 지그
        "condition_material_search",  # 조건에 붙일 재료 찾기
        "condition_material_get",  # 재료 받기 — 조건에 넣을 항목까지
        "recipe_bodies",  # 물성을 붙일 바디
        "doe_run",  # 조건까지 실어 폴더로
        "doe_probe",  # 끝 점 미리 만들어 보기
        "doe_extend",  # 점 더하기
        "doe_clone",  # 남의 DOE 를 내 것으로 — 이어서 하기
        "list_folders",  # 폴더 나무
        "move_to_folder",  # 골라 옮기기
        "rename_folder",  # 폴더 이름 바꾸기 · 지우기
        "list_tags",  # 꼬리표
        "update_work",  # 이름 · 꼬리표 · 폴더
        "duplicate_work",  # 복제
        "delete_work",  # 휴지통
        "restore_work",  # 되살리기
        "list_templates",  # 템플릿 공간
        "update_template",  # 공용으로 내놓기 · 옮기기
        "copy_template",  # 남의 것을 내 것으로
        "update_catalog_item",  # 부품 · 지그 이름 · 폴더
        "cancel_job",  # 멈추기
        "doe_cancel",  # DOE 멈추기 — 만든 점은 남긴다
        "worker_status",  # 워커가 살아 있나 · 줄
        "recipe_unfold",  # 판금 전개도
        "recipe_drawing",  # 2D 도면 — 세 뷰 · 치수 · 구멍표
        "find_by_shape",  # 형상으로 찾기 — 새로 그리기 전에
        "find_similar",  # 닮은 형상 — 비슷한 부품의 지그까지
        "recipe_midsurface",  # 셸 해석용 중간면
        "sketch_solve",  # 구속 윤곽 풀어 보기
    }
    assert needed <= tools, f"빠진 도구: {sorted(needed - tools)}"


def test_가이드가_파라메트릭과_지그_시작을_알려준다() -> None:
    _, sections = server._guide_sections()
    recipe = sections["recipe"]
    for word in (
        "params",
        "align",
        "part_geometry",
        "step_artifact_id",
        "recipe_geometry",
        "beam_frequency",
        "sweep_parameter",
        "모달 해석이 없다",  # 못 하는 것을 숨기지 않는다
        "doe_create",
        "공유 폴더",
        '"mates"',  # 조립 구속 — 치수가 바뀌어도 따라 앉는다
        "corner_relief",  # 상자 날개
        "`deform`",  # 비틀기 · 테이퍼
        "`constrained`",  # 구속 윤곽
        "`thicken`",  # 곡면에 두께
        "free_rotation",
    ):
        assert word in recipe, word


def test_오류_봉투를_그대로_전한다() -> None:
    response = httpx.Response(
        400,
        json={
            "error": {
                "code": "CCR-CAD-0003",
                "message": "만들지 못했습니다 — f: 반지름",
                "details": {"node_id": "f"},
            }
        },
    )
    got = server._unwrap(response)
    assert got["error"].startswith("[CCR-CAD-0003]") and got["details"]["node_id"] == "f"
    assert server._unwrap(httpx.Response(204)) == {"ok": True, "message": "완료"}


def test_작업_요약은_큰_것을_뺀다() -> None:
    job = {
        "id": "j",
        "kind": "jig",
        "status": "done",
        "error": None,
        "summary": {"interference": {"ok": True}},
        "artifacts": [
            {"id": "a", "kind": "jig_step", "filename": "jig.step", "size_bytes": 1}
        ],
        "progress": [{"name": "load"}],
    }
    slim = server._slim_job(job)
    assert slim["job_id"] == "j" and "progress" not in slim
    assert slim["artifacts"] == [{"kind": "jig_step", "id": "a", "filename": "jig.step"}]


def test_폴링은_error_null_을_오류로_읽지_않는다(monkeypatch) -> None:
    """작업 응답은 `"error": null` 을 늘 든다 — 그것을 오류 봉투로 보면 running 인 채로
    돌아온다."""
    states = iter(
        [
            {"id": "j", "kind": "jig", "status": "running", "error": None},
            {
                "id": "j",
                "kind": "jig",
                "status": "done",
                "error": None,
                "summary": {"ok": 1},
                "artifacts": [],
            },
        ]
    )

    async def fake_get(ctx, path, params=None):
        return next(states)

    real_sleep = asyncio.sleep

    async def no_sleep(_seconds: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr(server, "_get", fake_get)
    monkeypatch.setattr(server.asyncio, "sleep", no_sleep)
    got = asyncio.run(
        server._wait_job(
            SimpleNamespace(), {"id": "j", "kind": "jig", "status": "queued", "error": None}
        )
    )
    assert got["status"] == "done" and got["summary"] == {"ok": 1}


def test_물성과_바디_도구가_있다() -> None:
    """물성을 지어내지 않게 — 찾고, 받고, 붙일 바디를 안다."""
    for name in ("condition_material_search", "condition_material_get", "recipe_bodies"):
        assert hasattr(server, name), name


def test_재료_도구는_MatNexus_와_이름이_헷갈리지_않는다() -> None:
    """HWAX 게이트웨이는 앱마다의 도구를 한 목록에 편다. 옛 이름 `material_search` ·
    `material_get` 은 MatNexus 의 `search_materials` · `get_material` 과 낱말 순서만
    달라 나란히 보였다(ADR 0009)."""
    for old in ("material_search", "material_get", "search_materials", "get_material"):
        assert not hasattr(server, old), old


def test_재료_도구는_조건용이라고_먼저_말하고_물성_질문은_MatNexus_로_보낸다() -> None:
    for tool in (server.condition_material_search, server.condition_material_get):
        doc = tool.__doc__ or ""
        first = doc.strip().splitlines()[0]
        assert "해석 조건" in first and "물성을 묻는 질문의 답이 아니다" in first, first
        assert "get_material" in doc and "CompCore 설치의" in doc, tool.__name__


def test_재료_찾기_결과가_어디서_왔는지_말한다(monkeypatch) -> None:
    live = {
        "items": [
            {"code": "M-000158", "name": "AL5052", "source": "matnexus", "payload": {"x": 1}}
        ],
        "fallback": False,
    }

    async def fake_get(ctx, path, params=None):
        return live

    monkeypatch.setattr(server, "_get", fake_get)
    got = asyncio.run(server.condition_material_search(SimpleNamespace(), "AL5052"))
    assert "payload" not in got["items"][0]
    origin = got["origin"]
    assert origin["canonical"] == "MatNexus" and origin["copy"] is False
    assert "부르는 사람의 MatNexus 권한이 아니다" in origin["via"]
    assert "search_materials" in origin["use_for"] and "copy_note" not in origin

    # MatNexus 에 못 닿으면 올려 둔 카탈로그 — 사본이라고 말한다.
    live = {
        "items": [{"code": "M-000158", "name": "AL5052", "source": "catalog", "payload": {}}],
        "fallback": True,
        "detail": "MatNexus 에 닿지 못했습니다.",
    }
    got = asyncio.run(server.condition_material_search(SimpleNamespace(), "AL5052"))
    assert got["origin"]["copy"] is True and "사본" in got["origin"]["copy_note"]
    assert got["origin"]["detail"] == "MatNexus 에 닿지 못했습니다."


def test_재료_하나_결과도_어디서_왔는지_말한다(monkeypatch) -> None:
    row = {
        "id": "u-1",
        "code": "M-000158",
        "name": "AL5052",
        "source": "catalog",
        "payload": {},
    }

    async def fake_get(ctx, path, params=None):
        return row

    monkeypatch.setattr(server, "_get", fake_get)
    got = asyncio.run(server.condition_material_get(SimpleNamespace(), "M-000158"))
    assert got["condition_item"]["ref"]["code"] == "M-000158"
    assert got["origin"]["canonical"] == "MatNexus" and got["origin"]["copy"] is True

    row = {**row, "source": "matnexus"}
    got = asyncio.run(server.condition_material_get(SimpleNamespace(), "M-000158"))
    assert got["origin"]["copy"] is False


def test_버전의_재료_값은_고른_날의_사본이라고_말한다() -> None:
    picked = {
        "apply_to": ["블록"],
        "ref": {
            "source": "matnexus",
            "code": "M-000158",
            "name": "AL5052",
            "fetched_at": "2026-10-01T00:00:00+00:00",
        },
        "payload": {"density": 2680},
    }
    slim = server._slim_version(
        {"number": 1, "recipe": {}, "conditions": {"materials": [picked]}}
    )
    snapshot = slim["materials_snapshot"]
    assert snapshot["items"] == [
        {
            "code": "M-000158",
            "name": "AL5052",
            "source": "matnexus",
            "fetched_at": "2026-10-01T00:00:00+00:00",
        }
    ]
    assert "사본" in snapshot["note"] and "get_material" in snapshot["note"]
    # 재료가 없으면 표시도 없다 — 빈 표시가 「사본이 있다」 로 읽히지 않게.
    bare = server._slim_version({"number": 1, "recipe": {}, "conditions": {"loads": [1]}})
    assert "materials_snapshot" not in bare


def test_재료_한_줄은_화면이_싣는_모양으로_조건에_들어간다() -> None:
    row = {
        "id": "u-1",
        "code": "M-000158",
        "name": "AL5052",
        "source": "matnexus",
        "payload": {"density": 2680},
    }
    item = server._condition_item(row)
    assert item["apply_to"] == [] and item["payload"] == {"density": 2680}
    assert item["ref"]["source"] == "matnexus" and item["ref"]["code"] == "M-000158"
    literature = server._condition_item({**row, "source": "literature"})
    assert literature["ref"]["source"] == "matnexus-literature"


def test_버전_요약에_해석_조건이_있다() -> None:
    slim = server._slim_version({"number": 3, "recipe": {}, "conditions": {"loads": [1]}})
    assert slim["conditions"] == {"loads": [1]}


def test_DOE_는_조건을_안_주면_보내지_않아_서버가_작업의_조건을_싣는다(monkeypatch) -> None:
    import asyncio

    sent: list[dict] = []

    async def fake_post(ctx, path, json_body=None):
        sent.append(json_body)
        return {"id": "s"}

    monkeypatch.setattr(server, "_post", fake_post)
    asyncio.run(server.doe_create(None, name="a", recipe={}, factors=[], work_id="w"))
    asyncio.run(
        server.doe_create(None, name="b", recipe={}, factors=[], conditions={"loads": []})
    )
    assert "conditions" not in sent[0]
    assert sent[1]["conditions"] == {"loads": []}


def test_끊기면_예외가_아니라_오류_봉투로_무엇을_할지_말한다(monkeypatch) -> None:
    import asyncio

    import httpx

    def hang(request):
        raise httpx.ReadTimeout("느림", request=request)

    monkeypatch.setattr(server, "_TRANSPORT", httpx.MockTransport(hang))
    got = asyncio.run(server._post(None, "/api/doe/run", {}))
    assert got["error"].startswith("[MCP-TIMEOUT]") and "doe_status" in got["error"]
    assert got["retryable"] is True

    def refuse(request):
        raise httpx.ConnectError("거절", request=request)

    monkeypatch.setattr(server, "_TRANSPORT", httpx.MockTransport(refuse))
    assert asyncio.run(server._get(None, "/api/health"))["error"].startswith(
        "[MCP-UNREACHABLE]"
    )


def test_오래_기다리는_DOE_는_서버가_기다리는_것보다_길게_연결을_둔다(monkeypatch) -> None:
    import asyncio

    seen: list[float] = []

    async def fake_post(ctx, path, json_body=None, *, timeout=120):
        seen.append(timeout)
        return {"error": "그만"}

    monkeypatch.setattr(server, "_post", fake_post)
    asyncio.run(server.doe_run(None, "a", {}, [], "k", wait_seconds=900))
    asyncio.run(server.doe_wait(None, "s", seconds=600))
    assert seen[0] > 900 and seen[1] > 600


def test_결과에_화면에서_열기_링크를_붙인다(monkeypatch) -> None:
    work = {
        "id": "w1",
        "name": "판",
        "description": "",
        "current_version": 2,
        "current": None,
    }

    async def fake_get(ctx, path, params=None):
        return work if path == "/api/works/w1" else {"error": "[CCR-WORKS-0001] 없음"}

    monkeypatch.setattr(server, "_get", fake_get)
    # 주소를 모르면 붙이지 않는다(단독 설치의 기본).
    assert "url" not in asyncio.run(server.get_work(None, "w1"))

    monkeypatch.setattr(server, "_PUBLIC_URL", "https://portal.test/compcore")
    assert asyncio.run(server.get_work(None, "w1"))["url"] == (
        "https://portal.test/compcore/works/w1"
    )
    # 오류는 그대로 — 링크를 붙여 성공처럼 보이게 하지 않는다.
    assert "url" not in asyncio.run(server.get_work(None, "nope"))


def test_화면_주소는_백엔드에서_배우고_실패는_기억하지_않는다(monkeypatch) -> None:
    calls = []

    def health(request):
        calls.append(request.url.path)
        if len(calls) == 1:
            raise httpx.ConnectError("아직 안 뜸", request=request)
        return httpx.Response(200, json={"status": "ok", "public_url": "https://p.test/cc/"})

    monkeypatch.setattr(server, "_TRANSPORT", httpx.MockTransport(health))
    monkeypatch.setattr(server, "_public_seen", None)
    assert asyncio.run(server._public_url()) == ""
    assert asyncio.run(server._public_url()) == "https://p.test/cc"
    assert asyncio.run(server._public_url()) == "https://p.test/cc"
    assert calls == ["/api/health", "/api/health"]


def test_공용_부품의_해석_조건은_복사와_등록에_따라간다(monkeypatch) -> None:
    sent: list[tuple[str, dict]] = []

    async def fake_post(ctx, path, json_body=None):
        sent.append((path, json_body))
        if path.endswith("/copy-to-work"):
            return {
                "id": "w2",
                "name": "판 (복사)",
                "current_version": 1,
                "current": {"conditions": {"constraints": [{"name": "고정"}]}},
            }
        return {"part_id": "p1", "number": 1}

    monkeypatch.setattr(server, "_post", fake_post)
    copied = asyncio.run(server.copy_part_to_work(None, "p1"))
    assert copied["has_conditions"] is True
    asyncio.run(server.copy_part_to_work(None, "p1", with_conditions=False))
    asyncio.run(server.promote_part(None, "w1"))
    asyncio.run(server.promote_part(None, "w1", with_conditions=False))
    assert [body["conditions"] for _, body in sent] == [True, False, True, False]


def test_공용_지그도_복사와_등록에_해석_조건이_따라간다(monkeypatch) -> None:
    sent: list[tuple[str, dict]] = []

    async def fake_post(ctx, path, json_body=None, **kw):
        sent.append((path, json_body))
        if path.endswith("/copy-to-work"):
            return {
                "id": "w3",
                "name": "받침 지그 (복사)",
                "current_version": 1,
                "current": {},
            }
        return {"jig_id": "j1", "jig_version": 1}

    monkeypatch.setattr(server, "_post", fake_post)
    copied = asyncio.run(server.copy_jig_to_work(None, "j1"))
    assert copied["has_conditions"] is False and sent[0][0] == "/api/jigs/j1/copy-to-work"
    asyncio.run(server.promote_jig_recipe(None, "w1", with_conditions=False))
    assert [body["conditions"] for _, body in sent] == [True, False]


def test_지그를_고치면_제품과의_간섭을_함께_돌려준다(monkeypatch) -> None:
    async def fake_post(ctx, path, json_body=None, **kw):
        if path.endswith("/patch"):
            return {"number": 2, "recipe": {}, "job": None}
        return {
            "available": True,
            "ok": False,
            "parts": ["바닥판", "받침_1", "제품"],
            "items": [
                {"a": "받침_1", "b": "제품", "volume": 12.5, "ok": False},
                {"a": "바닥판", "b": "받침_1", "volume": 0.0, "ok": True},
            ],
        }

    async def no_wait(ctx, job):
        return job

    monkeypatch.setattr(server, "_post", fake_post)
    monkeypatch.setattr(server, "_wait_job", no_wait)
    got = asyncio.run(server.patch_work(None, "w1", [{"op": "set_param"}]))
    assert got["jig_interference"] == {
        "ok": False,
        "hits": [{"a": "받침_1", "b": "제품", "volume": 12.5}],
        "parts": ["바닥판", "받침_1", "제품"],
    }

    async def not_jig(ctx, path, json_body=None, **kw):
        if path.endswith("/patch"):
            return {"number": 2, "recipe": {}, "job": None}
        return {"available": False, "reason": "지그 작업이 아닙니다."}

    monkeypatch.setattr(server, "_post", not_jig)
    assert "jig_interference" not in asyncio.run(server.patch_work(None, "w1", []))


# --- HWAX 게이트웨이: 401 은 다시 받기 신호로(SP ADR 0028 결정 12) ---------------------

GATEWAY_TOKEN_REJECTED = re.compile(
    r"^Error executing tool \S+: (?:GET|POST|PUT|PATCH|DELETE) \S+ → HTTP 401\b"
)


def _gateway_serve(monkeypatch: pytest.MonkeyPatch, answer: Any) -> list[httpx.Request]:
    """CompCore 도구(`server`)와 옮긴 기준정보 도구(`ontology`) 모두 가짜 백엔드로."""
    import ontology

    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(request)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(server, "_TRANSPORT", transport)
    monkeypatch.setattr(ontology, "_TRANSPORT", transport)
    return seen


def _through_fastmcp(name: str, arguments: dict[str, Any], authorization: str) -> Any:
    """게이트웨이가 보는 그대로 — FastMCP 의 도구 호출 처리기(`tools/call`)를 거친 결과.
    도구에서 난 예외를 FastMCP 가 어떻게 감싸는지까지 이 길에서 돈다."""
    from mcp import types
    from mcp.server.lowlevel.server import request_ctx
    from mcp.shared.context import RequestContext

    handler = server.mcp._mcp_server.request_handlers[types.CallToolRequest]
    request = SimpleNamespace(headers={"authorization": authorization})
    held = request_ctx.set(
        RequestContext(
            request_id=1, meta=None, session=None, lifespan_context=None, request=request
        )
    )
    try:
        got = asyncio.run(
            handler(
                types.CallToolRequest(
                    method="tools/call",
                    params=types.CallToolRequestParams(name=name, arguments=arguments),
                )
            )
        )
    finally:
        request_ctx.reset(held)
    return got.root


def _text(result: Any) -> str:
    """게이트웨이가 읽는 글 — 내용 조각을 이어 붙여 앞뒤 공백을 뗀 것."""
    return "".join(getattr(one, "text", "") or "" for one in result.content).strip()


def test_백엔드가_토큰을_거절하면_게이트웨이가_다시_받는_모양으로_실패한다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """401 은 결과(`{"error": …}`)가 아니라 **오류**로 — 문구가 게이트웨이의 정규식에 맞아야
    게이트웨이가 위임 토큰을 새로 받아 한 번 다시 부른다. 읽는 도구 · 쓰는 도구 · 본문이 JSON
    이 아닌 401 · 옮긴 기준정보 도구(`ontology.py` · `ontology_links.py`) · 글로 받는 도구
    (`rdf_schema`) 모두 같다."""
    seen = _gateway_serve(
        monkeypatch,
        lambda _r: httpx.Response(
            401,
            json={"error": {"code": "CCR-AUTH-0001", "message": "토큰이 유효하지 않습니다."}},
        ),
    )
    got = _through_fastmcp("doe_status", {"study_id": "s1"}, "Bearer old")
    assert got.isError is True
    text = _text(got)
    assert GATEWAY_TOKEN_REJECTED.match(text), text
    # 경로는 물음표 앞까지 — 서버의 말은 그대로다.
    assert text == (
        "Error executing tool doe_status: GET /api/doe/s1/status → HTTP 401: "
        "[CCR-AUTH-0001] 토큰이 유효하지 않습니다."
    )
    assert seen[0].headers["authorization"] == "Bearer old"

    # 쓰는 도구(POST) · 본문이 JSON 이 아닌 401 도 같다.
    _gateway_serve(monkeypatch, lambda _r: httpx.Response(401, text="Unauthorized"))
    got = _through_fastmcp("doe_export", {"study_id": "s1"}, "Bearer t")
    assert got.isError is True and GATEWAY_TOKEN_REJECTED.match(_text(got)), _text(got)
    assert _text(got).startswith("Error executing tool doe_export: POST /api/doe/s1/export")

    # 옮긴 기준정보 도구 · CompCore 의 기준정보 칸 · 글로 받는 RDF 도 같은 길이다.
    for name, arguments in (
        ("ontology_schema", {}),
        ("ontology_links", {"kind": "part", "id": "p1"}),
        ("rdf_schema", {}),
    ):
        got = _through_fastmcp(name, arguments, "Bearer t")
        assert got.isError is True, name
        assert GATEWAY_TOKEN_REJECTED.match(_text(got)), (name, _text(got))


def test_401_이_아닌_오류는_결과로_전한다(monkeypatch: pytest.MonkeyPatch) -> None:
    """권한 없음(403) · 검증(422) 은 토큰 문제가 아니다 — 게이트웨이가 다시 받으면 같은 일이
    두 번 돈다. 결과로 그대로 전해 Claude 가 서버의 말을 읽는다."""
    for status in (403, 404, 409, 422, 500):
        _gateway_serve(
            monkeypatch,
            lambda _r, status=status: httpx.Response(
                status, json={"error": {"code": "CCR-X-0001", "message": "안 됩니다"}}
            ),
        )
        for name, arguments in (("doe_status", {"study_id": "s1"}), ("ontology_schema", {})):
            got = _through_fastmcp(name, arguments, "Bearer t")
            assert got.isError is False, (status, name)
            assert not GATEWAY_TOKEN_REJECTED.match(_text(got))
            assert "[CCR-X-0001] 안 됩니다" in _text(got), (status, name)


#: 이름만 보고도 지움 · 되돌리기 · 멈춤인 도구 — 새로 생기면 위험 목록에 들어 있어야 한다.
_DESTRUCTIVE_WORDS = (
    "delete",
    "remove",
    "cancel",
    "undo",
    "merge",
    "restore",
    "unlink",
    "purge",
)
#: 이름은 그렇지만 지우지 않는 것 — 까닭과 함께.
_NOT_DESTRUCTIVE = {
    "restore_version": "옛 판을 새 판으로 세운다 — 이력은 그대로 남는다",
    "restore_work": "지운 작업을 되살린다",
}


def test_위험_도구는_실제_도구이고_이름이_그런_것은_빠짐없다() -> None:
    """HWAX 게이트웨이에 범용 실행기 차단을 요청하는 목록(SP ADR 0028 결정 13) — 없는 이름을
    적으면 요청이 헛돌고, 새 지우기 도구를 빠뜨리면 그 도구는 게이트웨이의 이름 규칙(`delete_`
    로 **시작**)에도 안 걸린다."""
    tools = {one.name for one in asyncio.run(server.mcp.list_tools())}
    assert tools >= server.DESTRUCTIVE_TOOLS, server.DESTRUCTIVE_TOOLS - tools
    named = {
        one
        for one in tools
        if any(word in one for word in _DESTRUCTIVE_WORDS) and one not in _NOT_DESTRUCTIVE
    }
    assert named <= server.DESTRUCTIVE_TOOLS, named - server.DESTRUCTIVE_TOOLS
