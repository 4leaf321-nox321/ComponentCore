"""실험계획(DOE) 라우터 — 만들고, 보고, 표로 받는다. 파일은 공유 폴더에 있다."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.auth import services as auth_services
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
from app.modules.works.models import Work
from app.shared.auth import current_user, granted_scopes
from app.shared.errors import AppError, Forbidden, code
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/doe", tags=["doe"])


def _summary(db: Session, study: DoeStudy) -> StudySummaryOut:
    work = db.get(Work, study.work_id) if study.work_id else None
    return StudySummaryOut(
        **{
            key: getattr(study, key)
            for key in (
                "id",
                "name",
                "description",
                "work_id",
                "method",
                "samples",
                "seed",
                "point_count",
                "created_at",
            )
        },
        work_name=work.name if work else None,
        work_kind=work.kind if work else None,
        owner_name=_name_of(db, study.owner_id),
        visibility=study.visibility,
    )


def _name_of(db: Session, user_id: uuid.UUID | None) -> str:
    """사람의 표시 이름. 지워진 계정이면 빈 칸이지, 없는 이름을 지어 내지 않는다."""
    person = db.get(User, user_id) if user_id else None
    return (person.display_name or person.email) if person else ""


def _point_out(point: Any) -> PointOut:
    out = PointOut.model_validate(point)
    out.interference = (point.geometry or {}).get("interference")
    return out


def _out(db: Session, study: DoeStudy) -> StudyOut:
    rows = services.points(db, study)
    job = db.get(Job, study.job_id) if study.job_id else None
    return StudyOut(
        **_summary(db, study).model_dump(),
        recipe=study.recipe,
        conditions=study.conditions,
        requested_by_name=_name_of(db, study.requested_by_id),
        keep_forever=study.keep_forever,
        released_at=study.released_at,
        local_ready=services.local_ready(study),
        factors=study.factors,
        export_dir_windows=files.windows_path(Path(study.export_dir))
        if study.export_dir
        else "",
        exported_at=study.exported_at,
        job=jobs.job_out(db, job).model_dump() if job else None,
        points=[_point_out(one) for one in rows],
        done=sum(1 for one in rows if one.status == "ok"),
        failed=sum(1 for one in rows if one.status == "failed"),
    )


@router.post("/preview")
def preview(
    payload: PreviewRequest, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """**만들기 전에** 설계점이 몇 개인지와 앞 스무 줄. 격자는 곱으로 늘어난다."""
    return services.preview(db, payload.model_dump())


@router.get("", response_model=Page[StudySummaryOut])
def list_studies(
    work_id: uuid.UUID | None = Query(default=None),
    scope: str = Query(default="mine", pattern="^(mine|all)$"),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[StudySummaryOut]:
    """`scope=mine`(기본) 은 내 것, `all` 은 **공개된 것까지.**

    기본이 「내 것」 인 까닭: 「내 활동」 화면이 이것을 쓴다. 공개를 기본으로 하면 남의 것이
    내 활동에 섞인다 — 남의 이력을 찾는 것은 다른 물음이라 따로 묻게 한다."""
    size = clamp_limit(limit)
    rows, total = services.list_studies(
        db, user, work_id=work_id, limit=size, offset=offset, scope=scope
    )
    return Page(
        items=[_summary(db, one) for one in rows], total=total, limit=size, offset=offset
    )


def _acting_for(db: Session, caller: User, request: Request, asked: str) -> User | None:
    """`on_behalf_of` 를 사람으로 푼다 — **대행 자격이 있는 토큰만.**

    기계가 PAT 으로 만들면 소유자가 서비스 계정이 되고, 그러면 정작 사람이 제 활동에서 못
    찾는다. 그래서 「누구를 위해」 를 밝히게 한다. 다만 **남의 이름을 빌리는 일**이라 아무나
    못 한다: 토큰에 `act_for_others` 범위가 있어야 한다(관리자가 그 토큰을 만들 때 준다).
    사람 세션에는 범위가 없으므로 이 길로 못 온다 — 그쪽은 제 이름으로 만들면 된다.
    """
    if not asked:
        return None
    if "act_for_others" not in granted_scopes(request):
        raise Forbidden(
            code("DOE", 20),
            "이 토큰에는 대행(act_for_others) 자격이 없습니다 — 남의 이름으로는 못 만듭니다.",
        )
    person = db.scalar(select(User).where(User.email == asked))
    if person is None and _looks_like_uuid(asked):
        person = db.get(User, uuid.UUID(asked))
    if person is None:
        raise AppError(code("DOE", 21), f"그런 사용자가 없습니다: {asked}")
    # 떠난 사람 · 정지된 계정 이름으로 만들지 않는다 — 그 이름은 아무도 안 본다.
    auth_services.ensure_can_sign_in(person)
    return person


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _create(
    db: Session, user: User, payload: StudyCreateRequest, request: Request
) -> tuple[DoeStudy, bool]:
    """대행이면 **소유자는 그 사람**, 부른 쪽은 기계다."""
    person = _acting_for(db, user, request, payload.on_behalf_of)
    return services.create_study(
        db,
        owner=person or user,
        requested_by=user if person else None,
        name=payload.name,
        description=payload.description,
        recipe=payload.recipe,
        factors=[one.model_dump() for one in payload.factors],
        method=payload.method,
        samples=payload.samples,
        seed=payload.seed,
        work_id=payload.work_id,
        conditions=payload.conditions,
        idempotency_key=payload.idempotency_key,
    )


@router.post("", response_model=StudyOut, status_code=201)
def create_study(
    payload: StudyCreateRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StudyOut:
    """스터디를 만들고 **바로 작업을 건다** — 점마다 형상을 만들어 서버 보관 폴더에 쓴다.

    `idempotency_key` 를 주면 **두 번 불러도 한 벌**이다. 이미 있던 것을 돌려줄 때는
    **201 이 아니라 200** 이다 — 기계가 「새로 생겼나」 를 그 자리에서 알 수 있어야 한다."""
    study, reused = _create(db, user, payload, request)
    if reused:
        response.status_code = 200
    return _out(db, study)


@router.get("/{study_id}", response_model=StudyOut)
def get_study(
    study_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> StudyOut:
    return _out(db, services.get_study(db, study_id, user))


@router.post("/{study_id}/export", response_model=StudyOut)
def export_study(
    study_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> StudyOut:
    """서버 보관 폴더의 STEP · 표를 **공유 폴더로 보낸다.** 해석은 그때부터 읽는다.

    보는 것은 공개라도 **보내는 것은 소유자만** — 남의 DOE 를 해석에 넘길 수 있으면
    「읽기 공개」 가 사실상 「모두가 주인」 이 된다."""
    return _out(db, services.export_study(db, services.owned_study(db, study_id, user)))


@router.get("/{study_id}/status")
def study_status(
    study_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """**진행만** — 끝났나 · 몇 점 됐나 · 폴더는 어디인가. 설계점 표는 주지 않는다.

    기계가 「끝났나」 만 보려고 200줄짜리 표를 되풀이해 받는 것을 막으려고 따로 둔다."""
    return services.status_of(db, services.get_study(db, study_id, user))


#: 한 번 기다리는 시간의 상한. 오래 잡으면 프록시가 먼저 끊고, 짧으면 기계가 자주 되묻는다.
_WAIT_MAX = 120


@router.post("/{study_id}/wait")
async def wait_for_study(
    study_id: uuid.UUID,
    seconds: int = Query(default=30, ge=1, le=_WAIT_MAX),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """**끝날 때까지 기다려 준다**(길게 물기). 끝났든 시간이 다 됐든 지금 상태를 돌려준다.

    왜 있나: 기계는 「걸고 · 기다리고 · 다음」 이 한 줄이어야 한다. 이것이 없으면 부르는 쪽마다
    폴링 루프를 제 손으로 만들고, 그 간격은 제각각이 된다(1초마다 두드리는 것이 하나만
    있어도 서버가 안다).

    **끝을 보장하지 않는다.** 상한(2분)까지만 기다리고 상태를 준다 — 오래 잡으면 프록시가
    먼저 끊고, 그때 기계는 「실패했다」 와 「아직이다」 를 구별하지 못한다. 안 끝났으면
    `running` 이 참이니 다시 부르면 된다.

    세션을 **폴링마다 새로 연다** — 한 연결을 2분씩 쥐고 있으면 풀이 금세 마른다."""
    from app.database import SessionLocal

    def look() -> dict[str, Any]:
        with SessionLocal() as fresh:
            return services.status_of(fresh, services.get_study(fresh, study_id, user))

    deadline = asyncio.get_event_loop().time() + seconds
    while True:
        state = await run_in_threadpool(look)
        if not state["running"] or asyncio.get_event_loop().time() >= deadline:
            state["waited_out"] = state["running"]
            return state
        await asyncio.sleep(1.0)


@router.post("/run", response_model=StudyOut)
async def run_study(
    payload: StudyCreateRequest,
    request: Request,
    wait_seconds: int = Query(default=300, ge=0, le=1800),
    export: bool = Query(default=True),
    user: User = Depends(current_user),
) -> StudyOut:
    """**한 번 부르면 폴더까지** — 만들고 · 기다리고 · 공유 폴더로 보낸다.

    오케스트레이터가 쓰는 자리다. `POST /doe` 는 즉시 돌아오므로(화면이 폴링하는 전제) 부르는
    쪽이 제 폴링 루프를 만들어야 하는데, 기계에게는 **다음 단계로 갈 수 있는 한 번**이 맞다.

    `idempotency_key` 를 함께 주면 재시도해도 한 벌이다 — 기계는 재시도하므로 사실상 늘 줘야
    한다. `export=false` 면 만들기만 하고 보내지 않는다(조건만 바꿔 가며 쌓아 둘 때).

    **안 끝나도 답은 온다.** `wait_seconds` 가 다 되면 그때 상태로 돌려준다(`job.status` 가
    running). 그 경우 보내기는 하지 않는다 — 만들다 만 폴더를 해석이 읽으면 안 된다."""
    from app.database import SessionLocal

    def make() -> tuple[uuid.UUID, bool]:
        with SessionLocal() as fresh:
            caller = fresh.merge(user)
            study, reused = _create(fresh, caller, payload, request)
            return study.id, reused

    study_id, _ = await run_in_threadpool(make)

    def look() -> bool:
        with SessionLocal() as fresh:
            study = fresh.get(DoeStudy, study_id)
            job = fresh.get(Job, study.job_id) if study and study.job_id else None
            return bool(job and job.status in ("queued", "running"))

    deadline = asyncio.get_event_loop().time() + wait_seconds
    while await run_in_threadpool(look):
        if asyncio.get_event_loop().time() >= deadline:
            break
        await asyncio.sleep(1.0)

    def finish() -> StudyOut:
        with SessionLocal() as fresh:
            study = services.get_study(fresh, study_id, user)
            job = fresh.get(Job, study.job_id) if study.job_id else None
            if export and job is not None and job.status in ("done", "failed"):
                # 만들다 만 폴더는 안 보낸다 — 실패한 점이 섞여도 표가 온전하면 보낸다.
                study = services.export_study(fresh, study)
            return _out(fresh, study)

    return await run_in_threadpool(finish)


@router.post("/{study_id}/rerun", response_model=StudyOut)
def rerun_study(
    study_id: uuid.UUID,
    only: str = Query(default="all", pattern="^(all|failed)$"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StudyOut:
    """**다시 만들기** — 스냅샷(레시피 · 인자 · 시드 · 조건)으로 설계점 파일을 되살린다.

    보관 기한이 지나 파일이 치워졌거나, 실패한 점을 한 번 더 해 볼 때. 새 스터디가 아니라
    **같은 스터디**다 — 같은 재료로 같은 것이 나온다. `only=failed` 면 실패한 점만(파일이
    사라진 점은 `ok` 였어도 다시 만든다).

    범위를 고쳐 다시 돌리는 것은 이것이 아니다 — 그건 새 스터디다."""
    study = services.owned_study(db, study_id, user)
    return _out(db, services.rerun_study(db, study, requester=user, only=only))


@router.get("/{study_id}/points/{number}/mesh")
def point_mesh(
    study_id: uuid.UUID,
    number: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """설계점 하나의 형상(메시) — 화면이 점마다 3D 로 본다. 스냅샷 레시피에 그 점의 값을 넣어
    다시 만든다."""
    return services.point_mesh(db, services.get_study(db, study_id, user), number)


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
            point_file=point.point_file,
            unresolved=(point.geometry or {}).get("topology_unresolved"),
            error=point.error,
            interference=(point.geometry or {}).get("interference"),
        )
        for point in services.points(db, study)
    ]
    return Response(
        files.to_csv(columns, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="doe-{study_id.hex[:8]}.csv"'},
    )


@router.post("/{study_id}/keep", response_model=StudyOut)
def keep_study(
    study_id: uuid.UUID,
    keep: bool = Query(default=True),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StudyOut:
    """**영구보관** — 보관 기한이 지나도 공유 폴더를 남긴다.

    기한은 기본값이고 이것이 예외다. 지우는 일은 되돌릴 수 없으니, 「이건 남겨야 한다」 를
    아는 사람이 그때 켤 수 있어야 한다."""
    study = services.owned_study(db, study_id, user)
    return _out(db, services.set_keep(db, study, keep))


@router.post("/{study_id}/release", response_model=StudyOut)
def release_study(
    study_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StudyOut:
    """해석 쪽이 **다 읽었다** — 오케스트레이터가 부른다.

    「성공했다」 가 아니라 「더 안 읽는다」 는 뜻이다. 실패해서 다시 돌릴 생각이면 알리지
    마라 — 알린 폴더는 기한을 기다리지 않고 먼저 치워진다."""
    study = services.owned_study(db, study_id, user)
    return _out(db, services.release(db, study))


@router.post("/{study_id}/visibility", response_model=StudyOut)
def set_visibility(
    study_id: uuid.UUID,
    value: str = Query(pattern="^(read|private)$"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StudyOut:
    """**누가 보나** — `read`(기본, 모두) 또는 `private`(나와 관리자만).

    기본이 공개인 까닭: DOE 는 이 조직의 설계 이력이고, 옆 사람이 같은 훑기를 다시 도는 것이
    더 큰 손해다. 그리고 기계가 대행으로 만들기 시작하면 「누구 것인가」 가 흐려지므로, 보는
    것까지 닫아 두면 아무도 못 찾는 것이 쌓인다.

    쓰는 일(보내기 · 영구보관 · 다시 만들기 · 지우기)은 이 설정과 **무관하다** — 공개해도
    고치는 것은 소유자와 관리자뿐이다."""
    study = services.owned_study(db, study_id, user)
    return _out(db, services.set_visibility(db, study, value))


@router.delete("/{study_id}", status_code=204)
def delete_study(
    study_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    """스터디와 **서버 보관 폴더**를 지운다 — 공유 폴더의 사본은 남는다(해석이 보고 있을 수
    있다)."""
    services.delete_study(db, services.owned_study(db, study_id, user))
