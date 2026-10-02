"""지그 카탈로그 라우터 — 로그인한 누구나 본다."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.jigs import services
from app.modules.jigs.schemas import JigOut, JigSummaryOut, JigUpdateRequest, JigVersionOut
from app.shared import folders
from app.shared.auth import current_user
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/jigs", tags=["jigs"])


@router.get("/tags", response_model=list[str])
def jig_tags(_: User = Depends(current_user), db: Session = Depends(get_db)) -> list[str]:
    """지그 카탈로그의 꼬리표 전부 — 부품 쪽과 같은 모양."""
    return services.all_tags(db)


@router.get("/folders", response_model=list[folders.FolderOut])
def jig_folders(
    _: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[folders.FolderOut]:
    """카탈로그의 폴더들 — 경로와 바로 그 폴더의 지그 수. 위 폴더도 빠짐없이."""
    return services.jig_folders(db)


@router.post("/folders/rename", response_model=folders.MovedOut)
def rename_folder(
    payload: folders.FolderRenameRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> folders.MovedOut:
    """폴더 이름 바꾸기 · 옮기기(하위까지). 남의 지그가 든 폴더는 관리자만."""
    return folders.MovedOut(
        moved=services.rename_folder(db, user, path=payload.path, to=payload.to)
    )


@router.post("/move", response_model=folders.MovedOut)
def move_jigs(
    payload: folders.FolderMoveRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> folders.MovedOut:
    """지그 여럿을 한 폴더로 — 올린 사람 · 관리자만."""
    return folders.MovedOut(
        moved=services.move_jigs(db, user, ids=payload.ids, folder=payload.folder)
    )


@router.get("", response_model=Page[JigSummaryOut])
def list_jigs(
    part_id: uuid.UUID | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=120),
    tag: str = Query(default="", max_length=40),
    folder: str | None = Query(default=None, max_length=255),
    subfolders: bool = Query(default=True),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[JigSummaryOut]:
    """지그 카탈로그 — `q` · `tag` 로 찾고, `folder` 면 그 폴더(`subfolders` 면 하위까지)."""
    size = clamp_limit(limit)
    rows, total = services.list_jigs(
        db,
        part_id=part_id,
        limit=size,
        offset=offset,
        query=q,
        tag=tag,
        folder=folder,
        subfolders=subfolders,
    )
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
