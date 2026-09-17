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
