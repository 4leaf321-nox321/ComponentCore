"""형상 색인 채우기 — 이 기능 전에 만든 버전에도 색인을 적는다.

색인은 버전을 평가하는 작업이 끝날 때 적힌다(`core/shape_index.py`). 그 전에 만든 버전은
요약에 색인이 없어 형상으로 찾으면 빠진다. 여기서 **최신 버전**(내 작업 · 부품 · 지그)의
작업 중 색인이 없거나 옛 모양인 것을 골라, 그 작업이 남긴 STEP 을 열어 색인을 적는다 —
레시피를 다시 만들지 않는다(가져온 구성품이 그새 바뀌었어도 그때의 형상 그대로).

한 번에 몇 개씩 — 요청 하나가 오래 붙잡지 않게. 화면은 남은 것이 0 이 될 때까지 다시 부른다.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Integer, and_, cast, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core import shape_index
from app.modules.jigs.models import Jig, JigVersion
from app.modules.jobs.models import Artifact, Job
from app.modules.parts.models import Part, PartVersion
from app.modules.works.models import Work, WorkVersion
from app.shared import filestore

#: 형상이 든 STEP — CAD 평가는 모델, 지그 생성은 지그 부품(제품 제외).
_STEP_KINDS = ("model_step", "jig_step")


def _missing() -> Any:
    """색인이 없거나(이 기능 전) · 못 뽑았거나(null) · 옛 모양인 것."""
    version = Job.summary[("shape", "version")].astext
    return or_(
        ~Job.summary.has_key("shape"),
        version.is_(None),
        cast(version, Integer) < shape_index.VERSION,
    )


def _targets(db: Session) -> list[uuid.UUID]:
    """색인이 없는 최신 버전들의 작업 id — 겹침 없이(부품은 작업과 같은 작업을 가리킨다)."""
    picks = [
        select(Job.id)
        .join(WorkVersion, WorkVersion.job_id == Job.id)
        .join(
            Work,
            and_(Work.id == WorkVersion.work_id, Work.current_version == WorkVersion.number),
        )
        .where(Work.deleted_at.is_(None)),
        select(Job.id)
        .join(PartVersion, PartVersion.job_id == Job.id)
        .join(
            Part,
            and_(Part.id == PartVersion.part_id, Part.current_version == PartVersion.number),
        )
        .where(Part.deleted_at.is_(None)),
        select(Job.id)
        .join(JigVersion, JigVersion.job_id == Job.id)
        .join(Jig, and_(Jig.id == JigVersion.jig_id, Jig.current_version == JigVersion.number))
        .where(Jig.deleted_at.is_(None)),
    ]
    seen: dict[uuid.UUID, None] = {}
    for query in picks:
        for job_id in db.scalars(query.where(Job.status == "done", _missing())):
            seen[job_id] = None
    return list(seen)


def missing(db: Session) -> int:
    return len(_targets(db))


def _recipe(job: Job) -> dict[str, Any] | None:
    """그 형상을 그린 레시피 — CAD 평가는 입력에, 지그 생성은 요약에 있다."""
    recipe = (job.input or {}).get("recipe") or (job.summary or {}).get("recipe")
    return recipe if isinstance(recipe, dict) else None


def fill(db: Session, *, limit: int = 20) -> dict[str, Any]:
    """색인을 `limit` 개까지 채운다. 못 연 것(STEP 이 없거나 깨짐)은 건너뛰고 센다."""
    from build123d import import_step

    filled = failed = 0
    problems: list[str] = []
    for job_id in _targets(db)[:limit]:
        job = db.get(Job, job_id)
        if job is None:
            continue
        artifact = db.scalar(
            select(Artifact)
            .where(Artifact.job_id == job.id, Artifact.kind.in_(_STEP_KINDS))
            .order_by(Artifact.kind)
        )
        made = None
        if artifact is not None:
            try:
                shape = import_step(filestore.resolve(artifact.path))
                made = shape_index.index(shape, _recipe(job))
            except Exception as failure:
                problems.append(f"{job.id}: {type(failure).__name__}: {failure}")
        else:
            problems.append(f"{job.id}: STEP 이 없습니다")
        if made is None:
            failed += 1
            # 다시 골라지지 않게 — 빈 색인(version 만)을 적어 둔다. 찾기에서는 빠진다.
            made = {"version": shape_index.VERSION, "unreadable": True}
        else:
            filled += 1
        job.summary = {**(job.summary or {}), "shape": made}
        flag_modified(job, "summary")
        db.commit()
    return {
        "filled": filled,
        "failed": failed,
        "remaining": missing(db),
        "problems": problems[:10],
    }
