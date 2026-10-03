"""닮은 형상 찾기 — 「이 부품과 비슷한 것이 이미 있나」 · 「비슷한 부품의 지그를 다시 쓸 수
있나」.

견주는 것은 **최신 버전의 형상 색인**이다(`core/shape_index.py` — 버전을 평가할 때 작업 요약에
적힌다). 형상을 다시 만들지 않는다. 후보는 내 작업(내 것만) · 부품 · 지그 카탈로그(누구나
보는 것)이고, 같은 버전(같은 평가 작업)을 가리키는 것은 뺀다 — 작업에서 올린 부품은 그 작업과
꼭 같다.

점수는 크기 · 비율 · 꽉 찬 정도 · 구멍 · 쓴 연산 · 덩어리 수의 무게 합이다(`similarity`).
가장 긴 변이 네 배 넘게 다른 것은 처음부터 견주지 않는다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Float, and_, cast, select
from sqlalchemy.orm import Session

from app.core import shape_index
from app.modules.accounts.models import User
from app.modules.jigs.models import Jig, JigVersion
from app.modules.jobs.models import Job
from app.modules.parts.models import Part, PartVersion
from app.modules.works.models import Work, WorkVersion
from app.shared.errors import AppError, code

_BAD_SOURCE = code("SEARCH", 2)
_NO_INDEX = code("SEARCH", 3)
#: 가장 긴 변이 이 배보다 더 다르면 견주지 않는다 — 닮았다고 하기엔 이미 너무 다르다.
_SPAN = 4.0


@dataclass
class _Candidate:
    source: str
    kind: str
    name: str
    folder: str
    version: int
    job_id: uuid.UUID
    shape: dict[str, Any]
    part_id: uuid.UUID | None = None


def _usable(shape: Any) -> bool:
    return isinstance(shape, dict) and isinstance(shape.get("dims"), list)


def _reference(
    db: Session, viewer: User, source: str | None, recipe: dict[str, Any] | None
) -> tuple[dict[str, Any], uuid.UUID | None]:
    """견줄 형상 색인과 그 평가 작업(같은 것을 빼려고)."""
    if recipe is not None:
        from app.modules.cad.services import build

        evaluation = build(recipe)
        return shape_index.index(evaluation.shape, recipe), None
    assert source is not None
    kind, _, raw_id = source.partition(":")
    try:
        item_id = uuid.UUID(raw_id)
    except ValueError as failure:
        raise AppError(
            _BAD_SOURCE, "source 는 work:<id> · part:<id> · jig:<id> 입니다"
        ) from failure
    job_id: uuid.UUID | None
    if kind == "work":
        from app.modules.works import services as works

        work = works.get_work(db, item_id)
        works.require_owner(work, viewer)
        version = works.current_version(db, work)
        job_id = version.job_id if version else None
    elif kind == "part":
        from app.modules.parts import services as parts

        part_version = parts.current_version(db, parts.get_part(db, item_id))
        job_id = part_version.job_id if part_version else None
    elif kind == "jig":
        from app.modules.jigs import services as jigs

        jig_version = jigs.current_version(db, jigs.get_jig(db, item_id))
        job_id = jig_version.job_id if jig_version else None
    else:
        raise AppError(_BAD_SOURCE, "source 는 work:<id> · part:<id> · jig:<id> 입니다")
    job = db.get(Job, job_id) if job_id else None
    shape = (job.summary or {}).get("shape") if job else None
    if not _usable(shape):
        raise AppError(
            _NO_INDEX,
            "이 버전에는 형상 색인이 없습니다 — 평가가 끝나지 않았거나 이 기능 전에 만든 "
            "버전입니다(관리자가 서버 화면에서 「형상 색인 채우기」).",
        )
    assert isinstance(shape, dict)
    return shape, job_id


def _span(shape: dict[str, Any]) -> Any:
    """가장 긴 변이 기준의 1/4 ~ 4 배인 것만 — SQL 에서 먼저 거른다."""
    longest = float(shape["dims"][2])
    side = cast(Job.summary[("shape", "dims", "2")].astext, Float)
    return side.between(longest / _SPAN, longest * _SPAN)


def _works(db: Session, viewer: User, reference: dict[str, Any]) -> list[_Candidate]:
    rows = db.execute(
        select(Work, Job.id, Job.summary["shape"])
        .join(
            WorkVersion,
            and_(WorkVersion.work_id == Work.id, WorkVersion.number == Work.current_version),
        )
        .join(Job, Job.id == WorkVersion.job_id)
        .where(Work.owner_id == viewer.id, Work.deleted_at.is_(None), _span(reference))
    ).all()
    return [
        _Candidate(
            f"work:{one.id}", one.kind, one.name, one.folder, one.current_version, job, shape
        )
        for one, job, shape in rows
        if _usable(shape)
    ]


def _parts(db: Session, reference: dict[str, Any]) -> list[_Candidate]:
    rows = db.execute(
        select(Part, Job.id, Job.summary["shape"])
        .join(
            PartVersion,
            and_(PartVersion.part_id == Part.id, PartVersion.number == Part.current_version),
        )
        .join(Job, Job.id == PartVersion.job_id)
        .where(Part.deleted_at.is_(None), _span(reference))
    ).all()
    return [
        _Candidate(
            f"part:{one.id}",
            "part",
            one.name,
            one.folder,
            one.current_version,
            job,
            shape,
            one.id,
        )
        for one, job, shape in rows
        if _usable(shape)
    ]


def _jigs(db: Session, reference: dict[str, Any]) -> list[_Candidate]:
    rows = db.execute(
        select(Jig, Job.id, Job.summary["shape"])
        .join(
            JigVersion,
            and_(JigVersion.jig_id == Jig.id, JigVersion.number == Jig.current_version),
        )
        .join(Job, Job.id == JigVersion.job_id)
        .where(Jig.deleted_at.is_(None), _span(reference))
    ).all()
    return [
        _Candidate(
            f"jig:{one.id}",
            "jig",
            one.name,
            one.folder,
            one.current_version,
            job,
            shape,
            one.part_id,
        )
        for one, job, shape in rows
        if _usable(shape)
    ]


def _brief(shape: dict[str, Any]) -> dict[str, Any]:
    return {key: shape.get(key) for key in ("size", "dims", "volume", "holes", "hole_count")}


def similar(
    db: Session,
    viewer: User,
    *,
    source: str | None,
    recipe: dict[str, Any] | None,
    where: list[str],
    limit: int,
) -> dict[str, Any]:
    """닮은 것 — 점수가 높은 것부터, 성분별 닮음과 「왜」 를 함께."""
    reference, own_job = _reference(db, viewer, source, recipe)
    candidates: list[_Candidate] = []
    if "works" in where:
        candidates += _works(db, viewer, reference)
    if "parts" in where:
        candidates += _parts(db, reference)
    if "jigs" in where:
        candidates += _jigs(db, reference)
    scored: list[tuple[float, _Candidate, dict[str, float]]] = []
    for one in candidates:
        if one.source == source or (own_job is not None and one.job_id == own_job):
            continue  # 자기 자신 · 같은 버전(작업에서 올린 부품)
        score, parts = shape_index.similarity(reference, one.shape)
        scored.append((score, one, parts))
    scored.sort(key=lambda row: (-row[0], row[1].name))
    top = scored[:limit]

    # **비슷한 부품의 지그** — 지그를 새로 만들기 전에 다시 쓸 길. 한 번에 모아 온다.
    part_ids = [one.part_id for _, one, _ in top if one.kind == "part" and one.part_id]
    jigs_of: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if part_ids:
        for jig in db.scalars(
            select(Jig).where(Jig.part_id.in_(part_ids), Jig.deleted_at.is_(None))
        ):
            assert jig.part_id is not None
            jigs_of.setdefault(jig.part_id, []).append(
                {"source": f"jig:{jig.id}", "name": jig.name}
            )
    names = {
        part.id: part.name
        for part in db.scalars(
            select(Part).where(
                Part.id.in_(
                    [one.part_id for _, one, _ in top if one.kind == "jig" and one.part_id]
                )
            )
        )
    }
    items = []
    for score, one, parts in top:
        row: dict[str, Any] = {
            "source": one.source,
            "kind": one.kind,
            "name": one.name,
            "folder": one.folder,
            "version": one.version,
            "score": score,
            "parts": parts,
            "why": shape_index.reasons(parts, reference, one.shape),
            "shape": _brief(one.shape),
        }
        if one.kind == "part" and one.part_id:
            row["jigs"] = jigs_of.get(one.part_id, [])
        if one.kind == "jig" and one.part_id:
            row["part_name"] = names.get(one.part_id)
        items.append(row)
    return {
        "reference": {"source": source, **_brief(reference)},
        "compared": len(scored),
        "items": items,
    }
