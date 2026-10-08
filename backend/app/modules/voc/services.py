"""VOC — 게시판이고 절차다.

접수는 누구나(로그인한 사람). **목록도 누구나 본다** — 같은 문제를 여럿이 따로 내고 무엇이
고쳐졌는지 낸 사람만 아는 것을 막는다. 상태를 옮기는 것은 관리자와 낸 사람이 각자 갈 수 있는
곳만(`models.ADMIN_MOVES` · `AUTHOR_MOVES`), 말을 보태는 것은 누구나.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.voc.models import (
    ADMIN_MOVES,
    AUTHOR_MOVES,
    NOTE_REQUIRED,
    VOC_STATUS_LABELS,
    VOC_STATUSES,
    VocAttachment,
    VocEvent,
    VocItem,
)
from app.modules.voc.schemas import (
    VocAttachmentOut,
    VocDetailOut,
    VocEventOut,
    VocOut,
    VocSummaryOut,
)
from app.shared import filestore, search
from app.shared.errors import AppError, Forbidden, NotFound, code

#: 옮기는 단추에 적을 말. 상태 이름만 적으면 「해결」 이 지금 상태인지 갈 곳인지 안 갈린다.
MOVE_LABELS: dict[str, str] = {
    "open": "다시 열기",
    "accepted": "접수",
    "in_progress": "처리 시작",
    "resolved": "해결 처리",
    "closed": "확인 후 종료",
    "rejected": "반려",
}

#: 첨부 한 개의 상한. 화면 캡처 · 로그 · 작은 STEP 이 대상이다 — 큰 형상은 작업으로 올린다.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def _label(status: str) -> str:
    return VOC_STATUS_LABELS.get(status, status)


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    """이름을 **한 번에** 읽는다. 줄마다 `db.get` 하면 목록이 N+1 이다."""
    wanted = {one for one in ids if one is not None}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(wanted))).all()
    return {row.id: row.display_name for row in rows}


def _name(names: dict[uuid.UUID, str], user_id: uuid.UUID | None) -> str | None:
    return names.get(user_id) if user_id is not None else None


def _others_spoke(db: Session, item: VocItem) -> bool:
    """낸 사람 아닌 누군가가 이 건에 말을 남겼는가."""
    count = db.scalar(
        select(func.count())
        .select_from(VocEvent)
        .where(VocEvent.item_id == item.id, VocEvent.by_id != item.created_by_id)
    )
    return bool(count)


def _editable(db: Session, item: VocItem, user: User) -> bool:
    """고치거나 지울 수 있는가 — **낸 사람은 남이 말을 남기기 전까지, 관리자는 언제나.**
    남의 말이 달린 뒤에 본문이 바뀌면 그 말이 딴소리가 된다. 그때는 말을 보태는 것이 맞다."""
    if user.is_system_admin:
        return True
    if item.created_by_id != user.id:
        return False
    return not _others_spoke(db, item)


def _moves(item: VocItem, user: User) -> list[str]:
    """이 사람이 지금 옮길 수 있는 상태. 관리자면 관리자 것에 낸 사람 것을 더한다."""
    allowed: list[str] = []
    if user.is_system_admin:
        allowed.extend(ADMIN_MOVES.get(item.status, ()))
    if item.created_by_id == user.id:
        allowed.extend(one for one in AUTHOR_MOVES.get(item.status, ()) if one not in allowed)
    return allowed


def _can_attach(item: VocItem, user: User) -> bool:
    """붙이고 떼는 것은 낸 사람과 관리자 — 남이 말을 남긴 뒤에도 된다(캡처를 나중에 보태는 것이
    흔하다). 글 자체를 고치는 규칙(`_editable`)과는 다르다."""
    return bool(user.is_system_admin or item.created_by_id == user.id)


def _out(
    item: VocItem,
    *,
    viewer: User,
    names: dict[uuid.UUID, str],
    editable: bool,
    event_count: int,
    attachment_count: int,
) -> VocOut:
    return VocOut(
        id=item.id,
        seq=item.seq,
        title=item.title,
        status=item.status,
        status_label=_label(item.status),
        page_path=item.page_path,
        created_at=item.created_at,
        created_by=_name(names, item.created_by_id),
        status_at=item.status_at,
        status_by=_name(names, item.status_by_id),
        is_mine=item.created_by_id == viewer.id,
        can_edit=editable,
        event_count=event_count,
        attachment_count=attachment_count,
    )


def _events(db: Session, item: VocItem) -> list[VocEvent]:
    return list(
        db.scalars(
            select(VocEvent)
            .where(VocEvent.item_id == item.id)
            .order_by(VocEvent.at, VocEvent.id)
        )
    )


def _attachments(db: Session, item: VocItem) -> list[VocAttachment]:
    return list(
        db.scalars(
            select(VocAttachment)
            .where(VocAttachment.item_id == item.id)
            .order_by(VocAttachment.created_at, VocAttachment.id)
        )
    )


def detail(db: Session, item: VocItem, viewer: User) -> VocDetailOut:
    events = _events(db, item)
    attachments = _attachments(db, item)
    names = _names(
        db,
        {
            item.created_by_id,
            item.status_by_id,
            *(one.by_id for one in events),
            *(one.created_by_id for one in attachments),
        },
    )
    allowed = _moves(item, viewer)
    head = _out(
        item,
        viewer=viewer,
        names=names,
        editable=_editable(db, item, viewer),
        # 등록 이벤트는 빼고 센다 — 「말이 오간 건」 을 세는 수다.
        event_count=max(len(events) - 1, 0),
        attachment_count=len(attachments),
    )
    return VocDetailOut(
        **head.model_dump(),
        body=item.body,
        events=[
            VocEventOut(
                id=one.id,
                at=one.at,
                by=_name(names, one.by_id),
                from_status=one.from_status,
                to_status=one.to_status,
                to_status_label=_label(one.to_status),
                note=one.note,
            )
            for one in events
        ],
        attachments=[
            VocAttachmentOut(
                id=one.id,
                filename=one.filename,
                content_type=one.content_type,
                size=one.size,
                created_at=one.created_at,
                created_by=_name(names, one.created_by_id),
                url=f"/api/voc/{item.id}/attachments/{one.id}",
            )
            for one in attachments
        ],
        can_attach=_can_attach(item, viewer),
        allowed=allowed,
        allowed_labels={one: MOVE_LABELS.get(one, one) for one in allowed},
        note_required=[one for one in allowed if one in NOTE_REQUIRED],
        can_delete_events=bool(viewer.is_system_admin),
    )


def get_item(db: Session, item_id: uuid.UUID) -> VocItem:
    """지운 건은 없는 것으로 본다."""
    item = db.get(VocItem, item_id)
    if item is None or item.deleted_at is not None:
        raise NotFound(code("VOC", 1), "VOC를 찾을 수 없습니다.")
    return item


def create_item(
    db: Session, *, by: User, title: str, body: str, page_path: str | None
) -> VocItem:
    now = datetime.now(UTC)
    item = VocItem(
        title=title,
        body=body,
        page_path=page_path,
        created_by_id=by.id,
        status="open",
        status_at=now,
        status_by_id=by.id,
    )
    db.add(item)
    db.flush()
    # **등록도 이벤트다.** 이력의 첫 줄이 「누가 언제 냈다」 여야 절차가 처음부터 읽힌다.
    db.add(VocEvent(item_id=item.id, at=now, by_id=by.id, from_status=None, to_status="open"))
    db.commit()
    db.refresh(item)
    return item


def list_items(
    db: Session,
    viewer: User,
    *,
    status: str | None,
    query: str,
    mine: bool,
    limit: int,
    offset: int,
) -> tuple[list[VocOut], int]:
    """게시판 — **누구나 전부 본다**, 최신이 위다."""
    stmt = select(VocItem).where(VocItem.deleted_at.is_(None))
    if status:
        if status not in VOC_STATUSES:
            raise AppError(code("VOC", 2), "허용되지 않는 상태입니다.", status=422)
        stmt = stmt.where(VocItem.status == status)
    if mine:
        stmt = stmt.where(VocItem.created_by_id == viewer.id)
    found = search.matches(
        query, columns=[VocItem.title, VocItem.body], owner=VocItem.created_by_id
    )
    if found is not None:
        stmt = stmt.where(found)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(VocItem.seq.desc()).limit(limit).offset(offset)))
    ids = [one.id for one in items]
    names = _names(
        db, {one.created_by_id for one in items} | {one.status_by_id for one in items}
    )
    # 건마다 세지 않는다 — 한 번에 묶어 센다.
    counts: dict[uuid.UUID, int] = {}
    files: dict[uuid.UUID, int] = {}
    spoken: set[uuid.UUID] = set()
    if ids:
        for item_id, count in db.execute(
            select(VocEvent.item_id, func.count())
            .where(VocEvent.item_id.in_(ids))
            .group_by(VocEvent.item_id)
        ).all():
            counts[item_id] = int(count)
        for item_id, count in db.execute(
            select(VocAttachment.item_id, func.count())
            .where(VocAttachment.item_id.in_(ids))
            .group_by(VocAttachment.item_id)
        ).all():
            files[item_id] = int(count)
        authors = {one.id: one.created_by_id for one in items}
        for item_id, by_id in db.execute(
            select(VocEvent.item_id, VocEvent.by_id)
            .where(VocEvent.item_id.in_(ids))
            .distinct()
        ).all():
            if by_id != authors.get(item_id):
                spoken.add(item_id)
    rows = [
        _out(
            one,
            viewer=viewer,
            names=names,
            editable=viewer.is_system_admin
            or (one.created_by_id == viewer.id and one.id not in spoken),
            event_count=max(counts.get(one.id, 0) - 1, 0),
            attachment_count=files.get(one.id, 0),
        )
        for one in items
    ]
    return rows, int(total)


def summary(db: Session, user: User) -> VocSummaryOut:
    """이 사용자가 손댈 차례인 건 — 관리자는 접수 대기, 작성자는 확인 대기."""

    def count(*where: Any) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(VocItem)
                .where(VocItem.deleted_at.is_(None), *where)
            )
            or 0
        )

    return VocSummaryOut(
        waiting=count(VocItem.status == "open") if user.is_system_admin else 0,
        to_confirm=count(VocItem.status == "resolved", VocItem.created_by_id == user.id),
    )


def editable_item(db: Session, item_id: uuid.UUID, user: User) -> VocItem:
    """고치거나 지울 수 있는 것만 돌려준다. 규칙은 `_editable` 과 같다 — 화면은 단추를 감출
    뿐이고, 주소를 아는 사람은 여기서 막힌다."""
    item = get_item(db, item_id)
    if user.is_system_admin:
        return item
    if item.created_by_id != user.id:
        raise Forbidden(code("VOC", 3), "본인이 등록한 VOC만 수정하거나 삭제할 수 있습니다.")
    if _others_spoke(db, item):
        raise Forbidden(
            code("VOC", 4),
            "다른 사용자가 댓글을 남긴 뒤에는 수정하거나 삭제할 수 없습니다. "
            "덧붙일 내용은 댓글로 남기십시오.",
        )
    return item


def update_item(db: Session, item: VocItem, changes: dict[str, Any]) -> VocItem:
    """**안 보낸 것과 비운 것을 가른다** — 라우터가 `exclude_unset` 으로 넘긴다."""
    if changes.get("title") is not None:
        item.title = str(changes["title"])
    if changes.get("body") is not None:
        item.body = str(changes["body"])
    db.commit()
    return item


def delete_item(db: Session, item: VocItem) -> None:
    """`deleted_at` 만 채운다 — 행 · 이력 · 첨부 파일은 남는다(AGENTS.md 「지우지 않는다」)."""
    item.deleted_at = datetime.now(UTC)
    db.commit()


def add_event(
    db: Session, item: VocItem, user: User, *, status: str | None, note: str | None
) -> VocItem:
    """상태를 옮기거나 말을 보탠다. **갈 수 있는 곳만 간다** — 「해결됐다」 는 관리자가 말하고
    「됐다」 는 낸 사람이 확인한다. 말만 보태는 것은 보는 사람 누구나 할 수 있다."""
    text = (note or "").strip() or None
    if status is not None:
        if status not in VOC_STATUSES:
            raise AppError(code("VOC", 2), "허용되지 않는 상태입니다.", status=422)
        if status == item.status:
            raise AppError(
                code("VOC", 5),
                f"이미 ‘{_label(status)}’ 상태입니다. "
                "댓글만 남기려면 상태를 선택하지 마십시오.",
                status=422,
            )
        allowed = _moves(item, user)
        if status not in allowed:
            where = (
                " 지금 옮길 수 있는 상태: " + ", ".join(_label(one) for one in allowed) + "."
                if allowed
                else ""
            )
            raise Forbidden(
                code("VOC", 6),
                f"‘{_label(item.status)}’ 상태에서 ‘{_label(status)}’ 상태로 옮길 수 "
                f"없습니다.{where}",
            )
        if status in NOTE_REQUIRED and text is None:
            raise AppError(
                code("VOC", 7),
                f"‘{_label(status)}’ 상태로 옮길 때는 내용을 입력해야 합니다. 조치 내용이나 "
                "사유가 없으면 작성자가 다시 문의해야 합니다.",
                status=422,
            )
    now = datetime.now(UTC)
    db.add(
        VocEvent(
            item_id=item.id,
            at=now,
            by_id=user.id,
            from_status=item.status,
            to_status=status or item.status,
            note=text,
        )
    )
    if status is not None:
        item.status = status
        item.status_at = now
        item.status_by_id = user.id
    db.commit()
    return item


def _event(db: Session, item: VocItem, event_id: uuid.UUID, user: User) -> VocEvent:
    if not user.is_system_admin:
        raise Forbidden(
            code("VOC", 8), "이력은 시스템 관리자만 수정하거나 삭제할 수 있습니다."
        )
    event = db.get(VocEvent, event_id)
    if event is None or event.item_id != item.id:
        raise NotFound(code("VOC", 9), "해당 이력을 찾을 수 없습니다.")
    return event


def update_event(
    db: Session, item: VocItem, event_id: uuid.UUID, user: User, note: str | None
) -> VocItem:
    """이력 한 줄의 말을 고친다 — **시스템 관리자만.** 옮기면서 적었어야 할 말을 빠뜨린 경우다.
    말이 필수인 상태로 옮긴 줄은 비울 수 없고, 댓글을 비우려면 줄을 지운다."""
    event = _event(db, item, event_id, user)
    text = (note or "").strip() or None
    moved = event.from_status is not None and event.from_status != event.to_status
    if text is None and moved and event.to_status in NOTE_REQUIRED:
        raise AppError(
            code("VOC", 7),
            f"‘{_label(event.to_status)}’ 상태로 옮긴 이력의 내용은 비울 수 없습니다.",
            status=422,
        )
    if text is None and not moved:
        raise AppError(
            code("VOC", 11), "댓글의 내용을 비우려면 해당 이력을 삭제하십시오.", status=422
        )
    event.note = text
    db.commit()
    return item


def delete_event(db: Session, item: VocItem, event_id: uuid.UUID, user: User) -> VocItem:
    """이력 한 줄을 지운다 — **시스템 관리자만.** 「해결」 로 옮겼다가 되돌리는 실수가 난다.
    지우면 **상태는 남은 이력에서 다시 정한다** — 마지막으로 상태를 옮긴 줄이 곧 지금 상태다.
    등록 줄은 못 지운다: 그것이 건의 시작이다."""
    event = _event(db, item, event_id, user)
    if event.from_status is None:
        raise AppError(
            code("VOC", 10),
            "등록 이력은 삭제할 수 없습니다. VOC 자체를 삭제하려면 VOC를 삭제하십시오.",
            status=422,
        )
    db.delete(event)
    db.flush()
    remaining = list(
        db.scalars(
            select(VocEvent)
            .where(VocEvent.item_id == item.id)
            .order_by(VocEvent.at.desc(), VocEvent.id.desc())
        )
    )
    # 댓글(from == to)은 상태를 안 바꾼다.
    last_move = next(
        (
            one
            for one in remaining
            if one.from_status is None or one.from_status != one.to_status
        ),
        None,
    )
    if last_move is not None:
        item.status = last_move.to_status
        item.status_at = last_move.at
        item.status_by_id = last_move.by_id
    db.commit()
    return item


# --- 첨부 -------------------------------------------------------------------------


def _require_attach(item: VocItem, user: User) -> None:
    if not _can_attach(item, user):
        raise Forbidden(
            code("VOC", 12), "본인이 등록한 VOC에만 파일을 첨부하거나 삭제할 수 있습니다."
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def attach(
    db: Session,
    item: VocItem,
    user: User,
    *,
    filename: str,
    content_type: str | None,
    stream: BinaryIO,
) -> VocItem:
    """파일 하나를 붙인다. 여럿이면 여러 번 부른다 — 하나가 커서 막혀도 나머지는 붙는다."""
    _require_attach(item, user)
    attachment_id = uuid.uuid4()
    safe = filestore.safe_filename(filename or "attachment")
    target = filestore.root() / "voc" / str(item.id) / str(attachment_id) / safe
    try:
        size = filestore.save_stream(stream, target, limit_bytes=MAX_ATTACHMENT_BYTES)
    except ValueError as failure:
        raise AppError(
            code("VOC", 14),
            f"첨부 파일은 {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB까지 "
            "업로드할 수 있습니다.",
            status=413,
        ) from failure
    db.add(
        VocAttachment(
            id=attachment_id,
            item_id=item.id,
            filename=safe,
            content_type=(content_type or "application/octet-stream").split(";")[0].strip()
            or "application/octet-stream",
            size=size,
            sha256=_sha256(target),
            path=filestore.relative_to_root(target),
            created_by_id=user.id,
        )
    )
    db.commit()
    return item


def attachment(db: Session, item: VocItem, attachment_id: uuid.UUID) -> VocAttachment:
    row = db.get(VocAttachment, attachment_id)
    if row is None or row.item_id != item.id:
        raise NotFound(code("VOC", 13), "첨부 파일을 찾을 수 없습니다.")
    return row


def attachment_path(row: VocAttachment) -> Path:
    path = filestore.resolve(row.path)
    if not path.is_file():
        raise AppError(code("VOC", 15), "첨부 파일이 저장소에 없습니다.", status=404)
    return path


def detach(db: Session, item: VocItem, user: User, attachment_id: uuid.UUID) -> VocItem:
    """뗀다 — 올린 사람이 스스로 빼는 것이라 파일도 지운다."""
    _require_attach(item, user)
    row = attachment(db, item, attachment_id)
    filestore.remove_dir(f"voc/{item.id}/{row.id}")
    db.delete(row)
    db.commit()
    return item


# --- 내보내기 ------------------------------------------------------------------------


def _folder_name(item: VocItem) -> str:
    """`voc-0012-제목` — 번호가 앞이라 정렬되고, 제목은 파일 이름에 못 쓰는 글자를 뺀다."""
    slug = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", item.title).strip()
    slug = re.sub(r"\s+", "-", slug)[:60].strip("-.")
    return f"voc-{item.seq:04d}" + (f"-{slug}" if slug else "")


def export_zip(db: Session, ids: list[uuid.UUID], user: User) -> bytes:
    """고른 건들을 zip 하나로 — **건마다 폴더**, 그 안에 `item.json` 과 `attachments/`.

    `item.json` 이 제목 · 본문 · 상태 · 이력과 첨부 목록을 들고, 첨부는 폴더 안 파일을 상대
    경로로 가리킨다. 맨 위 `index.json` 이 건 목록이다. 사람이 읽고 다른 곳(이슈 트래커 ·
    보고서)으로 옮기는 용도라 JSON 은 들여쓴다."""
    wanted = list(dict.fromkeys(ids))
    items = {
        one.id: one
        for one in db.scalars(
            select(VocItem).where(VocItem.id.in_(wanted), VocItem.deleted_at.is_(None))
        )
    }
    missing = [str(one) for one in wanted if one not in items]
    if missing:
        raise NotFound(code("VOC", 1), "VOC를 찾을 수 없습니다: " + ", ".join(missing))

    buffer = io.BytesIO()
    index: list[dict[str, Any]] = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(items.values(), key=lambda one: one.seq):
            folder = _folder_name(item)
            shown = detail(db, item, user)
            used: set[str] = set()
            files: list[dict[str, Any]] = []
            rows = _attachments(db, item)
            uploaders = _names(db, {row.created_by_id for row in rows})
            for row in rows:
                # 같은 이름이 둘이면 뒤엣것에 첨부 id 앞자리를 붙인다 — 덮어쓰지 않는다.
                name = row.filename
                if name in used:
                    stem, dot, ext = name.rpartition(".")
                    name = f"{stem or ext}-{str(row.id)[:8]}{dot}{ext if stem else ''}"
                used.add(name)
                relative = f"attachments/{name}"
                path = filestore.resolve(row.path)
                if path.is_file():
                    bundle.write(path, f"{folder}/{relative}")
                    files.append(
                        {
                            "filename": row.filename,
                            "path": relative,
                            "content_type": row.content_type,
                            "size": row.size,
                            "sha256": row.sha256,
                            "uploaded_by": _name(uploaders, row.created_by_id),
                        }
                    )
                else:
                    files.append({"filename": row.filename, "path": None, "missing": True})
            body = {
                "seq": item.seq,
                "id": str(item.id),
                "title": item.title,
                "body": item.body,
                "status": item.status,
                "status_label": shown.status_label,
                "page_path": item.page_path,
                "created_at": item.created_at.isoformat(),
                "created_by": shown.created_by,
                "events": [
                    {
                        "at": one.at.isoformat(),
                        "by": one.by,
                        "from_status": one.from_status,
                        "to_status": one.to_status,
                        "to_status_label": one.to_status_label,
                        "note": one.note,
                    }
                    for one in shown.events
                ],
                "attachments": files,
            }
            bundle.writestr(
                f"{folder}/item.json", json.dumps(body, ensure_ascii=False, indent=2)
            )
            index.append(
                {
                    "seq": item.seq,
                    "title": item.title,
                    "status": item.status,
                    "folder": folder,
                    "item": f"{folder}/item.json",
                    "attachments": len(files),
                }
            )
        bundle.writestr(
            "index.json",
            json.dumps(
                {
                    "exported_at": datetime.now(UTC).isoformat(),
                    "exported_by": user.display_name,
                    "count": len(index),
                    "items": index,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return buffer.getvalue()
