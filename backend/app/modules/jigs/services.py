"""지그 카탈로그 — 읽기와 이름 고치기뿐. 버전은 승격(`modules/works.promote_jig`)으로만
생긴다."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.jigs.models import Jig, JigVersion
from app.modules.jigs.schemas import JigOut, JigSummaryOut, JigVersionOut
from app.modules.jobs import services as jobs
from app.modules.jobs.models import Job
from app.modules.parts.models import Part, PartVersion
from app.shared.errors import Forbidden, NotFound, code


def get_jig(db: Session, jig_id: uuid.UUID) -> Jig:
    jig = db.get(Jig, jig_id)
    if jig is None or jig.deleted_at is not None:
        raise NotFound(code("JIGS", 1), "지그를 찾을 수 없습니다.")
    return jig


def require_owner(jig: Jig, user: User) -> None:
    if jig.owner_id != user.id and not user.is_system_admin:
        raise Forbidden(code("JIGS", 2), "이 지그를 고칠 권한이 없습니다.")


def get_version(db: Session, jig: Jig, number: int) -> JigVersion:
    version = db.scalar(
        select(JigVersion).where(JigVersion.jig_id == jig.id, JigVersion.number == number)
    )
    if version is None:
        raise NotFound(code("JIGS", 3), f"버전 {number} 이 없습니다.")
    return version


def current_version(db: Session, jig: Jig) -> JigVersion | None:
    return get_version(db, jig, jig.current_version) if jig.current_version > 0 else None


def version_out(db: Session, version: JigVersion) -> JigVersionOut:
    who = db.get(User, version.promoted_by_id) if version.promoted_by_id else None
    job = db.get(Job, version.job_id) if version.job_id else None
    part_version = (
        db.get(PartVersion, version.part_version_id) if version.part_version_id else None
    )
    part = db.get(Part, part_version.part_id) if part_version else None
    return JigVersionOut(
        id=version.id,
        jig_id=version.jig_id,
        number=version.number,
        job=jobs.job_out(db, job) if job else None,
        options=version.options,
        summary=version.summary,
        part_id=part.id if part else None,
        part_name=part.name if part else None,
        part_version=part_version.number if part_version else None,
        note=version.note,
        promoted_by_name=who.display_name if who else None,
        created_at=version.created_at,
    )


def jig_out(db: Session, jig: Jig) -> JigOut:
    owner = db.get(User, jig.owner_id)
    part = db.get(Part, jig.part_id) if jig.part_id else None
    count = int(db.scalar(select(func.count()).where(JigVersion.jig_id == jig.id)) or 0)
    current = current_version(db, jig)
    return JigOut(
        id=jig.id,
        name=jig.name,
        description=jig.description,
        owner_id=jig.owner_id,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        work_id=jig.work_id,
        part_id=jig.part_id,
        part_name=part.name if part else None,
        current_version=jig.current_version,
        version_count=count,
        current=version_out(db, current) if current else None,
        created_at=jig.created_at,
        updated_at=jig.updated_at,
    )


def jig_summary(db: Session, jig: Jig) -> JigSummaryOut:
    owner = db.get(User, jig.owner_id)
    part = db.get(Part, jig.part_id) if jig.part_id else None
    current = current_version(db, jig)
    ok: bool | None = None
    if current and current.summary:
        ok = bool(current.summary.get("interference", {}).get("ok"))
    return JigSummaryOut(
        id=jig.id,
        name=jig.name,
        description=jig.description,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        part_id=jig.part_id,
        part_name=part.name if part else None,
        current_version=jig.current_version,
        interference_ok=ok,
        updated_at=jig.updated_at,
    )


def list_jigs(
    db: Session, *, part_id: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[Jig], int]:
    base = select(Jig).where(Jig.deleted_at.is_(None))
    if part_id is not None:
        base = base.where(Jig.part_id == part_id)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(db.scalars(base.order_by(Jig.updated_at.desc()).limit(limit).offset(offset)))
    return rows, total


def list_versions(db: Session, jig: Jig) -> list[JigVersion]:
    return list(
        db.scalars(
            select(JigVersion)
            .where(JigVersion.jig_id == jig.id)
            .order_by(JigVersion.number.desc())
        )
    )


def update_jig(db: Session, jig: Jig, *, fields: dict[str, Any]) -> Jig:
    for key, value in fields.items():
        if value is not None:
            setattr(jig, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(jig)
    return jig


def delete_jig(db: Session, jig: Jig) -> None:
    jig.deleted_at = datetime.now(UTC)
    db.commit()
