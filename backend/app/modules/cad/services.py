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

from app.core import export
from app.core.recipe import Evaluation, RecipeError, evaluate, parse
from app.core.recipe.digest import digest
from app.core.recipe.schema import RecipeValidationError
from app.modules.jobs import registry
from app.modules.jobs.models import Artifact
from app.shared import filestore
from app.shared.errors import AppError, code

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


def build(raw: dict[str, Any], *, allow_sketch: bool = False) -> Evaluation:
    """만들어 본다. 실패는 AppError — 메시지가 그대로 화면 · AI 에 간다. `allow_sketch` 는
    미리보기(info · preview · mesh)만 — 그리는 도중의 2D 도 보여 줘야 한다."""
    try:
        recipe = parse(raw)
    except RecipeValidationError as failure:
        raise AppError(
            code("CAD", 2),
            "레시피가 올바르지 않습니다",
            details={"problems": failure.problems},
        ) from failure
    try:
        return evaluate(recipe, resolve_file=resolve_import, allow_sketch=allow_sketch)
    except RecipeError as failure:
        raise AppError(
            code("CAD", 3),
            f"만들지 못했습니다 — {failure.message}",
            details={"node_id": failure.node_id},
        ) from failure


# --- Job kind="cad" -------------------------------------------------------------


def sweep(
    raw: dict[str, Any], *, param: str, values: list[float], material: str | None = None
) -> list[dict[str, Any]]:
    """치수 하나를 값마다 바꿔 가며 만들어 보고 **치수표를 나란히** 돌려준다.

    「연결부는 그대로 두고 두께만 바꿔 가며 알맞은 것을 찾는다」 가 이 한 번의 부름으로 된다.
    실패한 값은 그 이유와 함께 남는다 — 끊기지 않게(가느다란 값에서 형상이 깨지는 일은 흔하다).
    """
    params = raw.get("params") or {}
    if param not in params:
        known = ", ".join(sorted(params)) or "(없음)"
        raise AppError(
            code("CAD", 10),
            f"레시피에 '{param}' 치수가 없습니다",
            details={"known": known},
        )
    if len(values) > 40:
        raise AppError(code("CAD", 11), "한 번에 40개까지 봅니다")
    out: list[dict[str, Any]] = []
    for value in values:
        variant = {**raw, "params": {**params, param: value}}
        try:
            evaluation = build(variant)
        except AppError as failure:
            out.append({param: value, "ok": False, "error": failure.message})
            continue
        out.append(
            {param: value, "ok": True, "geometry": digest(evaluation.shape, material=material)}
        )
    return out


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
