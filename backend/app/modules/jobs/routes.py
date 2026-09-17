"""작업 · 작업물 라우터 — 종류에 무관한 조회와 내려받기. 거는 것은 각 도메인 라우터가 한다."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.jobs import registry, services
from app.modules.jobs.schemas import ArtifactOut, JobOut
from app.shared.auth import current_user
from app.shared.pagination import Page, clamp_limit

router = APIRouter(tags=["jobs"])


@router.get("/jobs/kinds", response_model=list[str])
def kinds(_: User = Depends(current_user)) -> list[str]:
    return list(registry.known_kinds())


@router.get("/jobs", response_model=Page[JobOut])
def list_jobs(
    mine: bool = Query(default=True, description="내가 건 것만"),
    work_id: uuid.UUID | None = None,
    kind: str | None = None,
    status: str | None = Query(default=None, pattern="^(queued|running|done|failed)$"),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[JobOut]:
    size = clamp_limit(limit)
    # 남의 것을 보려면(mine=false) 관리자여야 한다 — 작업은 내 공간의 것이다.
    if not mine and not user.is_system_admin:
        mine = True
    rows, total = services.list_jobs(
        db,
        requested_by=user.id if mine else None,
        work_id=work_id,
        kind=kind,
        status=status,
        limit=size,
        offset=offset,
    )
    return Page(
        items=[services.job_out(db, one) for one in rows],
        total=total,
        limit=size,
        offset=offset,
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> JobOut:
    """화면이 도는 동안 이것을 폴링한다 — `progress` 가 단계마다 늘어난다."""
    job = services.get_job(db, job_id)
    services.require_visible(db, job, user)
    return services.job_out(db, job)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
def get_artifact(
    artifact_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> ArtifactOut:
    artifact = services.get_artifact(db, artifact_id)
    services.require_artifact_visible(db, artifact, user)
    return ArtifactOut.model_validate(artifact)


@router.get("/artifacts/{artifact_id}/download", response_class=FileResponse)
def download_artifact(
    artifact_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> FileResponse:
    artifact = services.get_artifact(db, artifact_id)
    services.require_artifact_visible(db, artifact, user)
    return FileResponse(
        services.artifact_path(artifact),
        media_type=artifact.content_type,
        filename=artifact.filename,
    )
