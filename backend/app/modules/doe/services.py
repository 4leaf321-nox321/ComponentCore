"""DOE — 설계점을 만들고, 형상마다 STEP 을 공유 폴더에 쓴다.

**실패한 점에서 멈추지 않는다.** 얇은 두께에서 형상이 깨지는 것은 흔한 일이고, 거기서 멈추면
48 개짜리 표가 12 개에서 끊긴다. 실패는 그 점의 줄에 이유를 적고 다음으로 간다.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import doe as engine
from app.core import export as shapes
from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.digest import digest
from app.core.recipe.schema import RecipeValidationError
from app.modules.accounts.models import User
from app.modules.cad.services import resolve_component, resolve_import
from app.modules.doe import export as files
from app.modules.doe.models import DoePoint, DoeStudy
from app.modules.jobs import registry
from app.modules.jobs import services as jobs
from app.shared.errors import AppError, Forbidden, NotFound, code

JOB_KIND = "doe"


def _settings_root() -> Path:
    return Path(get_settings().doe_export_root)


def check_root() -> Path:
    """공유 폴더가 쓸 수 있는가. **미리 본다** — 48 점을 다 만들고 나서 못 쓰면 늦다."""
    root = _settings_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".autojig-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as failure:
        raise AppError(
            code("DOE", 1),
            f"공유 폴더에 쓸 수 없습니다: {files.windows_path(root)} ({failure.strerror})",
        ) from failure
    return root


def preview(raw: dict[str, Any]) -> dict[str, Any]:
    """만들기 전에 **몇 개인지** 와 앞 몇 줄. 격자는 곱으로 늘어난다."""
    factors = _factors(raw.get("factors") or [])
    method = raw.get("method", "factorial")
    samples = int(raw.get("samples") or 20)
    seed = int(raw.get("seed") or 1)
    total = engine.count(factors, method, samples)
    rows: list[dict[str, float]] = []
    if total <= engine.MAX_POINTS:
        rows = engine.build_points(factors, method=method, samples=samples, seed=seed)
    return {
        "count": total,
        "max": engine.MAX_POINTS,
        "too_many": total > engine.MAX_POINTS,
        "points": rows[:20],
        "varying": [f.name for f in factors if f.varying],
    }


def _factors(raw: list[dict[str, Any]]) -> list[engine.Factor]:
    try:
        return engine.parse_factors(raw)
    except engine.DoeError as failure:
        raise AppError(code("DOE", 2), str(failure)) from failure


def _points(raw: dict[str, Any]) -> list[dict[str, float]]:
    try:
        return engine.build_points(
            _factors(raw.get("factors") or []),
            method=raw.get("method", "factorial"),
            samples=int(raw.get("samples") or 20),
            seed=int(raw.get("seed") or 1),
        )
    except engine.DoeError as failure:
        raise AppError(code("DOE", 3), str(failure)) from failure


def create_study(
    db: Session,
    *,
    owner: User,
    name: str,
    description: str,
    recipe: dict[str, Any],
    factors: list[dict[str, Any]],
    method: str,
    samples: int,
    seed: int,
    material: str,
    work_id: uuid.UUID | None,
) -> DoeStudy:
    """스터디를 만들고 작업을 건다. 레시피는 **스냅샷**으로 박는다."""
    root = check_root()
    try:
        parse(recipe)
    except RecipeValidationError as failure:
        raise AppError(
            code("DOE", 4),
            "레시피가 올바르지 않습니다",
            details={"problems": failure.problems},
        ) from failure
    params = recipe.get("params") or {}
    unknown = [one["name"] for one in factors if one.get("name") not in params]
    if unknown:
        known = ", ".join(sorted(params)) or "(없음)"
        raise AppError(
            code("DOE", 5),
            f"레시피에 없는 치수입니다: {', '.join(unknown)} — 있는 치수: {known}",
        )
    rows = _points({"factors": factors, "method": method, "samples": samples, "seed": seed})
    study = DoeStudy(
        name=name.strip(),
        description=description.strip(),
        owner_id=owner.id,
        work_id=work_id,
        recipe=recipe,
        factors=factors,
        method=method,
        samples=samples,
        seed=seed,
        material=material,
        point_count=len(rows),
    )
    db.add(study)
    db.flush()
    study.export_dir = str(files.study_dir(root, study.name, str(study.id)))
    for number, row in enumerate(rows, start=1):
        db.add(DoePoint(study_id=study.id, number=number, params=row, status="pending"))
    db.flush()
    job = jobs.enqueue(
        db,
        kind=JOB_KIND,
        requested_by=owner,
        work_id=work_id,
        input={"study_id": str(study.id)},
        options={},
    )
    study.job_id = job.id
    db.commit()
    db.refresh(study)
    return study


def get_study(db: Session, study_id: uuid.UUID, viewer: User) -> DoeStudy:
    study = db.get(DoeStudy, study_id)
    if study is None:
        raise NotFound(code("DOE", 6), "실험계획을 찾을 수 없습니다.")
    if study.owner_id != viewer.id and not viewer.is_system_admin:
        raise Forbidden(code("DOE", 7), "남의 실험계획입니다.")
    return study


def list_studies(
    db: Session, viewer: User, *, work_id: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[DoeStudy], int]:
    statement = select(DoeStudy).where(DoeStudy.owner_id == viewer.id)
    if work_id is not None:
        statement = statement.where(DoeStudy.work_id == work_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(
        statement.order_by(DoeStudy.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def points(db: Session, study: DoeStudy) -> list[DoePoint]:
    return list(
        db.scalars(
            select(DoePoint).where(DoePoint.study_id == study.id).order_by(DoePoint.number)
        ).all()
    )


def delete_study(db: Session, study: DoeStudy) -> None:
    """DB 에서만 지운다 — **공유 폴더의 파일은 남긴다.** 해석이 이미 그 폴더를 보고 있을 수
    있고, 남의 도구가 읽는 파일을 말없이 지우면 안 된다."""
    db.delete(study)
    db.commit()


def metrics_of(geometry: dict[str, Any]) -> dict[str, Any]:
    """치수표에서 **표에 바로 쓰는 값**만 추린다 — 필터 · CSV 가 이 이름을 쓴다."""
    size = geometry["bbox"]["size"]
    mass = geometry.get("mass") or {}
    inertia = mass.get("inertia_g_mm2_about_com") or [[None] * 3] * 3
    center = mass.get("center_of_mass") or [None, None, None]
    return {
        "volume_mm3": geometry.get("volume"),
        "mass_g": mass.get("mass_g"),
        "size_x": size[0],
        "size_y": size[1],
        "size_z": size[2],
        "com_x": center[0],
        "com_y": center[1],
        "com_z": center[2],
        "ixx": inertia[0][0],
        "iyy": inertia[1][1],
        "izz": inertia[2][2],
        "hole_count": geometry.get("holes_total"),
        "face_count": geometry["faces"]["total"],
    }


def run_job(
    input: dict[str, Any], options: dict[str, Any], out_dir: Path, progress: registry.Progress
) -> registry.Outcome:
    """Job kind="doe" — 점마다 형상을 만들어 공유 폴더에 STEP 을 쓴다.

    작업 함수는 웹을 모르지만 **DB 는 본다** — 설계점이 수십 개라 결과를 그때그때 적어야
    화면이 진행을 보여 줄 수 있다(다 끝나고 한꺼번에 적으면 5 분 동안 빈 표를 본다)."""
    del options, out_dir
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        study = db.get(DoeStudy, uuid.UUID(str(input["study_id"])))
        if study is None:
            raise registry.UserFacingError("실험계획이 사라졌습니다")
        folder = Path(study.export_dir)
        (folder / "points").mkdir(parents=True, exist_ok=True)
        factor_names = [one["name"] for one in study.factors]
        columns = files.manifest_columns(factor_names)
        rows: list[dict[str, Any]] = []
        made = 0
        failed = 0
        for point in points(db, study):
            started = time.perf_counter()
            recipe = {
                **study.recipe,
                "params": {**(study.recipe.get("params") or {}), **point.params},
            }
            try:
                evaluation = evaluate(
                    parse(recipe),
                    resolve_file=resolve_import,
                    resolve_component=resolve_component,
                )
                got = digest(evaluation.shape, material=study.material)
                name = f"p{point.number:04d}.step"
                shapes.write_step(evaluation.shape, folder / "points" / name)
                point.status = "ok"
                point.geometry = got
                point.metrics = metrics_of(got)
                point.step_file = f"points/{name}"
                made += 1
                rows.append(
                    files.manifest_row(
                        point.number,
                        point.params,
                        factor_names,
                        status="ok",
                        step_file=point.step_file,
                        metrics=point.metrics,
                    )
                )
            except (RecipeError, RecipeValidationError, ValueError, RuntimeError) as failure:
                point.status = "failed"
                point.error = str(failure)[:500]
                failed += 1
                rows.append(
                    files.manifest_row(
                        point.number,
                        point.params,
                        factor_names,
                        status="failed",
                        error=point.error,
                    )
                )
            db.commit()
            progress(
                f"point-{point.number}",
                int((time.perf_counter() - started) * 1000),
                f"{made + failed}/{study.point_count}",
            )
        files.write_manifest(folder, columns, rows)
        files.write_study(
            folder,
            {
                "id": str(study.id),
                "name": study.name,
                "description": study.description,
                "method": study.method,
                "samples": study.samples,
                "seed": study.seed,
                "material": study.material,
                "factors": study.factors,
                "recipe": study.recipe,
            },
        )
        files.write_readme(
            folder,
            {
                "name": study.name,
                "description": study.description,
                "method": study.method,
                "seed": study.seed,
                "material": study.material,
                "factors": study.factors,
            },
            study.point_count,
        )
        return registry.Outcome(
            summary={
                "points": study.point_count,
                "ok": made,
                "failed": failed,
                "folder": files.windows_path(folder),
            }
        )
    finally:
        db.close()
