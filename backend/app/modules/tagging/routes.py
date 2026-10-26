"""태그 API — 타입 고르기 · 그 안에서 고르기 · 붙이기 · 떼기 · 관리(ADR 0011).

붙이고 떼는 사람은 **그 행을 고칠 수 있는 사람**이다 — 작업은 주인(내 공간), 부품 · 지그는 올린
사람과 시스템 관리자. 읽기는 그 행을 볼 수 있는 사람(작업은 주인, 부품 · 지그는 누구나).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.jigs import services as jigs
from app.modules.parts import services as parts
from app.modules.tagging import services
from app.modules.tagging.services import (
    AddTagRequest,
    MergeTagsOut,
    MergeTagsRequest,
    SimilarTagsOut,
    TagCandidate,
    TagItem,
    TagModeRequest,
    TagSettingOut,
    TagTypeOut,
    TagUse,
)
from app.modules.templates import services as templates
from app.modules.works import services as works
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, Forbidden, code

router = APIRouter(prefix="/tags", tags=["tags"])

TargetKey = Literal["work", "part", "jig", "template"]


def _row(db: Session, user: User, target: TargetKey, row_id: uuid.UUID, *, write: bool) -> Any:
    if target == "work":
        work = works.get_work(db, row_id)
        works.require_owner(work, user)
        return work
    if target == "part":
        part = parts.get_part(db, row_id)
        if write:
            parts.require_owner(part, user)
        return part
    if target == "template":
        # 내 템플릿은 주인만 본다(공용이면 누구나) — 붙이고 떼는 것은 주인 · 관리자.
        template = templates.get_template(db, row_id, user)
        if write:
            templates.require_owner(template, user)
        return template
    jig = jigs.get_jig(db, row_id)
    if write:
        jigs.require_owner(jig, user)
    return jig


@router.get("/types", response_model=list[TagTypeOut])
def tag_types(
    _: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[TagTypeOut]:
    """태그로 고를 수 있는 타입 — 「일반 태그」 가 맨 앞. `can_create` 면 이름을 쳐서 새로
    만든다."""
    out = services.tag_types(db)
    db.commit()  # 처음 부르면 기본 정의가 선다
    return out


@router.get("/types/{type_slug}/objects", response_model=list[TagCandidate])
def tag_candidates(
    type_slug: str,
    q: str = "",
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TagCandidate]:
    """그 타입에서 고를 것 — 이름에 `q` 가 든 것, 많이 쓴 것부터."""
    return services.candidates(db, type_slug, q, limit)


@router.get("/used/{target}", response_model=list[TagUse])
def used_tags(
    target: TargetKey,
    owner: str = Query(
        default="",
        max_length=36,
        description="작업만 — 비우면 내 것. `all`(모두) · 사람 id(그 사람)는 시스템 관리자만.",
    ),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TagUse]:
    """쓰인 태그 **객체**를 타입별로 — 목록의 타입별 거르개(`?tag_id=`)가 칩으로 그린다. 작업은
    내 것(관리자는 `owner` 로 남의 것 · 모두), 부품 · 지그는 카탈로그 전부, 템플릿은 볼 수 있는
    것(내 것 · 공용)."""
    if target == "part":
        return services.used(db, services.TARGETS["part"].model)
    if target == "jig":
        return services.used(db, services.TARGETS["jig"].model)
    if target == "template":
        return templates.used_tags(db, user)
    model = services.TARGETS["work"].model
    if not owner:
        return services.used(db, model, model.owner_id == user.id)
    if not user.is_system_admin:
        raise Forbidden(code("TAGS", 14), "다른 사용자의 작업 태그는 시스템 관리자만 봅니다.")
    if owner == "all":
        return services.used(db, model)
    try:
        whose = uuid.UUID(owner)
    except ValueError as failure:
        raise AppError(
            code("TAGS", 15), "owner 는 비우거나 all · 사람 id 중 하나입니다."
        ) from failure
    return services.used(db, model, model.owner_id == whose)


@router.get("/settings", response_model=list[TagSettingOut])
def tag_settings(
    _: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> list[TagSettingOut]:
    """관리 › 온톨로지 › 태그 — 타입마다 「태그로 안 씀 · 고르기 · 늘리기」."""
    out = services.settings(db)
    db.commit()
    return out


@router.put("/settings/{type_slug}", response_model=list[TagSettingOut])
def set_tag_mode(
    type_slug: str,
    payload: TagModeRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[TagSettingOut]:
    services.set_mode(db, user, type_slug, payload.mode)
    db.commit()
    return services.settings(db)


@router.get("/similar", response_model=SimilarTagsOut)
def similar_tags(
    _: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> SimilarTagsOut:
    """관리 › 온톨로지 › 태그의 「비슷한 태그 정리」 — 같은 타입 안에서 이름이 띄어쓰기 ·
    이음표 · 대소문자만 다른 태그 묶음과 남길 것의 추천."""
    out = services.similar(db)
    db.commit()
    return out


@router.post("/merge", response_model=MergeTagsOut)
def merge_tags(
    payload: MergeTagsRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> MergeTagsOut:
    """태그를 하나로 — 붙은 선이 남길 것으로 옮겨 가고, 지는 쪽 이름은 남길 것의 별칭이 된다
    (온톨로지의 객체 합치기 그대로, 하나씩 커밋한다)."""
    return services.merge(db, user, payload)


@router.get("/{target}/{row_id}", response_model=list[TagItem])
def row_tags(
    target: TargetKey,
    row_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TagItem]:
    row = _row(db, user, target, row_id, write=False)
    return services.tags_of(db, row.id)


@router.post("/{target}/{row_id}", response_model=list[TagItem])
def add_tag(
    target: TargetKey,
    row_id: uuid.UUID,
    payload: AddTagRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TagItem]:
    """하나 붙인다 — 고른 객체(`object_id`), 또는 타입과 이름(없으면 만든다 — 「늘리기」
    타입만). 이미 붙어 있으면 그대로다. 붙은 태그 전부를 돌려준다."""
    row = _row(db, user, target, row_id, write=True)
    services.add(db, user, target, row, payload)
    db.commit()
    return services.tags_of(db, row.id)


@router.delete("/{target}/{row_id}/{object_id}", response_model=list[TagItem])
def remove_tag(
    target: TargetKey,
    row_id: uuid.UUID,
    object_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TagItem]:
    """하나 뗀다 — 객체는 남는다(다른 데 붙어 있을 수 있다)."""
    row = _row(db, user, target, row_id, write=True)
    services.remove(db, user, target, row, object_id)
    db.commit()
    return services.tags_of(db, row.id)
