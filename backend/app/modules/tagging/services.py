"""태그 — **온톨로지의 객체를 붙인다**(2026-10-23, ADR 0011).

전에는 작업 · 부품 · 지그에 글자 목록(`tags` JSONB)을 달았다. 같은 말을 사람마다 달리 적고
(「굽힘시험」 · 「굽힘 시험」), 그 말이 무엇인지(프로젝트인가 · 고객사인가) 아무도 몰랐다. 이제
태그는 온톨로지의 객체다:

- 태그로 쓸 타입을 관리자가 고른다(`TagType`). 「고르기」 면 있는 객체에서 고르고,
  「늘리기」 면 **붙이는 사람 누구나** 그 타입에 새 객체를 만든다 — 태그를 달수록 어휘가
  쌓인다. 타입을 안 고르면 「일반 태그」(`cc_tag`)다.
- 붙인 것은 선이다(`object_links`, 관계 `cc_tagged`). 작업 · 부품 · 지그는 원 표(system 타입)로
  비춘다 — 온톨로지에서 그 객체를 열면 무엇에 붙었는지 보이고, 그래프 · 경로가 그 선을 탄다.
- 태그 객체는 **전역**(부서 소유가 아니다)만 붙고 보인다. 공용 부품의 태그가 보는 사람마다
  다르면 안 되고, 부서마다 같은 이름이 따로 생기면 묶음이 갈린다.

**글자 목록으로 주고받는 길은 남긴다**(`tags: list[str]` — MCP · 시편 · 규격 묶음). 읽을 때는
붙은 객체의 이름이고, 쓸 때는 이름마다 이미 붙은 것을 두고 없는 것은 「일반 태그」 에서 찾거나
만든다.

정본은 선 하나다 — 이름을 따로 적어 두지 않는다. 온톨로지 화면에서도 선을 잇고 끊고, 객체를
고치고 합치므로 적어 둔 사본은 반드시 갈린다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import exists, func, literal, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.modules.accounts.models import User
from app.modules.jigs.models import Jig
from app.modules.objects import aliases, links
from app.modules.objects.models import ObjectInstance, ObjectLink
from app.modules.objects.services import properties_of
from app.modules.objects.system import End, end_of
from app.modules.ontology import managed
from app.modules.ontology.models import ObjectType, RelationType
from app.modules.ontology.services import InvalidValue, validate_properties
from app.modules.parts.models import Part
from app.modules.tagging.models import DEFAULT_TAG_TYPE, TAG_MODES, TAG_RELATION, TagType
from app.modules.templates.models import RecipeTemplate
from app.modules.works.models import Work
from app.shared import audit, search
from app.shared.errors import Conflict, NotFound, code
from app.shared.text import clean

#: 새로 만드는 태그 이름의 길이 — 목록의 칩에 들어갈 만큼.
LABEL_MAX = 80
#: 기본 정의를 만들 때 잡는 잠금 — 처음 쓰는 요청 둘이 같은 타입을 두 번 만들지 않게.
_ENSURE_LOCK = 0x43435447


@dataclass(frozen=True)
class Target:
    """태그가 붙는 원 표 하나."""

    key: str
    """원 표의 키(`SystemSource.key`) — API 경로에도 쓴다."""
    model: Any
    slug: str
    """그 원 표를 비추는 시스템 타입이 없을 때 만드는 slug."""
    label: str
    noun: str


TARGETS: dict[str, Target] = {
    "work": Target("work", Work, "cc_work", "CompCore 작업", "작업"),
    "part": Target("part", Part, "cc_part", "CompCore 부품", "부품"),
    "jig": Target("jig", Jig, "cc_jig", "CompCore 지그", "지그"),
    "template": Target("template", RecipeTemplate, "cc_template", "CompCore 템플릿", "템플릿"),
}


def _alive(model: Any) -> tuple[ColumnElement[bool], ...]:
    """지운 행은 안 센다 — 지우면 행이 사라지는 표(템플릿)는 거를 칸이 없다."""
    deleted = getattr(model, "deleted_at", None)
    return (deleted.is_(None),) if deleted is not None else ()


def _named(target: Target, row: Any) -> str:
    """선의 감사 기록 · 알림에 적을 이 행의 이름 — **남에게 안 보이는 행은 이름을 안 적는다**
    (작업은 늘, 템플릿은 공용이 아니면 — 그 기록은 태그 객체의 이력으로 모두에게 나간다)."""
    if target.key == "work" or (target.key == "template" and not row.is_shared):
        return target.noun
    return str(row.name)


@dataclass(frozen=True)
class Defaults:
    relation: RelationType
    sources: dict[str, ObjectType]
    """원 표 키 → 그것을 비추는 시스템 타입."""
    default_type: ObjectType


class TagItem(BaseModel):
    object_id: uuid.UUID
    label: str
    type_slug: str
    type_label: str


class TagCandidate(TagItem):
    uses: int
    """이 객체를 태그로 단 작업 · 부품 · 지그 수 — 많이 쓴 것이 앞이다."""


class TagUse(TagItem):
    uses: int
    """이 객체가 붙은 행 수(지운 것 빼고) — 거르개의 칩 곁에 적는다."""


class TagTypeOut(BaseModel):
    slug: str
    label: str
    icon: str
    mode: str
    can_create: bool
    """붙이는 사람이 이 타입에 새 객체를 만들 수 있나."""
    note: str = ""
    """못 만드는 까닭 — 「늘리기」 로 정했는데 다른 규칙이 막을 때 관리 화면이 보인다."""
    is_default: bool


class TagSettingOut(BaseModel):
    """관리 화면의 한 줄 — 태그로 쓸 수 있는 타입(원 표 타입은 빼고) 하나."""

    slug: str
    label: str
    mode: str
    """`off`(태그로 안 씀) · `pick` · `grow`."""
    managed_by: str
    entry_policy: str
    is_default: bool
    note: str = ""


class AddTagRequest(BaseModel):
    """붙이기 — 고른 객체(`object_id`), 또는 타입과 이름(`type_slug` · `label`). 이름은 그
    타입에서 같은 이름 · 별칭을 먼저 찾고, 없으면 만든다(「늘리기」 타입만)."""

    object_id: uuid.UUID | None = None
    type_slug: str | None = None
    """비우면 「일반 태그」."""
    label: str | None = Field(default=None, max_length=LABEL_MAX)


class TagModeRequest(BaseModel):
    mode: str
    """`off` · `pick` · `grow`."""


# --- 기본 정의 ------------------------------------------------------------------


def _system_type(db: Session, target: Target, *, create: bool) -> ObjectType | None:
    """그 원 표를 비추는 시스템 타입 — 관리자가 만든 것이 있으면 그것(쓰는 것 · 앞 순서가
    먼저)."""
    found = db.scalars(
        select(ObjectType)
        .where(ObjectType.kind_class == "system", ObjectType.system_source == target.key)
        .order_by(ObjectType.is_active.desc(), ObjectType.sort_order, ObjectType.slug)
    ).first()
    if found is not None or not create:
        return found
    row = ObjectType(
        slug=target.slug,
        label=target.label,
        kind_class="system",
        system_source=target.key,
        description=f"CompCore 의 {target.noun} — 원 표를 비춘다(행을 복제하지 않는다).",
    )
    db.add(row)
    db.flush()
    return row


def _read(db: Session) -> Defaults | None:
    sources: dict[str, ObjectType] = {}
    for key, target in TARGETS.items():
        found = _system_type(db, target, create=False)
        if found is None:
            return None
        sources[key] = found
    default = db.scalar(select(ObjectType).where(ObjectType.slug == DEFAULT_TAG_TYPE))
    relation = db.scalar(select(RelationType).where(RelationType.slug == TAG_RELATION))
    if default is None or relation is None or db.get(TagType, default.id) is None:
        return None
    ends = relation.src_type_slugs
    if ends is not None and not {one.slug for one in sources.values()} <= set(ends):
        return None
    return Defaults(relation=relation, sources=sources, default_type=default)


def ensure(db: Session) -> Defaults:
    """기본 정의 — 원 표 타입 셋 · 「일반 태그」 · 태그 관계. **없으면 만든다**(여러 번 불러도
    같다). 운영 DB 는 마이그레이션 0037 이 넣었고, 시험 · 새 설치는 처음 쓸 때 여기서 선다.
    부르는 쪽이 커밋한다."""
    found = _read(db)
    if found is not None:
        return found
    db.execute(select(func.pg_advisory_xact_lock(_ENSURE_LOCK)))
    sources = {key: _system_type(db, one, create=True) for key, one in TARGETS.items()}
    default = db.scalar(select(ObjectType).where(ObjectType.slug == DEFAULT_TAG_TYPE))
    if default is None:
        default = ObjectType(
            slug=DEFAULT_TAG_TYPE,
            label="일반 태그",
            icon="tag",
            kind_class="reference",
            description="타입을 고르지 않고 붙인 태그 — 붙이는 사람 누구나 늘린다.",
        )
        db.add(default)
        db.flush()
    if db.get(TagType, default.id) is None:
        db.add(TagType(type_id=default.id, mode="grow"))
    wanted = sorted({one.slug for one in sources.values() if one is not None})
    relation = db.scalar(select(RelationType).where(RelationType.slug == TAG_RELATION))
    if relation is None:
        db.add(
            RelationType(
                slug=TAG_RELATION,
                label="태그",
                inverse_label="태그가 붙은 것",
                description="작업 · 부품 · 지그에 붙인 태그(ADR 0011). 상대 타입은 정하지 "
                "않는다 — 어느 타입이 태그인지는 관리 › 온톨로지 › 태그가 정한다.",
                cardinality="many_to_many",
                src_type_slugs=wanted,
                dst_type_slugs=None,
            )
        )
    elif relation.src_type_slugs is not None:
        relation.src_type_slugs = sorted({*relation.src_type_slugs, *wanted})
    db.flush()
    made = _read(db)
    if made is None:  # pragma: no cover - 위에서 다 만들었다
        raise Conflict(code("TAGS", 9), "태그의 기본 정의를 만들지 못했습니다.")
    return made


# --- 읽기 ---------------------------------------------------------------------


def _shown() -> tuple[ColumnElement[bool], ...]:
    """붙어 보이는 객체 — 지우지(합치지) 않은 전역 객체."""
    return (ObjectInstance.deleted_at.is_(None), ObjectInstance.owner_workspace_id.is_(None))


def tags_of(db: Session, row_id: uuid.UUID) -> list[TagItem]:
    """이 행에 붙은 태그 — 붙인 순서대로."""
    rows = db.execute(
        select(ObjectInstance.id, ObjectInstance.label, ObjectType.slug, ObjectType.label)
        .select_from(ObjectLink)
        .join(ObjectInstance, ObjectInstance.id == ObjectLink.dst_id)
        .join(ObjectType, ObjectType.id == ObjectInstance.type_id)
        .where(ObjectLink.src_id == row_id, ObjectLink.relation == TAG_RELATION, *_shown())
        .order_by(ObjectLink.created_at, ObjectInstance.label)
    )
    return [
        TagItem(object_id=one, label=label, type_slug=slug, type_label=type_label)
        for one, label, slug, type_label in rows
    ]


def labels(db: Session, row_id: uuid.UUID) -> list[str]:
    """이 행의 태그 이름 — 글자 목록으로 내보내는 자리(목록 · MCP)가 쓴다. 다른 타입의 같은
    이름은 한 번만."""
    out: list[str] = []
    for one in tags_of(db, row_id):
        if one.label not in out:
            out.append(one.label)
    return out


def label_like(row_id: Any) -> Callable[[str], ColumnElement[bool]]:
    """찾기(`shared/search.py` 의 `also`)에 끼우는 조건 — 붙은 태그의 이름에 낱말이 들었나."""

    def build(like: str) -> ColumnElement[bool]:
        return exists(
            select(literal(1))
            .select_from(ObjectLink)
            .join(ObjectInstance, ObjectInstance.id == ObjectLink.dst_id)
            .where(
                ObjectLink.src_id == row_id,
                ObjectLink.relation == TAG_RELATION,
                ObjectInstance.label.ilike(like),
                *_shown(),
            )
        )

    return build


def tagged(row_id: Any, label: str) -> ColumnElement[bool]:
    """목록 거르개(`?tag=`) — 이 이름의 태그가 붙었나(대소문자는 안 가린다)."""
    return exists(
        select(literal(1))
        .select_from(ObjectLink)
        .join(ObjectInstance, ObjectInstance.id == ObjectLink.dst_id)
        .where(
            ObjectLink.src_id == row_id,
            ObjectLink.relation == TAG_RELATION,
            func.lower(ObjectInstance.label) == clean(label).lower(),
            *_shown(),
        )
    )


def tagged_object(row_id: Any, object_id: uuid.UUID) -> ColumnElement[bool]:
    """목록 거르개(`?tag_id=`) — **이 태그 객체**가 붙었나. 이름이 같은 다른 타입의 태그(고객사
    「A」 와 프로젝트 「A」)는 안 걸린다 — 그것이 이름 거르개(`tagged`)와 다른 점이다."""
    return exists(
        select(literal(1)).where(
            ObjectLink.src_id == row_id,
            ObjectLink.relation == TAG_RELATION,
            ObjectLink.dst_id == object_id,
        )
    )


def used(db: Session, model: Any, *where: ColumnElement[bool]) -> list[TagUse]:
    """`model`(작업 · 부품 · 지그)에 붙은 태그 **객체**와 붙은 수 — 타입별 거르개가 쓴다.
    「일반 태그」 가 먼저, 그다음 타입 이름 순, 한 타입 안에서는 많이 쓴 것부터. `where` 로
    행을 좁힌다(내 작업만 · DOE 의 대상 작업만)."""
    rows = db.execute(
        select(
            ObjectInstance.id,
            ObjectInstance.label,
            ObjectType.slug,
            ObjectType.label,
            func.count(func.distinct(ObjectLink.src_id)),
        )
        .select_from(ObjectLink)
        .join(ObjectInstance, ObjectInstance.id == ObjectLink.dst_id)
        .join(ObjectType, ObjectType.id == ObjectInstance.type_id)
        .join(model, model.id == ObjectLink.src_id)
        .where(
            ObjectLink.relation == TAG_RELATION,
            *_alive(model),
            *_shown(),
            *where,
        )
        .group_by(ObjectInstance.id, ObjectInstance.label, ObjectType.slug, ObjectType.label)
    ).all()
    out = [
        TagUse(object_id=one, label=label, type_slug=slug, type_label=kind, uses=int(n))
        for one, label, slug, kind, n in rows
    ]
    out.sort(
        key=lambda one: (
            one.type_slug != DEFAULT_TAG_TYPE,
            one.type_label,
            -one.uses,
            one.label,
        )
    )
    return out


def label_counts(db: Session, model: Any, *where: ColumnElement[bool]) -> list[str]:
    """`model`(작업 · 부품 · 지그)에 붙은 태그 이름 — 많이 쓴 것부터. 거르개 · 자동 완성이
    쓴다. `where` 로 그 표의 행을 더 좁힌다(내 작업만 · DOE 의 대상 작업만). 지운 행은 안
    센다."""
    rows = db.execute(
        select(ObjectInstance.label, func.count(func.distinct(ObjectLink.src_id)))
        .select_from(ObjectLink)
        .join(ObjectInstance, ObjectInstance.id == ObjectLink.dst_id)
        .join(model, model.id == ObjectLink.src_id)
        .where(
            ObjectLink.relation == TAG_RELATION,
            *_alive(model),
            *_shown(),
            *where,
        )
        .group_by(ObjectInstance.label)
    ).all()
    return [label for label, _count in sorted(rows, key=lambda one: (-one[1], one[0]))]


def _setting_of(db: Session, object_type: ObjectType) -> TagType | None:
    return db.get(TagType, object_type.id)


def creation_refusal(object_type: ObjectType, setting: TagType | None) -> str | None:
    """붙이는 사람이 이 타입에 새 객체를 못 만드는 까닭 — 만들 수 있으면 None."""
    if setting is None or setting.mode != "grow":
        return (
            f"{object_type.label}은(는) 고르기만 하는 태그 타입입니다 — 새 이름은 관리자가 그 "
            "타입에 만듭니다."
        )
    owner = managed.owner_of(object_type)
    if owner:
        return (
            f"{object_type.label}은(는) {owner} 가 관리하는 타입이라 여기서 만들지 않습니다."
        )
    if not object_type.is_active:
        return f"{object_type.label}은(는) 지금 쓰지 않는 타입입니다."
    if object_type.entry_policy != "open":
        return f"{object_type.label}은(는) 입력 정책이 닫혀 있어 관리자가 등록한 값만 씁니다."
    if object_type.key_policy == "required":
        return f"{object_type.label}은(는) 식별자가 꼭 있어야 해 이름만으로 만들 수 없습니다."
    return None


def tag_types(db: Session) -> list[TagTypeOut]:
    """태그로 고를 수 있는 타입 — 「일반 태그」 가 맨 앞."""
    ensure(db)
    rows = sorted(
        db.execute(
            select(ObjectType, TagType)
            .join(TagType, TagType.type_id == ObjectType.id)
            .where(ObjectType.is_active.is_(True), ObjectType.kind_class != "system")
        ).tuples(),
        key=lambda one: (one[0].slug != DEFAULT_TAG_TYPE, one[1].sort_order, one[0].label),
    )
    out: list[TagTypeOut] = []
    for one, setting in rows:
        refused = creation_refusal(one, setting)
        out.append(
            TagTypeOut(
                slug=one.slug,
                label=one.label,
                icon=one.icon,
                mode=setting.mode,
                can_create=refused is None,
                note=(refused or "") if setting.mode == "grow" else "",
                is_default=one.slug == DEFAULT_TAG_TYPE,
            )
        )
    return out


def _tag_type(db: Session, slug: str) -> tuple[ObjectType, TagType]:
    object_type = db.scalar(select(ObjectType).where(ObjectType.slug == slug))
    setting = _setting_of(db, object_type) if object_type is not None else None
    if object_type is None or setting is None or object_type.kind_class == "system":
        raise NotFound(
            code("TAGS", 1),
            f"태그로 쓰는 타입이 아닙니다({slug}) — 관리 › 온톨로지 › 태그에서 고릅니다.",
        )
    return object_type, setting


def candidates(db: Session, slug: str, q: str, limit: int) -> list[TagCandidate]:
    """그 태그 타입에서 고를 객체 — 이름 · 별칭에 낱말이 든 것, 많이 쓴 것부터."""
    object_type, _setting = _tag_type(db, slug)
    uses = (
        select(ObjectLink.dst_id, func.count().label("n"))
        .where(ObjectLink.relation == TAG_RELATION)
        .group_by(ObjectLink.dst_id)
        .subquery()
    )
    stmt = (
        select(ObjectInstance, func.coalesce(uses.c.n, 0))
        .outerjoin(uses, uses.c.dst_id == ObjectInstance.id)
        .where(
            ObjectInstance.type_id == object_type.id,
            ObjectInstance.status == "active",
            *_shown(),
        )
    )
    text = clean(q or "")
    if text:
        stmt = stmt.where(ObjectInstance.label.ilike(search.pattern(text)))
    rows = db.execute(
        stmt.order_by(func.coalesce(uses.c.n, 0).desc(), ObjectInstance.label).limit(limit)
    ).all()
    return [
        TagCandidate(
            object_id=row.id,
            label=row.label,
            type_slug=object_type.slug,
            type_label=object_type.label,
            uses=int(count),
        )
        for row, count in rows
    ]


# --- 붙이기 · 떼기 ---------------------------------------------------------------


def _end(defaults: Defaults, target: Target, row: Any) -> End:
    """붙인 행 쪽 끝. **남에게 안 보이는 행(작업 · 내 템플릿)은 이름을 안 적는다**(`_named`)
    — 선의 감사 기록은 태그 객체의 이력 · 지켜보기 알림 · 웹훅으로 나가고, 그쪽을 보는 사람은
    남의 작업 · 템플릿을 못 본다(`works/system.py` · `templates/system.py`)."""
    label = _named(target, row)
    return End(
        id=row.id, type_slug=defaults.sources[target.key].slug, label=label, is_system=True
    )


def _find(db: Session, object_type: ObjectType, name: str) -> ObjectInstance | None:
    """그 타입에서 같은 이름(대소문자 무시), 없으면 같은 별칭의 전역 객체."""
    found = db.scalars(
        select(ObjectInstance)
        .where(
            ObjectInstance.type_id == object_type.id,
            func.lower(ObjectInstance.label) == name.lower(),
            *_shown(),
        )
        .order_by(ObjectInstance.created_at)
    ).first()
    if found is not None:
        return found
    ids = aliases.lookup(db, object_type, name)
    if not ids:
        return None
    return db.scalars(
        select(ObjectInstance)
        .where(ObjectInstance.id.in_(ids), *_shown())
        .order_by(ObjectInstance.created_at)
    ).first()


def _create(db: Session, user: User, object_type: ObjectType, name: str) -> ObjectInstance:
    """붙이는 사람이 만드는 태그 객체 — **전역**이고 감사 기록에 남는다. 객체 화면의 「만들기」
    는 전역 객체를 시스템 관리자에게만 열지만, 태그 타입의 「늘리기」 는 관리자가 그 타입을
    그렇게 열어 둔 것이다."""
    refused = creation_refusal(object_type, _setting_of(db, object_type))
    if refused:
        raise Conflict(code("TAGS", 2), refused)
    defs = properties_of(db, object_type.id)
    missing = [one.label for one in defs if one.required and one.default_value is None]
    if missing:
        raise Conflict(
            code("TAGS", 3),
            f"{object_type.label}에는 채워야 할 칸({', '.join(missing)})이 있어 태그로 바로 "
            "만들 수 없습니다 — 그 타입 화면에서 만든 뒤 고르세요.",
        )
    row = ObjectInstance(
        type_id=object_type.id,
        key=None,
        label=name,
        properties=validate_properties(defs, {}, apply_defaults=True),
        owner_workspace_id=None,
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        action="object.create",
        actor=user,
        target_table="objects",
        target_id=row.id,
        target_label=f"{object_type.slug}:{row.label}",
        workspace_id=None,
        reason="태그로 만듦",
    )
    return row


def _name(raw: str | None) -> str:
    name = clean(raw or "")
    if not name:
        raise InvalidValue(code("TAGS", 4), "태그 이름을 적으세요.")
    if len(name) > LABEL_MAX:
        raise InvalidValue(code("TAGS", 5), f"태그 이름은 {LABEL_MAX}자까지입니다.")
    return name


def _link(
    db: Session, user: User, defaults: Defaults, target: Target, row: Any, obj: ObjectInstance
) -> None:
    if links.existing(db, row.id, obj.id, TAG_RELATION) is not None:
        return
    object_type = db.get(ObjectType, obj.type_id)
    if object_type is None:  # pragma: no cover - FK 가 지킨다
        raise NotFound(code("TAGS", 6), "태그의 타입을 찾을 수 없습니다.")
    made = links.add(
        db,
        user,
        defaults.relation,
        _end(defaults, target, row),
        end_of(obj, object_type),
        reason="태그",
    )
    # 붙인 순서가 곧 보이는 순서다 — 칸의 기본값(`now()`)은 트랜잭션의 시각이라 한 번에 붙인
    # 여럿(글자 목록 · 승격)이 같은 시각이 된다.
    made.created_at = datetime.now(UTC)


def add(db: Session, user: User, key: str, row: Any, request: AddTagRequest) -> TagItem:
    """하나 붙인다 — 이미 붙어 있으면 그대로. **권한은 부르는 쪽이 봤다.** 부르는 쪽이
    커밋한다."""
    defaults = ensure(db)
    target = TARGETS[key]
    if request.object_id is not None:
        obj = db.scalar(
            select(ObjectInstance).where(ObjectInstance.id == request.object_id, *_shown())
        )
        if obj is None:
            raise NotFound(
                code("TAGS", 7),
                "태그로 붙일 객체를 찾을 수 없습니다 — 지웠거나, 부서 소유입니다(태그는 "
                "모두가 보는 객체만 붙습니다).",
            )
        object_type = db.get(ObjectType, obj.type_id)
        if object_type is None or _setting_of(db, object_type) is None:
            label = object_type.label if object_type else "그 타입"
            raise Conflict(
                code("TAGS", 8),
                f"{label}은(는) 태그로 쓰는 타입이 아닙니다 — 관리 › 온톨로지 › 태그에서 "
                "고릅니다.",
            )
    else:
        object_type, _setting = _tag_type(db, request.type_slug or DEFAULT_TAG_TYPE)
        name = _name(request.label)
        obj = _find(db, object_type, name) or _create(db, user, object_type, name)
    _link(db, user, defaults, target, row, obj)
    return TagItem(
        object_id=obj.id,
        label=obj.label,
        type_slug=object_type.slug,
        type_label=object_type.label,
    )


def remove(db: Session, user: User, key: str, row: Any, object_id: uuid.UUID) -> None:
    """하나 뗀다. 객체는 남는다 — 다른 데 붙어 있을 수 있고, 어휘는 쌓이는 것이다."""
    found = links.existing(db, row.id, object_id, TAG_RELATION)
    if found is None:
        raise NotFound(code("TAGS", 10), "이 태그는 붙어 있지 않습니다.")
    target = TARGETS[key]
    obj = db.get(ObjectInstance, object_id)
    links.remove(
        db,
        user,
        found,
        src_label=_named(target, row),
        dst_label=obj.label if obj else "?",
        workspace_id=None,
        reason="태그 뗌",
    )


def set_labels(db: Session, user: User, key: str, row: Any, names: list[str]) -> None:
    """**글자 목록으로 통째로 바꾼다**(옛 길 — MCP 의 `update_work` · 시편 · 규격 묶음).

    이름이 같은(대소문자 무시) 태그는 그대로 둔다 — 타입을 골라 붙인 것도 이름이 목록에 있으면
    산다. 목록에 없는 것은 떼고, 새 이름은 「일반 태그」 에서 찾거나 만든다."""
    wanted: list[str] = []
    for raw in names:
        name = clean(str(raw))[:LABEL_MAX]
        if name and name.casefold() not in {one.casefold() for one in wanted}:
            wanted.append(name)
    keep = {one.casefold() for one in wanted}
    have: set[str] = set()
    for one in tags_of(db, row.id):
        if one.label.casefold() in keep:
            have.add(one.label.casefold())
        else:
            remove(db, user, key, row, one.object_id)
    for name in wanted:
        if name.casefold() not in have:
            add(db, user, key, row, AddTagRequest(label=name))


def forget(db: Session, row_id: uuid.UUID) -> int:
    """행이 **진짜로 지워질 때**(템플릿) 그 행에 닿은 선을 함께 지운다 — 남기면 태그 객체의
    「태그가 붙은 것」 에 없는 행이 「(지워짐)」 으로 남는다. 부르는 쪽이 커밋한다."""
    found = list(
        db.scalars(
            select(ObjectLink).where(
                (ObjectLink.src_id == row_id) | (ObjectLink.dst_id == row_id)
            )
        )
    )
    for one in found:
        db.delete(one)
    return len(found)


def copy(db: Session, user: User, source: Any, key: str, row: Any) -> None:
    """`source` 행의 태그를 `row` 에도 — 더하기만 한다(승격 · 복제가 물려준다)."""
    found = tags_of(db, source.id)
    if not found:
        return
    defaults = ensure(db)
    target = TARGETS[key]
    for one in found:
        obj = db.get(ObjectInstance, one.object_id)
        if obj is not None:
            _link(db, user, defaults, target, row, obj)


# --- 관리 ---------------------------------------------------------------------


def settings(db: Session) -> list[TagSettingOut]:
    """원 표 타입을 뺀 모든 타입과 그 태그 설정 — 관리 화면."""
    ensure(db)
    modes = {one.type_id: one for one in db.scalars(select(TagType))}
    out: list[TagSettingOut] = []
    for one in db.scalars(
        select(ObjectType)
        .where(ObjectType.kind_class != "system")
        .order_by(ObjectType.sort_order, ObjectType.label)
    ):
        setting = modes.get(one.id)
        refused = (
            creation_refusal(one, setting) if setting and setting.mode == "grow" else None
        )
        out.append(
            TagSettingOut(
                slug=one.slug,
                label=one.label,
                mode=setting.mode if setting else "off",
                managed_by=managed.owner_of(one),
                entry_policy=one.entry_policy,
                is_default=one.slug == DEFAULT_TAG_TYPE,
                note=refused or "",
            )
        )
    out.sort(key=lambda one: (not one.is_default, one.mode == "off", one.label))
    return out


def set_mode(db: Session, user: User, slug: str, mode: str) -> None:
    """이 타입을 태그로 쓸지 · 어떻게 — `off` 면 태그 타입에서 뺀다(붙은 태그는 그대로
    남는다)."""
    if mode not in ("off", *TAG_MODES):
        raise InvalidValue(
            code("TAGS", 11), f"알 수 없는 방식({mode})입니다 — off · pick · grow 중 하나."
        )
    ensure(db)
    object_type = db.scalar(select(ObjectType).where(ObjectType.slug == slug))
    if object_type is None or object_type.kind_class == "system":
        raise NotFound(code("TAGS", 12), f"태그로 쓸 수 있는 타입이 아닙니다({slug}).")
    if object_type.slug == DEFAULT_TAG_TYPE and mode == "off":
        raise Conflict(
            code("TAGS", 13),
            "「일반 태그」 는 끌 수 없습니다 — 타입을 안 고른 태그와 옛 꼬리표가 가는 "
            "곳입니다.",
        )
    setting = _setting_of(db, object_type)
    before = setting.mode if setting else "off"
    if before == mode:
        return
    if mode == "off" and setting is not None:
        db.delete(setting)
    elif setting is None:
        db.add(TagType(type_id=object_type.id, mode=mode))
    else:
        setting.mode = mode
    audit.record(
        db,
        action="tagging.type.set",
        actor=user,
        target_table="object_types",
        target_id=object_type.id,
        target_label=object_type.slug,
        changes={"mode": {"before": before, "after": mode}},
    )
