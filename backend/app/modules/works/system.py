"""내 작업을 온톨로지에 비추는 길 — `kind_class='system'` 타입이 `system_source='work'` 로
가리킨다(ADR 0008 · 0011, `shared/system_sources.py`).

태그(`tagging`)가 작업에 객체를 붙이려면 작업이 선의 한쪽 끝이 돼야 한다. 행은 복제하지 않는다.

**작업은 내 공간의 것이다 — 주인과 시스템 관리자만 본다.** 부품 · 지그(공용)와 다른 점이
그것이고, 원 표 계약의 `lookup` · `list_all` 은 보는 사람을 받지 않는다(그래프 · 내보내기 ·
상세의 관련 객체가 부른다). 그래서 이 원 표는 **요청의 사람**(`request_context.get_viewer`)으로
거른다 — 요청 밖(작업 · 스크립트)이면 아무것도 내지 않는다. 남의 작업은 없는 것과 같은 말이다:
태그 객체를 열어도 남의 작업은 안 보이고, 이름도 감사 기록에 안 남긴다(`tagging.services`).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.works.models import Work
from app.shared import system_sources
from app.shared.request_context import get_viewer
from app.shared.text import clean


def _ref(row: Work) -> system_sources.SystemRef:
    return system_sources.SystemRef(
        id=row.id,
        key=str(row.id),
        label=row.name,
        hint=row.folder or "",
    )


def _base(viewer: uuid.UUID | None, admin: bool) -> Any:
    stmt = select(Work).where(Work.deleted_at.is_(None))
    if admin:
        return stmt
    if viewer is None:
        return stmt.where(false())
    return stmt.where(Work.owner_id == viewer)


def _requested() -> Any:
    seen = get_viewer()
    return _base(*seen) if seen else _base(None, False)


def _search(
    db: Session, viewer: User, q: str | None, limit: int, offset: int
) -> tuple[list[system_sources.SystemRef], int]:
    stmt = _base(viewer.id, viewer.is_system_admin)
    if q:
        needle = f"%{clean(q)}%"
        stmt = stmt.where(Work.name.ilike(needle) | Work.folder.ilike(needle))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Work.name, Work.id).limit(limit).offset(offset))
    return [_ref(row) for row in rows], int(total)


def _lookup(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, system_sources.SystemRef]:
    if not ids:
        return {}
    return {row.id: _ref(row) for row in db.scalars(_requested().where(Work.id.in_(ids)))}


def _list_all(db: Session) -> list[system_sources.SystemRef]:
    return [_ref(row) for row in db.scalars(_requested().order_by(Work.name, Work.id))]


#: `kind_class='system'` 타입이 `system_source='work'` 로 가리키는 원 표.
SYSTEM_SOURCE = system_sources.SystemSource(
    key="work",
    label="작업",
    search=_search,
    lookup=_lookup,
    list_all=_list_all,
)
