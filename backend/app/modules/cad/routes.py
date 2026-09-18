"""CAD 라우터 — 레시피의 스키마 · 검증 · 미리보기 · 내려받기. **상태가 없다.**

미리보기는 요청 안에서 동기로 만든다 — 편집기가 칸을 고칠 때마다 부르는 길이라 큐를 거치면
느리다. 저장은 남의 일이다: 버전은 `modules/works`, 시작점은 `modules/templates`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.core import export
from app.core.recipe import describe
from app.core.recipe import templates as recipe_templates
from app.core.recipe.mesh import mesh
from app.modules.accounts.models import User
from app.modules.cad import services
from app.modules.cad.schemas import (
    RecipeInfoOut,
    RecipeProblemsOut,
    RecipeRequest,
    RecipeSchemaOut,
)
from app.shared.auth import current_user

router = APIRouter(prefix="/cad", tags=["cad"])


# --- 레시피 -------------------------------------------------------------------


@router.get("/recipe/schema", response_model=RecipeSchemaOut, response_model_by_alias=True)
def recipe_schema(_: User = Depends(current_user)) -> RecipeSchemaOut:
    """노드 종류 · 칸 · 템플릿. **화면이 목록을 손으로 들지 않는다** — 연산을 더하면 편집기가
    따라온다."""
    return RecipeSchemaOut(
        schema=describe(),
        templates=recipe_templates.all_templates(),
        template_labels=recipe_templates.TEMPLATE_LABELS,
    )


@router.post("/recipe/check", response_model=RecipeProblemsOut)
def recipe_check(payload: RecipeRequest, _: User = Depends(current_user)) -> RecipeProblemsOut:
    """모양만 본다(만들지 않는다). 편집기가 칸을 고칠 때마다 부른다."""
    problems = services.check(payload.recipe)
    return RecipeProblemsOut(ok=not problems, problems=problems)


@router.post("/recipe/info", response_model=RecipeInfoOut)
def recipe_info(payload: RecipeRequest, _: User = Depends(current_user)) -> RecipeInfoOut:
    """만들어 본 요약(크기 · 부피 · 노드별 정보). 실패하면 어느 노드가 왜인지."""
    return RecipeInfoOut(summary=services.build(payload.recipe, allow_sketch=True).summary())


@router.post("/recipe/preview")
def recipe_preview(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """미리보기 glTF. 스케치까지만 그렸으면 면으로 보인다."""
    evaluation = services.build(payload.recipe, allow_sketch=True)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "preview.glb"
        export.write_gltf(evaluation.shape, target)
        return Response(target.read_bytes(), media_type="model/gltf-binary")


@router.post("/recipe/mesh")
def recipe_mesh(payload: RecipeRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """면 · 엣지 단위 메시 + 요약 — 편집기의 미리보기이자 「3D 에서 고르기」 의 근거.
    스케치까지만 그렸으면 면으로 보인다."""
    evaluation = services.build(payload.recipe, allow_sketch=True)
    return {"summary": evaluation.summary(), "mesh": mesh(evaluation.shape)}


@router.post("/recipe/step")
def recipe_step(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """저장하지 않고 STEP 만 받는다 — 한 번 쓰고 말 도형."""
    evaluation = services.build(payload.recipe)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "model.step"
        export.write_step(evaluation.shape, target)
        return Response(
            target.read_bytes(),
            media_type="application/step",
            headers={"Content-Disposition": 'attachment; filename="model.step"'},
        )


@router.post("/recipe/stl")
def recipe_stl(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """STL — 3D 프린터로 지그를 뽑을 때."""
    evaluation = services.build(payload.recipe)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "model.stl"
        export.write_stl(evaluation.shape, target)
        return Response(
            target.read_bytes(),
            media_type="model/stl",
            headers={"Content-Disposition": 'attachment; filename="model.stl"'},
        )


@router.post("/recipe/dxf")
def recipe_dxf(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """DXF — 2D 도면. 스케치 · 단면이면 그대로, 입체면 **높이 절반의 단면**을 낸다."""
    evaluation = services.build(payload.recipe, allow_sketch=True)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "model.dxf"
        export.write_dxf(evaluation.shape, target)
        return Response(
            target.read_bytes(),
            media_type="application/dxf",
            headers={"Content-Disposition": 'attachment; filename="model.dxf"'},
        )


@router.post("/recipe/svg")
def recipe_svg(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """SVG — 문서에 붙이는 2D 그림. 잘라 내는 규칙은 DXF 와 같다."""
    evaluation = services.build(payload.recipe, allow_sketch=True)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "model.svg"
        export.write_svg(evaluation.shape, target)
        return Response(
            target.read_bytes(),
            media_type="image/svg+xml",
            headers={"Content-Disposition": 'attachment; filename="model.svg"'},
        )
