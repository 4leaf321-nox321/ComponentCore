"""내 작업 — 형상 버전 · STEP 가져오기 · 지그 생성 · 승격.

지그 생성(`Job(kind="jig")`)의 실행 함수도 여기 있다. 지그를 만드는 일은 「내 작업」 안에서
일어나고, 카탈로그(`modules/jigs`)는 그 결과를 승격한 기록만 든다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from build123d import Shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import pipeline
from app.core.geometry import GeometryError
from app.core.options import JigOptions
from app.core.planning import PlanningError
from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.schema import RecipeValidationError
from app.modules.accounts.models import User
from app.modules.cad import services as cad
from app.modules.jigs.models import Jig, JigVersion
from app.modules.jobs import registry
from app.modules.jobs import services as jobs
from app.modules.jobs.models import Artifact, Job
from app.modules.parts.models import Part, PartVersion
from app.modules.works.models import VERSION_SOURCES, WORK_KINDS, Work, WorkVersion
from app.modules.works.schemas import PromoteJigOut, VersionOut, WorkOut, WorkSummaryOut
from app.shared import filestore
from app.shared.errors import AppError, Forbidden, NotFound, code

logger = logging.getLogger(__name__)

JIG_JOB_KIND = "jig"


def _now() -> datetime:
    return datetime.now(UTC)


# --- 권한 ---------------------------------------------------------------------


def get_work(db: Session, work_id: uuid.UUID) -> Work:
    work = db.get(Work, work_id)
    if work is None or work.deleted_at is not None:
        raise NotFound(code("WORKS", 1), "작업을 찾을 수 없습니다.")
    return work


def require_owner(work: Work, user: User) -> None:
    """**내 공간이다.** 소유자와 시스템 관리자만 보고 고친다. 남에게 보이려면 승격한다."""
    if work.owner_id != user.id and not user.is_system_admin:
        raise Forbidden(code("WORKS", 2), "남의 작업입니다.")


# --- 조회 ---------------------------------------------------------------------


def _promoted_part_version(db: Session, version_id: uuid.UUID) -> PartVersion | None:
    return db.scalar(
        select(PartVersion)
        .where(PartVersion.work_version_id == version_id)
        .order_by(PartVersion.created_at.desc())
        .limit(1)
    )


def version_out(db: Session, version: WorkVersion) -> VersionOut:
    author = db.get(User, version.created_by_id) if version.created_by_id else None
    job = db.get(Job, version.job_id) if version.job_id else None
    promoted = _promoted_part_version(db, version.id)
    return VersionOut(
        id=version.id,
        work_id=version.work_id,
        number=version.number,
        recipe=version.recipe,
        source=version.source,
        note=version.note,
        created_by_id=version.created_by_id,
        created_by_name=author.display_name if author else None,
        job=jobs.job_out(db, job) if job else None,
        promoted_part_id=promoted.part_id if promoted else None,
        promoted_part_version=promoted.number if promoted else None,
        created_at=version.created_at,
    )


def get_version(db: Session, work: Work, number: int) -> WorkVersion:
    version = db.scalar(
        select(WorkVersion).where(WorkVersion.work_id == work.id, WorkVersion.number == number)
    )
    if version is None:
        raise NotFound(code("WORKS", 3), f"버전 {number} 이 없습니다.")
    return version


def current_version(db: Session, work: Work) -> WorkVersion | None:
    return get_version(db, work, work.current_version) if work.current_version > 0 else None


def _jig_stats(db: Session, work_id: uuid.UUID) -> tuple[int, str | None]:
    count = int(
        db.scalar(select(func.count()).where(Job.work_id == work_id, Job.kind == JIG_JOB_KIND))
        or 0
    )
    last = db.scalar(
        select(Job.status)
        .where(Job.work_id == work_id, Job.kind == JIG_JOB_KIND)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return count, last


def _promoted_ids(
    db: Session, work_id: uuid.UUID
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    part = db.scalar(
        select(Part.id).where(Part.work_id == work_id, Part.deleted_at.is_(None)).limit(1)
    )
    jig = db.scalar(
        select(Jig.id).where(Jig.work_id == work_id, Jig.deleted_at.is_(None)).limit(1)
    )
    return part, jig


def work_out(db: Session, work: Work) -> WorkOut:
    owner = db.get(User, work.owner_id)
    count = int(db.scalar(select(func.count()).where(WorkVersion.work_id == work.id)) or 0)
    current = current_version(db, work)
    runs, last = _jig_stats(db, work.id)
    part_id, jig_id = _promoted_ids(db, work.id)
    return WorkOut(
        id=work.id,
        name=work.name,
        description=work.description,
        owner_id=work.owner_id,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        kind=work.kind,
        jig_for_part_id=work.jig_for_part_id,
        jig_for_part_name=_part_name(db, work.jig_for_part_id),
        current_version=work.current_version,
        version_count=count,
        current=version_out(db, current) if current else None,
        jig_options=work.jig_options,
        jig_run_count=runs,
        last_jig_status=last,
        promoted_part_id=part_id,
        promoted_jig_id=jig_id,
        created_at=work.created_at,
        updated_at=work.updated_at,
    )


def _part_name(db: Session, part_id: uuid.UUID | None) -> str | None:
    if part_id is None:
        return None
    part = db.get(Part, part_id)
    return part.name if part else None


def work_summary(db: Session, work: Work) -> WorkSummaryOut:
    owner = db.get(User, work.owner_id)
    current = current_version(db, work)
    job = db.get(Job, current.job_id) if current and current.job_id else None
    runs, last = _jig_stats(db, work.id)
    part_id, jig_id = _promoted_ids(db, work.id)
    return WorkSummaryOut(
        id=work.id,
        name=work.name,
        description=work.description,
        owner_id=work.owner_id,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        kind=work.kind,
        current_version=work.current_version,
        current_status=job.status if job else None,
        jig_run_count=runs,
        last_jig_status=last,
        promoted_part_id=part_id,
        promoted_jig_id=jig_id,
        updated_at=work.updated_at,
    )


def list_works(db: Session, *, owner: User, limit: int, offset: int) -> tuple[list[Work], int]:
    base = select(Work).where(Work.deleted_at.is_(None), Work.owner_id == owner.id)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(db.scalars(base.order_by(Work.updated_at.desc()).limit(limit).offset(offset)))
    return rows, total


def list_versions(db: Session, work: Work) -> list[WorkVersion]:
    return list(
        db.scalars(
            select(WorkVersion)
            .where(WorkVersion.work_id == work.id)
            .order_by(WorkVersion.number.desc())
        )
    )


def list_jig_runs(db: Session, work: Work) -> list[Job]:
    return list(
        db.scalars(
            select(Job)
            .where(Job.work_id == work.id, Job.kind == JIG_JOB_KIND)
            .order_by(Job.created_at.desc())
        )
    )


# --- 버전 ---------------------------------------------------------------------


def _validated(raw: dict[str, Any]) -> dict[str, Any]:
    problems = cad.check(raw)
    if problems:
        raise AppError(
            code("CAD", 2), "레시피가 올바르지 않습니다", details={"problems": problems}
        )
    return raw


def add_version(
    db: Session, work: Work, *, recipe: dict[str, Any], source: str, note: str, by: User
) -> WorkVersion:
    if source not in VERSION_SOURCES:
        raise AppError(code("WORKS", 4), f"모르는 출처입니다: {source}")
    version = WorkVersion(
        work_id=work.id,
        number=work.current_version + 1,
        recipe=_validated(recipe),
        source=source,
        note=note.strip(),
        created_by_id=by.id,
    )
    db.add(version)
    work.current_version = version.number
    db.flush()
    job = jobs.enqueue(
        db,
        kind=cad.JOB_KIND,
        requested_by=by,
        work_id=work.id,
        input={"work_version_id": str(version.id), "recipe": recipe},
        options={},
    )
    version.job_id = job.id
    db.commit()
    db.refresh(version)
    return version


def create_work(
    db: Session,
    *,
    owner: User,
    name: str,
    description: str,
    recipe: dict[str, Any],
    source: str,
    note: str,
    kind: str = "part",
    jig_for_part_id: uuid.UUID | None = None,
) -> Work:
    _validated(recipe)
    if kind not in WORK_KINDS:
        raise AppError(code("WORKS", 23), f"모르는 종류입니다: {kind} (part · jig)")
    work = Work(
        name=name.strip(),
        description=description.strip(),
        owner_id=owner.id,
        kind=kind,
        jig_for_part_id=jig_for_part_id,
    )
    db.add(work)
    db.flush()
    add_version(db, work, recipe=recipe, source=source, note=note or "첫 버전", by=owner)
    db.refresh(work)
    return work


def update_work(db: Session, work: Work, *, fields: dict[str, Any]) -> Work:
    if "jig_options" in fields and fields["jig_options"] is not None:
        fields["jig_options"] = JigOptions.from_dict(fields["jig_options"]).to_dict()
    if fields.get("kind") is not None and fields["kind"] not in WORK_KINDS:
        raise AppError(code("WORKS", 23), f"모르는 종류입니다: {fields['kind']} (part · jig)")
    for key, value in fields.items():
        if value is None:
            continue
        setattr(work, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(work)
    return work


def restore_version(db: Session, work: Work, number: int, *, by: User) -> WorkVersion:
    old = get_version(db, work, number)
    return add_version(
        db, work, recipe=old.recipe, source="restore", note=f"v{number} 으로 되돌림", by=by
    )


def delete_work(db: Session, work: Work) -> None:
    """행은 남긴다. 승격된 부품 · 지그는 자기 복사본을 들고 있으므로 영향이 없다."""
    work.deleted_at = _now()
    db.commit()


# --- STEP 가져오기 ---------------------------------------------------------------


def create_work_from_step(
    db: Session, *, owner: User, name: str, filename: str, stream: BinaryIO
) -> Work:
    """STEP 에서 시작하는 작업 — 첫 버전이 `import_step` 이다. 실패하면 작업도 안 남긴다."""
    work = Work(name=name.strip()[:120], description="", owner_id=owner.id)
    db.add(work)
    db.flush()
    try:
        import_step(db, work, filename=filename, stream=stream, by=owner)
    except AppError:
        db.rollback()
        raise
    db.refresh(work)
    return work


def import_step(
    db: Session, work: Work, *, filename: str, stream: BinaryIO, by: User
) -> WorkVersion:
    """STEP 을 올리면 작업물이 되고, `import_step` 노드 하나짜리 **새 버전**이 된다.

    그래서 제품은 늘 「이 작업의 형상」 이고, 올린 STEP 위에 구멍 하나 더 같은 편집도 레시피로
    쌓인다."""
    safe = filestore.safe_filename(filename)
    if not safe.lower().endswith((".step", ".stp")):
        raise AppError(code("WORKS", 5), "STEP 파일(.step · .stp)만 올릴 수 있습니다.")
    limit = get_settings().max_upload_mb * 1024 * 1024
    target = filestore.new_dir("imports", str(work.id)) / safe
    try:
        size = filestore.save_stream(stream, target, limit_bytes=limit)
    except ValueError as failure:
        raise AppError(
            code("WORKS", 6),
            f"파일이 너무 큽니다 (최대 {get_settings().max_upload_mb} MB).",
            status=413,
        ) from failure
    try:
        pipeline.resolve_product(target)  # 읽히는지 **지금** 본다
    except GeometryError as failure:
        target.unlink(missing_ok=True)
        raise AppError(code("WORKS", 7), str(failure)) from failure

    artifact = Artifact(
        job_id=None,
        work_id=work.id,
        owner_id=by.id,
        kind="import_step",
        filename=safe,
        path=filestore.relative_to_root(target),
        content_type="application/step",
        size_bytes=size,
    )
    db.add(artifact)
    db.flush()
    recipe = {
        "version": 1,
        "nodes": [
            {"id": "imported", "op": "import_step", "label": safe, "file": str(artifact.id)}
        ],
    }
    return add_version(db, work, recipe=recipe, source="import", note=f"{safe} 가져옴", by=by)


# --- 지그 생성 ----------------------------------------------------------------


def request_jig(db: Session, work: Work, *, by: User, options: dict[str, Any]) -> Job:
    version = current_version(db, work)
    if version is None:
        raise AppError(code("WORKS", 8), "형상이 없습니다 — 먼저 그리거나 STEP 을 올리세요.")
    opts = JigOptions.from_dict(options)
    work.jig_options = opts.to_dict()  # 다음에 열면 그대로
    db.commit()
    return jobs.enqueue(
        db,
        kind=JIG_JOB_KIND,
        requested_by=by,
        work_id=work.id,
        input={
            "work_version_id": str(version.id),
            "work_version": version.number,
            "product_recipe": version.recipe,
        },
        options=opts.to_dict(),
    )


def _product_from_input(input: dict[str, Any]) -> Shape | Path | None:
    if input.get("product_recipe"):
        try:
            recipe = parse(dict(input["product_recipe"]))
            return evaluate(recipe, resolve_file=cad.resolve_import).shape
        except RecipeValidationError as failure:
            raise registry.UserFacingError(
                "제품 레시피가 올바르지 않습니다: " + " / ".join(failure.problems)
            ) from failure
        except RecipeError as failure:
            raise registry.UserFacingError(
                f"제품 레시피를 만들지 못했습니다 — {failure.node_id}: {failure.message}"
            ) from failure
    if input.get("product_path"):  # 옛 작업(마이그레이션 전) 호환
        return filestore.resolve(str(input["product_path"]))
    return None


_ARTIFACT_KINDS: dict[str, tuple[str, str]] = {
    "jig_step": ("jig_step", "application/step"),
    "assembly_step": ("assembly_step", "application/step"),
    "jig_glb": ("jig_glb", "model/gltf-binary"),
    "product_glb": ("product_glb", "model/gltf-binary"),
    "jig_stl": ("jig_stl", "model/stl"),
}


def run_jig_job(
    input: dict[str, Any], options: dict[str, Any], out_dir: Path, progress: registry.Progress
) -> registry.Outcome:
    """Job kind="jig" 의 실행 함수. **웹 · DB 를 모른다** — 입력과 폴더만 받는다."""
    opts = JigOptions.from_dict(options)
    try:
        result = pipeline.run(_product_from_input(input), opts, out_dir, on_stage=progress)
    except (GeometryError, PlanningError) as failure:
        raise registry.UserFacingError(str(failure)) from failure
    artifacts = [
        registry.ArtifactSpec(
            kind=_ARTIFACT_KINDS[key][0], path=path, content_type=_ARTIFACT_KINDS[key][1]
        )
        for key, path in result.files.items()
        if key in _ARTIFACT_KINDS
    ]
    return registry.Outcome(summary=result.summary(), artifacts=artifacts)


# --- 승격 ---------------------------------------------------------------------


def _done_job(db: Session, job_id: uuid.UUID | None, what: str) -> Job:
    job = db.get(Job, job_id) if job_id else None
    if job is None or job.status != "done":
        raise AppError(code("WORKS", 9), f"{what}이 아직 끝나지 않았거나 실패했습니다.")
    return job


def promote_part(
    db: Session, work: Work, *, by: User, name: str | None, note: str
) -> PartVersion:
    """현재 형상 버전을 부품으로. 이 작업에서 이미 승격한 부품이 있으면 거기에 다음 버전."""
    version = current_version(db, work)
    if version is None:
        raise AppError(code("WORKS", 8), "형상이 없습니다.")
    already = _promoted_part_version(db, version.id)
    if already is not None:
        raise AppError(
            code("WORKS", 10),
            f"이 버전(v{version.number})은 이미 부품 v{already.number} 으로 올라가 있습니다.",
        )
    _done_job(db, version.job_id, "형상 평가")

    part = db.scalar(select(Part).where(Part.work_id == work.id, Part.deleted_at.is_(None)))
    if part is None:
        part = Part(
            name=(name or work.name).strip(),
            description=work.description,
            owner_id=by.id,
            work_id=work.id,
        )
        db.add(part)
        db.flush()
    elif part.owner_id != by.id and not by.is_system_admin:
        raise Forbidden(code("WORKS", 11), "이 부품에 버전을 올릴 권한이 없습니다.")

    promoted = PartVersion(
        part_id=part.id,
        number=part.current_version + 1,
        work_version_id=version.id,
        recipe=version.recipe,
        job_id=version.job_id,
        note=note.strip() or f"작업 v{version.number} 에서",
        promoted_by_id=by.id,
    )
    db.add(promoted)
    part.current_version = promoted.number
    db.commit()
    db.refresh(promoted)
    return promoted


def promote_jig_recipe(
    db: Session,
    work: Work,
    *,
    by: User,
    number: int | None,
    name: str | None,
    note: str,
    part_id: uuid.UUID | None,
) -> PromoteJigOut:
    """**손으로 그린 지그**(레시피 버전)를 지그 카탈로그로.

    자동 생성기(`run_jig`)가 만들 수 없는 지그가 있다 — 공진을 맞추는 시험 지그처럼 「연결부는
    제품에 맞추고 나머지는 우리가 정하는」 것들이다. 그런 지그는 레시피로 그리고, 그리는 것이니
    **변수를 심을 수 있다**(그래야 DOE 로 훑는다). 그 레시피 버전을 그대로 지그로 올린다.

    생성 작업이 없으므로 `options` 는 비고, 형상 · STEP 은 그 버전의 **평가 작업**에서 온다.
    어느 부품의 지그인지는 골라서 잇는다(안 고르면 홀로 선 지그다)."""
    version = current_version(db, work) if number is None else get_version(db, work, number)
    if version is None:
        raise AppError(code("WORKS", 20), "올릴 버전이 없습니다.")
    job = db.get(Job, version.job_id) if version.job_id else None
    if job is None or job.status != "done":
        raise AppError(
            code("WORKS", 21),
            "이 버전의 평가가 끝나지 않았습니다 — 형상이 만들어져야 지그로 올립니다.",
        )
    part_version: PartVersion | None = None
    part_id = part_id or work.jig_for_part_id  # 작업에 이어 둔 부품이 기본
    if part_id is not None:
        part = db.get(Part, part_id)
        if part is None or part.deleted_at is not None:
            raise NotFound(code("WORKS", 22), "고른 부품을 찾을 수 없습니다.")
        part_version = db.scalar(
            select(PartVersion).where(
                PartVersion.part_id == part.id, PartVersion.number == part.current_version
            )
        )

    jig = _jig_for(db, work, by=by, name=name, part_version=part_version)
    promoted = JigVersion(
        jig_id=jig.id,
        number=jig.current_version + 1,
        job_id=job.id,
        part_version_id=part_version.id if part_version else None,
        options={},
        summary=job.summary,
        note=note.strip() or f"v{version.number} 레시피에서",
        promoted_by_id=by.id,
    )
    db.add(promoted)
    jig.current_version = promoted.number
    db.commit()
    return PromoteJigOut(
        jig_id=jig.id,
        jig_version=promoted.number,
        part_id=part_version.part_id if part_version else None,
        part_version=part_version.number if part_version else None,
        part_promoted_now=False,
    )


def _jig_for(
    db: Session, work: Work, *, by: User, name: str | None, part_version: PartVersion | None
) -> Jig:
    """이 작업의 지그를 찾거나 만든다 — 두 승격 길이 같은 지그에 버전을 쌓게."""
    jig = db.scalar(select(Jig).where(Jig.work_id == work.id, Jig.deleted_at.is_(None)))
    if jig is None:
        jig = Jig(
            name=(name or f"{work.name} 지그").strip(),
            description=work.description,
            owner_id=by.id,
            work_id=work.id,
            part_id=part_version.part_id if part_version else None,
        )
        db.add(jig)
        db.flush()
    elif jig.owner_id != by.id and not by.is_system_admin:
        raise Forbidden(code("WORKS", 15), "이 지그에 버전을 올릴 권한이 없습니다.")
    if part_version is not None:
        jig.part_id = part_version.part_id
    return jig


def promote_jig(
    db: Session,
    work: Work,
    *,
    by: User,
    job_id: uuid.UUID,
    name: str | None,
    note: str,
    promote_product: bool,
) -> PromoteJigOut:
    """지그 생성 작업 하나를 지그로. **어느 부품 버전의 지그인가**를 고정한다 — 제품(그때의
    형상 버전)이 부품에 없으면 함께 올린다. 지그만 있고 제품이 없는 카탈로그는 반쪽이다."""
    job = _done_job(db, job_id, "지그 생성")
    if job.work_id != work.id or job.kind != JIG_JOB_KIND:
        raise NotFound(code("WORKS", 12), "이 작업의 지그 생성이 아닙니다.")
    if db.scalar(select(JigVersion.id).where(JigVersion.job_id == job.id)) is not None:
        raise AppError(code("WORKS", 13), "이 지그 생성은 이미 올라가 있습니다.")

    # 제품 = 그때의 형상 버전. 부품 카탈로그에 있으면 그것을, 없으면 지금 올린다.
    part_version: PartVersion | None = None
    part_promoted_now = False
    raw_version_id = job.input.get("work_version_id")
    if raw_version_id:
        product_version = db.get(WorkVersion, uuid.UUID(str(raw_version_id)))
        if product_version is not None:
            part_version = _promoted_part_version(db, product_version.id)
            if part_version is None and promote_product:
                if product_version.number != work.current_version:
                    # 승격은 현재 버전으로만 — 옛 버전을 올리려면 되돌린 뒤.
                    raise AppError(
                        code("WORKS", 14),
                        f"이 지그의 제품은 작업 v{product_version.number} 인데 현재는 "
                        f"v{work.current_version} 입니다. 먼저 v{product_version.number} 으로 "
                        f"되돌리거나 현재 형상으로 지그를 다시 만드세요.",
                    )
                part_version = promote_part(db, work, by=by, name=None, note="지그와 함께")
                part_promoted_now = True

    jig = _jig_for(db, work, by=by, name=name, part_version=part_version)

    promoted = JigVersion(
        jig_id=jig.id,
        number=jig.current_version + 1,
        job_id=job.id,
        part_version_id=part_version.id if part_version else None,
        options=job.options,
        summary=job.summary,
        note=note.strip(),
        promoted_by_id=by.id,
    )
    db.add(promoted)
    jig.current_version = promoted.number
    db.commit()
    return PromoteJigOut(
        jig_id=jig.id,
        jig_version=promoted.number,
        part_id=part_version.part_id if part_version else None,
        part_version=part_version.number if part_version else None,
        part_promoted_now=part_promoted_now,
    )
