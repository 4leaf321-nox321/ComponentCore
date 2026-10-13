"""계정을 온톨로지에 비추는 길 — StandardPlatform `accounts/services.py` 의 「온톨로지가 계정을
비추는 길」 그대로(ADR 0008). `kind_class='system'` 타입이 `system_source='user'` 로 가리킨다.

CompCore 의 계정 서비스(`services.py`)는 손대지 않고 여기 따로 둔다 — 들인 것과 원래 것을
가른다.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.shared import extensions, system_sources
from app.shared.text import clean


def stats(db: Session) -> list[extensions.StatItem]:
    total = (
        db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0
    )
    return [extensions.StatItem(label="계정", count=total)]


def _system_ref(row: User) -> system_sources.SystemRef:
    return system_sources.SystemRef(
        id=row.id,
        key=row.email,
        label=row.display_name or row.email,
        hint=row.email,
        active=row.deleted_at is None and row.status == "active",
    )


def _system_base() -> Any:
    # 지워진 계정은 없는 것이다. 정지는 **있되 못 고르는** 것 — 이미 걸린 「담당자」 칸이 빈
    # 칸으로 변하면 안 되기 때문이다.
    return select(User).where(User.deleted_at.is_(None))


def _system_search(
    db: Session, _viewer: User, q: str | None, limit: int, offset: int
) -> tuple[list[system_sources.SystemRef], int]:
    stmt = _system_base()
    if q:
        needle = f"%{clean(q)}%"
        stmt = stmt.where(User.display_name.ilike(needle) | User.email.ilike(needle))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.display_name, User.email).limit(limit).offset(offset))
    return [_system_ref(row) for row in rows], int(total)


def _system_lookup(
    db: Session, ids: list[uuid.UUID]
) -> dict[uuid.UUID, system_sources.SystemRef]:
    if not ids:
        return {}
    found = db.scalars(_system_base().where(User.id.in_(ids)))
    return {row.id: _system_ref(row) for row in found}


def _system_list_all(db: Session) -> list[system_sources.SystemRef]:
    return [
        _system_ref(row)
        for row in db.scalars(_system_base().order_by(User.display_name, User.email))
    ]


#: `kind_class='system'` 타입이 `system_source='user'` 로 가리키는 원 표.
SYSTEM_SOURCE = system_sources.SystemSource(
    key="user",
    label="계정",
    search=_system_search,
    lookup=_system_lookup,
    list_all=_system_list_all,
)
