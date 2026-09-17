"""지그 카탈로그 라우터 — 로그인한 누구나 본다."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.jigs import services
from app.modules.jigs.schemas import JigOut, JigSummaryOut, JigUpdateRequest, JigVersionOut
from app.shared.auth import current_user
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/jigs", tags=["jigs"])


@router.get("", response_model=Page[JigSummaryOut])
def list_jigs(
    part_id: uuid.UUID | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[JigSummaryOut]:
    size = clamp_limit(limit)
    rows, total = services.list_jigs(db, part_id=part_id, limit=size, offset=offset)
    return Page(
        items=[services.jig_summary(db, one) for one in rows],
        total=total,
        limit=size,
        offset=offset,
    )


@router.get("/{jig_id}", response_model=JigOut)
def get_jig(
    jig_id: uuid.UUID, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> JigOut:
    return services.jig_out(db, services.get_jig(db, jig_id))


@router.patch("/{jig_id}", response_model=JigOut)
def update_jig(
    jig_id: uuid.UUID,
    payload: JigUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> JigOut:
    jig = services.get_jig(db, jig_id)
    services.require_owner(jig, user)
    fields = payload.model_dump(exclude_unset=True)
    return services.jig_out(db, services.update_jig(db, jig, fields=fields))


@router.delete("/{jig_id}", status_code=204)
def delete_jig(
    jig_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    jig = services.get_jig(db, jig_id)
    services.require_owner(jig, user)
    services.delete_jig(db, jig)


@router.get("/{jig_id}/versions", response_model=list[JigVersionOut])
def list_versions(
    jig_id: uuid.UUID, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[JigVersionOut]:
    jig = services.get_jig(db, jig_id)
    return [services.version_out(db, one) for one in services.list_versions(db, jig)]
