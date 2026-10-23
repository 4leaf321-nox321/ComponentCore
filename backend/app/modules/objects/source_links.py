"""부품 · 지그 화면의 「기준정보」 칸 — **원 표의 행에서 본 관계**(CompCore, ADR 0008).

부품 · 지그는 온톨로지의 원 표다(`parts/system.py` · `jigs/system.py`). 여기는 그 행 하나에
닿는 **관계 종류마다 한 줄**을 세운다 — 「적용 모델」 · 「서비스 부품」 · 「분류」 처럼. 칸을
코드에 박지 않는다: 관리자가 관계 종류를 더하면 그 칸이 저절로 선다.

**잇고 끊는 사람은 그 부품(지그)을 고칠 수 있는 사람이다.** SP 의 규칙은 「출발점을 고칠 수
있는 사람」 인데, 받은 기준정보(기본 모델 등)는 「기준정보」 부서 소유라 그 규칙대로면 부품을
만든 설계자가 제 부품에 적용 모델을 못 단다. 선의 방향(기본 모델 → 부품)은 관계 정의대로
두고, 권한만 이 행 쪽에서 본다 — 부르는 쪽(`parts` · `jigs` 라우터)이 확인한다.

오류 번호는 900번대다 — SP 가 앞 번호를 계속 쓰므로 들인 모듈에 더한 것과 겹치지 않게.

추천은 **이름에 든 낱말**로만 한다 — 상대 이름의 낱말이 이 행 이름에 얼마나 들었나. 짐작은
거기까지고, 잇는 것은 사람이다.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.objects import links, system
from app.modules.objects import relations as rel
from app.modules.objects.models import ObjectInstance, ObjectLink
from app.modules.ontology import managed
from app.modules.ontology.models import ObjectType, RelationType
from app.modules.tagging.models import TAG_RELATION
from app.shared.errors import Conflict, NotFound, code
from app.shared.permissions import visible_owner_clause

#: 칸마다 추천은 이만큼까지 — 많으면 안 읽는다.
SUGGEST_MAX = 3
#: 상대 이름의 낱말이 이 비율 이상 이 행 이름에 들어야 추천한다.
SUGGEST_SHARE = 0.6

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


class LinkedItem(BaseModel):
    object_id: uuid.UUID
    label: str
    key: str | None
    type_slug: str
    type_label: str
    link_id: uuid.UUID | None = None


class TypeRef(BaseModel):
    slug: str
    label: str


class LinkRow(BaseModel):
    relation: str
    label: str
    """이 행 쪽에서 본 말 — 이 행이 도착점이면 역방향 이름."""
    incoming: bool
    """이 행이 도착점인가(상대 → 이 행)."""
    single: bool
    """이 행 쪽에서 하나만 걸 수 있나(개수 제약)."""
    other_types: list[TypeRef]
    items: list[LinkedItem] = Field(default_factory=list)
    suggestions: list[LinkedItem] = Field(default_factory=list)


class SourceLinks(BaseModel):
    type_slug: str | None
    """이 원 표를 비추는 시스템 타입 — 없으면 칸이 없다(관리자가 타입부터 만든다)."""
    rows: list[LinkRow]


def system_types(db: Session, source_key: str) -> list[ObjectType]:
    """이 원 표를 비추는 시스템 타입들 — 보통 하나지만 둘 이상 만들 수 있다(그때는 모두에 닿는
    관계가 칸이 된다)."""
    return list(
        db.scalars(
            select(ObjectType)
            .where(
                ObjectType.kind_class == "system",
                ObjectType.system_source == source_key,
                ObjectType.is_active.is_(True),
            )
            .order_by(ObjectType.sort_order, ObjectType.slug)
        )
    )


def _sides(kind: RelationType, slugs: set[str]) -> list[bool]:
    """이 원 표가 그 관계의 어느 쪽에 서나 — 참이면 도착점. **타입을 정해 둔 관계만** 본다 (안
    정한 관계는 원 표를 뒤지지 않는다 — `system.find_end` 와 같은 규칙). 태그(`cc_tagged`)는
    칸이 아니다 — 제 자리(태그 줄, `tagging`)가 있다."""
    out: list[bool] = []
    if kind.slug == TAG_RELATION:
        return out
    if slugs & set(kind.dst_type_slugs or []):
        out.append(True)
    if slugs & set(kind.src_type_slugs or []):
        out.append(False)
    return out


def _words(text: str) -> set[str]:
    return {one.casefold() for one in _WORD.findall(text) if len(one) >= 2}


def _suggest(
    db: Session,
    user: User,
    name: str,
    other_slugs: list[str],
    types: dict[str, ObjectType],
    taken: set[uuid.UUID],
) -> list[LinkedItem]:
    """상대 이름의 낱말이 이 행 이름에 많이 든 것부터. 원 표 타입은 추천하지 않는다(원 표끼리는
    사람이 고른다)."""
    mine = _words(name)
    if not mine:
        return []
    targets = [
        types[one] for one in other_slugs if one in types and not system.is_system(types[one])
    ]
    if not targets:
        return []
    by_id = {one.id: one for one in targets}
    patterns = [f"%{word}%" for word in mine]
    rows = db.scalars(
        select(ObjectInstance)
        .where(
            ObjectInstance.type_id.in_(list(by_id)),
            ObjectInstance.deleted_at.is_(None),
            visible_owner_clause(user, ObjectInstance.owner_workspace_id),
            or_(*[ObjectInstance.label.ilike(one) for one in patterns]),
        )
        .limit(200)
    )
    scored: list[tuple[float, int, ObjectInstance]] = []
    for row in rows:
        if row.id in taken:
            continue
        theirs = _words(row.label)
        if not theirs:
            continue
        share = len(theirs & mine) / len(theirs)
        if share >= SUGGEST_SHARE:
            scored.append((share, len(theirs & mine), row))
    # **겹친 낱말이 가장 많은 무리만** — 모델 이름만 같은 것(「P5 플립 메인보드」)이 「P5 플립
    # 힌지 어셈블리」 곁에 서면 추천이 목록이 된다(실제 SP 자료로 본 것, 2026-10-14).
    best = max((hits for _share, hits, _row in scored), default=0)
    scored = [one for one in scored if one[1] == best]
    scored.sort(key=lambda one: (-one[0], one[2].label))
    return [
        LinkedItem(
            object_id=row.id,
            label=row.label,
            key=row.key,
            type_slug=by_id[row.type_id].slug,
            type_label=by_id[row.type_id].label,
        )
        for _share, _hits, row in scored[:SUGGEST_MAX]
    ]


def read(
    db: Session, user: User, source_key: str, row_id: uuid.UUID, name: str
) -> SourceLinks:
    """이 행의 칸들 — 관계 종류마다 한 줄, 걸린 것과 추천."""
    mine_types = system_types(db, source_key)
    if not mine_types:
        return SourceLinks(type_slug=None, rows=[])
    mine_slugs = {one.slug for one in mine_types}
    types = system.types_by_slug(db)
    kinds = [
        kind
        for kind in db.scalars(
            select(RelationType)
            .where(RelationType.is_active.is_(True))
            .order_by(RelationType.label, RelationType.slug)
        )
        if _sides(kind, mine_slugs)
    ]
    found = [
        one for one in system.links_of(db, row_id) if one.relation in {k.slug for k in kinds}
    ]
    out: list[LinkRow] = []
    for kind in kinds:
        for incoming in _sides(kind, mine_slugs):
            others = (kind.src_type_slugs if incoming else kind.dst_type_slugs) or []
            row = LinkRow(
                relation=kind.slug,
                label=(kind.inverse_label or kind.label) if incoming else kind.label,
                incoming=incoming,
                single=kind.cardinality
                in (
                    ("one_to_one", "one_to_many")
                    if incoming
                    else ("one_to_one", "many_to_one")
                ),
                other_types=[
                    TypeRef(slug=one, label=types[one].label) for one in others if one in types
                ],
            )
            for link in found:
                if link.relation != kind.slug:
                    continue
                if (link.dst_id if incoming else link.src_id) != row_id:
                    continue
                end = system.other_end(db, user, link, row_id, types)
                if end is None:
                    continue  # 못 보는 것 — 없는 것과 같은 말로.
                key = None
                if not end.is_system:
                    key = db.scalar(
                        select(ObjectInstance.key).where(ObjectInstance.id == end.id)
                    )
                row.items.append(
                    LinkedItem(
                        object_id=end.id,
                        label=end.label,
                        key=key,
                        type_slug=end.type_slug,
                        type_label=types[end.type_slug].label
                        if end.type_slug in types
                        else "",
                        link_id=link.id,
                    )
                )
            if not (row.single and row.items):
                row.suggestions = _suggest(
                    db, user, name, others, types, {one.object_id for one in row.items}
                )
            out.append(row)
    return SourceLinks(type_slug=mine_types[0].slug, rows=out)


def link(
    db: Session,
    user: User,
    source_key: str,
    row_id: uuid.UUID,
    *,
    relation: str,
    object_id: uuid.UUID,
) -> None:
    """이 행과 상대 하나를 잇는다 — 방향은 관계 정의대로. **권한은 부르는 쪽이 봤다.**"""
    mine_types = system_types(db, source_key)
    if not mine_types:
        raise Conflict(
            code("OBJECTS", 901),
            "이 원 표를 비추는 시스템 타입이 없습니다 — 관리 › 온톨로지 › 타입에서 먼저 "
            "만드세요.",
        )
    kind = rel.relation_type(db, relation)
    managed.require_relation_editable(kind)
    sides = _sides(kind, {one.slug for one in mine_types})
    if not sides:
        raise Conflict(
            code("OBJECTS", 902),
            f"{kind.label}은(는) {mine_types[0].label}에 닿지 않는 관계입니다.",
        )
    incoming = sides[0]
    # 이 관계가 이쪽 끝으로 받는 타입 — 원 표 타입이 여럿이면 관계 정의가 고른 것.
    ends = set((kind.dst_type_slugs if incoming else kind.src_type_slugs) or [])
    mine_type = next(one for one in mine_types if one.slug in ends)
    ref = system.find(db, mine_type, row_id)
    if ref is None:
        raise NotFound(code("OBJECTS", 903), "원 표에서 이 행을 찾을 수 없습니다.")
    mine = system.End(id=ref.id, type_slug=mine_type.slug, label=ref.label, is_system=True)
    allowed = (kind.src_type_slugs if incoming else kind.dst_type_slugs) or []
    other = system.find_end(db, user, object_id, allowed=allowed)
    if other is None:
        raise NotFound(code("OBJECTS", 28), "이을 객체를 찾을 수 없습니다.")
    src, dst = (other, mine) if incoming else (mine, other)
    links.add(db, user, kind, src, dst)
    db.commit()


def unlink(db: Session, user: User, row_id: uuid.UUID, link_id: uuid.UUID) -> None:
    """이 행에 걸린 선 하나를 끊는다. 다른 행의 선 id 면 없는 것과 같다."""
    found = db.get(ObjectLink, link_id)
    if found is None or row_id not in (found.src_id, found.dst_id):
        raise NotFound(code("OBJECTS", 904), "이 행에 걸린 선이 아닙니다.")
    kind = rel.relation_type(db, found.relation)
    managed.require_relation_editable(kind)
    types = system.types_by_slug(db)
    # 양 끝의 이름 — 감사 기록에 「누가 → 누구를」 로 남긴다(반대쪽 끝을 물으면 그 끝이 온다).
    src_end = system.other_end(db, user, found, found.dst_id, types)
    dst_end = system.other_end(db, user, found, found.src_id, types)
    links.remove(
        db,
        user,
        found,
        src_label=src_end.label if src_end else "?",
        dst_label=dst_end.label if dst_end else "?",
        workspace_id=(src_end.owner_workspace_id if src_end else None)
        or (dst_end.owner_workspace_id if dst_end else None),
    )
    db.commit()


class LinkRequest(BaseModel):
    """부품 · 지그 화면에서 잇기 — 관계 종류와 상대 하나."""

    relation: str
    object_id: uuid.UUID
