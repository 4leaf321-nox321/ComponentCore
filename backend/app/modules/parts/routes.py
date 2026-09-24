"""부품 카탈로그 라우터 — 로그인한 누구나 본다. 「내 공간으로 복사」 가 새 작업을 만든다."""

from __future__ import annotations

import uuid

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
)
from app.modules.works import services as works
from app.modules.works.schemas import WorkOut
from app.shared.auth import current_user
from app.shared.errors import NotFound, code
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/parts", tags=["parts"])


@router.get("/tags", response_model=list[str])
def part_tags(_: User = Depends(current_user), db: Session = Depends(get_db)) -> list[str]:
    """카탈로그에 붙은 꼬리표 전부 — 거르개 · 자동 완성. 많이 쓰인 것이 앞이다.

    **승격이 내 작업의 것을 물려받는다** — 붙여 둔 것이 공용 공간으로 나가면서 없어지던
    것을 고쳤다(2026-09-24). 내 작업은 열두 개쯤이라 이름으로 찾지만, 공용 공간은 남의
    것까지 쌓여 이름만으로는 못 찾는다."""
    return services.all_tags(db)


@router.get("", response_model=Page[PartSummaryOut])
def list_parts(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=120),
    tag: str = Query(default="", max_length=40),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[PartSummaryOut]:
    size = clamp_limit(limit)
    rows, total = services.list_parts(db, limit=size, offset=offset, query=q, tag=tag)
    return Page(
        items=[services.part_summary(db, one) for one in rows],
        total=total,
        limit=size,
        offset=offset,
    )


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
        note=f"부품 {part.name} v{version.number} 에서 복사",
    )
    return works.work_out(db, work)
