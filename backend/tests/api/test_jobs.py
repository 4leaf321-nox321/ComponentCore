"""작업 · 워커 — 인라인이 아니라 **진짜 집기(claim) → 돌리기(execute)** 경로를 본다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.jobs import registry, services
from tests.api.conftest import Signed, make_user


@pytest.fixture
def worker_mode() -> Any:
    """이 시험 동안만 인라인을 끈다 — 걸린 작업이 queued 로 남아야 워커 경로를 볼 수 있다."""
    settings = get_settings()
    before = settings.jobs_inline
    settings.jobs_inline = False
    yield
    settings.jobs_inline = before


BOX = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 60, "height": 40}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 20},
    ]
}


def _work(client: TestClient, who: Signed) -> str:
    got = client.post(
        "/api/works", json={"name": "큐 시험", "recipe": BOX}, headers=who.headers
    )
    assert got.status_code == 201, got.text
    return str(got.json()["id"])


def test_워커가_집어서_돌린다(
    client: TestClient, db: Session, member: Signed, worker_mode: Any
) -> None:
    work = _work(client, member)
    # 형상 평가(cad)가 먼저 queued 로 걸려 있다 — 워커가 그것부터 집는다.
    first = services.claim_next(db, "test-worker")
    assert first is not None and first.kind == "cad"
    services.execute(db, first, worker_id="test-worker")

    queued = client.post(
        "/api/works/jig-from-part", json={"source": f"work:{work}"}, headers=member.headers
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["job"]["status"] == "queued"
    job_id = queued.json()["job"]["id"]

    # 화면이 보는 것 — 아직 진행이 없다.
    seen = client.get(f"/api/jobs/{job_id}", headers=member.headers).json()
    assert seen["status"] == "queued" and seen["progress"] == []

    # 워커의 한 바퀴.
    job = services.claim_next(db, "test-worker")
    assert job is not None and job.id.hex == job_id.replace("-", "")
    assert job.status == "running" and job.attempts == 1
    # 같은 행은 두 번 집히지 않는다.
    assert services.claim_next(db, "other-worker") is None

    done = services.execute(db, job, worker_id="test-worker")
    assert done.status == "done", done.error
    assert len(done.progress) == 8  # 파이프라인 단계 수
    assert done.summary is not None
    assert len(services.artifacts_of(db, done.id)) == 4

    seen = client.get(f"/api/jobs/{job_id}", headers=member.headers).json()
    assert seen["status"] == "done" and len(seen["artifacts"]) == 4
    assert seen["work_name"] == "큐 시험 지그"  # 생성 작업은 새 지그 작업에 매달린다


def test_사람이_읽을_수_있는_실패는_메시지_그대로(
    db: Session, member: Signed, worker_mode: Any
) -> None:
    def broken(
        _: dict[str, Any], __: dict[str, Any], ___: Path, ____: Any
    ) -> registry.Outcome:
        raise registry.UserFacingError("바닥면이 없습니다")

    registry.register("test-broken", broken)
    user = make_user(db, label="q", is_system_admin=False)
    job = services.enqueue(
        db, kind="test-broken", requested_by=user, work_id=None, input={}, options={}
    )
    done = services.execute(db, job, worker_id="t")
    assert done.status == "failed"
    assert done.error == "바닥면이 없습니다"


def test_모르는_종류는_걸_때_거절(db: Session, member: Signed) -> None:
    user = make_user(db, label="k", is_system_admin=False)
    with pytest.raises(KeyError):
        services.enqueue(
            db, kind="nope", requested_by=user, work_id=None, input={}, options={}
        )


def test_갇힌_작업을_되살린다(db: Session, member: Signed, worker_mode: Any) -> None:
    from datetime import UTC, datetime, timedelta

    user = make_user(db, label="s", is_system_admin=False)
    job = services.enqueue(
        db, kind="jig", requested_by=user, work_id=None, input={}, options={}
    )
    job.status = "running"
    job.attempts = 1
    job.started_at = datetime.now(UTC) - timedelta(hours=2)
    db.commit()
    assert services.requeue_stale(db) == 1
    db.refresh(job)
    assert job.status == "queued" and job.worker_id is None

    # 한도를 넘긴 것은 실패로.
    job.status = "running"
    job.attempts = services.MAX_ATTEMPTS
    job.started_at = datetime.now(UTC) - timedelta(hours=2)
    db.commit()
    services.requeue_stale(db)
    db.refresh(job)
    assert job.status == "failed"
