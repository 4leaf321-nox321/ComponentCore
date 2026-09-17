"""내 작업 라우터 — 전부 소유자(또는 관리자)만. 목록은 내 것만 나온다."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.jobs import services as jobs
from app.modules.jobs.schemas import JobOut
from app.modules.parts import services as parts
from app.modules.parts.schemas import PartVersionOut
from app.modules.works import services
from app.modules.works.models import Work
from app.modules.works.schemas import (
    JigRunRequest,
    PromoteJigOut,
    PromoteJigRequest,
    PromotePartRequest,
    VersionCreateRequest,
    VersionOut,
    WorkCreateRequest,
    WorkOut,
    WorkSummaryOut,
    WorkUpdateRequest,
)
from app.shared.auth import current_user
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/works", tags=["works"])


@router.get("/jig-options", response_model=dict[str, object])
def jig_options(_: User = Depends(current_user)) -> dict[str, object]:
    """지그 옵션 기본값 — 화면 폼의 초깃값. 손으로 두 벌 적지 않는다."""
    from app.core.options import JigOptions

    return dict(JigOptions().to_dict())


def _mine(db: Session, work_id: uuid.UUID, user: User) -> Work:
    work = services.get_work(db, work_id)
    services.require_owner(work, user)
    return work


@router.get("", response_model=Page[WorkSummaryOut])
def list_works(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[WorkSummaryOut]:
    size = clamp_limit(limit)
    rows, total = services.list_works(db, owner=user, limit=size, offset=offset)
    return Page(
        items=[services.work_summary(db, one) for one in rows],
        total=total,
        limit=size,
        offset=offset,
    )


@router.post("", response_model=WorkOut, status_code=201)
def create_work(
    payload: WorkCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkOut:
    work = services.create_work(
        db,
        owner=user,
        name=payload.name,
        description=payload.description,
        recipe=payload.recipe,
        source=payload.source,
        note=payload.note,
    )
    return services.work_out(db, work)


@router.post("/from-step", response_model=WorkOut, status_code=201)
def create_work_from_step(
    name: str = Form(default=""),
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkOut:
    """STEP 파일에서 작업을 시작한다 — 첫 버전이 `import_step` 노드 하나다."""
    filename = file.filename or "import.step"
    work = services.create_work_from_step(
        db,
        owner=user,
        name=name.strip() or filename.rsplit(".", 1)[0],
        filename=filename,
        stream=file.file,
    )
    return services.work_out(db, work)


@router.get("/{work_id}", response_model=WorkOut)
def get_work(
    work_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> WorkOut:
    return services.work_out(db, _mine(db, work_id, user))


@router.patch("/{work_id}", response_model=WorkOut)
def update_work(
    work_id: uuid.UUID,
    payload: WorkUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkOut:
    work = _mine(db, work_id, user)
    fields = payload.model_dump(exclude_unset=True)
    return services.work_out(db, services.update_work(db, work, fields=fields))


@router.delete("/{work_id}", status_code=204)
def delete_work(
    work_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    services.delete_work(db, _mine(db, work_id, user))


# --- 형상 버전 ----------------------------------------------------------------


@router.get("/{work_id}/versions", response_model=list[VersionOut])
def list_versions(
    work_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[VersionOut]:
    work = _mine(db, work_id, user)
    return [services.version_out(db, one) for one in services.list_versions(db, work)]


@router.post("/{work_id}/versions", response_model=VersionOut, status_code=202)
def create_version(
    work_id: uuid.UUID,
    payload: VersionCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VersionOut:
    """새 버전 — 저장하고 평가 작업을 건다. 202: STEP · glTF 는 작업이 끝나야 있다."""
    work = _mine(db, work_id, user)
    version = services.add_version(
        db, work, recipe=payload.recipe, source=payload.source, note=payload.note, by=user
    )
    return services.version_out(db, version)


@router.get("/{work_id}/versions/{number}", response_model=VersionOut)
def get_version(
    work_id: uuid.UUID,
    number: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VersionOut:
    work = _mine(db, work_id, user)
    return services.version_out(db, services.get_version(db, work, number))


@router.post(
    "/{work_id}/versions/{number}/restore", response_model=VersionOut, status_code=202
)
def restore_version(
    work_id: uuid.UUID,
    number: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VersionOut:
    work = _mine(db, work_id, user)
    return services.version_out(db, services.restore_version(db, work, number, by=user))


@router.post("/{work_id}/import-step", response_model=VersionOut, status_code=202)
def import_step(
    work_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VersionOut:
    """STEP 을 올려 `import_step` 노드 하나짜리 새 버전으로."""
    work = _mine(db, work_id, user)
    version = services.import_step(
        db, work, filename=file.filename or "import.step", stream=file.file, by=user
    )
    return services.version_out(db, version)


# --- 지그 생성 ----------------------------------------------------------------


@router.get("/{work_id}/jig-runs", response_model=list[JobOut])
def list_jig_runs(
    work_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[JobOut]:
    work = _mine(db, work_id, user)
    return [jobs.job_out(db, one) for one in services.list_jig_runs(db, work)]


@router.post("/{work_id}/jig-runs", response_model=JobOut, status_code=202)
def create_jig_run(
    work_id: uuid.UUID,
    payload: JigRunRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> JobOut:
    """현재 형상을 제품으로 지그 생성을 **건다.** 화면은 `GET /api/jobs/{id}` 를 폴링한다."""
    work = _mine(db, work_id, user)
    return jobs.job_out(db, services.request_jig(db, work, by=user, options=payload.options))


# --- 승격 ---------------------------------------------------------------------


@router.post("/{work_id}/promote/part", response_model=PartVersionOut, status_code=201)
def promote_part(
    work_id: uuid.UUID,
    payload: PromotePartRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PartVersionOut:
    """현재 형상 버전을 부품 카탈로그에 올린다."""
    work = _mine(db, work_id, user)
    promoted = services.promote_part(db, work, by=user, name=payload.name, note=payload.note)
    return parts.version_out(db, promoted)


@router.post("/{work_id}/promote/jig", response_model=PromoteJigOut, status_code=201)
def promote_jig(
    work_id: uuid.UUID,
    payload: PromoteJigRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PromoteJigOut:
    """지그 생성 작업 하나를 지그 카탈로그에 올린다. 제품이 부품에 없으면 함께 올린다."""
    work = _mine(db, work_id, user)
    return services.promote_jig(
        db,
        work,
        by=user,
        job_id=payload.job_id,
        name=payload.name,
        note=payload.note,
        promote_product=payload.promote_product,
    )
