"""작업 로직 — 걸기(enqueue) · 집기(claim) · 돌리기(execute) · 조회.

`execute` 는 워커가 부르지만 **요청 안에서도 부를 수 있다**(`JOBS_INLINE`). 시험과 워커 없는
작은 설치가 그 길을 쓴다. 두 길이 같은 함수를 지나므로 "워커에서는 되는데 인라인에서는 안
되는" 차이가 안 생긴다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.accounts.models import User
from app.modules.jobs import registry
from app.modules.jobs.models import Artifact, Job
from app.modules.jobs.schemas import ArtifactOut, JobOut, StageOut
from app.modules.works.models import Work
from app.shared import filestore
from app.shared.errors import Forbidden, NotFound, code

logger = logging.getLogger(__name__)

#: 이보다 오래 `running` 인 작업은 워커가 죽은 것으로 보고 다시 건다.
STALE_AFTER = timedelta(minutes=30)
MAX_ATTEMPTS = 2


def _now() -> datetime:
    return datetime.now(UTC)


# --- 조회 ---------------------------------------------------------------------


def artifacts_of(db: Session, job_id: uuid.UUID) -> list[Artifact]:
    return list(
        db.scalars(select(Artifact).where(Artifact.job_id == job_id).order_by(Artifact.kind))
    )


def job_out(db: Session, job: Job) -> JobOut:
    requester = db.get(User, job.requested_by_id) if job.requested_by_id else None
    work = db.get(Work, job.work_id) if job.work_id else None
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        requested_by_id=job.requested_by_id,
        requested_by_name=requester.display_name if requester else None,
        work_id=job.work_id,
        work_name=work.name if work else None,
        options=job.options,
        progress=[StageOut(**one) for one in job.progress],
        summary=job.summary,
        error=job.error,
        artifacts=[ArtifactOut.model_validate(one) for one in artifacts_of(db, job.id)],
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def get_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound(code("JOBS", 1), "작업을 찾을 수 없습니다.")
    return job


def list_jobs(
    db: Session,
    *,
    requested_by: uuid.UUID | None,
    work_id: uuid.UUID | None,
    kind: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Job], int]:
    query = select(Job)
    if requested_by is not None:
        query = query.where(Job.requested_by_id == requested_by)
    if work_id is not None:
        query = query.where(Job.work_id == work_id)
    if kind:
        query = query.where(Job.kind == kind)
    if status:
        query = query.where(Job.status == status)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(db.scalars(query.order_by(Job.created_at.desc()).limit(limit).offset(offset)))
    return rows, total


def get_artifact(db: Session, artifact_id: uuid.UUID) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if artifact is None:
        raise NotFound(code("JOBS", 2), "작업물을 찾을 수 없습니다.")
    return artifact


def artifact_path(artifact: Artifact) -> Path:
    path = filestore.resolve(artifact.path)
    if not path.exists():
        raise NotFound(code("JOBS", 3), "작업물 파일이 저장소에서 사라졌습니다.")
    return path


# --- 걸기 ---------------------------------------------------------------------


def enqueue(
    db: Session,
    *,
    kind: str,
    requested_by: User | None,
    work_id: uuid.UUID | None,
    input: dict[str, Any],
    options: dict[str, Any],
) -> Job:
    """작업을 건다. **종류가 등록돼 있는지 여기서 본다** — 워커가 집어 들고 나서 모르는
    종류라고 실패하면, 사람은 「왜 실패했나」 를 목록에서 찾아야 한다."""
    registry.resolve(kind)
    job = Job(
        kind=kind,
        status="queued",
        requested_by_id=requested_by.id if requested_by else None,
        work_id=work_id,
        input=input,
        options=options,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if get_settings().jobs_inline:
        execute(db, job, worker_id="inline")
    return job


# --- 집기 ---------------------------------------------------------------------


def claim_next(db: Session, worker_id: str) -> Job | None:
    """queued 하나를 running 으로 바꿔 가져온다. 여러 워커가 같은 행을 집지 않게 잠근다.

    `SKIP LOCKED` — 다른 워커가 잠근 행은 건너뛴다. 이것이 없으면 두 번째 워커는 첫 워커가
    커밋할 때까지 서고, 워커를 늘린 뜻이 없어진다.
    """
    picked = db.execute(
        text(
            "SELECT id FROM jobs WHERE status = 'queued' "
            "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
    ).scalar()
    if picked is None:
        db.commit()
        return None
    db.execute(
        update(Job)
        .where(Job.id == picked)
        .values(
            status="running", worker_id=worker_id, started_at=_now(), attempts=Job.attempts + 1
        )
    )
    db.commit()
    job = db.get(Job, picked)
    assert job is not None
    return job


def requeue_stale(db: Session) -> int:
    """워커가 죽어 `running` 에 갇힌 작업을 되살린다. 시도 횟수를 넘긴 것은 실패로 적는다."""
    cutoff = _now() - STALE_AFTER
    stale = list(
        db.scalars(select(Job).where(Job.status == "running", Job.started_at < cutoff))
    )
    for job in stale:
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "failed"
            job.error = "워커가 응답하지 않아 중단됐습니다(재시도 한도)."
            job.finished_at = _now()
        else:
            job.status = "queued"
            job.worker_id = None
            job.started_at = None
    db.commit()
    return len(stale)


# --- 돌리기 -------------------------------------------------------------------


def execute(db: Session, job: Job, *, worker_id: str) -> Job:
    """실행 함수를 부르고 결과를 적는다. **실패도 기록이다.**"""
    if job.status != "running":
        job.status = "running"
        job.worker_id = worker_id
        job.started_at = _now()
        job.attempts += 1
        db.commit()

    out_dir = filestore.new_dir("jobs", job.kind)
    job.output_dir = filestore.relative_to_root(out_dir)
    job.progress = []
    db.commit()

    def progress(name: str, millis: int, detail: str) -> None:
        # 새 리스트로 갈아 끼운다 — JSONB 는 제자리 변경을 못 알아챈다.
        job.progress = [*job.progress, {"name": name, "millis": millis, "detail": detail}]
        db.commit()

    try:
        outcome = registry.resolve(job.kind)(job.input, job.options, out_dir, progress)
    except registry.UserFacingError as failure:
        job.status = "failed"
        job.error = str(failure)
        logger.warning("작업 실패 (%s %s): %s", job.kind, job.id, failure)
    except Exception as failure:
        job.status = "failed"
        job.error = f"실행 중 오류: {type(failure).__name__}: {failure}"
        logger.exception("작업 중 예외 (%s %s)", job.kind, job.id)
    else:
        job.status = "done"
        job.summary = outcome.summary
        for spec in outcome.artifacts:
            db.add(
                Artifact(
                    job_id=job.id,
                    work_id=job.work_id,
                    owner_id=job.requested_by_id,
                    kind=spec.kind,
                    filename=spec.path.name,
                    path=filestore.relative_to_root(spec.path),
                    content_type=spec.content_type,
                    size_bytes=spec.path.stat().st_size,
                )
            )
    job.finished_at = _now()
    db.commit()
    db.refresh(job)
    return job


def _is_promoted(db: Session, job_id: uuid.UUID) -> bool:
    """이 작업이 카탈로그(부품 · 지그 버전)에 실려 있나 — 그러면 누구나 본다."""
    from app.modules.jigs.models import JigVersion
    from app.modules.parts.models import PartVersion

    in_parts = db.scalar(select(PartVersion.id).where(PartVersion.job_id == job_id).limit(1))
    if in_parts is not None:
        return True
    in_jigs = db.scalar(select(JigVersion.id).where(JigVersion.job_id == job_id).limit(1))
    return in_jigs is not None


def _work_owner(db: Session, work_id: uuid.UUID | None) -> uuid.UUID | None:
    if work_id is None:
        return None
    work = db.get(Work, work_id)
    return work.owner_id if work else None


def require_visible(db: Session, job: Job, user: User) -> None:
    """**작업(work)이 곧 공간이다.** 그 작업의 소유자(와 관리자)가 본다. 카탈로그에 승격된
    결과는 누구나 본다 — 부품 · 지그 화면이 그것을 내려받는다."""
    if user.is_system_admin or job.requested_by_id == user.id:
        return
    if _work_owner(db, job.work_id) == user.id:
        return
    if _is_promoted(db, job.id):
        return
    raise Forbidden(code("JOBS", 4), "이 작업을 볼 권한이 없습니다.")


def require_artifact_visible(db: Session, artifact: Artifact, user: User) -> None:
    if user.is_system_admin or artifact.owner_id == user.id:
        return
    if _work_owner(db, artifact.work_id) == user.id:
        return
    if artifact.job_id is not None and _is_promoted(db, artifact.job_id):
        return
    raise Forbidden(code("JOBS", 5), "이 작업물을 볼 권한이 없습니다.")
