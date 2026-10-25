"""템플릿을 온톨로지에 비추는 길 — `kind_class='system'` 타입이 `system_source='template'`
로 가리킨다(ADR 0011, `shared/system_sources.py`). 태그가 템플릿에도 객체를 붙이려면 선의 한쪽
끝이 돼야 한다. 행은 복제하지 않는다.

**공용(`is_shared`)이 아닌 템플릿은 주인만 본다**(`services.get_template` 과 같은 규칙 —
관리자도 남의 내 템플릿은 안 본다). 그래서 작업 원 표(`works/system.py`)처럼 **요청의
사람**으로 거른다 — 요청 밖이면 공용만 낸다.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.templates.models import RecipeTemplate
from app.shared import system_sources
from app.shared.request_context import get_viewer
from app.shared.text import clean


def _ref(row: RecipeTemplate) -> system_sources.SystemRef:
    return system_sources.SystemRef(
        id=row.id, key=str(row.id), label=row.name, hint=row.folder or ""
    )


def _base(viewer: uuid.UUID | None) -> Any:
    shared = RecipeTemplate.is_shared.is_(True)
    if viewer is None:
        return select(RecipeTemplate).where(shared)
    return select(RecipeTemplate).where(or_(shared, RecipeTemplate.owner_id == viewer))


def _requested() -> Any:
    seen = get_viewer()
    return _base(seen[0] if seen else None)


def _search(
    db: Session, viewer: User, q: str | None, limit: int, offset: int
) -> tuple[list[system_sources.SystemRef], int]:
    stmt = _base(viewer.id)
    if q:
        needle = f"%{clean(q)}%"
        stmt = stmt.where(
            RecipeTemplate.name.ilike(needle) | RecipeTemplate.folder.ilike(needle)
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(RecipeTemplate.name, RecipeTemplate.id).limit(limit).offset(offset)
    )
    return [_ref(row) for row in rows], int(total)


def _lookup(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, system_sources.SystemRef]:
    if not ids:
        return {}
    found = db.scalars(_requested().where(RecipeTemplate.id.in_(ids)))
    return {row.id: _ref(row) for row in found}


def _list_all(db: Session) -> list[system_sources.SystemRef]:
    found = db.scalars(_requested().order_by(RecipeTemplate.name, RecipeTemplate.id))
    return [_ref(row) for row in found]


#: `kind_class='system'` 타입이 `system_source='template'` 로 가리키는 원 표.
SYSTEM_SOURCE = system_sources.SystemSource(
    key="template",
    label="템플릿",
    search=_search,
    lookup=_lookup,
    list_all=_list_all,
)
