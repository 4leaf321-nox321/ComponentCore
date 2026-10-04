"""부품 카탈로그 — 읽기와 이름 고치기뿐. 버전은 승격(`modules/works`)으로만 생긴다."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import version as app_version
from app.config import get_settings
from app.modules.accounts.models import User
from app.modules.jigs.models import Jig
from app.modules.jobs import services as jobs
from app.modules.jobs.models import Job
from app.modules.parts.models import Part, PartVersion
from app.modules.parts.schemas import (
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    STANDARD_RANGES,
    PartOut,
    PartSummaryOut,
    PartVersionOut,
    StandardBundle,
    StandardBundleItem,
    StandardImportItemOut,
    StandardImportOut,
    StandardSpec,
)
from app.shared import folders, search, shape_search
from app.shared.errors import AppError, Forbidden, NotFound, code


def get_part(db: Session, part_id: uuid.UUID) -> Part:
    part = db.get(Part, part_id)
    if part is None or part.deleted_at is not None:
        raise NotFound(code("PARTS", 1), "부품을 찾을 수 없습니다.")
    return part


def require_owner(part: Part, user: User) -> None:
    if part.owner_id != user.id and not user.is_system_admin:
        raise Forbidden(code("PARTS", 2), "이 부품을 수정할 권한이 없습니다.")


def get_version(db: Session, part: Part, number: int) -> PartVersion:
    version = db.scalar(
        select(PartVersion).where(PartVersion.part_id == part.id, PartVersion.number == number)
    )
    if version is None:
        raise NotFound(code("PARTS", 3), f"v{number} 버전을 찾을 수 없습니다.")
    return version


def current_version(db: Session, part: Part) -> PartVersion | None:
    return get_version(db, part, part.current_version) if part.current_version > 0 else None


def version_out(db: Session, version: PartVersion) -> PartVersionOut:
    who = db.get(User, version.promoted_by_id) if version.promoted_by_id else None
    job = db.get(Job, version.job_id) if version.job_id else None
    return PartVersionOut(
        id=version.id,
        part_id=version.part_id,
        number=version.number,
        recipe=version.recipe,
        conditions=version.conditions or {},
        job=jobs.job_out(db, job) if job else None,
        note=version.note,
        promoted_by_id=version.promoted_by_id,
        promoted_by_name=who.display_name if who else None,
        work_version_id=version.work_version_id,
        created_at=version.created_at,
    )


def _jig_count(db: Session, part_id: uuid.UUID) -> int:
    return int(
        db.scalar(select(func.count()).where(Jig.part_id == part_id, Jig.deleted_at.is_(None)))
        or 0
    )


def part_out(db: Session, part: Part) -> PartOut:
    owner = db.get(User, part.owner_id)
    count = int(db.scalar(select(func.count()).where(PartVersion.part_id == part.id)) or 0)
    current = current_version(db, part)
    return PartOut(
        id=part.id,
        name=part.name,
        description=part.description,
        owner_id=part.owner_id,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        work_id=part.work_id,
        current_version=part.current_version,
        version_count=count,
        current=version_out(db, current) if current else None,
        jig_count=_jig_count(db, part.id),
        created_at=part.created_at,
        tags=list(part.tags or []),
        folder=part.folder,
        standard=part.standard,
        updated_at=part.updated_at,
    )


def part_summary(db: Session, part: Part) -> PartSummaryOut:
    owner = db.get(User, part.owner_id)
    current = current_version(db, part)
    return PartSummaryOut(
        id=part.id,
        name=part.name,
        description=part.description,
        owner_id=part.owner_id,
        owner_name=owner.display_name if owner else "(삭제된 계정)",
        current_version=part.current_version,
        jig_count=_jig_count(db, part.id),
        tags=list(part.tags or []),
        folder=part.folder,
        standard=part.standard,
        updated_at=part.updated_at,
        shape=shape_search.latest_shape(db, current.job_id if current else None),
    )


def list_parts(
    db: Session,
    *,
    limit: int,
    offset: int,
    query: str = "",
    tag: str = "",
    folder: str | None = None,
    subfolders: bool = True,
    shape: shape_search.ShapeFilter | None = None,
    standard: str = "",
) -> tuple[list[Part], int]:
    base = select(Part).where(Part.deleted_at.is_(None))
    # 규격 부품만 — `any` 면 종류를 안 가린다.
    if standard == "any":
        base = base.where(Part.standard.is_not(None))
    elif standard:
        base = base.where(Part.standard["kind"].astext == standard)
    if shape is not None:
        base = shape_search.narrowed(
            base, shape, model=Part, version=PartVersion, owner=PartVersion.part_id
        )
    base = folders.narrowed(base, Part.folder, folder, subfolders, _BAD_FOLDER)
    found = search.matches(
        query, columns=[Part.name, Part.description], tags=Part.tags, owner=Part.owner_id
    )
    if found is not None:
        base = base.where(found)
    if tag.strip():
        base = base.where(Part.tags.contains([tag.strip()]))
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(
        db.scalars(base.order_by(Part.updated_at.desc(), Part.id).limit(limit).offset(offset))
    )
    return rows, total


#: 폴더 경로가 틀렸을 때 · 폴더째 옮길 수 없을 때.
_BAD_FOLDER = code("PARTS", 4)


def part_folders(db: Session) -> list[folders.FolderOut]:
    """카탈로그의 폴더들 — 지운 부품은 세지 않는다."""
    return folders.tree(db, Part.folder, Part.deleted_at.is_(None))


def rename_folder(db: Session, user: User, *, path: str, to: str) -> int:
    return folders.rename_shared(
        db,
        Part,
        Part.deleted_at.is_(None),
        path=path,
        to=to,
        user=user,
        noun="부품",
        error_code=_BAD_FOLDER,
        forbidden_code=code("PARTS", 2),
    )


def move_parts(db: Session, user: User, *, ids: list[uuid.UUID], folder: str) -> int:
    return folders.move_shared(
        db,
        Part,
        Part.deleted_at.is_(None),
        ids=ids,
        folder=folder,
        user=user,
        noun="부품",
        error_code=_BAD_FOLDER,
        forbidden_code=code("PARTS", 2),
        missing_code=code("PARTS", 1),
    )


def list_versions(db: Session, part: Part) -> list[PartVersion]:
    return list(
        db.scalars(
            select(PartVersion)
            .where(PartVersion.part_id == part.id)
            .order_by(PartVersion.number.desc())
        )
    )


def update_part(db: Session, part: Part, *, fields: dict[str, Any]) -> Part:
    if fields.get("folder") is not None:
        fields["folder"] = folders.normalize(fields["folder"], _BAD_FOLDER)
    for key, value in fields.items():
        if value is not None:
            setattr(part, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(part)
    return part


def delete_part(db: Session, part: Part) -> None:
    part.deleted_at = datetime.now(UTC)
    db.commit()


def all_tags(db: Session) -> list[str]:
    """카탈로그에 붙은 꼬리표 전부 — 거르개 · 자동 완성. 많이 쓰인 것이 앞이다.

    내 작업의 `my_tags` 와 **같은 모양**이다(화면이 한 벌이면 된다). 다만 여기는 **남의
    것까지** 센다 — 공용 공간이라 그것이 맞다."""
    seen: dict[str, int] = {}
    for tags in db.scalars(select(Part.tags).where(Part.deleted_at.is_(None))):
        for one in tags or []:
            seen[one] = seen.get(one, 0) + 1
    return sorted(seen, key=lambda t: (-seen[t], t))


# --- 규격 부품 -------------------------------------------------------------------


def _standard_problems(spec: StandardSpec, recipe: dict[str, Any]) -> list[str]:
    """그린 형상이 사양의 기준을 지키나 — 생성기는 이 기준을 믿고 놓는다."""
    from app.modules.cad import services as cad

    problems: list[str] = []
    ops = {str(one.get("op")) for one in recipe.get("nodes") or [] if isinstance(one, dict)}
    if ops & {"import_step", "component"}:
        problems.append(
            "규격 부품의 형상은 레시피로만 그립니다. STEP 가져오기 · 다른 도면 가져오기 없이 "
            "다시 그리십시오(지그 생성 작업은 다른 파일을 열지 않습니다)."
        )
        return problems
    params = recipe.get("params") or {}
    span = STANDARD_RANGES.get(spec.kind)
    if span is not None and getattr(spec, span[0]) and getattr(spec, span[0]) not in params:
        problems.append(f"레시피에 변수 ‘{getattr(spec, span[0])}’이(가) 없습니다.")
    box = cad.build(recipe).summary()["bbox"]
    low, high = box["min"], box["max"]
    if abs(low[2]) > 0.5:
        problems.append(
            f"바닥이 z=0 이 아닙니다(z={low[2]:.2f}). 바닥을 원점 높이에 맞추십시오."
        )
    if spec.kind in ("support", "pin"):
        cx, cy = (low[0] + high[0]) / 2, (low[1] + high[1]) / 2
        if abs(cx) > 0.5 or abs(cy) > 0.5:
            problems.append(f"바닥 중심이 원점이 아닙니다(x={cx:.2f}, y={cy:.2f}).")
        tall = float((spec.height if spec.kind == "support" else spec.length) or 0.0)
        if abs(high[2] - low[2] - tall) > 0.5:
            name = "height" if spec.kind == "support" else "length"
            problems.append(
                f"{name}({tall:g})가 그린 높이({high[2] - low[2]:.2f})와 다릅니다."
            )
    else:
        reach, pad = float(spec.reach or 0), float(spec.pad_height or 0)
        if not (low[0] - 0.5 <= reach <= high[0] + 0.5 and low[2] <= pad <= high[2] + 0.5):
            problems.append(
                f"패드 중심 (reach {reach:g}, 0, pad_height {pad:g})이 형상 밖입니다. 팔이 "
                "+X 로 뻗고 베이스 바닥 중심이 원점이어야 합니다."
            )
    return problems


def set_standard(db: Session, part: Part, spec: StandardSpec) -> Part:
    """규격 사양을 붙인다 — 관리자만(라우터가 막는다). 쓰는 버전의 형상이 기준을 지키는지
    본 뒤에 저장한다."""
    taken = [one for one in _by_part_no(db, spec.part_no) if one.id != part.id]
    if taken:
        raise AppError(
            code("PARTS", 11),
            f"품번 ‘{spec.part_no}’은(는) 이미 ‘{taken[0].name}’ 부품에 등록되어 있습니다.",
            status=409,
        )
    version = get_version(db, part, spec.version)
    problems = _standard_problems(spec, version.recipe)
    if problems:
        raise AppError(
            code("PARTS", 10),
            "규격 사양이 형상과 맞지 않습니다.",
            details={"problems": problems},
        )
    part.standard = spec.stored()
    db.commit()
    db.refresh(part)
    return part


def _by_part_no(db: Session, part_no: str) -> list[Part]:
    """같은 품번의 규격 부품 — 품번은 부품표의 열쇠라 하나여야 한다. 가져오기가 이것으로
    짝짓는다."""
    return list(
        db.scalars(
            select(Part).where(
                Part.deleted_at.is_(None), Part.standard["part_no"].astext == part_no
            )
        )
    )


def clear_standard(db: Session, part: Part) -> Part:
    part.standard = None
    db.commit()
    db.refresh(part)
    return part


def standard_library(db: Session) -> list[dict[str, Any]]:
    """지그 생성기에 넘길 **규격 부품 목록** — 사양 · 쓰는 버전의 레시피. 값으로 넘긴다
    (코어는 DB 를 모른다). 생성 작업의 입력에도 이대로 담아, 나중에 사양이 바뀌어도 그 작업은
    그때 것으로 돈다."""
    rows = db.scalars(
        select(Part).where(Part.deleted_at.is_(None), Part.standard.is_not(None))
    ).all()
    out: list[dict[str, Any]] = []
    for part in rows:
        spec = dict(part.standard or {})
        version = db.scalar(
            select(PartVersion).where(
                PartVersion.part_id == part.id,
                PartVersion.number == int(spec.get("version", 0)),
            )
        )
        if version is None:
            continue
        out.append(
            {
                "source": f"part:{part.id}@{version.number}",
                "kind": spec.get("kind"),
                "part_no": spec.get("part_no", ""),
                "name": part.name,
                "preference": int(spec.get("preference", 100)),
                "spec": spec,
                "recipe": version.recipe,
            }
        )
    return out


# --- 규격 부품 옮기기 -------------------------------------------------------------
#
# 개발 PC 에서 그린 규격품을 **묶음 파일**(JSON 하나)로 내보내고 운영 서버에서 가져온다.
# 형상이 레시피뿐이라(STEP · 다른 도면을 가리키지 않는다) 따라가야 할 파일이 없다. 가져오기는
# 내 작업을 거치지 않고 카탈로그 버전을 **바로** 만든다 — 관리자만(ADR 0005).


def export_standard(db: Session, ids: list[uuid.UUID]) -> StandardBundle:
    """고른 규격 부품(비우면 전부)을 묶음으로 — 사양(쓰는 버전 빼고)과 **그 버전의** 레시피."""
    if ids:
        parts = [get_part(db, one) for one in dict.fromkeys(ids)]
        plain = [one.name for one in parts if one.standard is None]
        if plain:
            raise AppError(
                code("PARTS", 12),
                f"규격 사양이 없는 부품은 내보낼 수 없습니다: {', '.join(plain)}",
            )
    else:
        parts = list(
            db.scalars(
                select(Part)
                .where(Part.deleted_at.is_(None), Part.standard.is_not(None))
                .order_by(Part.folder, Part.name)
            )
        )
    items: list[StandardBundleItem] = []
    for part in parts:
        spec = dict(part.standard or {})
        number = int(spec.pop("version"))
        pinned = get_version(db, part, number)
        items.append(
            StandardBundleItem(
                name=part.name,
                description=part.description,
                tags=list(part.tags or []),
                folder=part.folder,
                standard=spec,
                recipe=pinned.recipe,
                origin={"part_id": str(part.id), "version": number},
            )
        )
    settings = get_settings()
    origin = f"{settings.app_name} {app_version.current()} {settings.app_public_url}"
    return StandardBundle(
        format=BUNDLE_FORMAT,
        format_version=BUNDLE_VERSION,
        exported_at=datetime.now(UTC),
        exported_from=origin.strip(),
        items=items,
    )


def _spec_problems(failure: ValidationError) -> list[str]:
    out = []
    for one in failure.errors():
        where = ".".join(str(part) for part in one["loc"])
        message = str(one["msg"]).removeprefix("Value error, ")
        out.append(f"{where}: {message}" if where else message)
    return out


def _tags(raw: list[str]) -> list[str]:
    cleaned: list[str] = []
    for one in raw:
        tag = str(one).strip()[:40]
        if tag and tag not in cleaned:
            cleaned.append(tag)
    return cleaned


def _same_spec(stored: dict[str, Any], given: dict[str, Any]) -> bool:
    def drop(spec: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in spec.items() if key != "version"}

    return drop(stored) == drop(given)


def _plan_item(
    db: Session, item: StandardBundleItem, seen: set[str]
) -> tuple[StandardImportItemOut, StandardSpec | None, Part | None]:
    """묶음의 한 항목을 이 서버에서 어떻게 할까 — 아무것도 쓰지 않는다."""
    raw = item.standard
    out = StandardImportItemOut(
        part_no=str(raw.get("part_no") or ""),
        name=item.name,
        kind=str(raw.get("kind") or ""),
        action="skip",
    )
    try:
        spec = StandardSpec(**{**raw, "version": 1})
    except ValidationError as failure:
        out.problems = _spec_problems(failure)
        return out, None, None
    problems: list[str] = []
    try:
        folders.normalize(item.folder, _BAD_FOLDER)
    except AppError as failure:
        problems.append(failure.message)
    if spec.part_no in seen:
        problems.append("묶음 안에 같은 품번이 또 있습니다.")
    seen.add(spec.part_no)
    matches = _by_part_no(db, spec.part_no)
    if len(matches) > 1:
        problems.append(
            "이 서버에 같은 품번의 규격 부품이 둘 이상 있습니다. 하나만 남기십시오."
        )
    try:
        problems.extend(_standard_problems(spec, item.recipe))
    except AppError as failure:
        problems.extend(failure.details.get("problems") or [failure.message])
    if problems:
        out.problems = problems
        return out, None, None

    existing = matches[0] if matches else None
    if existing is None:
        out.action, out.version = "create", 1
        return out, spec, None
    current = dict(existing.standard or {})
    pinned = get_version(db, existing, int(current["version"]))
    out.part_id = existing.id
    if pinned.recipe != item.recipe:
        out.action, out.version = "version", existing.current_version + 1
    elif not _same_spec(current, spec.stored()):
        out.action, out.version = "spec", pinned.number
    else:
        out.action, out.version = "same", pinned.number
    return out, spec, existing


def import_standard(
    db: Session, bundle: StandardBundle, *, by: User, dry_run: bool
) -> StandardImportOut:
    """묶음을 이 서버의 카탈로그로 — **품번으로 짝짓는다.** 없으면 새 부품(v1), 있으면 형상이
    다를 때 새 버전 · 사양만 다르면 사양만. 이름 · 설명 · 폴더 · 태그는 새로 만들 때만 쓴다(이
    서버에서 옮기거나 고친 것을 되돌리지 않는다). 문제가 있는 항목은 건너뛰고 까닭을 말한다.

    `dry_run` 이면 아무것도 쓰지 않고 할 일만 돌려준다 — 화면이 먼저 보여 주고 확인받는다.
    새 버전은 평가 작업(`cad`)을 걸어 STEP · glTF 를 만든다(부품 화면 · 3D)."""
    if bundle.format_version > BUNDLE_VERSION:
        raise AppError(
            code("PARTS", 13),
            f"이 서버가 읽을 수 없는 묶음 형식입니다(판 {bundle.format_version}). "
            "서버를 최신 버전으로 갱신하십시오.",
        )
    seen: set[str] = set()
    planned = [(item, *_plan_item(db, item, seen)) for item in bundle.items]
    if dry_run:
        return StandardImportOut(dry_run=True, items=[out for _, out, _, _ in planned])

    from app.modules.cad import services as cad

    stamp = bundle.exported_at.strftime("%Y-%m-%d")
    fresh: list[PartVersion] = []
    for item, out, spec, existing in planned:
        if spec is None or out.action == "same":
            continue
        part = existing
        if part is None:
            part = Part(
                name=item.name.strip(),
                description=item.description.strip(),
                owner_id=by.id,
                tags=_tags(item.tags),
                folder=folders.normalize(item.folder, _BAD_FOLDER),
                current_version=0,
            )
            db.add(part)
            db.flush()
        number = int(out.version or 1)
        if out.action in ("create", "version"):
            origin = item.origin
            made = PartVersion(
                part_id=part.id,
                number=part.current_version + 1,
                recipe=item.recipe,
                conditions={},
                note=(
                    f"가져옴: {bundle.exported_from or '다른 서버'} 부품 "
                    f"{origin.get('part_id', '?')} v{origin.get('version', '?')} ({stamp})"
                ),
                promoted_by_id=by.id,
            )
            db.add(made)
            part.current_version = made.number
            number = made.number
            fresh.append(made)
        part.standard = spec.model_copy(update={"version": number}).stored()
        out.part_id, out.version = part.id, number
    db.commit()
    for made in fresh:
        job = jobs.enqueue(
            db,
            kind=cad.JOB_KIND,
            requested_by=by,
            work_id=None,
            input={"part_version_id": str(made.id), "recipe": made.recipe},
            options={},
        )
        made.job_id = job.id
        db.commit()
    return StandardImportOut(dry_run=False, items=[out for _, out, _, _ in planned])
