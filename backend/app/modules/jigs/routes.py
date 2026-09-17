"""지그 라우터 — 프로젝트(제품) 와 실행(생성)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core import primitives
from app.core.options import JigOptions
from app.database import get_db
from app.modules.accounts.models import User
from app.modules.jigs import services
from app.modules.jigs.schemas import (
    OptionsOut,
    ProjectCreateRequest,
    ProjectOut,
    ProjectUpdateRequest,
    RunCreateRequest,
    RunOut,
)
from app.shared.auth import current_user
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/jigs", tags=["jigs"])


@router.get("/options", response_model=OptionsOut)
def options(_: User = Depends(current_user)) -> OptionsOut:
    """기본 옵션과 그릴 수 있는 도형 종류. **화면이 목록을 손으로 들지 않는다.**"""
    return OptionsOut(defaults=JigOptions().to_dict(), primitive_kinds=list(primitives.KINDS))


@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[ProjectOut]:
    size = clamp_limit(limit)
    rows, total = services.list_projects(db, limit=size, offset=offset)
    return Page(
        items=[services.project_out(db, one) for one in rows],
        total=total,
        limit=size,
        offset=offset,
    )


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = services.create_project(
        db,
        owner=user,
        name=payload.name,
        description=payload.description,
        product_spec=payload.product_spec,
    )
    return services.project_out(db, project)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> ProjectOut:
    return services.project_out(db, services.get_project(db, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = services.get_project(db, project_id)
    services.require_owner(project, user)
    # exclude_unset — 안 보낸 칸은 건드리지 않는다. product_spec 은 null 로 비울 수 있다.
    fields = payload.model_dump(exclude_unset=True)
    return services.project_out(db, services.update_project(db, project, fields=fields))


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    project = services.get_project(db, project_id)
    services.require_owner(project, user)
    services.delete_project(db, project)


@router.post("/projects/{project_id}/product", response_model=ProjectOut)
def upload_product(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = services.get_project(db, project_id)
    services.require_owner(project, user)
    project = services.attach_product(
        db, project, filename=file.filename or "product.step", stream=file.file
    )
    return services.project_out(db, project)


@router.delete("/projects/{project_id}/product", response_model=ProjectOut)
def remove_product(
    project_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = services.get_project(db, project_id)
    services.require_owner(project, user)
    return services.project_out(db, services.detach_product(db, project))


# --- 실행 ---------------------------------------------------------------------


@router.get("/projects/{project_id}/runs", response_model=list[RunOut])
def list_runs(
    project_id: uuid.UUID, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[RunOut]:
    project = services.get_project(db, project_id)
    return [services.run_out(one) for one in services.list_runs(db, project.id)]


@router.post("/projects/{project_id}/runs", response_model=RunOut, status_code=201)
def create_run(
    project_id: uuid.UUID,
    payload: RunCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunOut:
    """지그를 만든다. 동기로 돌고 끝난 결과(성공 · 실패)를 돌려준다."""
    project = services.get_project(db, project_id)
    run = services.execute_run(db, project, requested_by=user, options=payload.options)
    return services.run_out(run)


@router.get("/projects/{project_id}/runs/{run_id}", response_model=RunOut)
def get_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunOut:
    project = services.get_project(db, project_id)
    return services.run_out(services.get_run(db, project, run_id))


@router.get("/projects/{project_id}/runs/{run_id}/files/{key}", response_class=FileResponse)
def download_result(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    key: str,
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    project = services.get_project(db, project_id)
    run = services.get_run(db, project, run_id)
    path, name, mime = services.result_file(run, key)
    return FileResponse(path, media_type=mime, filename=name)
