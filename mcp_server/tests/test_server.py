"""백엔드 없이 볼 수 있는 것 — 가이드 파싱 · 응답 언래핑 · 요약 줄이기."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
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
    """AI 는 이 가이드만 읽고 레시피를 쓴다 — 좌표로 환산하지 않아도 되는 칸이 적혀 있어야 한다."""
    _, sections = server._guide_sections()
    recipe = sections["recipe"]
    for word in ('radius', 'tangent', 'measure overall|centers', 'triangle', 'sheet_metal'):
        assert word in recipe, word
    assert "via" in recipe and "사람이 캔버스에서 찍을 때" in recipe


def test_사람이_손으로_하는_일이_도구로_다_있다() -> None:
    """화면에서 되는 것은 AI 도 돼야 한다 — 그리기 · 치수 확인 · 저장 · 지그 · 승격 · 템플릿."""
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
        "jig_options",
        "run_jig",
        "promote_part",
        "promote_jig",
        "sweep_parameter",  # 치수를 훑어 고르기
        "beam_frequency",  # 공진 가늠값
        "doe_preview",  # 형상 여러 벌
        "doe_create",
        "doe_points",
        "doe_tradeoff",  # 목표가 맞설 때
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
    ):
        assert word in recipe, word


def test_오류_봉투를_그대로_전한다() -> None:
    response = httpx.Response(
        400,
        json={
            "error": {
                "code": "AJG-CAD-0003",
                "message": "만들지 못했습니다 — f: 반지름",
                "details": {"node_id": "f"},
            }
        },
    )
    got = server._unwrap(response)
    assert got["error"].startswith("[AJG-CAD-0003]") and got["details"]["node_id"] == "f"
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
