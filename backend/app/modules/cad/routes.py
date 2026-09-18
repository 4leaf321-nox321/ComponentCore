"""CAD 라우터 — 레시피의 스키마 · 검증 · 미리보기 · 일회용 STEP. 상태가 없다.

미리보기는 요청 안에서 동기로 만든다 — 편집기가 칸을 고칠 때마다 부르는 길이라 큐를 거치면
느리다. 저장(버전)은 `modules/works` 의 일이다.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import export
from app.core.recipe import describe
from app.core.recipe import templates as recipe_templates
from app.core.recipe.mesh import mesh
from app.database import get_db
from app.modules.accounts.models import User
from app.modules.cad import services
from app.modules.cad.schemas import (
    RecipeInfoOut,
    RecipeProblemsOut,
    RecipeRequest,
    RecipeSchemaOut,
    TemplateCreateRequest,
    TemplateOut,
    TemplateUpdateRequest,
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


# --- 템플릿 — 사람이 저장한 출발점 ---------------------------------------------


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[TemplateOut]:
    """내 템플릿 + 공용 템플릿. 내장 넷은 `recipe/schema` 의 templates 에 있다."""
    return [services.template_out(db, one, user) for one in services.list_templates(db, user)]


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(
    payload: TemplateCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TemplateOut:
    made = services.create_template(
        db,
        owner=user,
        name=payload.name,
        description=payload.description,
        recipe=payload.recipe,
        is_shared=payload.is_shared,
    )
    return services.template_out(db, made, user)


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: uuid.UUID,
    payload: TemplateUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TemplateOut:
    template = services.get_template(db, template_id, user)
    services.require_template_owner(template, user)
    fields = payload.model_dump(exclude_unset=True)
    return services.template_out(
        db, services.update_template(db, template, fields=fields), user
    )


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    template = services.get_template(db, template_id, user)
    services.require_template_owner(template, user)
    services.delete_template(db, template)
