"""템플릿 공간 — 「그리기」 의 출발점을 모아 둔 곳.

부품 · 지그 카탈로그와 다른 점: 템플릿은 **버전이 없고** 소유자가 언제든 고친다. 대신 자리가
둘이다 — **내 것**과 **공용**. 공용으로 내놓아도 고치는 것은 소유자뿐이고 남은 복사해서 쓴다.
승격이 아니라 스위치인 이유는 시작점이라서다(고친 결과는 작업으로 간다).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.recipe.schema import RecipeValidationError, parse
from app.modules.accounts.models import User
from app.modules.templates.models import RecipeTemplate
from app.modules.templates.schemas import TemplateOut, TemplateSummaryOut
from app.shared.errors import AppError, Forbidden, NotFound, code

#: 목록에서 고를 수 있는 자리.
SCOPES = ("mine", "shared", "all")


def _node_count(recipe: dict[str, Any]) -> int:
    nodes = recipe.get("nodes")
    return len(nodes) if isinstance(nodes, list) else 0


def _owner_name(db: Session, owner_id: uuid.UUID) -> str:
    owner = db.get(User, owner_id)
    return owner.display_name if owner else "(삭제된 계정)"


def template_summary(
    db: Session, template: RecipeTemplate, viewer: User
) -> TemplateSummaryOut:
    return TemplateSummaryOut(
        id=template.id,
        name=template.name,
        description=template.description,
        owner_id=template.owner_id,
        owner_name=_owner_name(db, template.owner_id),
        is_shared=template.is_shared,
        mine=template.owner_id == viewer.id,
        node_count=_node_count(template.recipe),
        updated_at=template.updated_at,
    )


def template_out(db: Session, template: RecipeTemplate, viewer: User) -> TemplateOut:
    return TemplateOut(
        **template_summary(db, template, viewer).model_dump(), recipe=template.recipe
    )


def list_templates(
    db: Session, viewer: User, *, scope: str = "all", query: str = "", limit: int, offset: int
) -> tuple[list[RecipeTemplate], int]:
    """`scope` 는 mine(내 것) · shared(공용) · all(둘 다). 내 것이 먼저 온다."""
    if scope not in SCOPES:
        raise AppError(code("TPL", 3), f"모르는 자리입니다: {scope}")
    visible = or_(RecipeTemplate.owner_id == viewer.id, RecipeTemplate.is_shared.is_(True))
    if scope == "mine":
        visible = RecipeTemplate.owner_id == viewer.id
    elif scope == "shared":
        visible = RecipeTemplate.is_shared.is_(True)
    statement = select(RecipeTemplate).where(visible)
    if query.strip():
        like = f"%{query.strip()}%"
        statement = statement.where(
            or_(RecipeTemplate.name.ilike(like), RecipeTemplate.description.ilike(like))
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(
        statement.order_by(
            (RecipeTemplate.owner_id != viewer.id),  # 내 것이 먼저
            RecipeTemplate.updated_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get_template(db: Session, template_id: uuid.UUID, viewer: User) -> RecipeTemplate:
    template = db.get(RecipeTemplate, template_id)
    if template is None or (template.owner_id != viewer.id and not template.is_shared):
        raise NotFound(code("TPL", 1), "템플릿을 찾을 수 없습니다.")
    return template


def require_owner(template: RecipeTemplate, user: User) -> None:
    if template.owner_id != user.id and not user.is_system_admin:
        raise Forbidden(code("TPL", 2), "이 템플릿을 고칠 권한이 없습니다.")


def _checked(recipe: dict[str, Any]) -> dict[str, Any]:
    """모양만 본다 — 만들어 보지는 않는다. 템플릿은 그리다 만 상태여도 시작점이 된다."""
    try:
        parse(recipe)
    except RecipeValidationError as failure:
        raise AppError(
            code("TPL", 4),
            "레시피가 올바르지 않습니다",
            details={"problems": failure.problems},
        ) from failure
    return recipe


def create_template(
    db: Session,
    *,
    owner: User,
    name: str,
    description: str,
    recipe: dict[str, Any],
    is_shared: bool,
) -> RecipeTemplate:
    template = RecipeTemplate(
        name=name.strip(),
        description=description.strip(),
        owner_id=owner.id,
        recipe=_checked(recipe),
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
        _checked(fields["recipe"])
    for key, value in fields.items():
        if value is None:
            continue
        setattr(template, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(template)
    return template


def copy_to_mine(db: Session, template: RecipeTemplate, *, owner: User) -> RecipeTemplate:
    """공용 템플릿을 내 것으로. 남의 것을 고칠 수는 없으니 복사해서 쓴다 —
    부품 · 지그의 「내 공간으로 복사」 와 같은 손놀림이다."""
    return create_template(
        db,
        owner=owner,
        name=template.name if template.owner_id == owner.id else f"{template.name} (복사)",
        description=template.description,
        recipe=template.recipe,
        is_shared=False,
    )


def delete_template(db: Session, template: RecipeTemplate) -> None:
    db.delete(template)
    db.commit()
