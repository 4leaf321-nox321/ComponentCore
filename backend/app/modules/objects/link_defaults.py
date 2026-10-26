"""CompCore 의 **기본 기준정보 관계** — 부품 · 지그에 SP 기준정보를 잇는 관계 종류 꾸러미.

부품 · 지그 화면의 「기준정보」 칸 · 목록의 기준정보 거르개 · DOE 폴더의 `ontology` 는 관계
종류가 있어야 선다(`source_links.py`). 설치마다 관리자가 손으로 만들면 slug 와 말이 설치마다
갈리고(「적용 모델」 · 「대상 모델」), 그러면 SimEngBay 가 받는 `relation` 도 갈린다. 그래서
기본을 여기 한 곳에 두고, 관리 › 온톨로지 › 관계의 「CompCore 기본 관계」 가 만든다.

**저절로 만들지 않는다.** 출발 타입(기본 모델 · 서비스 부품)은 SP 기준정보를 받아야 생기고,
잇는 말은 설치의 결정이다. 그래서:

- 만들 수 있는 것만 만든다 — 출발 타입이 없으면 까닭을 적고 뺀다.
- **이미 있는 것은 건드리지 않는다** — 같은 slug 거나, 같은 두 타입을 잇는 관계가 이미 있으면
  (관리자가 다른 이름으로 만들었으면) 그대로 둔다. 관리자가 고친 말이 기본으로 되돌아가거나
  같은 칸이 두 줄이 되지 않게.
- 만드는 길은 정의 가져오기 그대로다(`importer.apply` · 적용 전 스냅샷 · 감사 기록). 스냅샷
  복원은 더하기만 하므로 만든 관계 종류를 지우지 않는다 — 안 쓸 것은 관계 종류 화면에서 지운다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.ontology import importer
from app.modules.ontology.models import ObjectType, RelationType
from app.modules.tagging import services as tagging
from app.shared import audit
from app.shared.errors import Conflict, code

#: 스냅샷 · 감사 기록에 적는 까닭.
REASON = "CompCore 기본 관계"


@dataclass(frozen=True)
class LinkDefault:
    slug: str
    label: str
    """출발(기준정보) 쪽에서 읽는 말 — 「사용 부품」."""
    inverse_label: str
    """부품 · 지그 쪽에서 읽는 말 — 「기준정보」 칸의 이름이 된다(「적용 모델」)."""
    source_type: str
    """출발 타입 slug — SP 기준정보 받기(`sp_core` 데이터 소스)가 만든다."""
    target: str
    """도착 원 표 — `part` · `jig`(`tagging.TARGETS` 의 키). 그 원 표를 비추는 타입으로
    잇는다."""
    cardinality: str
    description: str


#: 개발 서버에서 2026-10-14 부터 써 온 정의 그대로다(`docs/온톨로지-이식-계획.md` E 단계).
DEFAULTS: tuple[LinkDefault, ...] = (
    LinkDefault(
        "uses_part",
        "사용 부품",
        "적용 모델",
        "base_model",
        "part",
        "many_to_many",
        "이 기본 모델(제품)에 쓰이는 CompCore 부품.",
    ),
    LinkDefault(
        "design_part",
        "설계 부품",
        "서비스 부품",
        "part",
        "part",
        "many_to_one",
        "서비스 부품(SP)의 설계 형상 — 서비스 부품 하나에 CompCore 부품 하나.",
    ),
    LinkDefault(
        "verify_jig",
        "검증 지그",
        "대상 모델",
        "base_model",
        "jig",
        "many_to_many",
        "이 기본 모델을 검증하는 CompCore 지그.",
    ),
)


class LinkDefaultOut(BaseModel):
    slug: str
    label: str
    inverse_label: str
    source_type: str
    source_label: str
    """출발 타입의 이름 — 아직 없으면 빈칸."""
    target_type: str
    target_label: str
    status: Literal["ready", "exists", "missing"]
    """`ready` 만들 수 있다 · `exists` 이미 있다(건드리지 않는다) · `missing` 출발 타입이
    없다."""
    note: str = ""


class LinkDefaultsApplied(BaseModel):
    created: list[str]
    snapshot_id: uuid.UUID | None
    """적용 전 정의(가져오기와 같다). 만든 것이 없으면 없다."""
    items: list[LinkDefaultOut]


def _same_ends(relation: RelationType, source: str, target: str) -> bool:
    """두 타입을 **콕 집어** 잇는 관계인가 — 아무 타입이나 받는 쪽(빈 목록)은 안 센다(태그
    관계는 도착이 아무것이다)."""
    return source in (relation.src_type_slugs or []) and target in (
        relation.dst_type_slugs or []
    )


def _plan(db: Session) -> tuple[list[LinkDefaultOut], list[dict[str, Any]]]:
    """꾸러미의 줄마다 상태, 그리고 만들 것의 가져오기 파일(`relation_types`)."""
    sources = tagging.ensure(db).sources
    types = {one.slug: one for one in db.scalars(select(ObjectType))}
    relations = list(db.scalars(select(RelationType).order_by(RelationType.slug)))
    items: list[LinkDefaultOut] = []
    payload: list[dict[str, Any]] = []
    for one in DEFAULTS:
        target = sources[one.target]
        source = types.get(one.source_type)
        same_slug = next((row for row in relations if row.slug == one.slug), None)
        same_ends = next(
            (row for row in relations if _same_ends(row, one.source_type, target.slug)), None
        )
        status: Literal["ready", "exists", "missing"] = "ready"
        note = ""
        if same_slug is not None:
            status = "exists"
            if same_slug.inverse_label != one.inverse_label:
                note = f"이미 있습니다(「{same_slug.inverse_label}」) — 그대로 둡니다."
        elif same_ends is not None:
            status = "exists"
            note = (
                f"같은 두 타입을 잇는 관계 `{same_ends.slug}`"
                f"(「{same_ends.inverse_label}」)가 이미 있습니다 — 같은 칸이 두 줄이 되지 "
                "않게 만들지 않습니다."
            )
        elif source is None:
            status = "missing"
            note = (
                f"출발 타입 `{one.source_type}` 이 아직 없습니다 — SP 기준정보(데이터 소스 › "
                "SP 코어)를 먼저 받으십시오."
            )
        else:
            payload.append(
                {
                    "slug": one.slug,
                    "label": one.label,
                    "inverse_label": one.inverse_label,
                    "description": one.description,
                    "cardinality": one.cardinality,
                    "src_type_slugs": [one.source_type],
                    "dst_type_slugs": [target.slug],
                }
            )
        items.append(
            LinkDefaultOut(
                slug=one.slug,
                label=one.label,
                inverse_label=one.inverse_label,
                source_type=one.source_type,
                source_label=source.label if source is not None else "",
                target_type=target.slug,
                target_label=target.label,
                status=status,
                note=note,
            )
        )
    return items, payload


def read(db: Session) -> list[LinkDefaultOut]:
    """꾸러미의 줄마다 상태 — 부르는 쪽이 커밋한다(처음이면 원 표 타입이 선다)."""
    return _plan(db)[0]


def apply(db: Session, user: User) -> LinkDefaultsApplied:
    """`ready` 인 것을 만든다 — 정의 가져오기 그대로, 적용 전 스냅샷을 남기고. 커밋한다."""
    _items, payload = _plan(db)
    if not payload:
        db.commit()
        return LinkDefaultsApplied(created=[], snapshot_id=None, items=read(db))
    snapshot = importer.take_snapshot(db, user, reason=REASON)
    prepared = importer.apply(db, {"relation_types": payload}, actor=user, reason=REASON)
    if prepared.errors:
        db.rollback()
        raise Conflict(
            code("OBJECTS", 905),
            "기본 관계를 만들지 못했습니다 — " + "; ".join(prepared.errors),
        )
    audit.record(
        db,
        action="ontology.import",
        actor=user,
        target_table="ontology_snapshots",
        target_id=snapshot.id,
        target_label=f"{REASON} {len(payload)}건",
    )
    db.commit()
    return LinkDefaultsApplied(
        created=[one["slug"] for one in payload], snapshot_id=snapshot.id, items=read(db)
    )
