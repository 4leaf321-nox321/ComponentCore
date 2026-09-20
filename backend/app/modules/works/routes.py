"""내 작업 라우터 — 전부 소유자(또는 관리자)만. 목록은 내 것만 나온다."""

from __future__ import annotations

import uuid
from typing import Any

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
    AssembleOut,
    AssembleRequest,
    JigFromPartOut,
    JigFromPartRequest,
    PromoteJigOut,
    PromoteJigRecipeRequest,
    PromotePartRequest,
    VersionCreateRequest,
    VersionOut,
    WorkCreateRequest,
    WorkOut,
    WorkPatchRequest,
    WorkSummaryOut,
    WorkUpdateRequest,
)
from app.shared.auth import current_user
from app.shared.errors import AppError, code
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
    q: str = Query(default="", max_length=120),
    tag: str = Query(default="", max_length=40),
    kind: str = Query(default="", max_length=10),
    trashed: bool = Query(default=False),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[WorkSummaryOut]:
    """내 작업 — `q` 로 이름 · 설명을 찾고, `tag` · `kind` 로 거르고, `trashed` 면 휴지통."""
    size = clamp_limit(limit)
    rows, total = services.list_works(
        db, owner=user, limit=size, offset=offset, query=q, tag=tag, kind=kind, trashed=trashed
    )
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
        kind=payload.kind,
        jig_for_part_id=payload.jig_for_part_id,
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


@router.get("/tags", response_model=list[str])
def my_tags(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[str]:
    """내 작업에 붙은 꼬리표 — 많이 쓴 것부터."""
    return services.my_tags(db, user)


@router.post("/{work_id}/restore", response_model=WorkOut)
def restore_work(
    work_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> WorkOut:
    """휴지통에서 되살린다."""
    work = db.get(Work, work_id)
    if work is None or work.deleted_at is None:
        raise AppError(code("WORKS", 31), "휴지통에 없는 작업입니다.")
    services.require_owner(work, user)
    return services.work_out(db, services.restore_work(db, work))


@router.post("/{work_id}/duplicate", response_model=WorkOut, status_code=201)
def duplicate_work(
    work_id: uuid.UUID,
    name: str | None = Query(default=None, max_length=120),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkOut:
    """현재 도면으로 새 작업 — 종류 · 꼬리표 · 잡는 부품을 따라간다."""
    work = _mine(db, work_id, user)
    return services.work_out(db, services.duplicate_work(db, work, by=user, name=name))


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


@router.post("/{work_id}/patch", response_model=VersionOut, status_code=202)
def patch_work(
    work_id: uuid.UUID,
    payload: WorkPatchRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VersionOut:
    """현재 도면을 연산 몇 개로 고쳐 **새 버전**으로 — 레시피 전체를 되보내지 않는다."""
    from app.modules.cad import services as cad

    work = _mine(db, work_id, user)
    version = services.current_version(db, work)
    if version is None:
        raise AppError(code("WORKS", 8), "고칠 도면이 없습니다.")
    made = cad.patch(version.recipe, payload.ops)
    if made["problems"]:
        raise AppError(
            code("WORKS", 30),
            "고친 도면이 올바르지 않습니다",
            details={"problems": made["problems"], "recipe": made["recipe"]},
        )
    new = services.add_version(
        db, work, recipe=made["recipe"], source="ai", note=payload.note or "부분 수정", by=user
    )
    return services.version_out(db, new)


@router.post("/assemble", response_model=AssembleOut, status_code=201)
def assemble(
    payload: AssembleRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AssembleOut:
    """부품 + 지그를 **맞는 자리에** 놓은 조립 작업. 부품 높이는 변수(`부품_높이`)라 DOE 로
    훑는다. 생성기로 만든 지그는 그 좌표계로 정확히, 손으로 그린 지그는 윗면에 얹어 어림
    (`placement.mode`)."""
    made, placement = services.assemble_jig_on_part(
        db,
        by=user,
        part_source=payload.part_source,
        jig_work_id=payload.jig_work_id,
        name=payload.name,
    )
    return AssembleOut(work=services.work_out(db, made), placement=placement)


@router.post("/jig-from-part/preview")
def jig_preview(
    payload: JigFromPartRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """만들기 전 미리보기 — 계획(받침 · 로케이터 · 클램프 자리) · 간섭 · 제품 + 지그 메시.
    메시의 면마다 `part`(제품 · 바닥판 · 받침 n · 위치 핀 n · 클램프 n)가 붙어 있다."""
    return services.jig_preview(db, by=user, source=payload.source, options=payload.options)


@router.post("/jig-from-part", response_model=JigFromPartOut, status_code=202)
def jig_from_part(
    payload: JigFromPartRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> JigFromPartOut:
    """부품에서 **지그 작업을 생성**한다. 지그 작업이 바로 생기고 생성이 걸린다 — 화면은
    `GET /api/jobs/{id}` 를 폴링하다 끝나면 `adopt` 로 결과를 첫 버전으로 가져온다."""
    made, job = services.jig_from_part(
        db, by=user, source=payload.source, name=payload.name, options=payload.options
    )
    return JigFromPartOut(
        work=services.work_out(db, made), job=jobs.job_out(db, job).model_dump()
    )


@router.post("/{work_id}/jig-runs/{job_id}/adopt", response_model=VersionOut, status_code=201)
def adopt_jig_run(
    work_id: uuid.UUID,
    job_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VersionOut:
    """끝난 생성 결과를 이 지그 작업의 버전으로 — 그 다음부터는 그냥 그린다(변수 · DOE)."""
    work = _mine(db, work_id, user)
    return services.version_out(db, services.adopt_jig_run(db, work, by=user, job_id=job_id))


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


@router.post("/{work_id}/promote/jig-recipe", response_model=PromoteJigOut, status_code=201)
def promote_jig_recipe(
    work_id: uuid.UUID,
    payload: PromoteJigRecipeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PromoteJigOut:
    """레시피로 그린 지그를 지그 카탈로그로 — 생성기를 거치지 않는 길.

    부품은 그리고(레시피), 지그는 만들어 준다(생성기)는 것이 기본 흐름이다. 그런데 생성기가
    만들 수 없는 지그가 있다 — 그런 것은 **그린다**. 그리는 것이니 변수를 심고 DOE 로 훑을 수
    있다."""
    work = services.get_work(db, work_id)
    services.require_owner(work, user)
    return services.promote_jig_recipe(
        db,
        work,
        by=user,
        number=payload.number,
        name=payload.name,
        note=payload.note,
        part_id=payload.part_id,
    )
