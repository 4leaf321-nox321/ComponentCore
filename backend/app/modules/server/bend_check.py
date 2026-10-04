"""판금 굽힘 점검 — 2026-10-04 의 고침으로 **모양이 바뀌거나 이제 만들어지지 않는** 판금을
찾는다.

판금 절곡(`sheet_metal`)에서 두께가 굽힘 안쪽에 붙는 굽힘은 안쪽 반지름이 r - t 로 지어지고
있었다(문서의 약속은 「안쪽 반지름 r」). 고친 뒤에는 r 이라, 그렇게 그린 판은 다시 평가하면
굽힘 안쪽이 커진다 — 바깥 치수(꺾은선)는 그대로. 짧은 구간 사이의 굽힘은 반지름 + 두께가
들어가지 않아 **이제 실패**할 수도 있다.

훑는 것: 내 작업(지운 것 제외)의 현재 버전, 공용 부품 · 지그의 현재 버전, 템플릿, DOE
스냅샷(재생성하면 처음 내보낸 것과 다른 형상이 된다). 지그 버전은 2026-10-04 부터 레시피를
든다(「내 작업 공간으로 복사」 가 그것을 다시 평가한다). 생성기로 만든 이전 버전은 레시피가
없어 건너뛴다.
형상은 바뀐 판금 노드 하나만 지어 본다 — 도면 전체를 다시 만들지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Text, and_, cast, select
from sqlalchemy.orm import Session

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe import schema as S
from app.core.recipe.evaluate import inside_bends
from app.core.recipe.params import resolve
from app.core.recipe.schema import RecipeValidationError
from app.modules.accounts.models import User
from app.modules.doe.models import DoeStudy
from app.modules.jigs.models import Jig, JigVersion
from app.modules.parts.models import Part, PartVersion
from app.modules.templates.models import RecipeTemplate
from app.modules.works.models import Work, WorkVersion

#: 한 번에 지어 볼 판금 노드의 상한 — 요청 하나가 서버를 오래 붙잡지 않게.
LIMIT = 300


def _has_sheet(column: Any) -> Any:
    return cast(column, Text).like('%"sheet_metal"%')


def _rows(db: Session) -> Iterator[tuple[str, Any, str, Any, int | None, dict[str, Any]]]:
    """(종류, id, 이름, 주인 id, 버전, 레시피) — 판금이 든 것만."""
    works = db.execute(
        select(Work.id, Work.name, Work.owner_id, WorkVersion.number, WorkVersion.recipe)
        .join(
            WorkVersion,
            and_(WorkVersion.work_id == Work.id, WorkVersion.number == Work.current_version),
        )
        .where(Work.deleted_at.is_(None), _has_sheet(WorkVersion.recipe))
    )
    for one in works:
        yield "work", one.id, one.name, one.owner_id, one.number, one.recipe
    parts = db.execute(
        select(Part.id, Part.name, Part.owner_id, PartVersion.number, PartVersion.recipe)
        .join(
            PartVersion,
            and_(PartVersion.part_id == Part.id, PartVersion.number == Part.current_version),
        )
        .where(Part.deleted_at.is_(None), _has_sheet(PartVersion.recipe))
    )
    for one in parts:
        yield "part", one.id, one.name, one.owner_id, one.number, one.recipe
    jigs = db.execute(
        select(Jig.id, Jig.name, Jig.owner_id, JigVersion.number, JigVersion.recipe)
        .join(
            JigVersion,
            and_(JigVersion.jig_id == Jig.id, JigVersion.number == Jig.current_version),
        )
        .where(Jig.deleted_at.is_(None), _has_sheet(JigVersion.recipe))
    )
    for one in jigs:
        yield "jig", one.id, one.name, one.owner_id, one.number, one.recipe
    for template in db.scalars(
        select(RecipeTemplate).where(_has_sheet(RecipeTemplate.recipe))
    ):
        yield "template", template.id, template.name, template.owner_id, None, template.recipe
    for study in db.scalars(select(DoeStudy).where(_has_sheet(DoeStudy.recipe))):
        yield "doe", study.id, study.name, study.owner_id, None, study.recipe


def _try(recipe: dict[str, Any], node: dict[str, Any]) -> str:
    """그 판금 노드 하나만 지어 본다 — 비면 된 것, 아니면 까닭."""
    try:
        evaluate(parse({"params": recipe.get("params") or {}, "nodes": [node]}))
    except (RecipeError, RecipeValidationError, ValueError) as failure:
        return str(failure)[:200]
    return ""


def check(db: Session) -> dict[str, Any]:
    """바뀐 판금 노드마다 한 줄 — `status` 는 `changed`(모양만 바뀜) · `failing`(이제 실패)."""
    names = {one.id: one.display_name for one in db.scalars(select(User))}
    items: list[dict[str, Any]] = []
    built = 0
    truncated = False
    scanned = 0
    for kind, ident, name, owner, number, recipe in _rows(db):
        scanned += 1
        for raw in (recipe or {}).get("nodes") or []:
            if not isinstance(raw, dict) or raw.get("op") != "sheet_metal":
                continue
            try:
                # 두께 · 꺾은선의 `=식` 을 그 도면의 변수로 풀어서 본다.
                solved = resolve(
                    {"params": (recipe or {}).get("params") or {}, "nodes": [raw]}
                )
                node = S.SheetMetalNode.model_validate(solved["nodes"][0])
            except Exception:
                continue  # 풀리지 않는 노드 — 그 도면은 이 고침과 상관없이 실패한다
            bends = inside_bends(node)
            if bends == 0:
                continue
            if built >= LIMIT:
                truncated = True
                break
            built += 1
            error = _try(recipe, raw)
            items.append(
                {
                    "kind": kind,
                    "id": str(ident),
                    "name": name,
                    "owner": names.get(owner, ""),
                    "version": number,
                    "node": str(raw.get("id", "")),
                    "bends": bends,
                    "status": "failing" if error else "changed",
                    "error": error,
                }
            )
    return {
        "scanned": scanned,
        "items": items,
        "failing": sum(1 for one in items if one["status"] == "failing"),
        "truncated": truncated,
    }
