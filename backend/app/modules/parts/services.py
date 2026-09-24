"""부품 카탈로그 — 읽기와 이름 고치기뿐. 버전은 승격(`modules/works`)으로만 생긴다."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.jigs.models import Jig
from app.modules.jobs import services as jobs
from app.modules.jobs.models import Job
from app.modules.parts.models import Part, PartVersion
from app.modules.parts.schemas import PartOut, PartSummaryOut, PartVersionOut
from app.shared.errors import Forbidden, NotFound, code


def get_part(db: Session, part_id: uuid.UUID) -> Part:
    part = db.get(Part, part_id)
    if part is None or part.deleted_at is not None:
        raise NotFound(code("PARTS", 1), "부품을 찾을 수 없습니다.")
    return part


def require_owner(part: Part, user: User) -> None:
    if part.owner_id != user.id and not user.is_system_admin:
        raise Forbidden(code("PARTS", 2), "이 부품을 고칠 권한이 없습니다.")


def get_version(db: Session, part: Part, number: int) -> PartVersion:
    version = db.scalar(
        select(PartVersion).where(PartVersion.part_id == part.id, PartVersion.number == number)
    )
    if version is None:
        raise NotFound(code("PARTS", 3), f"버전 {number} 이 없습니다.")
    return version


def current_version(db: Session, part: Part) -> PartVersion | None:
    return get_version(db, part, part.current_version) if part.current_version > 0 else None


def version_out(db: Session, version: PartVersion) -> PartVersionOut:
    who = db.get(User, version.promoted_by_id) if version.promoted_by_id else None
    job = db.get(Job, version.job_id) if version.job_id else None
    return PartVersionOut(
        id=version.id,
        part_id=version.part_id,
        number=version.number,
        recipe=version.recipe,
        job=jobs.job_out(db, job) if job else None,
        note=version.note,
        promoted_by_id=version.promoted_by_id,
        promoted_by_name=who.display_name if who else None,
        work_version_id=version.work_version_id,
        created_at=version.created_at,
    )


def _jig_count(db: Session, part_id: uuid.UUID) -> int:
    return int(
        db.scalar(select(func.count()).where(Jig.part_id == part_id, Jig.deleted_at.is_(None)))
        or 0
    )


def part_out(db: Session, part: Part) -> PartOut:
    owner = db.get(User, part.owner_id)
    count = int(db.scalar(select(func.count()).where(PartVersion.part_id == part.id)) or 0)
    current = current_version(db, part)
    return PartOut(
        id=part.id,
        name=part.name,
        description=part.description,
        owner_id=part.owner_id,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        work_id=part.work_id,
        current_version=part.current_version,
        version_count=count,
        current=version_out(db, current) if current else None,
        jig_count=_jig_count(db, part.id),
        created_at=part.created_at,
        tags=list(part.tags or []),
        updated_at=part.updated_at,
    )


def part_summary(db: Session, part: Part) -> PartSummaryOut:
    owner = db.get(User, part.owner_id)
    return PartSummaryOut(
        id=part.id,
        name=part.name,
        description=part.description,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        current_version=part.current_version,
        jig_count=_jig_count(db, part.id),
        tags=list(part.tags or []),
        updated_at=part.updated_at,
    )


def list_parts(
    db: Session, *, limit: int, offset: int, query: str = "", tag: str = ""
) -> tuple[list[Part], int]:
    base = select(Part).where(Part.deleted_at.is_(None))
    if query.strip():
        like = f"%{query.strip()}%"
        base = base.where(or_(Part.name.ilike(like), Part.description.ilike(like)))
    if tag.strip():
        base = base.where(Part.tags.contains([tag.strip()]))
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(db.scalars(base.order_by(Part.updated_at.desc()).limit(limit).offset(offset)))
    return rows, total


def list_versions(db: Session, part: Part) -> list[PartVersion]:
    return list(
        db.scalars(
            select(PartVersion)
            .where(PartVersion.part_id == part.id)
            .order_by(PartVersion.number.desc())
        )
    )


def update_part(db: Session, part: Part, *, fields: dict[str, Any]) -> Part:
    for key, value in fields.items():
        if value is not None:
            setattr(part, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(part)
    return part


def delete_part(db: Session, part: Part) -> None:
    part.deleted_at = datetime.now(UTC)
    db.commit()


def all_tags(db: Session) -> list[str]:
    """카탈로그에 붙은 꼬리표 전부 — 거르개 · 자동 완성. 많이 쓰인 것이 앞이다.

    내 작업의 `my_tags` 와 **같은 모양**이다(화면이 한 벌이면 된다). 다만 여기는 **남의
    것까지** 센다 — 공용 공간이라 그것이 맞다."""
    seen: dict[str, int] = {}
    for tags in db.scalars(select(Part.tags).where(Part.deleted_at.is_(None))):
        for one in tags or []:
            seen[one] = seen.get(one, 0) + 1
    return sorted(seen, key=lambda t: (-seen[t], t))
