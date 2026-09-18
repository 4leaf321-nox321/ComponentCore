"""실험계획(DOE) 라우터 — 만들고, 보고, 표로 받는다. 파일은 공유 폴더에 있다."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import doe as engine
from app.database import get_db
from app.modules.accounts.models import User
from app.modules.doe import export as files
from app.modules.doe import services
from app.modules.doe.models import DoeStudy
from app.modules.doe.schemas import (
    PointOut,
    PreviewRequest,
    StudyCreateRequest,
    StudyOut,
    StudySummaryOut,
)
from app.modules.jobs import services as jobs
from app.modules.jobs.models import Job
from app.shared.auth import current_user
from app.shared.errors import AppError, code
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/doe", tags=["doe"])


def _summary(study: DoeStudy) -> StudySummaryOut:
    return StudySummaryOut.model_validate(study)


def _out(db: Session, study: DoeStudy) -> StudyOut:
    rows = services.points(db, study)
    job = db.get(Job, study.job_id) if study.job_id else None
    return StudyOut(
        **_summary(study).model_dump(),
        recipe=study.recipe,
        factors=study.factors,
        export_dir_windows=files.windows_path(Path(study.export_dir)),
        job=jobs.job_out(db, job).model_dump() if job else None,
        points=[PointOut.model_validate(one) for one in rows],
        done=sum(1 for one in rows if one.status == "ok"),
        failed=sum(1 for one in rows if one.status == "failed"),
    )


@router.post("/preview")
def preview(payload: PreviewRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """**만들기 전에** 설계점이 몇 개인지와 앞 스무 줄. 격자는 곱으로 늘어난다."""
    return services.preview(payload.model_dump())


@router.get("", response_model=Page[StudySummaryOut])
def list_studies(
    work_id: uuid.UUID | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[StudySummaryOut]:
    size = clamp_limit(limit)
    rows, total = services.list_studies(db, user, work_id=work_id, limit=size, offset=offset)
    return Page(items=[_summary(one) for one in rows], total=total, limit=size, offset=offset)


@router.post("", response_model=StudyOut, status_code=201)
def create_study(
    payload: StudyCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StudyOut:
    """스터디를 만들고 **바로 작업을 건다** — 점마다 형상을 만들어 공유 폴더에 STEP 을 쓴다."""
    study = services.create_study(
        db,
        owner=user,
        name=payload.name,
        description=payload.description,
        recipe=payload.recipe,
        factors=[one.model_dump() for one in payload.factors],
        method=payload.method,
        samples=payload.samples,
        seed=payload.seed,
        material=payload.material,
        work_id=payload.work_id,
    )
    return _out(db, study)


@router.get("/{study_id}", response_model=StudyOut)
def get_study(
    study_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> StudyOut:
    return _out(db, services.get_study(db, study_id, user))


@router.get("/{study_id}/manifest.csv")
def manifest(
    study_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    """공유 폴더에 있는 것과 같은 표 — 화면에서 바로 받을 때."""
    study = services.get_study(db, study_id, user)
    names = [one["name"] for one in study.factors]
    columns = files.manifest_columns(names)
    rows = [
        files.manifest_row(
            point.number,
            point.params,
            names,
            status=point.status,
            step_file=point.step_file,
            metrics=point.metrics,
            error=point.error,
        )
        for point in services.points(db, study)
    ]
    return Response(
        files.to_csv(columns, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="doe-{study_id.hex[:8]}.csv"'},
    )


@router.post("/{study_id}/filter", response_model=list[PointOut])
def filter_points(
    study_id: uuid.UUID,
    conditions: list[dict[str, Any]],
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[PointOut]:
    """설계 조건(부등식)을 만족하는 점만. 값이 없는 점은 **만족하지 않은 것**으로 센다."""
    study = services.get_study(db, study_id, user)
    kept = []
    for point in services.points(db, study):
        ok, _why = engine.passes(point.metrics or {}, conditions)
        if ok:
            kept.append(PointOut.model_validate(point))
    return kept


@router.post("/{study_id}/tradeoff")
def tradeoff(
    study_id: uuid.UUID,
    objectives: list[dict[str, Any]],
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """맞서는 목표에서 **아무한테도 지지 않는 점**(파레토)을 가린다.

    목표 하나는 `{"key": "mass_g", "goal": "min"}` 또는 `{"key": "hz", "goal": "target",
    "target": 440}`. 가중치로 한 값을 만들지 않는다 — 고르는 것은 사람의 몫이다."""
    study = services.get_study(db, study_id, user)
    try:
        goals = engine.parse_objectives(objectives)
    except engine.DoeError as failure:
        raise AppError(code("DOE", 8), str(failure)) from failure
    rows = [
        {
            "id": str(point.id),
            "number": point.number,
            "params": point.params,
            **(point.metrics or {}),
        }
        for point in services.points(db, study)
    ]
    marked = engine.pareto(rows, goals)
    return {
        "objectives": objectives,
        "points": marked,
        "pareto_count": sum(1 for one in marked if one["pareto"]),
    }


@router.delete("/{study_id}", status_code=204)
def delete_study(
    study_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    """DB 에서만 지운다 — 공유 폴더의 파일은 남는다(해석이 보고 있을 수 있다)."""
    services.delete_study(db, services.get_study(db, study_id, user))
