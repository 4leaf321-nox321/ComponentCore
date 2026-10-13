"""지그를 온톨로지에 비추는 길 — `kind_class='system'` 타입이
`system_source='jig'` 로 가리킨다(ADR 0008, `shared/system_sources.py`).

행을 복제하지 않는다. SP 에서 받은 제품 · 프로젝트 같은 객체가 **이 지그 자체**를 관계 ·
참조 칸으로 가리키고, 그 선은 `object_links` 에 남는다. 지그 이름을 바꾸면 온톨로지 쪽도 그
이름을 본다.

지그는 모든 사용자가 본다(공용 공간) — 보는 사람으로 거르지 않는다. 지운 지그는 없는
것이다. 식별자(`key`)는 id 다 — 이름은 겹칠 수 있어 파일로 넣을 때 사람을 헷갈리게 한다.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.jigs.models import Jig
from app.shared import system_sources
from app.shared.text import clean


def _ref(row: Jig) -> system_sources.SystemRef:
    return system_sources.SystemRef(
        id=row.id,
        key=str(row.id),
        label=row.name,
        hint=row.folder or "",
    )


def _base() -> Any:
    return select(Jig).where(Jig.deleted_at.is_(None))


def _search(
    db: Session, _viewer: User, q: str | None, limit: int, offset: int
) -> tuple[list[system_sources.SystemRef], int]:
    stmt = _base()
    if q:
        needle = f"%{clean(q)}%"
        stmt = stmt.where(Jig.name.ilike(needle) | Jig.folder.ilike(needle))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Jig.name, Jig.id).limit(limit).offset(offset))
    return [_ref(row) for row in rows], int(total)


def _lookup(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, system_sources.SystemRef]:
    if not ids:
        return {}
    return {row.id: _ref(row) for row in db.scalars(_base().where(Jig.id.in_(ids)))}


def _list_all(db: Session) -> list[system_sources.SystemRef]:
    return [_ref(row) for row in db.scalars(_base().order_by(Jig.name, Jig.id))]


#: `kind_class='system'` 타입이 `system_source='jig'` 로 가리키는 원 표.
SYSTEM_SOURCE = system_sources.SystemSource(
    key="jig",
    label="지그",
    search=_search,
    lookup=_lookup,
    list_all=_list_all,
)
