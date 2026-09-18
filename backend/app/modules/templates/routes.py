"""템플릿 라우터 — 내 것과 공용이 한 자리에 있다. 고치는 것은 소유자, 쓰는 것은 모두."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.templates import services
from app.modules.templates.schemas import (
    TemplateCreateRequest,
    TemplateOut,
    TemplateSummaryOut,
    TemplateUpdateRequest,
)
from app.shared.auth import current_user
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=Page[TemplateSummaryOut])
def list_templates(
    scope: str = Query(default="all", description="mine · shared · all"),
    q: str = Query(default="", max_length=120),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[TemplateSummaryOut]:
    """내 템플릿 · 공용 템플릿. 내장 넷은 `cad/recipe/schema` 의 templates 에 있다."""
    size = clamp_limit(limit)
    rows, total = services.list_templates(
        db, user, scope=scope, query=q, limit=size, offset=offset
    )
    return Page(
        items=[services.template_summary(db, one, user) for one in rows],
        total=total,
        limit=size,
        offset=offset,
    )


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> TemplateOut:
    """레시피 본문까지 — 「그리기에서 열기」 가 이것을 받는다."""
    return services.template_out(db, services.get_template(db, template_id, user), user)


@router.post("", response_model=TemplateOut, status_code=201)
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


@router.patch("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: uuid.UUID,
    payload: TemplateUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TemplateOut:
    """이름 · 설명 · 레시피 · **공용 여부**. 공용으로 내놓는 것도 거두는 것도 소유자 몫이다."""
    template = services.get_template(db, template_id, user)
    services.require_owner(template, user)
    fields = payload.model_dump(exclude_unset=True)
    return services.template_out(
        db, services.update_template(db, template, fields=fields), user
    )


@router.post("/{template_id}/copy", response_model=TemplateOut, status_code=201)
def copy_template(
    template_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> TemplateOut:
    """공용 템플릿을 내 것으로 복사한다 — 남의 것은 고칠 수 없으니."""
    template = services.get_template(db, template_id, user)
    return services.template_out(db, services.copy_to_mine(db, template, owner=user), user)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    template = services.get_template(db, template_id, user)
    services.require_owner(template, user)
    services.delete_template(db, template)
