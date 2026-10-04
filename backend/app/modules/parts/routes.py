"""부품 카탈로그 라우터 — 로그인한 누구나 본다. 「내 공간으로 복사」 가 새 작업을 만든다."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.parts import services
from app.modules.parts.schemas import (
    CopyToWorkRequest,
    PartOut,
    PartSummaryOut,
    PartUpdateRequest,
    PartVersionOut,
    StandardBundle,
    StandardExportRequest,
    StandardImportOut,
    StandardSpec,
)
from app.modules.works import services as works
from app.modules.works.schemas import WorkOut
from app.shared import folders
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import NotFound, code
from app.shared.pagination import Page, clamp_limit
from app.shared.shape_search import ShapeFilter, shape_query

router = APIRouter(prefix="/parts", tags=["parts"])


@router.get("/tags", response_model=list[str])
def part_tags(_: User = Depends(current_user), db: Session = Depends(get_db)) -> list[str]:
    """카탈로그에 붙은 꼬리표 전부 — 거르개 · 자동 완성. 많이 쓰인 것이 앞이다.

    **승격이 내 작업의 것을 물려받는다** — 붙여 둔 것이 공용 공간으로 나가면서 없어지던
    것을 고쳤다(2026-09-24). 내 작업은 열두 개쯤이라 이름으로 찾지만, 공용 공간은 남의
    것까지 쌓여 이름만으로는 못 찾는다."""
    return services.all_tags(db)


@router.get("/folders", response_model=list[folders.FolderOut])
def part_folders(
    _: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[folders.FolderOut]:
    """카탈로그의 폴더들 — 경로와 바로 그 폴더의 부품 수. 위 폴더도 빠짐없이."""
    return services.part_folders(db)


@router.post("/folders/rename", response_model=folders.MovedOut)
def rename_folder(
    payload: folders.FolderRenameRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> folders.MovedOut:
    """폴더 이름 바꾸기 · 옮기기(하위까지). 남의 부품이 든 폴더는 관리자만."""
    return folders.MovedOut(
        moved=services.rename_folder(db, user, path=payload.path, to=payload.to)
    )


@router.post("/move", response_model=folders.MovedOut)
def move_parts(
    payload: folders.FolderMoveRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> folders.MovedOut:
    """부품 여럿을 한 폴더로 — 올린 사람 · 관리자만."""
    return folders.MovedOut(
        moved=services.move_parts(db, user, ids=payload.ids, folder=payload.folder)
    )


@router.get("", response_model=Page[PartSummaryOut])
def list_parts(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=120),
    tag: str = Query(default="", max_length=40),
    folder: str | None = Query(default=None, max_length=255),
    subfolders: bool = Query(default=True),
    shape: ShapeFilter = Depends(shape_query),
    standard: Literal["", "any", "support", "pin", "clamp"] = Query(default=""),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[PartSummaryOut]:
    """부품 카탈로그 — `q` · `tag` 로 찾고, `folder` 면 그 폴더(`subfolders` 면 하위까지).
    **형상으로**: `has` · `thread` · `param` · `fits` · `volume_min` · `volume_max` · `hole` ·
    `holes` — 최신 버전의 형상 색인으로 거른다. `standard` 면 규격 부품만(`any` 또는 종류)."""
    size = clamp_limit(limit)
    rows, total = services.list_parts(
        db,
        limit=size,
        offset=offset,
        query=q,
        tag=tag,
        folder=folder,
        subfolders=subfolders,
        shape=shape,
        standard=standard,
    )
    return Page(
        items=[services.part_summary(db, one) for one in rows],
        total=total,
        limit=size,
        offset=offset,
    )


@router.post("/standard/export", response_model=StandardBundle)
def export_standard(
    payload: StandardExportRequest,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> StandardBundle:
    """**규격 부품 묶음**을 만든다 — 시스템 관리자만. 고른 것(`ids`, 비우면 전부)의 사양과 쓰는
    버전의 레시피를 JSON 하나로. 개발 PC 에서 그린 규격품을 운영 서버로 옮길 때 쓴다."""
    return services.export_standard(db, payload.ids)


@router.post("/standard/import", response_model=StandardImportOut)
def import_standard(
    payload: StandardBundle,
    dry_run: bool = Query(default=False),
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> StandardImportOut:
    """**규격 부품 묶음**을 가져온다 — 시스템 관리자만. 품번으로 짝지어 없으면 새 부품, 있으면
    형상이 다를 때 새 버전 · 사양만 다르면 사양만. 형상 기준을 어긴 항목은 건너뛰고 까닭을
    말한다. `dry_run` 이면 아무것도 바꾸지 않고 할 일만 돌려준다."""
    return services.import_standard(db, payload, by=user, dry_run=dry_run)


@router.put("/{part_id}/standard", response_model=PartOut)
def set_standard(
    part_id: uuid.UUID,
    payload: StandardSpec,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> PartOut:
    """**규격 사양**을 붙이거나 고친다 — 시스템 관리자만. 종류(받침 · 위치 핀 · 토글 클램프) ·
    품번 · 쓰는 버전 · 치수. 그 버전의 형상이 기준(바닥 중심 원점 · 패드 자리)을 지키는지 본
    뒤에 저장한다. 지그 생성기가 요구에 맞는 것을 골라 놓고 부품표에 품번 · 수량을 남긴다."""
    part = services.get_part(db, part_id)
    return services.part_out(db, services.set_standard(db, part, payload))


@router.delete("/{part_id}/standard", response_model=PartOut)
def clear_standard(
    part_id: uuid.UUID,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> PartOut:
    """규격 사양을 뗀다 — 일반 부품으로 돌아간다. 이미 만든 지그는 그대로다."""
    part = services.get_part(db, part_id)
    return services.part_out(db, services.clear_standard(db, part))


@router.get("/{part_id}", response_model=PartOut)
def get_part(
    part_id: uuid.UUID, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> PartOut:
    return services.part_out(db, services.get_part(db, part_id))


@router.patch("/{part_id}", response_model=PartOut)
def update_part(
    part_id: uuid.UUID,
    payload: PartUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PartOut:
    part = services.get_part(db, part_id)
    services.require_owner(part, user)
    fields = payload.model_dump(exclude_unset=True)
    return services.part_out(db, services.update_part(db, part, fields=fields))


@router.delete("/{part_id}", status_code=204)
def delete_part(
    part_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    part = services.get_part(db, part_id)
    services.require_owner(part, user)
    services.delete_part(db, part)


@router.get("/{part_id}/versions", response_model=list[PartVersionOut])
def list_versions(
    part_id: uuid.UUID, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[PartVersionOut]:
    part = services.get_part(db, part_id)
    return [services.version_out(db, one) for one in services.list_versions(db, part)]


@router.post("/{part_id}/copy-to-work", response_model=WorkOut, status_code=201)
def copy_to_work(
    part_id: uuid.UUID,
    payload: CopyToWorkRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkOut:
    """부품의 레시피로 **내 작업**을 새로 만든다. 남의 부품을 고치는 길은 이것뿐이다."""
    part = services.get_part(db, part_id)
    version = (
        services.get_version(db, part, payload.number)
        if payload.number is not None
        else services.current_version(db, part)
    )
    if version is None:
        raise NotFound(code("PARTS", 3), "버전이 없습니다.")
    work = works.create_work(
        db,
        owner=user,
        name=(payload.name or f"{part.name} (복사)").strip(),
        description=part.description,
        recipe=version.recipe,
        source="copy",
        note=f"부품 {part.name} v{version.number}에서 복사",
        conditions=version.conditions if payload.conditions else None,
    )
    return works.work_out(db, work)
