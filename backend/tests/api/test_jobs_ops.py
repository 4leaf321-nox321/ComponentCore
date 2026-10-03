"""운영 — 작업 멈추기와 워커 상태.

멈추기는 **단계 사이에서** 한다(돌던 계산을 자르지 않는다). 대기 중이면 바로 취소, 도는 중이면
요청을 적고 워커가 다음 단계에서 본다. 워커는 따로 도는 줄에서 살아 있다는 신호를 적고, 신호가
끊긴 워커가 잡은 작업은 30분을 기다리지 않고 되살린다.
"""

from __future__ import annotations

import csv
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.accounts.models import User
from app.modules.jobs import registry, services
from app.modules.jobs.models import Job, WorkerBeat
from tests.api.conftest import Signed, _login, make_user
from tests.api.test_doe import JIG

#: 단계를 셋 밟는 가짜 일 — 단계마다 진행을 적는다(그때 취소를 본다).
STEPS = ("읽기", "계획", "쓰기")


def _three_steps(
    input: dict[str, Any], options: dict[str, Any], out_dir: Path, progress: registry.Progress
) -> registry.Outcome:
    del options, out_dir
    for name in STEPS:
        progress(name, 1, f"{name} 끝")
        if input.get("cancel_after") == name:
            # 사람이 이 단계 뒤에 멈추라고 했다 — 다른 요청이 적는 것과 같다.
            from app.database import SessionLocal

            with SessionLocal() as other:
                other.execute(
                    update(Job)
                    .where(Job.id == uuid.UUID(input["job"]))
                    .values(cancel_requested_at=datetime.now(UTC))
                )
                other.commit()
    return registry.Outcome(summary={"steps": len(STEPS)})


if "test_three_steps" not in registry.known_kinds():
    registry.register("test_three_steps", _three_steps)


@pytest.fixture
def queued() -> Iterator[None]:
    """작업을 걸어도 바로 돌지 않게 — 워커가 집기 전의 모습."""
    settings = get_settings()
    before = settings.jobs_inline
    settings.jobs_inline = False
    yield
    settings.jobs_inline = before


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _user(db: Session, who: Signed) -> User:
    found = db.scalar(select(User).where(User.email == who.email))
    assert found is not None
    return found


def _enqueue(db: Session, who: Signed, **input: Any) -> Job:
    return services.enqueue(
        db,
        kind="test_three_steps",
        requested_by=_user(db, who),
        work_id=None,
        input=input,
        options={},
    )


def test_대기_중이면_바로_취소하고_워커는_집지_않는다(
    client: TestClient, db: Session, member: Signed, queued: None
) -> None:
    job = _enqueue(db, member)
    assert job.status == "queued"
    got = client.post(f"/api/jobs/{job.id}/cancel", headers=member.headers)
    assert got.status_code == 200, got.text
    assert got.json()["status"] == "cancelled" and got.json()["finished_at"]
    db.expire_all()
    assert services.claim_next(db, "시험:1") is None
    # 끝난 것은 다시 못 멈춘다.
    again = client.post(f"/api/jobs/{job.id}/cancel", headers=member.headers)
    assert again.status_code == 400 and "이미 끝난" in again.json()["error"]["message"]


def test_도는_작업은_다음_단계에서_멈춘다(
    client: TestClient, db: Session, member: Signed, queued: None
) -> None:
    job = _enqueue(db, member)
    # 「읽기」 를 마친 뒤 사람이 멈춘다 — 워커는 다음 단계(「계획」)를 적으며 그것을 본다.
    job.input = {"job": str(job.id), "cancel_after": "읽기"}
    db.commit()
    claimed = services.claim_next(db, "시험:1")
    assert claimed is not None and claimed.id == job.id
    done = services.execute(db, claimed, worker_id="시험:1")
    assert done.status == "cancelled"
    assert "계획 끝 에서 멈췄습니다" in (done.error or "")
    # 멈추기 전까지의 단계는 남는다 — 어디까지 했는지 안다.
    assert [one["name"] for one in done.progress] == ["읽기", "계획"]
    shown = client.get(f"/api/jobs/{job.id}", headers=member.headers).json()
    assert shown["status"] == "cancelled" and shown["cancel_requested_at"]


def test_멈추는_것은_건_사람_주인_관리자뿐이다(
    client: TestClient, db: Session, member: Signed, admin: Signed, queued: None
) -> None:
    job = _enqueue(db, member)
    stranger = make_user(db, label="stranger", is_system_admin=False)
    headers = {"Authorization": f"Bearer {_login(client, stranger.email)}"}
    assert client.post(f"/api/jobs/{job.id}/cancel", headers=headers).status_code == 403
    assert client.post(f"/api/jobs/{job.id}/cancel", headers=admin.headers).status_code == 200


def test_DOE_를_멈추면_만든_점은_남기고_다시_만들기가_잇는다(
    client: TestClient, db: Session, member: Signed, queued: None
) -> None:
    made = client.post(
        "/api/doe",
        json={
            "name": "멈출 DOE",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [4, 6, 8, 10]}],
            "conditions": {},
        },
        headers=member.headers,
    ).json()
    job = services.claim_next(db, "시험:1")
    assert job is not None and str(job.id) == made["job"]["id"]

    # 첫 점을 마치고 진행을 적는 순간 사람이 멈춘다.
    real = services._cancel_requested
    seen: list[int] = []

    def after_first(session: Session, job_id: uuid.UUID) -> bool:
        seen.append(1)
        return len(seen) >= 2  # 시작 전(1)에는 아니고, 첫 점을 적은 뒤(2) 멈춘다

    services._cancel_requested = after_first  # type: ignore[assignment]
    try:
        services.execute(db, job, worker_id="시험:1")
    finally:
        services._cancel_requested = real

    study = client.get(f"/api/doe/{made['id']}", headers=member.headers).json()
    assert study["job"]["status"] == "cancelled"
    assert [p["status"] for p in study["points"]] == ["ok", "pending", "pending", "pending"]
    # 표는 온전하다 — 못 만든 점도 제 줄이 있다.
    manifest = client.get(f"/api/doe/{made['id']}/manifest.csv", headers=member.headers).text
    rows = list(csv.DictReader(manifest.lstrip("﻿").splitlines()))
    assert [row["status"] for row in rows] == ["ok", "pending", "pending", "pending"]
    assert study["local_ready"] is True

    # 「실패한 점만 다시」 가 남은 점을 잇는다.
    settings = get_settings()
    settings.jobs_inline = True
    again = client.post(f"/api/doe/{made['id']}/rerun?only=failed", headers=member.headers)
    assert again.status_code == 200, again.text
    finished = client.get(f"/api/doe/{made['id']}", headers=member.headers).json()
    assert finished["done"] == 4 and finished["job"]["status"] == "done"


def test_DOE_멈추기는_소유자의_자리에서(
    client: TestClient, db: Session, member: Signed, queued: None
) -> None:
    made = client.post(
        "/api/doe",
        json={
            "name": "대기 DOE",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [4, 6]}],
            "conditions": {},
        },
        headers=member.headers,
    ).json()
    got = client.post(f"/api/doe/{made['id']}/cancel", headers=member.headers)
    assert got.status_code == 200, got.text
    assert got.json()["job"]["status"] == "cancelled"


def test_워커_신호와_줄을_보여_주고_신호가_끊긴_워커의_작업은_되살린다(
    client: TestClient, db: Session, member: Signed, admin: Signed, queued: None
) -> None:
    job = _enqueue(db, member)
    claimed = services.claim_next(db, "살아있음:1")
    assert claimed is not None
    services.beat(
        db, "살아있음:1", state="busy", current_job_id=claimed.id, hostname="h", pid=1
    )
    _enqueue(db, member)  # 줄에 하나 더

    got = client.get("/api/server/workers", headers=admin.headers)
    assert got.status_code == 200, got.text
    body = got.json()
    mine = next(one for one in body["workers"] if one["id"] == "살아있음:1")
    assert mine["state"] == "busy" and mine["job"]["id"] == str(job.id)
    assert (
        body["queue"]["queued"] >= 1 and body["queue"]["running"] >= 1 and body["alive"] >= 1
    )
    assert client.get("/api/server/workers", headers=member.headers).status_code == 403

    # 신호가 3분 끊겼다 — 죽은 것으로 보고 작업을 되살린다(30분을 안 기다린다).
    row = db.get(WorkerBeat, "살아있음:1")
    assert row is not None
    row.last_seen_at = datetime.now(UTC) - timedelta(minutes=3)
    db.commit()
    lost = next(
        one
        for one in client.get("/api/server/workers", headers=admin.headers).json()["workers"]
        if one["id"] == "살아있음:1"
    )
    assert lost["state"] == "lost" and lost["job"] is None
    assert services.requeue_stale(db) >= 1
    db.refresh(claimed)
    assert claimed.status == "queued" and claimed.worker_id is None


def test_워커는_따로_도는_줄에서_신호를_적는다(db: Session) -> None:
    import threading
    import time

    from app.worker import Worker

    worker = Worker()
    worker.state = "busy"
    beater = threading.Thread(target=worker._beat, daemon=True)
    beater.start()
    try:
        deadline = time.monotonic() + 10
        row = None
        while time.monotonic() < deadline:
            db.expire_all()
            row = db.get(WorkerBeat, worker.worker_id)
            if row is not None:
                break
            time.sleep(0.1)
        assert row is not None and row.state == "busy" and row.pid > 0
    finally:
        worker._beating.set()
        beater.join(timeout=5)
