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
