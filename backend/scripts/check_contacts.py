"""저장된 접촉 중 **면 그룹이 잘못 걸린 것**을 찾는다 — 읽기만 한다.

    .venv/bin/python scripts/check_contacts.py          작업 · 부품 · 지그 · DOE 의 조건 전부
    .venv/bin/python scripts/check_contacts.py --doe    DOE 스터디만(다시 낼 스터디 고르기)
    .venv/bin/python scripts/check_contacts.py --all    하중으로 닿을 수 있는 접촉(마찰 …)의
                                                       「처음에 떨어져 있음」 도

접촉 자동 찾기(해석 조건 화면의 「미정의 접촉을 본딩으로 생성」, v0.26.0 부터)는 면의
**중심**으로 면 규칙을 지었다. 중심이 구멍 속인 면(볼트 구멍 난 판 · 고리)과 딴 바디의 면과
자리가 같은 면(판 구멍 ↔ 볼트 몸통)은 그 규칙이 딴 면을 집었다 — 저장소의 볼트 예압 픽스처로
v0.26.0 ~ v0.30.1 은 본딩 셋 중 둘, v0.31.0 은 셋 다(v0.31.1 에서 고침). **이미 저장된 규칙은
다시 내보내도 그대로다.** 그런 접촉을 여기서 찾는다.

- 같은 면 — 접촉면 · 대상면 그룹이 같은 면을 집는다(한쪽이 딴 바디의 같은 자리 면을 가리킨다).
  두 바디는 안 묶인다.
- 맞닿지 않음 — 두 면 묶음이 겹친 넓이가 0 이다. 본딩 · 분리 없음이면 받는 쪽이 못 묶는다.

찾은 것은 해석 조건 화면에서 그 접촉의 두 선택 그룹을 다시 고르면 된다. v0.31.1 부터는 조건
화면의 접촉 점검과 DOE 점 파일의 경고(`quality.warnings` · `quality.misplaced_contacts`)도 같은
것을 말한다.

**DOE 스터디는 조건의 스냅샷이다** — 「재생성」 은 그 스냅샷으로 다시 만들므로 같은 규칙이
나간다. 작업의 조건을 고친 뒤 그 스터디의 「설정 변경 후 새 DOE 생성」 으로 새 스터디를
만든다(새 스터디 id). DOE 줄의 「만듦 · 보냄」 은 그 스터디를 만든 날 · 공유 폴더로 보낸 날이다
— 다시 낼 대상을 고를 때 쓴다(`--doe`). 판정은 스터디의 기본 형상(도면의 기본 치수)으로 한다 —
설계점마다 형상이 다르면 v0.31.1 이 낸 점 파일의 판정이 점마다 말한다.

재는 법은 조건 화면과 같다(`contact_check.misplaced`) — 저장된 레시피로 형상을 다시 만들므로
조건이 많으면 몇 분 걸린다. 바디 그룹 · 못 푼 그룹은 건너뛴다.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

import app.all_models  # noqa: F401  (관계 매핑)
from app.core import contact_check
from app.core.recipe import follow
from app.core.recipe import params as recipe_params
from app.database import SessionLocal
from app.modules.cad.services import build
from app.modules.doe.models import DoeStudy
from app.modules.jigs.models import Jig, JigVersion
from app.modules.parts.models import Part, PartVersion
from app.modules.works.models import Work, WorkVersion

Saved = tuple[str, dict[str, Any], dict[str, Any]]


def _saved(db: Any, only_doe: bool = False) -> Iterator[Saved]:
    """(어디 · 레시피 · 조건) — 접촉이 있는 것만."""
    rows: list[tuple[str, Any]] = [
        ("작업", select(Work.name, Work.id, WorkVersion)),
        ("부품", select(Part.name, Part.id, PartVersion)),
        ("지그", select(Jig.name, Jig.id, JigVersion)),
    ]
    if only_doe:
        rows = []
    joins = {
        "작업": (WorkVersion, Work.id == WorkVersion.work_id),
        "부품": (PartVersion, Part.id == PartVersion.part_id),
        "지그": (JigVersion, Jig.id == JigVersion.jig_id),
    }
    for kind, query in rows:
        model, on = joins[kind]
        for name, owner, version in db.execute(query.join(model, on)).all():
            if version.recipe and (version.conditions or {}).get("contacts"):
                where = f"{kind} ‘{name}’ v{version.number} ({owner})"
                yield where, version.recipe, version.conditions
    for study in db.scalars(select(DoeStudy).order_by(DoeStudy.created_at)):
        if study.recipe and (study.conditions or {}).get("contacts"):
            when = f"만듦 {study.created_at:%Y-%m-%d}"
            if study.exported_at is not None:
                when += f" · 보냄 {study.exported_at:%Y-%m-%d}"
            yield f"DOE ‘{study.name}’ ({study.id}, {when})", study.recipe, study.conditions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="마찰 · 마찰 없음 · 거침 접촉도(처음에 떨어져도 될 수 있다)",
    )
    parser.add_argument(
        "--doe", action="store_true", help="DOE 스터디만(다시 낼 스터디 고르기)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    checked = contacts = failed = 0
    found: list[str] = []
    try:
        for where, recipe, conditions in _saved(db, args.doe):
            checked += 1
            try:
                made = build(recipe)
            except Exception as failure:
                failed += 1
                print(f"건너뜀 {where}: 형상을 만들지 못함 — {str(failure)[:120]}")
                continue
            selections = [
                one
                for one in conditions.get("named_selections") or []
                if isinstance(one, dict)
            ]
            with contextlib.suppress(Exception):
                selections = follow.resolved(
                    selections,
                    recipe_params.resolve_params({"params": recipe.get("params") or {}}),
                )
            declared = [
                one for one in conditions.get("contacts") or [] if isinstance(one, dict)
            ]
            contacts += len(declared)
            for one in contact_check.misplaced(made.shape, declared, selections, made.tags):
                if not args.all and contact_check.misplaced_level(one) != "warn":
                    continue
                problem = "같은 면" if one["problem"] == "same_face" else "맞닿지 않음"
                found.append(
                    f"{where} · 접촉 ‘{one.get('name', '')}’({one.get('type', '')}) "
                    f"{problem}: ‘{one.get('source', '')}’ ↔ ‘{one.get('target', '')}’"
                )
    finally:
        db.rollback()
        db.close()

    print(f"\n조건 {checked}벌 · 접촉 {contacts}개를 봤습니다(형상을 못 만든 것 {failed}벌).")
    if not found:
        print("면 그룹이 잘못 걸린 접촉이 없습니다.")
        return 0
    print(
        f"면 그룹이 잘못 걸린 접촉 {len(found)}개 — "
        "해석 조건 화면에서 두 선택 그룹을 다시 고르십시오:"
    )
    for line in found:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
