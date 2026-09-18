"""레시피 평가 — 상태 없는 층.

레시피는 두 길로 만들어진다:
- **미리보기**(`build`) — 편집기가 칸을 고칠 때마다. 요청 안에서 동기로. 작으면 수십 ms.
- **버전 평가**(`Job(kind="cad")`) — 저장한 버전의 STEP · glTF 를 작업물로 남긴다. 워커가 돈다.

두 길이 같은 `core.recipe.evaluate` 를 지난다. 버전 · 작업(work) 은 `modules/works` 가 든다.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import export
from app.core.recipe import Evaluation, RecipeError, evaluate, parse
from app.core.recipe.schema import RecipeValidationError
from app.modules.accounts.models import User
from app.modules.cad.models import RecipeTemplate
from app.modules.cad.schemas import TemplateOut
from app.modules.jobs import registry
from app.modules.jobs.models import Artifact
from app.shared import filestore
from app.shared.errors import AppError, Forbidden, NotFound, code

logger = logging.getLogger(__name__)

JOB_KIND = "cad"


# --- 레시피 -------------------------------------------------------------------


def resolve_import(key: str) -> Path:
    """`import_step` 노드의 `file` — 작업물 id 다. 워커 · 미리보기 · 지그 작업이 같은 규칙을
    쓴다."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        artifact = db.get(Artifact, uuid.UUID(key))
        if artifact is None:
            raise ValueError(f"작업물이 없습니다: {key}")
        return filestore.resolve(artifact.path)
    finally:
        db.close()


def check(raw: dict[str, Any]) -> list[str]:
    """만들지 않고 모양만 본다. 비어 있으면 통과."""
    try:
        parse(raw)
    except RecipeValidationError as failure:
        return failure.problems
    return []


def build(raw: dict[str, Any]) -> Evaluation:
    """만들어 본다. 실패는 AppError — 메시지가 그대로 화면 · AI 에 간다."""
    try:
        recipe = parse(raw)
    except RecipeValidationError as failure:
        raise AppError(
            code("CAD", 2),
            "레시피가 올바르지 않습니다",
            details={"problems": failure.problems},
        ) from failure
    try:
        return evaluate(recipe, resolve_file=resolve_import)
    except RecipeError as failure:
        raise AppError(
            code("CAD", 3),
            f"만들지 못했습니다 — {failure.message}",
            details={"node_id": failure.node_id},
        ) from failure


# --- Job kind="cad" -------------------------------------------------------------


def run_job(
    input: dict[str, Any],
    options: dict[str, Any],
    out_dir: Path,
    progress: registry.Progress,
) -> registry.Outcome:
    """버전의 레시피를 만들어 STEP · glTF 를 남긴다."""
    del options
    import time

    started = time.perf_counter()
    try:
        recipe = parse(dict(input["recipe"]))
    except RecipeValidationError as failure:
        raise registry.UserFacingError(" / ".join(failure.problems)) from failure
    try:
        evaluation = evaluate(recipe, resolve_file=resolve_import)
    except RecipeError as failure:
        raise registry.UserFacingError(f"{failure.node_id}: {failure.message}") from failure
    progress(
        "evaluate",
        int((time.perf_counter() - started) * 1000),
        f"노드 {len(evaluation.nodes)}",
    )

    started = time.perf_counter()
    step = export.write_step(evaluation.shape, out_dir / "model.step")
    glb = export.write_gltf(evaluation.shape, out_dir / "model.glb")
    progress("export", int((time.perf_counter() - started) * 1000), "STEP · glTF")

    return registry.Outcome(
        summary=evaluation.summary(),
        artifacts=[
            registry.ArtifactSpec(
                kind="model_step", path=step, content_type="application/step"
            ),
            registry.ArtifactSpec(
                kind="model_glb", path=glb, content_type="model/gltf-binary"
            ),
        ],
    )


# --- 템플릿 -------------------------------------------------------------------


def template_out(db: Session, template: RecipeTemplate, viewer: User) -> TemplateOut:
    owner = db.get(User, template.owner_id)
    return TemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        owner_id=template.owner_id,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        recipe=template.recipe,
        is_shared=template.is_shared,
        mine=template.owner_id == viewer.id,
        updated_at=template.updated_at,
    )


def list_templates(db: Session, viewer: User) -> list[RecipeTemplate]:
    """내 것 전부 + 남이 공용으로 둔 것. 내 것이 먼저."""
    rows = db.scalars(
        select(RecipeTemplate)
        .where(or_(RecipeTemplate.owner_id == viewer.id, RecipeTemplate.is_shared.is_(True)))
        .order_by(RecipeTemplate.updated_at.desc())
    ).all()
    return sorted(rows, key=lambda t: (t.owner_id != viewer.id, t.name))


def get_template(db: Session, template_id: uuid.UUID, viewer: User) -> RecipeTemplate:
    template = db.get(RecipeTemplate, template_id)
    if template is None or (template.owner_id != viewer.id and not template.is_shared):
        raise NotFound(code("CAD", 8), "템플릿을 찾을 수 없습니다.")
    return template


def require_template_owner(template: RecipeTemplate, user: User) -> None:
    if template.owner_id != user.id and not user.is_system_admin:
        raise Forbidden(code("CAD", 9), "이 템플릿을 고칠 권한이 없습니다.")


def create_template(
    db: Session,
    *,
    owner: User,
    name: str,
    description: str,
    recipe: dict[str, Any],
    is_shared: bool,
) -> RecipeTemplate:
    problems = check(recipe)
    if problems:
        raise AppError(
            code("CAD", 2), "레시피가 올바르지 않습니다", details={"problems": problems}
        )
    template = RecipeTemplate(
        name=name.strip(),
        description=description.strip(),
        owner_id=owner.id,
        recipe=recipe,
        is_shared=is_shared,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_template(
    db: Session, template: RecipeTemplate, *, fields: dict[str, Any]
) -> RecipeTemplate:
    if fields.get("recipe") is not None:
        problems = check(fields["recipe"])
        if problems:
            raise AppError(
                code("CAD", 2), "레시피가 올바르지 않습니다", details={"problems": problems}
            )
    for key, value in fields.items():
        if value is None:
            continue
        setattr(template, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(template)
    return template


def delete_template(db: Session, template: RecipeTemplate) -> None:
    db.delete(template)
    db.commit()
