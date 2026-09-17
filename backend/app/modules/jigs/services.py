"""지그 프로젝트 · 실행 로직.

**파이프라인은 요청 스레드에서 동기로 돈다.** 손바닥만 한 부품은 1초 안쪽이라 지금은 이것으로
충분하다. 큰 조립체를 받기 시작하면 워커(큐)로 옮긴다 — 그때도 이 파일의 `execute_run` 이
워커가 부르는 함수가 되고 API 는 안 바뀐다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import pipeline, primitives
from app.core.geometry import GeometryError
from app.core.options import JigOptions
from app.core.planning import PlanningError
from app.modules.accounts.models import User
from app.modules.jigs.models import JigProject, JigRun
from app.modules.jigs.schemas import ProjectOut, RunOut
from app.shared import filestore
from app.shared.errors import AppError, Forbidden, NotFound, code

logger = logging.getLogger(__name__)

#: 실행 결과 파일 키 → 내려받기 이름 · MIME.
FILE_KINDS: dict[str, tuple[str, str]] = {
    "jig_step": ("jig.step", "application/step"),
    "assembly_step": ("jig-assembly.step", "application/step"),
    "jig_glb": ("jig.glb", "model/gltf-binary"),
    "product_glb": ("product.glb", "model/gltf-binary"),
    "jig_stl": ("jig.stl", "model/stl"),
}


def _now() -> datetime:
    return datetime.now(UTC)


# --- 프로젝트 -----------------------------------------------------------------


def _run_stats(db: Session, project_id: uuid.UUID) -> tuple[int, str | None]:
    count = int(db.scalar(select(func.count()).where(JigRun.project_id == project_id)) or 0)
    last = db.scalar(
        select(JigRun.status)
        .where(JigRun.project_id == project_id)
        .order_by(JigRun.started_at.desc())
        .limit(1)
    )
    return count, last


def project_out(db: Session, project: JigProject) -> ProjectOut:
    owner = db.get(User, project.owner_id)
    count, last = _run_stats(db, project.id)
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        owner_id=project.owner_id,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        product_filename=project.product_filename,
        product_size_bytes=project.product_size_bytes,
        product_spec=project.product_spec,
        has_product_file=project.product_path is not None,
        run_count=count,
        last_run_status=last,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def get_project(db: Session, project_id: uuid.UUID) -> JigProject:
    project = db.get(JigProject, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFound(code("JIGS", 1), "프로젝트를 찾을 수 없습니다.")
    return project


def require_owner(project: JigProject, user: User) -> None:
    """소유자나 시스템 관리자만 고친다. 보는 것은 누구나 — 지그는 팀이 함께 보는 자료다."""
    if project.owner_id != user.id and not user.is_system_admin:
        raise Forbidden(code("JIGS", 2), "이 프로젝트를 고칠 권한이 없습니다.")


def list_projects(db: Session, *, limit: int, offset: int) -> tuple[list[JigProject], int]:
    base = select(JigProject).where(JigProject.deleted_at.is_(None))
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(
        db.scalars(base.order_by(JigProject.updated_at.desc()).limit(limit).offset(offset))
    )
    return rows, total


def validate_spec(spec: dict[str, Any] | None) -> None:
    """스펙이 실제로 그려지는지 **만들어 본다.** 저장만 하고 실행에서 터지면 그때는 사람이
    없다."""
    if spec is None:
        return
    try:
        primitives.build(spec)
    except primitives.PrimitiveError as failure:
        raise AppError(
            code("JIGS", 3), f"제품 도형이 올바르지 않습니다: {failure}"
        ) from failure


def create_project(
    db: Session,
    *,
    owner: User,
    name: str,
    description: str,
    product_spec: dict[str, Any] | None,
) -> JigProject:
    validate_spec(product_spec)
    project = JigProject(
        name=name.strip(),
        description=description.strip(),
        owner_id=owner.id,
        product_spec=product_spec,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project(db: Session, project: JigProject, *, fields: dict[str, Any]) -> JigProject:
    if "product_spec" in fields:
        validate_spec(fields["product_spec"])
    for key, value in fields.items():
        setattr(project, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(project)
    return project


def attach_product(
    db: Session, project: JigProject, *, filename: str, stream: BinaryIO
) -> JigProject:
    """제품 STEP 을 올린다. 있던 파일은 바꾼다 — 실행 결과는 그때 파일로 만든 것이므로
    남긴다."""
    safe = filestore.safe_filename(filename)
    if not safe.lower().endswith((".step", ".stp")):
        raise AppError(code("JIGS", 4), "STEP 파일(.step · .stp)만 올릴 수 있습니다.")
    limit = get_settings().max_upload_mb * 1024 * 1024
    target_dir = filestore.new_dir("products", str(project.id))
    target = target_dir / safe
    try:
        size = filestore.save_stream(stream, target, limit_bytes=limit)
    except ValueError as failure:
        raise AppError(
            code("JIGS", 5),
            f"파일이 너무 큽니다 (최대 {get_settings().max_upload_mb} MB).",
            status=413,
        ) from failure

    # 읽히는 파일인지 **지금** 본다. 실행 때 터지면 올린 사람은 이미 자리를 떴다.
    try:
        pipeline.resolve_product(target)
    except GeometryError as failure:
        target.unlink(missing_ok=True)
        raise AppError(code("JIGS", 6), str(failure)) from failure

    if project.product_path:
        filestore.remove_dir(str(Path(project.product_path).parent))
    project.product_filename = safe
    project.product_path = filestore.relative_to_root(target)
    project.product_size_bytes = size
    db.commit()
    db.refresh(project)
    return project


def detach_product(db: Session, project: JigProject) -> JigProject:
    if project.product_path:
        filestore.remove_dir(str(Path(project.product_path).parent))
    project.product_filename = None
    project.product_path = None
    project.product_size_bytes = None
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: JigProject) -> None:
    """행은 남긴다(deleted_at). 파일도 남긴다 — 되돌릴 수 있어야 한다."""
    project.deleted_at = _now()
    db.commit()


# --- 실행 ---------------------------------------------------------------------


def run_out(run: JigRun) -> RunOut:
    files = list((run.summary or {}).get("files", {}).keys()) if run.status == "done" else []
    return RunOut(
        id=run.id,
        project_id=run.project_id,
        status=run.status,
        options=run.options,
        summary=run.summary,
        error=run.error,
        files=files,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def list_runs(db: Session, project_id: uuid.UUID) -> list[JigRun]:
    return list(
        db.scalars(
            select(JigRun)
            .where(JigRun.project_id == project_id)
            .order_by(JigRun.started_at.desc())
        )
    )


def get_run(db: Session, project: JigProject, run_id: uuid.UUID) -> JigRun:
    run = db.get(JigRun, run_id)
    if run is None or run.project_id != project.id:
        raise NotFound(code("JIGS", 7), "실행 기록을 찾을 수 없습니다.")
    return run


def _product_source(project: JigProject) -> Path | dict[str, Any] | None:
    if project.product_path:
        return filestore.resolve(project.product_path)
    return project.product_spec


def execute_run(
    db: Session, project: JigProject, *, requested_by: User, options: dict[str, Any]
) -> JigRun:
    """파이프라인을 돌리고 기록한다. **실패도 기록이다** — 왜 못 만들었는지가 화면에 떠야
    한다."""
    opts = JigOptions.from_dict(options)
    run = JigRun(
        project_id=project.id,
        requested_by_id=requested_by.id,
        status="running",
        options=opts.to_dict(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    out_dir = filestore.new_dir("runs", str(project.id))
    run.output_dir = filestore.relative_to_root(out_dir)
    try:
        result = pipeline.run(_product_source(project), opts, out_dir)
    except (GeometryError, PlanningError, primitives.PrimitiveError) as failure:
        # 제품 쪽 사정 — 사람이 읽고 고칠 수 있는 말이다.
        run.status = "failed"
        run.error = str(failure)
        logger.warning("지그 생성 실패 (project=%s): %s", project.id, failure)
    except Exception as failure:
        # 코어의 버그 — 트레이스백을 남기고 화면에는 한 줄만.
        run.status = "failed"
        run.error = f"생성 중 오류: {type(failure).__name__}: {failure}"
        logger.exception("지그 생성 중 예외 (project=%s)", project.id)
    else:
        run.status = "done"
        run.summary = result.summary()
    run.finished_at = _now()
    db.commit()
    db.refresh(run)
    return run


def result_file(run: JigRun, key: str) -> tuple[Path, str, str]:
    """(경로, 내려받기 이름, MIME)."""
    if run.status != "done" or not run.summary or not run.output_dir:
        raise NotFound(
            code("JIGS", 8), "결과 파일이 없습니다 — 실행이 끝나지 않았거나 실패했습니다."
        )
    names: dict[str, str] = run.summary.get("files", {})
    if key not in names or key not in FILE_KINDS:
        raise NotFound(code("JIGS", 9), f"그런 결과 파일이 없습니다: {key}")
    path = filestore.resolve(f"{run.output_dir}/{names[key]}")
    if not path.exists():
        raise NotFound(code("JIGS", 10), "결과 파일이 저장소에서 사라졌습니다.")
    download_name, mime = FILE_KINDS[key]
    return path, download_name, mime
