"""시험 규격 — 공개 규격(코드)과 사내 규격(DB)을 한 목록으로 보이고, 프리셋으로 시편 · 시험
지그 · 해석 조건을 그려 내 작업을 만든다(ADR 0006).

사내 규격은 **시스템 관리자만** 더하고 고친다(라우터가 막는다). 저장할 때 코어의 프리셋 검사와
실제로 그려 보기를 지난다 — 틀린 값이 목록에 올라 다른 사람이 고른 뒤에 터지지 않게.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import conditions as condition_model
from app.core import specimens
from app.core.recipe import topology
from app.core.recipe.params import resolve_params
from app.core.specimens import PRODUCT_TESTS, TESTS, Preset
from app.core.specimens.product import FacePick, ProductTestError
from app.modules.accounts.models import User
from app.modules.parts import services as parts
from app.modules.specimens.models import SpecimenPreset
from app.modules.specimens.schemas import (
    PresetOut,
    ProductSourceRequest,
    ProductTestRequest,
    SpecimenBuildOut,
    SpecimenRequest,
    SpecimenWorkRequest,
)
from app.modules.works import services as works
from app.modules.works.models import Work
from app.shared.errors import AppError, NotFound, code

_MISSING = code("SPECIMENS", 1)
_INVALID = code("SPECIMENS", 2)
_BUILTIN = code("SPECIMENS", 3)
_UNBUILDABLE = code("SPECIMENS", 4)
_WRONG_TEST = code("SPECIMENS", 5)
_BAD_SOURCE = code("SPECIMENS", 6)


def _problems(failure: ValidationError) -> list[str]:
    out = []
    for one in failure.errors():
        where = ".".join(str(part) for part in one["loc"])
        message = str(one["msg"]).removeprefix("Value error, ")
        out.append(f"{where}: {message}" if where else message)
    return out


def _builtin_out(preset: Preset) -> PresetOut:
    return PresetOut(
        id=preset.id,
        origin="builtin",
        test=preset.test,
        standard=preset.standard,
        name=preset.name,
        preset=preset.model_dump(mode="json"),
    )


def _internal_out(db: Session, row: SpecimenPreset) -> PresetOut:
    who = db.get(User, row.updated_by_id) if row.updated_by_id else None
    return PresetOut(
        id=str(row.id),
        origin="internal",
        test=row.test,
        standard=row.standard,
        name=row.name,
        preset=dict(row.body),
        updated_at=row.updated_at,
        updated_by_name=who.display_name if who else None,
    )


def _row(db: Session, preset_id: str) -> SpecimenPreset | None:
    try:
        key = uuid.UUID(preset_id)
    except ValueError:
        return None
    row = db.get(SpecimenPreset, key)
    return row if row is not None and row.deleted_at is None else None


def list_presets(db: Session, test: str = "") -> list[PresetOut]:
    """공개 규격 다음에 사내 규격 — 시험 종류 · 규격 번호 순."""
    out = [_builtin_out(one) for one in specimens.builtin() if not test or one.test == test]
    query = select(SpecimenPreset).where(SpecimenPreset.deleted_at.is_(None))
    if test:
        query = query.where(SpecimenPreset.test == test)
    out += [_internal_out(db, row) for row in db.scalars(query)]
    order = {name: index for index, name in enumerate(TESTS)}
    return sorted(
        out,
        key=lambda one: (
            order.get(one.test, 99),
            one.standard,
            one.origin != "builtin",
            one.name,
        ),
    )


def find(db: Session, preset_id: str) -> tuple[Preset, PresetOut]:
    """프리셋과 그 목록 줄 — 공개 규격의 이름이면 코드에서, 아니면 DB(사내 규격)에서."""
    builtin = specimens.find_builtin(preset_id)
    if builtin is not None:
        return builtin, _builtin_out(builtin)
    row = _row(db, preset_id)
    if row is None:
        raise NotFound(_MISSING, f"시험 규격({preset_id})을 찾을 수 없습니다.")
    return specimens.parse_preset({**row.body, "id": str(row.id)}), _internal_out(db, row)


def _checked(raw: dict[str, Any], preset_id: str) -> Preset:
    """코어의 프리셋 검사와 실제로 그려 보기 — 틀리면 어느 칸이 왜인지 `details.problems`."""
    try:
        preset = specimens.parse_preset({**raw, "id": preset_id})
    except ValidationError as failure:
        raise AppError(
            _INVALID,
            "시험 규격의 값이 올바르지 않습니다.",
            details={"problems": _problems(failure)},
        ) from failure
    try:
        if preset.test in PRODUCT_TESTS:
            # 제품에 거는 시험은 시편이 없다 — 기준 상자에 걸어 보고 조건이 맞는지 본다.
            # 손잡이 · 방향 하중은 고른 자리가 있어야 하고(윗면을 고른 셈), 압축은 무게가
            # 있어야 한다.
            made = specimens.product.apply(
                preset,
                _REFERENCE,
                None,
                bbox=([-50.0, -30.0, 0.0], [50.0, 30.0, 10.0]),
                faces=_REFERENCE_FACES.get(preset.test),
                mass=1.0,
            )
            condition_model.parse(made.conditions)
        else:
            specimens.build(preset)
    except (ValueError, condition_model.ConditionError) as failure:
        raise AppError(
            _INVALID,
            "이 시험 규격으로 해석 모델을 만들 수 없습니다.",
            details={"problems": [str(failure)]},
        ) from failure
    return preset


#: 제품 시험 규격을 저장하기 전에 걸어 보는 기준 제품 — 100 x 60 x 10 상자.
_REFERENCE: dict[str, Any] = {
    "version": 1,
    "nodes": [
        {
            "id": "기준",
            "op": "box",
            "length": 100,
            "width": 60,
            "height": 10,
            "align": ["center", "center", "min"],
        }
    ],
}
_TOP = [FacePick((0.0, 0.0, 10.0), (0.0, 0.0, 1.0))]
#: 고른 면이 꼭 있어야 하는 시험 — 기준 상자의 윗면을 고른 셈으로 걸어 본다.
_REFERENCE_FACES = {"handle": {"support": _TOP}, "directed": {"load": _TOP}}


def create_preset(db: Session, user: User, raw: dict[str, Any]) -> SpecimenPreset:
    key = uuid.uuid4()
    preset = _checked(raw, str(key))
    row = SpecimenPreset(
        id=key,
        test=preset.test,
        standard=preset.standard,
        name=preset.name,
        body=preset.model_dump(mode="json"),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _editable(db: Session, preset_id: str) -> SpecimenPreset:
    if specimens.find_builtin(preset_id) is not None:
        raise AppError(
            _BUILTIN,
            "공개 규격은 수정하거나 삭제할 수 없습니다. 사내 규격으로 복사한 뒤 수정하십시오.",
        )
    row = _row(db, preset_id)
    if row is None:
        raise NotFound(_MISSING, f"시험 규격({preset_id})을 찾을 수 없습니다.")
    return row


def update_preset(
    db: Session, user: User, preset_id: str, raw: dict[str, Any]
) -> SpecimenPreset:
    row = _editable(db, preset_id)
    preset = _checked(raw, str(row.id))
    row.test, row.standard, row.name = preset.test, preset.standard, preset.name
    row.body = preset.model_dump(mode="json")
    row.updated_by_id = user.id
    db.commit()
    db.refresh(row)
    return row


def delete_preset(db: Session, preset_id: str) -> None:
    """지운다(행은 남는다). 이 규격으로 만든 작업 · 지그는 그때의 값을 들고 있어 그대로다."""
    row = _editable(db, preset_id)
    row.deleted_at = datetime.now(UTC)
    db.commit()


def build(db: Session, request: SpecimenRequest) -> SpecimenBuildOut:
    preset, _ = find(db, request.preset_id)
    try:
        made = specimens.build(
            preset,
            length=request.length,
            width=request.width,
            thickness=request.thickness,
            dimensions=request.dimensions,
            fixture=request.fixture,
            conditions=request.conditions,
        )
    except ValueError as failure:
        raise AppError(_UNBUILDABLE, str(failure)) from failure
    return SpecimenBuildOut(
        recipe=made.recipe,
        conditions=made.conditions,
        notes=made.notes,
        values=resolve_params(made.recipe),
    )


def create_work(db: Session, user: User, request: SpecimenWorkRequest) -> Work:
    """프리셋으로 **내 작업**을 만든다 — 첫 버전이 시편(과 시험 지그)의 레시피, 해석 조건까지.
    치수가 레시피 변수라 바로 DOE 로 훑는다."""
    preset, _ = find(db, request.preset_id)
    made = build(db, request)
    parts = ["시편"]
    if request.fixture:
        parts.append("시험 지그" if preset.test == "bending" else "그립 자리")
    if made.conditions:
        parts.append("해석 조건")
    work = works.create_work(
        db,
        owner=user,
        name=(request.name or preset.name).strip(),
        description=f"시험 규격 ‘{preset.name}’의 {' · '.join(parts)}",
        recipe=made.recipe,
        source="template",
        note=f"시험 규격 ‘{preset.name}’에서 생성",
        folder=request.folder,
        conditions=made.conditions,
    )
    return works.update_work(
        db,
        work,
        fields={"tags": [f"{TESTS.get(preset.test, preset.test)} 시험", preset.standard]},
    )


def bending_setup(db: Session, preset_id: str) -> dict[str, Any]:
    """굽힘 지그 생성의 규칙 — 프리셋의 배치 규칙(`setup`)을 값으로. 코어는 DB 를 모른다."""
    preset, _ = find(db, preset_id)
    if preset.test != "bending":
        raise AppError(_WRONG_TEST, f"‘{preset.name}’은(는) 굽힘 시험 규격이 아닙니다.")
    return preset.setup.model_dump(mode="json")


# --- 제품 시험 ---------------------------------------------------------------------


def _product(
    db: Session, source: str, user: User
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """`work:<id>` · `part:<id>` → (레시피, 해석 조건, 이름). 내 부품 작업은 주인 · 관리자만,
    공용 부품은 누구나(카탈로그다)."""
    head, _, raw = source.partition(":")
    try:
        key = uuid.UUID(raw)
    except ValueError as failure:
        raise AppError(_BAD_SOURCE, f"제품({source})을 읽을 수 없습니다.") from failure
    if head == "work":
        work = works.get_work(db, key)
        works.require_owner(work, user)
        if work.kind != "part":
            raise AppError(_BAD_SOURCE, "부품 작업에만 시험을 걸 수 있습니다.")
        version = works.current_version(db, work)
        if version is None:
            raise AppError(
                _BAD_SOURCE, "형상이 없습니다. 먼저 모델링하거나 STEP을 업로드하십시오."
            )
        return version.recipe, dict(version.conditions or {}), work.name
    part = parts.get_part(db, key)
    catalog = parts.current_version(db, part)
    if catalog is None:
        raise AppError(_BAD_SOURCE, "이 부품에는 형상이 없습니다.")
    return catalog.recipe, dict(catalog.conditions or {}), part.name


def product_mesh(db: Session, user: User, request: ProductSourceRequest) -> dict[str, Any]:
    """제품의 형상(면 · 엣지 메시와 요약) — 「제품에 적용」 이 3D 에서 면을 고르게. 권한은
    시험을 걸 때와 같다."""
    from app.core.recipe.mesh import mesh
    from app.modules.cad import services as cad

    recipe, _conditions, _label = _product(db, request.source, user)
    cad.require_references(db, recipe, user)
    built = cad.build(recipe)
    return {"summary": built.summary(), "mesh": mesh(built.shape)}


def apply_product_test(db: Session, user: User, request: ProductTestRequest) -> Work:
    """제품에 시험 규격을 건 **새 내 작업** — 제품 레시피 그대로 + 시험 변수 · 하중 자리 ·
    구속 · 하중 · 해석 설정. 만들기 전에 그려 보고 시험 자리(받침면 · 하중 자리 · 끝 면)가
    실제로 풀리는지 본다(안 풀리는 조건을 해석으로 넘기면 저쪽에서야 실패한다)."""
    from app.modules.cad import services as cad

    preset, _ = find(db, request.preset_id)
    if preset.test not in PRODUCT_TESTS:
        raise AppError(
            _WRONG_TEST, f"‘{preset.name}’은(는) 시편 규격입니다. ‘시편 생성’을 사용하십시오."
        )
    recipe, conditions, label = _product(db, request.source, user)
    cad.require_references(db, recipe, user)
    box = cad.build(recipe).summary()["bbox"]
    faces: dict[str, list[FacePick]] = {
        str(slot): [FacePick(one.point, one.normal, one.kind) for one in picks]
        for slot, picks in request.faces.items()
    }
    try:
        made = specimens.product.apply(
            preset,
            recipe,
            conditions,
            bbox=(list(box["min"]), list(box["max"])),
            point=(request.x, request.y, request.z),
            axis=request.axis,
            faces=faces,
            mass=request.mass,
            direction=request.direction,
        )
    except ProductTestError as failure:
        raise AppError(_UNBUILDABLE, str(failure)) from failure
    try:
        built = cad.build(made.recipe)
    except AppError as failure:
        raise AppError(
            _UNBUILDABLE, f"시험을 건 형상을 만들 수 없습니다: {failure.message}"
        ) from failure
    names = [one["name"] for one in topology.bodies(built.shape)]
    try:
        condition_model.parse(made.conditions, names)
    except condition_model.ConditionError as failure:
        raise AppError(_UNBUILDABLE, str(failure)) from failure
    groups = [
        {
            "name": one["name"],
            "select": condition_model.selection_query(
                str(one.get("entity", "face")), one.get("select") or {}
            ),
        }
        for one in made.conditions["named_selections"]
        if one.get("entity", "face") != "body"
    ]
    found, unresolved = topology.regions(built.shape, groups, built.tags)
    ours = [one for one in unresolved if one in specimens.product.NAMES]
    if ours:
        raise AppError(
            _UNBUILDABLE,
            f"시험 자리를 찾지 못했습니다: {', '.join(ours)}. {specimens.product.HINT}",
        )
    for name, (index, at) in made.ends.items():
        # 끝이 둥근 제품이면 「그 방향을 보는 가장 가까운 평면」 이 안쪽의 엉뚱한 면이다.
        rows = found.get(name) or []
        if any(abs(float(row["centroid"][index]) - at) > 1.0 for row in rows):
            raise AppError(
                _UNBUILDABLE,
                f"‘{name}’: 제품의 끝에 평면이 없습니다(끝이 둥근 제품). 고정할 끝과 비트는 "
                "끝의 면을 3D에서 고르십시오.",
            )
    work = works.create_work(
        db,
        owner=user,
        name=(request.name or f"{label} — {preset.name}").strip()[:120],
        description=" ".join(
            [f"‘{label}’에 시험 규격 ‘{preset.name}’을(를) 적용했습니다.", *made.notes]
        ),
        recipe=made.recipe,
        source="copy",
        note=f"시험 규격 ‘{preset.name}’ 적용",
        folder=request.folder,
        conditions=made.conditions,
    )
    return works.update_work(
        db,
        work,
        fields={"tags": [f"{TESTS.get(preset.test, preset.test)} 시험", preset.standard]},
    )
