"""VOC 라우터 — 게시판이고 절차다. 규칙은 `services` 에 있다."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.voc import services
from app.modules.voc.schemas import (
    VocCreateRequest,
    VocDetailOut,
    VocEventRequest,
    VocEventUpdateRequest,
    VocExportRequest,
    VocOut,
    VocUpdateRequest,
)
from app.shared.auth import current_user
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/voc", tags=["voc"])


@router.get("", response_model=Page[VocOut])
def list_items(
    status: str | None = Query(default=None, max_length=20),
    q: str = Query(default="", max_length=200),
    mine: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[VocOut]:
    """게시판 — **누구나 전부 본다**, 최신이 위다. `q` 는 제목 · 본문 · 작성자."""
    size = clamp_limit(limit)
    rows, total = services.list_items(
        db, user, status=status, query=q, mine=mine, limit=size, offset=offset
    )
    return Page(items=rows, total=total, limit=size, offset=offset)


@router.post("", response_model=VocDetailOut, status_code=201)
def create_item(
    payload: VocCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    """의견 등록 — 번호가 붙고 「등록」 상태로 시작한다. 보던 화면(`page_path`)도 담는다."""
    item = services.create_item(
        db, by=user, title=payload.title, body=payload.body, page_path=payload.page_path
    )
    return services.detail(db, item, user)


@router.post("/export")
def export_items(
    payload: VocExportRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """고른 건들을 zip 하나로 — 건마다 폴더(`item.json` · `attachments/`)와 `index.json`."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=services.export_zip(db, payload.ids, user),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="voc-export-{stamp}.zip"'},
    )


@router.get("/{item_id}", response_model=VocDetailOut)
def get_item(
    item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> VocDetailOut:
    """본문 · 이력 · 첨부, 그리고 **이 사람이 지금 옮길 수 있는 상태**(`allowed`)."""
    return services.detail(db, services.get_item(db, item_id), user)


@router.patch("/{item_id}", response_model=VocDetailOut)
def update_item(
    item_id: uuid.UUID,
    payload: VocUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    """제목 · 본문 수정 — 작성자는 다른 사용자가 말을 남기기 전까지, 관리자는 언제나."""
    item = services.editable_item(db, item_id, user)
    services.update_item(db, item, payload.model_dump(exclude_unset=True))
    return services.detail(db, item, user)


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    """목록 · 상세에서 뺀다(`deleted_at`). 수정과 같은 사람만."""
    services.delete_item(db, services.editable_item(db, item_id, user))


@router.post("/{item_id}/events", response_model=VocDetailOut)
def add_event(
    item_id: uuid.UUID,
    payload: VocEventRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    """상태를 옮기거나(`status`) 말만 보탠다(`status` 없이). 갈 수 있는 곳은 상세의
    `allowed`, 말이 꼭 필요한 곳은 `note_required`."""
    item = services.add_event(
        db, services.get_item(db, item_id), user, status=payload.status, note=payload.note
    )
    return services.detail(db, item, user)


@router.patch("/{item_id}/events/{event_id}", response_model=VocDetailOut)
def update_event(
    item_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: VocEventUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    """이력 한 줄의 말을 고친다 — 시스템 관리자만. 상태 이동은 안 바뀐다."""
    item = services.update_event(
        db, services.get_item(db, item_id), event_id, user, payload.note
    )
    return services.detail(db, item, user)


@router.delete("/{item_id}/events/{event_id}", response_model=VocDetailOut)
def delete_event(
    item_id: uuid.UUID,
    event_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    """이력 한 줄을 지운다 — 시스템 관리자만. 상태는 남은 이력의 마지막 이동으로 돌아간다."""
    item = services.delete_event(db, services.get_item(db, item_id), event_id, user)
    return services.detail(db, item, user)


@router.post("/{item_id}/attachments", response_model=VocDetailOut, status_code=201)
def upload_attachment(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    """파일 하나를 붙인다(한 파일 25 MB) — 작성자와 관리자."""
    item = services.attach(
        db,
        services.get_item(db, item_id),
        user,
        filename=file.filename or "attachment",
        content_type=file.content_type,
        stream=file.file,
    )
    return services.detail(db, item, user)


@router.get("/{item_id}/attachments/{attachment_id}", response_class=FileResponse)
def download_attachment(
    item_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """**첨부로만 내린다.** 올린 파일은 무엇이든 될 수 있다 — HTML 을 문서로 열면 그 안의
    스크립트가 이 사이트의 권한으로 돈다."""
    row = services.attachment(db, services.get_item(db, item_id), attachment_id)
    return FileResponse(
        services.attachment_path(row),
        media_type="application/octet-stream",
        filename=row.filename,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{item_id}/attachments/{attachment_id}", response_model=VocDetailOut)
def delete_attachment(
    item_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    """첨부를 뗀다(파일도 지운다) — 작성자와 관리자."""
    item = services.detach(db, services.get_item(db, item_id), user, attachment_id)
    return services.detail(db, item, user)
