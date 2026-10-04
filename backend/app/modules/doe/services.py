"""DOE — 설계점을 만들고, 형상마다 STEP 을 공유 폴더에 쓴다.

표에는 **바꾼 변수와 파일 이름만** 적는다. 질량 · 크기 같은 값도, 해석 결과도 여기 담지 않는다
— **결과는 해석 플랫폼이 들고 거기서 본다**(2026-09-23 결정, `docs/해석-조건-설계.md` 0장).
이 플랫폼이 하는 일은 형상 · 영역 · 조건 · 설계점을 만들어 **자기 설명적인 폴더 하나**로
넘기는 것까지다.

**실패한 점에서 멈추지 않는다.** 얇은 두께에서 형상이 깨지는 것은 흔한 일이고, 거기서 멈추면
48 개짜리 표가 12 개에서 끊긴다. 실패는 그 점의 줄에 이유를 적고 다음으로 간다.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from collections import Counter, OrderedDict
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import exists, func, literal, or_, select
from sqlalchemy.orm import Session, object_session
from sqlalchemy.sql import ColumnElement

from app.config import get_settings
from app.core import conditions as condition_model
from app.core import doe as engine
from app.core import export as shapes
from app.core import frames
from app.core import measures as measuring
from app.core import quality as checking
from app.core.recipe import RecipeError, evaluate, follow, params, parse, topology
from app.core.recipe.mesh import mesh
from app.core.recipe.schema import RecipeValidationError
from app.modules.accounts.models import User
from app.modules.cad import services as cad
from app.modules.cad.services import resolve_component, resolve_import
from app.modules.doe import export as files
from app.modules.doe.models import DoePoint, DoeStudy
from app.modules.jobs import registry
from app.modules.jobs import services as jobs
from app.modules.jobs.models import Job
from app.modules.server import settings_store
from app.modules.works.models import Work
from app.shared import filestore, search
from app.shared.errors import AppError, Forbidden, NotFound, code

JOB_KIND = "doe"


def _settings_root() -> Path:
    return Path(get_settings().doe_export_root)


def check_root() -> Path:
    """공유 폴더가 쓸 수 있는가. **미리 본다** — 48 점을 다 만들고 나서 못 쓰면 늦다."""
    root = _settings_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".compcore-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as failure:
        raise AppError(
            code("DOE", 1),
            f"공유 폴더에 쓸 수 없습니다: {files.windows_path(root)} ({failure.strerror})",
        ) from failure
    return root


def _table_factors(
    factors_raw: list[dict[str, Any]], table: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """**표의 열**에서 인자 정의를 세운다 — 표가 값을 주는 변수는 그 표의 값 목록(`list`)으로.

    정의를 표에 맞춰 두는 까닭: 결과 화면 · README · 「바꾼 변수」 열이 인자 정의를 읽는다.
    표에만 있고 정의에 없는 변수는 더한다(MCP 가 표만 줘도 되게). 재료 · 고르기 · 배율 인자는
    후보를 정의가 들고 있으므로 그대로 둔다."""
    if not isinstance(table, list) or not table:
        raise AppError(code("DOE", 25), "표가 비어 있습니다. 설계점을 1행 이상 입력하십시오.")
    columns: list[str] = []
    for number, row in enumerate(table, start=1):
        if not isinstance(row, dict):
            raise AppError(code("DOE", 25), f"표 {number}행: 이름과 값의 쌍이어야 합니다.")
        for key in row:
            if str(key) not in columns:
                columns.append(str(key))

    def distinct(name: str) -> list[float]:
        values: set[float] = set()
        for number, row in enumerate(table, start=1):
            if name not in row or row[name] in (None, ""):
                continue
            try:
                values.add(float(row[name]))
            except (TypeError, ValueError) as failure:
                raise AppError(
                    code("DOE", 25),
                    f"표 {number}행: ‘{name}’ 값이 숫자가 아닙니다({row[name]!r}).",
                ) from failure
        return sorted(values)

    given = {str(one.get("name")) for one in factors_raw}
    out: list[dict[str, Any]] = []
    for one in factors_raw:
        name = str(one.get("name"))
        if name in columns and one.get("mode") not in engine.NON_SHAPE:
            # 표의 값은 가공 단위로 맞추지 않는다 — 정의도 그 값 그대로(1e-6 까지).
            out.append({**one, "mode": "list", "values": distinct(name), "resolution": 1e-6})
        else:
            out.append(one)
    for name in columns:
        if name not in given:
            out.append(
                {"name": name, "mode": "list", "values": distinct(name), "resolution": 1e-6}
            )
    return out


def _samples(db: Session, raw: dict[str, Any]) -> int:
    """LHS 표본 수 — 상한은 관리자 설정. 넘으면 이유와 상한을 말한다."""
    if raw.get("method") == "table":
        return len(raw.get("table") or [])
    samples = int(raw.get("samples") or 20)
    if raw.get("method", "factorial") in ("lhs", "sobol"):
        limit = settings_store.doe_max_samples(db)
        if samples > limit:
            raise AppError(
                code("DOE", 14),
                f"LHS 표본 수({samples})가 상한({limit})을 초과합니다. 상한은 관리자가 서버 "
                "설정에서 변경할 수 있습니다.",
            )
    return samples


def preview(db: Session, raw: dict[str, Any]) -> dict[str, Any]:
    """만들기 전에 **몇 개인지** 와 그 표. 격자는 곱으로 늘어난다.

    제약식이 있으면 거른 뒤의 수다 — 몇 개가 어느 제약에 걸렸는지도 함께(`rejected` ·
    `hits`). 표는 다 준다(상한 안이다) — 화면이 흩뿌림으로 그린다."""
    if raw.get("method") == "table":
        raw = {**raw, "factors": _table_factors(raw.get("factors") or [], raw.get("table"))}
    found = _plan(db, raw)
    factors = _factors(raw.get("factors") or [])
    return {
        "count": found.kept,
        "requested": found.requested,
        "max": settings_store.doe_max_points(db),
        "max_samples": settings_store.doe_max_samples(db),
        "too_many": found.too_many,
        "points": found.rows,
        "varying": [f.name for f in factors if f.varying],
        "rejected": found.rejected,
        "candidates": found.candidates,
        "hits": found.hits,
        "shortfall": found.shortfall,
        "rejected_points": found.rejected_rows,
    }


def _constraint_check(
    recipe: dict[str, Any] | None, factors: list[dict[str, Any]], constraints: list[str]
) -> engine.Check | None:
    """제약식을 **미리 읽어 보고** 설계점 한 줄을 판정하는 함수로 만든다.

    식은 도면의 치수 전체(이 점의 값을 덮어 푼 것)로 푼다 — `판_폭 = 길이 / 2` 처럼 다른
    치수에서 나온 값도 부를 수 있어야 한다. 재료 · 고르기 · 배율 인자는 수가 아니라 못 쓴다.
    한 줄에서 식이 풀리지 않으면(0 으로 나눔 등) 그 제약에 걸린 것으로 본다 — 만들어 봐야
    알 수 없는 점을 내보내지 않는다."""
    if not constraints:
        return None
    base = dict((recipe or {}).get("params") or {})
    other = {str(one.get("name")) for one in factors if one.get("mode") in engine.NON_SHAPE}
    try:
        known = set(params.resolve_params({"params": base})) | {
            str(one.get("name")) for one in factors if one.get("mode") not in engine.NON_SHAPE
        }
    except params.ExpressionError as failure:
        raise AppError(
            code("DOE", 23), f"도면의 치수를 계산하지 못했습니다: {failure}"
        ) from failure
    for index, text in enumerate(constraints, start=1):
        names = params.names_in(text)
        clash = sorted(names & other)
        if clash:
            raise AppError(
                code("DOE", 23),
                f"제약 {index} ‘{text}’: 재료, 선택, 배율 인자({', '.join(clash)})는 식에 "
                "사용할 수 없습니다.",
            )
        unknown = sorted(names - known)
        if unknown:
            raise AppError(
                code("DOE", 23),
                f"제약 {index} ‘{text}’: 알 수 없는 이름({', '.join(unknown)})입니다. "
                f"사용 가능한 변수: {', '.join(sorted(known)) or '(없음)'}",
            )
        try:
            params.evaluate_condition(text, {name: 1.0 for name in known})
        except params.ExpressionError as failure:
            raise AppError(code("DOE", 23), f"제약 {index}: {failure}") from failure
        except (ArithmeticError, ValueError):
            pass  # 시험값 1 로 0 을 나눈 것뿐 — 실제 값으로는 풀릴 수 있다.

    def check(row: dict[str, float | str]) -> list[int]:
        try:
            values = params.resolve_params(
                {"params": {**base, **engine.shape_values(row, factors)}}
            )
        except (params.ExpressionError, ArithmeticError, ValueError):
            return list(range(len(constraints)))
        failed = []
        for index, text in enumerate(constraints):
            try:
                if not params.evaluate_condition(text, values):
                    failed.append(index)
            except (params.ExpressionError, ArithmeticError, ValueError):
                failed.append(index)
        return failed

    return check


#: 고를 수 있는 방식 — `core/doe.Method` 와 같다.
METHODS = ("factorial", "lhs", "table", "oat", "ccd", "bbd", "sobol")


def _plan(db: Session, raw: dict[str, Any]) -> engine.Plan:
    """요청 한 벌 → 제약을 거친 설계점 표."""
    method = raw.get("method", "factorial")
    if method not in METHODS:
        raise AppError(
            code("DOE", 2),
            f"알 수 없는 방식({method})입니다. 사용 가능한 방식: {', '.join(METHODS)}",
        )
    factors_raw = raw.get("factors") or []
    factors = _factors(factors_raw)
    try:
        constraints = engine.parse_constraints(raw.get("constraints"))
    except engine.DoeError as failure:
        raise AppError(code("DOE", 23), str(failure)) from failure
    check = _constraint_check(raw.get("recipe"), factors_raw, constraints)
    try:
        return engine.plan(
            factors,
            method=raw.get("method", "factorial"),
            samples=_samples(db, raw),
            seed=int(raw.get("seed") or 1),
            limit=settings_store.doe_max_points(db),
            check=check,
            constraints=len(constraints),
            table=raw.get("table"),
            offset=int(raw.get("offset") or 0),
        )
    except engine.DoeError as failure:
        raise AppError(code("DOE", 3), str(failure)) from failure


def _factors(raw: list[dict[str, Any]]) -> list[engine.Factor]:
    try:
        return engine.parse_factors(raw)
    except engine.DoeError as failure:
        raise AppError(code("DOE", 2), str(failure)) from failure


def _points(db: Session, raw: dict[str, Any]) -> list[dict[str, float | str]]:
    found = _plan(db, raw)
    limit = settings_store.doe_max_points(db)
    if found.too_many:
        raise AppError(
            code("DOE", 3),
            f"설계점이 {len(found.rows) or found.requested}개입니다. "
            f"한 번에 최대 {limit}개까지 생성할 수 있습니다. 단계 수를 줄이거나 인자를 "
            "제외하거나, LHS로 표본 수를 지정하십시오.",
        )
    if raw.get("method") == "table" and found.rejected:
        # 표는 사람(또는 최적화기)이 고른 점이다 — 말없이 빼면 번호가 표의 줄과 어긋난다.
        raise AppError(
            code("DOE", 23),
            f"표의 {found.rejected}개 행이 제약을 위반합니다. 미리보기에서 해당 행을 "
            "확인한 후 표에서 제외하거나 제약을 수정하십시오.",
        )
    if not found.rows:
        raise AppError(
            code("DOE", 23),
            f"제약을 만족하는 설계점이 하나도 없습니다. 후보 {found.candidates}개가 모두 "
            "제약을 위반합니다. 제약 또는 범위를 수정하십시오.",
        )
    return found.rows


def _work_conditions(db: Session, work_id: uuid.UUID, owner: User) -> dict[str, Any]:
    """그 작업 **현재 버전의 해석 조건**. 남의 작업이면 거절한다 — 조건에는 물성 · 하중처럼
    그 사람의 것이 들어 있다."""
    from app.modules.works import services as works
    from app.modules.works.models import WorkVersion

    work = works.get_work(db, work_id)
    works.require_owner(work, owner)
    if not work.current_version:
        return {}
    version = db.scalar(
        select(WorkVersion).where(
            WorkVersion.work_id == work.id, WorkVersion.number == work.current_version
        )
    )
    return dict(version.conditions or {}) if version is not None else {}


def _check_condition_factors(
    recipe: dict[str, Any], conditions: dict[str, Any], factors: list[dict[str, Any]]
) -> None:
    """고르기 · 배율 인자와 조건의 식을 **만들기 전에** 본다.

    - 조건의 식이 부르는 이름이 도면 변수에 있나 — 없으면 모든 점이 같은 까닭으로 실패한다.
    - 고르기: 값마다 바꿔 끼운 한 벌이 조건으로서 온전한가(마찰로 바꾸면 마찰계수가 있나 …).
    - 배율: 바디에 재료가 붙어 있고 그 재료에 그 물성이 있나."""
    params = recipe.get("params") or {}
    bodies = _body_names(recipe)
    frame_names = frames.recipe_frame_names(recipe)
    if conditions:
        try:
            condition_model.resolve(conditions, params)
        except condition_model.ConditionError as failure:
            raise AppError(code("DOE", 15), f"해석 조건: {failure}") from failure
    for one in engine.non_shape_factors(factors, "choice"):
        name = str(one.get("name"))
        if not conditions:
            raise AppError(code("DOE", 22), f"선택 인자 ‘{name}’: 해석 조건이 없습니다.")
        for value in one.get("values") or []:
            try:
                condition_model.parse(
                    condition_model.with_choice(conditions, one["target"], value),
                    bodies,
                    frame_names,
                )
            except condition_model.ConditionError as failure:
                raise AppError(
                    code("DOE", 22), f"선택 인자 ‘{name}’ = {value!r}: {failure}"
                ) from failure
    scales = engine.non_shape_factors(factors, "scale")
    if not scales:
        return
    from app.shared.clients import matnexus as _matnexus

    keys = _matnexus.property_keys()
    # **내보낼 때와 같은 함수로 본다**(`with_scale`) — 따로 셈하면 「검사는 통과, 내보내기는
    # 실패」 가 생긴다. 재료 인자가 같은 바디를 훑으면 후보 재료마다 한 번씩.
    swaps = engine.non_shape_factors(factors, "material")
    for one in scales:
        name = str(one.get("name"))
        targets = [str(b) for b in one.get("bodies") or []]
        if not conditions:
            raise AppError(code("DOE", 22), f"배율 인자 ‘{name}’: 해석 조건(재료)이 없습니다.")
        missing = [
            b
            for b in targets
            if bodies is not None and b not in bodies and b != condition_model.ALL_BODIES
        ]
        if missing:
            raise AppError(
                code("DOE", 22),
                f"배율 인자 ‘{name}’: 도면에 없는 바디({', '.join(missing)})입니다.",
            )
        variants: list[tuple[str, dict[str, Any]]] = [("", conditions)]
        for swap in swaps:
            if set(swap.get("bodies") or []) & set(targets):
                variants = [
                    (
                        f" (재료 {choice})",
                        condition_model.with_material(
                            base_conditions, list(swap.get("bodies") or []), str(choice)
                        ),
                    )
                    for label, base_conditions in variants
                    for choice in swap.get("values") or []
                ]
        for label, variant in variants:
            try:
                resolved = condition_model.resolve(variant, params, keys)
                if not any(
                    set(m.get("apply_to") or [])
                    & (set(targets) | {condition_model.ALL_BODIES})
                    for m in resolved.get("materials") or []
                ):
                    raise condition_model.ConditionError(
                        f"{', '.join(targets)}에 지정된 재료가 없습니다."
                    )
                condition_model.with_scale(resolved, targets, str(one.get("property")), 1.5)
            except condition_model.ConditionError as failure:
                raise AppError(
                    code("DOE", 22), f"배율 인자 ‘{name}’{label}: {failure}"
                ) from failure


def _check_material_factors(
    recipe: dict[str, Any], conditions: dict[str, Any], factors: list[dict[str, Any]]
) -> None:
    """재료 인자를 **만들기 전에** 본다 — 후보가 조건에 담겨 있나, 바디가 도면에 있나, 바꿔
    끼운 한 벌이 조건으로서 온전한가. 설계점 마흔 개를 만든 뒤에 알면 폴더에 반쪽이 남는다."""
    if not (conditions or {}).get("materials"):
        raise AppError(
            code("DOE", 22),
            "재료 인자는 해석 조건에 등록된 재료 중에서 선택합니다. "
            "현재 조건에 재료가 없습니다.",
        )
    params = recipe.get("params") or {}
    bodies = _body_names(recipe)
    for one in factors:
        if one.get("mode") != "material":
            continue
        name = str(one.get("name"))
        if name in params:
            raise AppError(
                code("DOE", 22), f"재료 인자 ‘{name}’: 도면의 치수 이름과 중복됩니다."
            )
        targets = [str(b) for b in one.get("bodies") or []]
        missing = [b for b in targets if bodies is not None and b not in bodies]
        if missing:
            raise AppError(
                code("DOE", 22),
                f"재료 인자 ‘{name}’: 도면에 없는 바디({', '.join(missing)})입니다. "
                f"사용 가능한 바디: {', '.join(bodies or []) or '없음'}",
            )
        for choice in one.get("values") or []:
            try:
                condition_model.parse(
                    condition_model.with_material(conditions, targets, str(choice)),
                    bodies,
                    frames.recipe_frame_names(recipe),
                )
            except condition_model.ConditionError as failure:
                raise AppError(code("DOE", 22), f"재료 인자 ‘{name}’: {failure}") from failure


def _body_names(recipe: dict[str, Any]) -> list[str] | None:
    """이 도면의 바디 이름들. **못 만들면 None** — 그때는 바디 검사를 건너뛴다(도면이
    깨진 것은 다른 오류가 이미 말한다)."""
    try:
        return [str(one["name"]) for one in topology.bodies(cad.build(recipe).shape)]
    except Exception:
        return None


def _request_digest(
    *,
    recipe: dict[str, Any],
    factors: list[dict[str, Any]],
    method: str,
    samples: int,
    seed: int,
    conditions: dict[str, Any] | None,
    work_id: uuid.UUID | None,
    constraints: list[str] | None = None,
    checks: dict[str, Any] | None = None,
    table: list[dict[str, Any]] | None = None,
    measures: list[dict[str, Any]] | None = None,
    outputs: list[str] | None = None,
) -> str:
    """이 요청이 **무엇을 만들라는 것인가**의 지문. 멱등 열쇠가 같은데 이것이 다르면 사고다.

    열쇠만 보고 돌려주면, 열쇠를 재사용한 다른 요청이 **엉뚱한 스터디를 받아 간다** — 기계는
    그것을 제가 방금 시킨 것으로 믿는다. 그래서 지문을 맞춰 보고 다르면 거절한다."""
    payload = {
        "recipe": recipe,
        "factors": factors,
        "method": method,
        "samples": samples,
        "seed": seed,
        "conditions": conditions or {},
        "work_id": str(work_id) if work_id else None,
    }
    # 더한 칸은 **있을 때만** 넣는다 — 예전 요청의 지문이 그대로여야 재시도가 이어진다.
    if constraints:
        payload["constraints"] = constraints
    if checks:
        payload["checks"] = checks
    if table:
        payload["table"] = table
    if measures:
        payload["measures"] = measures
    if outputs:
        payload["outputs"] = sorted(set(outputs))
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def digest_of(study: DoeStudy) -> str:
    """이미 있는 스터디에서 같은 지문을 다시 뽑는다 — 칸을 하나 더 두지 않으려고."""
    return _request_digest(
        recipe=study.recipe,
        factors=study.factors,
        method=study.method,
        samples=study.samples,
        seed=study.seed,
        conditions=study.conditions,
        work_id=study.work_id,
        constraints=list(study.constraints or []),
        checks=dict(study.checks or {}),
        table=_table_of(study),
        measures=list(study.measures or []),
        outputs=list(study.outputs or []),
    )


def _normal_table(
    factors: list[dict[str, Any]], table: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """표를 한 모양으로 — 바꾸는 변수만, 수는 수로(CSV 는 글자로 온다). 멱등 지문이 설계점에서
    되짚은 표(`_table_of`)와 같아야 재시도가 이어진다."""
    try:
        parsed = engine.table_points(engine.parse_factors(factors), table)
    except engine.DoeError as failure:
        raise AppError(code("DOE", 25), str(failure)) from failure
    names = [str(one["name"]) for one in factors if one.get("mode") != "fixed"]
    return [{name: row[name] for name in names} for row in parsed]


def _table_of(study: DoeStudy) -> list[dict[str, Any]] | None:
    """표로 만든 스터디의 **처음 표** — 설계점에서 되짚는다(더한 묶음은 빼고)."""
    if study.method != "table":
        return None
    first = int(study.samples or 0)
    names = [
        str(one["name"])
        for one in study.factors
        if one.get("mode") != "fixed" and one.get("name") is not None
    ]
    db = object_session(study)
    if db is None:
        return None
    rows = [
        {name: point.params.get(name) for name in names}
        for point in points(db, study)
        if point.number <= first
    ]
    return rows or None


def _check_factor_names(recipe: dict[str, Any], factors: list[dict[str, Any]]) -> None:
    """치수 인자는 도면에 있어야 하고, 재료 · 고르기 · 배율 인자는 도면 치수와 이름이 겹치면
    안 된다."""
    names = recipe.get("params") or {}
    # 재료 · 고르기 · 배율 인자는 치수가 아니다 — 레시피에 없는 것이 맞다.
    other = {str(one.get("name")) for one in factors if one.get("mode") in engine.NON_SHAPE}
    clash = sorted(other & set(names))
    if clash:
        raise AppError(
            code("DOE", 22), f"인자 이름이 도면의 치수 이름과 중복됩니다: {', '.join(clash)}"
        )
    unknown = [one["name"] for one in factors if one.get("name") not in set(names) | other]
    if unknown:
        known = ", ".join(sorted(names)) or "(없음)"
        raise AppError(
            code("DOE", 5),
            f"레시피에 없는 치수({', '.join(unknown)})입니다. 사용 가능한 치수: {known}",
        )


#: 「미리 만들어 보기」 가 쓰는 시간의 상한(초). 넘으면 남은 점은 건너뛴다 — 요청 하나가 서버를
#: 오래 잡지 않게. 그래도 무엇을 못 봤는지는 점마다 말한다.
PROBE_SECONDS = 90.0


def probe(db: Session, owner: User, raw: dict[str, Any]) -> dict[str, Any]:
    """**만들기 전에 몇 점만 먼저 만들어 본다** — 범위의 끝(모두 최소 · 모두 최대 · 인자마다
    혼자 최소 · 최대)과 가운데.

    설계점 200개를 한참 돌린 뒤에야 「절반이 깨졌다」 · 「고정면이 딴 면을 집었다」 를 아는
    일을 막는다. 만들기 작업과 **같은 길**(`_shape_point`)로 만들고, 점마다 실패 사유 · 못 푼
    영역 · 어긋남(drift) · 겹침 · 걸린 시간을 돌려준다. 걸린 시간의 평균으로 화면이 전체 시간을
    가늠한다. 파일은 쓰지 않는다."""
    recipe = raw.get("recipe") or {}
    factors_raw = raw.get("factors") or []
    try:
        parse(recipe)
    except RecipeValidationError as failure:
        raise AppError(
            code("DOE", 4),
            "레시피가 올바르지 않습니다.",
            details={"problems": failure.problems},
        ) from failure
    if raw.get("method") == "table":
        # 표의 열이 바꿀 변수다 — 끝 점은 표의 값들 중 가장 작은 · 큰 것으로 고른다.
        factors_raw = _table_factors(factors_raw, raw.get("table"))
    _check_factor_names(recipe, factors_raw)
    factors = _factors(factors_raw)
    try:
        constraints = engine.parse_constraints(raw.get("constraints"))
    except engine.DoeError as failure:
        raise AppError(code("DOE", 23), str(failure)) from failure
    check = _constraint_check(recipe, factors_raw, constraints)
    conditions = raw.get("conditions")
    if conditions is None:
        work_id = raw.get("work_id")
        conditions = _work_conditions(db, uuid.UUID(str(work_id)), owner) if work_id else {}
    try:
        limits = checking.thresholds(raw.get("checks"))
    except checking.QualityError as failure:
        raise AppError(code("DOE", 24), str(failure)) from failure
    started = time.perf_counter()
    definitions, base_values, tracks = _tracking(recipe, conditions, factors_raw)
    limits, reference = _checking(recipe, raw.get("checks"))
    measure_list = _measures(raw.get("measures"), recipe, conditions, factors_raw)
    setup_ms = int((time.perf_counter() - started) * 1000)
    out: list[dict[str, Any]] = []
    for label, row in engine.probe_points(factors):
        entry: dict[str, Any] = {"label": label, "params": row}
        failed = check(row) if check else []
        if failed:
            out.append(
                {
                    **entry,
                    "status": "skipped",
                    "error": "제약 위반("
                    + ", ".join(str(i + 1) for i in failed)
                    + ")으로 생성하지 않습니다(실제 DOE에도 이 조합은 포함되지 않습니다).",
                }
            )
            continue
        if time.perf_counter() - started > PROBE_SECONDS:
            out.append(
                {**entry, "status": "skipped", "error": "제한 시간을 초과하여 건너뛰었습니다."}
            )
            continue
        values = engine.shape_values(row, factors_raw)
        begun = time.perf_counter()
        try:
            made = _shape_point(
                _with_values(recipe, values), values, definitions, tracks, base_values
            )
        except (
            Exception
        ) as failure:  # 무엇이든 그 점의 실패다 — 미리보기가 500 으로 죽지 않게.
            out.append(
                {
                    **entry,
                    "status": "failed",
                    "error": str(failure)[:500] or type(failure).__name__,
                    "ms": int((time.perf_counter() - begun) * 1000),
                }
            )
            continue
        summary = made.evaluation.summary()
        out.append(
            {
                **entry,
                "status": "ok",
                "error": "",
                "ms": int((time.perf_counter() - begun) * 1000),
                "unresolved": made.topology["unresolved"],
                "drift": made.topology.get("drift", []),
                "interference": made.interference,
                "solids": summary["solid_count"],
                "faces": summary["face_count"],
                "warnings": summary["warnings"],
                "quality": _inspect(made.evaluation.shape, limits, reference),
                "measures": _measure_point(
                    measure_list, made, None, _with_values(recipe, values)
                )[1],
            }
        )
    timed = [one["ms"] for one in out if one["status"] == "ok"]
    return {
        "points": out,
        "mean_ms": int(sum(timed) / len(timed)) if timed else None,
        "setup_ms": setup_ms,
        "regions": [one["name"] for one in definitions or []],
    }


def create_study(
    db: Session,
    *,
    owner: User,
    name: str,
    description: str,
    recipe: dict[str, Any],
    factors: list[dict[str, Any]],
    method: str,
    samples: int,
    seed: int,
    work_id: uuid.UUID | None,
    conditions: dict[str, Any] | None = None,
    idempotency_key: str = "",
    requested_by: User | None = None,
    constraints: list[str] | None = None,
    checks: dict[str, Any] | None = None,
    table: list[dict[str, Any]] | None = None,
    measures: list[dict[str, Any]] | None = None,
    outputs: list[str] | None = None,
) -> tuple[DoeStudy, bool]:
    """스터디를 만들고 작업을 건다. 레시피와 **해석 조건**을 스냅샷으로 박는다.

    설계점은 **서버 보관 폴더**에 만든다. 공유 폴더로는 다 만들어진 뒤 「보내기」 로 간다 —
    해석이 읽는 폴더에 만들다 만 것이 보이면 안 된다.

    `idempotency_key` 를 주면 **두 번 불러도 한 벌**이다 — 이미 있으면 그것을 돌려준다
    (돌려준 것인지는 두 번째 값이 말한다). 기계는 재시도하고, 망이 끊겨 답을 못 받았을 뿐인데
    다시 걸면 스터디 둘 · 폴더 둘이 생겨 해석 쪽이 어느 것이 진짜인지 모른다.

    `requested_by` 는 **대행**일 때만 찬다 — `owner` 는 그 DOE 가 누구 것인가(사람)이고,
    `requested_by` 는 누가 실제로 돌렸나(오케스트레이터의 서비스 계정)다. 둘을 한 칸에
    욱여넣으면 「내 DOE 목록」 과 「누가 돌렸나」 중 하나를 잃는다.

    **열쇠를 우리가 지어 내지 않는다.** 「없으면 레시피 다이제스트로」 도 생각했지만, 그러면
    사람이 **같은 설정으로 한 벌 더** 만드는 정상적인 일이 막힌다(비교하려고 두 번 돌리는
    것은 흔하다). 열쇠를 안 주면 「멱등하지 않다」 는 뜻이고, 그것이 사람의 기본값이다.

    `conditions` 를 **안 주면(None)** `work_id` 작업의 현재 버전 조건을 스냅샷으로 박는다.
    화면도 MCP 도 조건을 따로 실어 보내지 않았고, 그래서 DOE 폴더에 조건이 빠진 채 나가고
    있었다(2026-09-29 에 잡았다). 조건 없이 형상만 훑으려면 빈 한 벌(`{}`)을 준다.
    """
    # **대상 작업과 레시피가 가리키는 것은 소유자의 것이어야 한다** — 조건을 함께 주면 작업을
    # 안 열어 봐서, 남의 작업 id 로 그 이름 · 꼬리표를 보고 DOE 를 그 작업에 붙일 수 있었다
    # (2026-10-04 점검).
    if work_id is not None:
        from app.modules.works import services as works

        works.require_owner(works.get_work(db, work_id), owner)
    cad.require_references(db, recipe, owner)
    if conditions is None:
        conditions = _work_conditions(db, work_id, owner) if work_id else {}
    # **쉘로 푸는 파트가 있으면 중간면은 고르지 않아도 나간다** — 쉘 요소는 중간면과 두께로
    # 짓는다. 멱등 지문보다 먼저 채워 재시도도 같은 지문을 낸다.
    if condition_model.has_shell(conditions):
        outputs = sorted({*(outputs or []), "midsurface"})
    try:
        constraints = engine.parse_constraints(constraints)
    except engine.DoeError as failure:
        raise AppError(code("DOE", 23), str(failure)) from failure
    checks = dict(checks or {})
    try:
        checking.thresholds(checks)
    except checking.QualityError as failure:
        raise AppError(code("DOE", 24), str(failure)) from failure
    if method == "table":
        # 표가 값을 주는 변수는 정의를 표에 맞춘다(결과 화면 · README 가 정의를 읽는다).
        factors = _table_factors(factors, table)
        table = _normal_table(factors, table or [])
        samples = len(table)
    else:
        table = None
    if idempotency_key:
        found = db.scalar(
            select(DoeStudy).where(
                DoeStudy.owner_id == owner.id,
                DoeStudy.idempotency_key == idempotency_key,
            )
        )
        if found is not None:
            asked = _request_digest(
                recipe=recipe,
                factors=factors,
                method=method,
                samples=samples,
                seed=seed,
                conditions=conditions,
                work_id=work_id,
                constraints=constraints,
                checks=checks,
                table=table,
                measures=measures or [],
                outputs=outputs or [],
            )
            if digest_of(found) != asked:
                raise AppError(
                    code("DOE", 18),
                    f"같은 멱등 키({idempotency_key})로 다른 요청이 접수되었습니다. 이미 "
                    f"‘{found.name}’에서 이 키를 사용하고 있습니다. 키를 변경하거나 설정을 "
                    "일치시키십시오.",
                )
            return found, True
    try:
        parse(recipe)
    except RecipeValidationError as failure:
        raise AppError(
            code("DOE", 4),
            "레시피가 올바르지 않습니다.",
            details={"problems": failure.problems},
        ) from failure
    _check_factor_names(recipe, factors)
    swaps = engine.material_factors(factors)
    # **조건을 지금 검증한다.** 설계점 마흔 개를 만든 뒤에 「그런 이름표가 없다」 를 알면
    # 늦다 — 그때는 폴더에 반쪽짜리가 남는다.
    #
    # 바디 이름까지 본다: 물성을 없는 바디에 붙이면 해석이 그 바디를 **맨몸으로** 푼다.
    # 여기가 정작 해석으로 나가는 자리라 작업 저장보다 더 중요하다.
    try:
        condition_model.parse(
            conditions, _body_names(recipe), frames.recipe_frame_names(recipe)
        )
    except condition_model.ConditionError as failure:
        raise AppError(code("DOE", 15), f"해석 조건: {failure}") from failure
    if swaps:
        _check_material_factors(recipe, conditions, factors)
    _check_condition_factors(recipe, conditions or {}, factors)
    measures = _measures(measures, recipe, conditions, factors)
    rows = _points(
        db,
        {
            "factors": factors,
            "method": method,
            "samples": samples,
            "seed": seed,
            "recipe": recipe,
            "constraints": constraints,
            "table": table,
        },
    )
    study = DoeStudy(
        name=name.strip(),
        description=description.strip(),
        owner_id=owner.id,
        requested_by_id=requested_by.id if requested_by else None,
        idempotency_key=idempotency_key,
        work_id=work_id,
        recipe=recipe,
        conditions=conditions or {},
        factors=factors,
        constraints=constraints,
        checks=checks,
        measures=measures,
        outputs=sorted(set(outputs or [])),
        method=method,
        samples=samples,
        seed=seed,
        point_count=len(rows),
    )
    db.add(study)
    db.flush()
    study.local_dir = str(files.study_dir(filestore.root() / "doe", study.name, str(study.id)))
    for number, row in enumerate(rows, start=1):
        db.add(DoePoint(study_id=study.id, number=number, params=row, status="pending"))
    db.flush()
    job = jobs.enqueue(
        db,
        kind=JOB_KIND,
        # 작업 기록에는 **실제로 부른 쪽**을 적는다 — 그 표의 물음이 그것이다.
        requested_by=requested_by or owner,
        work_id=work_id,
        input={"study_id": str(study.id)},
        options={},
    )
    study.job_id = job.id
    db.commit()
    db.refresh(study)
    return study, False


def get_study(db: Session, study_id: uuid.UUID, viewer: User) -> DoeStudy:
    """**보기**는 공개된 것이면 누구나. 고치는 일은 `owner_of` 가 따로 막는다.

    기계가 대행으로 만들기 시작하면 「누구 것인가」 가 흐려진다 — 보는 것까지 닫아 두면
    아무도 못 찾는 이력이 쌓인다(`DoeStudy.visibility`)."""
    study = db.get(DoeStudy, study_id)
    if study is None:
        raise NotFound(code("DOE", 6), "실험계획을 찾을 수 없습니다.")
    if study.visibility == "read":
        return study
    if study.owner_id != viewer.id and not viewer.is_system_admin:
        raise Forbidden(code("DOE", 7), "비공개 실험계획입니다.")
    return study


def owned_study(db: Session, study_id: uuid.UUID, viewer: User) -> DoeStudy:
    """**고치러 왔을 때** — 보내기 · 영구보관 · 다시 만들기 · 지우기 · 공개 바꾸기.

    읽기가 공개라고 해서 쓰기까지 공개는 아니다. 남의 DOE 를 공유 폴더로 보내거나 지울 수
    있으면, 「읽기 공개」 가 사실상 「모두가 주인」 이 된다.

    **대행으로 만든 기계도 고칠 수 있다.** 소유자는 사람이지만 그 DOE 를 돌리고 · 보내고 ·
    「다 읽었다」 고 알리는 것은 기계다. 이것이 없으면 오케스트레이터가 제가 만든 것을 제가
    못 내보낸다 — 문서의 한 바퀴를 실제로 돌려 보다가 잡았다(2026-09-24).
    """
    study = get_study(db, study_id, viewer)
    if viewer.is_system_admin:
        return study
    if viewer.id in (study.owner_id, study.requested_by_id):
        return study
    raise Forbidden(
        code("DOE", 7), "다른 사용자의 실험계획입니다. 조회만 가능하며 수정할 수 없습니다."
    )


def set_visibility(db: Session, study: DoeStudy, value: str) -> DoeStudy:
    """`read` 또는 `private`. 기본은 `read` 이고, 감추는 것이 예외다."""
    if value not in ("read", "private"):
        raise AppError(code("DOE", 19), "공개 설정은 read 또는 private이어야 합니다.")
    study.visibility = value
    db.commit()
    db.refresh(study)
    return study


def _visible(viewer: User, scope: str) -> ColumnElement[bool]:
    """내 것(대행으로 내 이름이 된 것 포함), `all` 이면 공개된 것까지."""
    if scope == "all":
        return or_(DoeStudy.visibility == "read", DoeStudy.owner_id == viewer.id)
    return DoeStudy.owner_id == viewer.id


def _target_named(like: str) -> ColumnElement[bool]:
    """대상 작업의 이름에 이 낱말이 있나 — 「브래킷의 DOE」 를 찾는 길."""
    return exists(select(literal(1)).where(Work.id == DoeStudy.work_id, Work.name.ilike(like)))


def list_studies(
    db: Session,
    viewer: User,
    *,
    work_id: uuid.UUID | None,
    limit: int,
    offset: int,
    scope: str = "mine",
    query: str = "",
    tag: str = "",
) -> tuple[list[DoeStudy], int]:
    """`scope="mine"` 은 내 것(대행으로 내 이름이 된 것 포함), `"all"` 은 공개된 것까지.

    기본이 「내 것」 인 까닭: 「내 활동」 화면이 이것을 쓴다. 공개를 기본으로 하면 남의 것이
    내 활동에 섞인다 — 찾는 것은 `scope=all` 로 따로 묻는다.

    `query` 는 한 곳의 규칙(`shared/search.py` — 이름 · 설명 · 만든 사람)에 **대상 작업의
    이름**을 더한 것, `tag` 는 **대상 작업의 꼬리표**다(DOE 에는 꼬리표가 없다 — 「브래킷 EMC」
    에 건 DOE 들을 꼬리표로 모은다)."""
    statement = select(DoeStudy).where(_visible(viewer, scope))
    if work_id is not None:
        statement = statement.where(DoeStudy.work_id == work_id)
    found = search.matches(
        query,
        columns=[DoeStudy.name, DoeStudy.description],
        owner=DoeStudy.owner_id,
        also=[_target_named],
    )
    if found is not None:
        statement = statement.where(found)
    if tag.strip():
        statement = statement.where(
            exists(
                select(literal(1)).where(
                    Work.id == DoeStudy.work_id, Work.tags.contains([tag.strip()])
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(
        statement.order_by(DoeStudy.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def study_tags(db: Session, viewer: User, *, scope: str = "mine") -> list[str]:
    """보이는 DOE 들의 **대상 작업** 꼬리표 — 많이 쓴 것부터(내 작업의 꼬리표 목록과 같은 꼴).
    거르개 · 자동 완성이 쓴다."""
    targets = select(DoeStudy.work_id).where(
        _visible(viewer, scope), DoeStudy.work_id.is_not(None)
    )
    seen: dict[str, int] = {}
    for tags in db.scalars(select(Work.tags).where(Work.id.in_(targets))):
        for one in tags or []:
            seen[one] = seen.get(one, 0) + 1
    return sorted(seen, key=lambda t: (-seen[t], t))


def points(db: Session, study: DoeStudy) -> list[DoePoint]:
    return list(
        db.scalars(
            select(DoePoint).where(DoePoint.study_id == study.id).order_by(DoePoint.number)
        ).all()
    )


#: 점 메시는 다시 계산하면 그만이라 DB 에 두지 않는다. 화면이 「하나씩 · 겹쳐 · 나란히」 넘길
#: 때 같은 점을 거듭 묻으므로 최근 것을 든다. 스냅샷은 바뀌지 않으니 (study, number) 로 족하다.
#: 열쇠는 (스터디, 점 번호) 또는 (스터디, **형상 지문**) — 뒤엣것이 형상이 같은 점들을 묶는다.
_MESH_CACHE: OrderedDict[tuple[uuid.UUID, int | str], dict[str, Any]] = OrderedDict()
_MESH_CACHE_SIZE = 64


def point_mesh(db: Session, study: DoeStudy, number: int) -> dict[str, Any]:
    """설계점 하나의 형상 — 스냅샷 레시피에 그 점의 값을 넣어 **다시 만든다.**

    형상이 같은 점끼리는 한 번만 만든다(`shape_digest`) — 조건만 훑으면 모든 점이 같은
    형상이라, 나란히 보기로 스물넷을 열면 같은 것을 스물네 번 만들게 된다.

    STEP 을 읽는 것보다 **빠르지는 않다**(구멍 24 짜리 판에서 만들기 257 ms 대 읽기 28 ms; 둘
    다 여기에 메시 144 ms 가 더 붙는다). 그런데도 다시 만드는 이유는 **STEP 이 없을 수 있기
    때문이다** — 공유 폴더는 전달 큐라 기한이 지나면 치워지고, 그때도 화면은 떠야 한다.
    레시피는 DB 에 남으므로 이 길은 언제나 있다. 면마다 어느 점인지는 화면이 붙인다."""
    key = (study.id, number)
    if key in _MESH_CACHE:
        _MESH_CACHE.move_to_end(key)
        return _MESH_CACHE[key]
    point = db.scalar(
        select(DoePoint).where(DoePoint.study_id == study.id, DoePoint.number == number)
    )
    if point is None:
        raise NotFound(code("DOE", 12), f"설계점 {number}번이 없습니다.")
    if point.status != "ok":
        raise AppError(
            code("DOE", 13),
            "이 설계점에는 형상이 없습니다. " + (point.error or "아직 생성 중입니다.")[:200],
        )
    recipe = {
        **study.recipe,
        "params": {**(study.recipe.get("params") or {}), **_shape_params(study, point.params)},
    }
    # **형상이 같은 점은 만들지 않는다.** 조건만 훑으면 모든 점의 형상이 같다 — 나란히 보기로
    # 스물넷을 열면 같은 것을 스물네 번 만들게 된다. 지문은 식을 푸는 산수라 거저다.
    digest = shape_digest(recipe)
    twin = _MESH_CACHE.get((study.id, digest)) if digest else None
    if twin is not None:
        _MESH_CACHE.move_to_end((study.id, digest))
        made = {**twin, "number": number, "params": point.params}
    else:
        evaluation = cad.build(recipe)
        made = {
            "number": number,
            "params": point.params,
            "summary": evaluation.summary(),
            "mesh": mesh(evaluation.shape),
        }
        if digest:
            _MESH_CACHE[(study.id, digest)] = made
    _MESH_CACHE[key] = made
    if len(_MESH_CACHE) > _MESH_CACHE_SIZE:
        _MESH_CACHE.popitem(last=False)
    return made


def status_of(db: Session, study: DoeStudy) -> dict[str, Any]:
    """**진행만** 묻는 자리 — 표 전체를 주지 않는다.

    `doe_points` 는 설계점 200줄을 통째로 준다. 기계가 「끝났나」 만 보려고 그것을 되풀이해
    받으면 오가는 양이 곧 비용이다. 여기는 세는 것만 한다(DB 에서 센다 — 줄을 안 싣는다).
    """
    job = db.get(Job, study.job_id) if study.job_id else None
    counted: dict[str, int] = {
        str(name): int(how_many)
        for name, how_many in db.execute(
            select(DoePoint.status, func.count())
            .where(DoePoint.study_id == study.id)
            .group_by(DoePoint.status)
        ).all()
    }
    done = int(counted.get("ok", 0))
    failed = int(counted.get("failed", 0))
    return {
        "study_id": str(study.id),
        "name": study.name,
        # 작업이 없으면(아주 옛 줄) 끝난 것으로 본다 — 영원히 기다리게 두지 않는다.
        "status": job.status if job else "done",
        "running": bool(job and job.status in ("queued", "running")),
        "points_total": study.point_count,
        "done": done,
        "failed": failed,
        "pending": max(0, study.point_count - done - failed),
        "error": job.error if job else None,
        # 파일이 아직 있나 · 해석에 나가 있나 — 다음에 무엇을 부를지가 여기서 갈린다.
        "files_ready": local_ready(study),
        "folder": files.windows_path(Path(study.export_dir)) if study.export_dir else None,
        "exported_at": study.exported_at.isoformat() if study.exported_at else None,
        "released_at": study.released_at.isoformat() if study.released_at else None,
        "keep_forever": study.keep_forever,
        # 보낸 뒤에 점을 더했으면 공유 폴더가 옛것이다 — 기계는 이것을 보고 다시 보낸다.
        "export_stale": export_stale(study),
        "batches": len(study.batches or []),
    }


def shape_digest(recipe: dict[str, Any]) -> str:
    """이 레시피가 **어떤 형상을 만드나**의 지문 — 만들어 보기 전에 안다.

    식을 다 푼 뒤의 노드만 본다(`params` 는 뺀다). 그러면 **아무 노드도 안 쓰는 치수**는
    지문에 안 들어간다 — 조건에만 쓰이는 `압력` 을 2 · 3 MPa 로 훑으면 설계점 둘의 지문이
    같고, 형상은 실제로 같다.

    그래서 조건 훑기는 형상을 **한 번만** 만든다. 이것이 없으면 똑같은 STEP 을 N 벌 만들어
    N 벌 쓴다 — 시간도 파일도 N 배다.

    못 풀면 빈 문자열이다(그 점은 어차피 만들다 실패한다) — 겹치지 않게 두는 편이 안전하다.
    """
    try:
        resolved = params.resolve(recipe)
    except Exception:  # 못 풀면 겹침을 포기한다 — 만들기가 제대로 실패한다.
        return ""
    body = {key: value for key, value in resolved.items() if key != "params"}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _needs_build(folder: Path, point: DoePoint, only: str) -> bool:
    """이 점을 다시 만들어야 하나 — 다 하라고 했거나, 실패했거나, **파일이 사라졌거나.**

    작업 함수와 「다시 만들기」 가 **같은 규칙을 본다.** 다르면 화면의 진행 표시가 건너뛴 점을
    두고 거짓말을 한다.

    `new` 는 **점을 더했을 때** — 새 점(pending)과 파일이 사라진 점만. 실패한 점은 실패로 둔다
    (같은 값이면 또 실패한다 — 다시 해 보려면 「실패한 점만 다시」)."""
    if only == "new":
        if point.status == "pending":
            return True
        if point.status == "failed":
            return False
        return not (point.step_file and (folder / point.step_file).exists())
    if only != "failed" or point.status != "ok":
        return True
    return not (point.step_file and (folder / point.step_file).exists())


def _batch_factors(
    study: DoeStudy, overrides: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """더할 묶음의 인자 — 스터디의 것에서 **준 것만 바꾼다**(범위를 좁히거나 단계를 바꾼다).

    변수를 새로 더하거나 빼지는 못한다 — 표의 열이 묶음마다 달라지면 한 폴더가 한 실험이 아니게
    된다(그건 새 DOE 다). 재료 · 고르기 · 배율 인자는 다른 방식으로 바꿀 수 없다(후보의 뜻이
    달라진다)."""
    current = {str(one["name"]): one for one in study.factors}
    out = {name: dict(one) for name, one in current.items()}
    for one in overrides or []:
        name = str(one.get("name") or "")
        if name not in current:
            raise AppError(
                code("DOE", 26),
                f"이 DOE에 없는 변수({name})입니다. 변수를 추가하려면 새 DOE를 생성하십시오.",
            )
        before = current[name].get("mode")
        after = one.get("mode", before)
        if (before in engine.NON_SHAPE or after in engine.NON_SHAPE) and before != after:
            raise AppError(
                code("DOE", 26), f"‘{name}’: {before} 인자는 방식을 변경할 수 없습니다."
            )
        out[name] = {**current[name], **one}
    return list(out.values())


def _sobol_drawn(db: Session, study: DoeStudy, seed: int) -> int:
    """이 시드의 Sobol 수열을 **이미 몇 번째까지 썼나** — 이어 뽑을 자리.

    첫 묶음이 Sobol 이면 그 계획을 다시 세워 센다(제약에 걸려 더 뽑았을 수 있다 — 산수라
    거저다). 더한 묶음은 제 `next` 를 적어 두었다."""
    drawn = 0
    if study.method == "sobol" and study.seed == seed:
        drawn = _plan(
            db,
            {
                "factors": study.factors,
                "method": "sobol",
                "samples": study.samples,
                "seed": study.seed,
                "recipe": study.recipe,
                "constraints": study.constraints or [],
            },
        ).next_index
    for batch in study.batches or []:
        if batch.get("method") == "sobol" and int(batch.get("seed") or 0) == seed:
            drawn = max(drawn, int(batch.get("next") or 0))
    return drawn


def extend_study(
    db: Session,
    study: DoeStudy,
    *,
    requester: User,
    raw: dict[str, Any],
    dry_run: bool = False,
) -> tuple[DoeStudy, dict[str, Any]]:
    """**이미 만든 DOE 에 설계점을 더한다** — 번호를 이어서, 같은 폴더에.

    첫 결과를 보고 관심 구간을 좁혀 더 뽑을 때 쓴다. 새 DOE 로 만들면 폴더 · 표가 둘로 갈라져
    해석 쪽이 둘을 이어 붙여야 한다. 묶음마다 방식 · 시드 · 범위를 `batches` 에 남긴다(스냅샷과
    같은 까닭 — 「이 점은 어디서 왔나」 를 나중에 되짚는다).

    - 스터디의 **제약식**이 그대로 걸린다.
    - 이미 있는 점과 값이 같은 줄은 빼고(`skipped`) 센다 — 격자를 좁히면 끝 값이 겹친다.
    - `idempotency_key` 가 같은 묶음이 이미 있으면 **더하지 않고** 그것을 돌려준다(기계의
      재시도).
    - `dry_run` 이면 세기만 한다(화면의 미리보기)."""
    job = db.get(Job, study.job_id) if study.job_id else None
    if job is not None and job.status in ("queued", "running"):
        raise AppError(
            code("DOE", 17),
            "아직 생성 중입니다. 생성이 완료된 후 설계점을 추가할 수 있습니다.",
        )
    key = str(raw.get("idempotency_key") or "")
    if key and not dry_run:
        for batch in study.batches or []:
            if batch.get("idempotency_key") == key:
                return study, {**batch, "reused": True}
    method = str(raw.get("method") or "lhs")
    factors = _batch_factors(study, raw.get("factors"))
    table = raw.get("table") if method == "table" else None
    if method == "table":
        columns = {str(k) for row in table or [] if isinstance(row, dict) for k in row}
        extra = sorted(columns - {str(one["name"]) for one in factors})
        if extra:
            raise AppError(
                code("DOE", 26),
                f"이 DOE에 없는 변수({', '.join(extra)})입니다. 변수를 추가하려면 새 DOE를 "
                "생성하십시오.",
            )
        factors = _table_factors(factors, table)
    batches = list(study.batches or [])
    # 시드를 안 주면 묶음마다 다르게 — 같은 시드면 첫 묶음과 같은 점이 다시 나온다. Sobol 은
    # 거꾸로 **같은 시드로 이어 뽑는다** — 앞의 점들과 함께 공간을 고르게 채우는 것이
    # 그 뜻이다.
    if method == "sobol":
        seed = int(raw.get("seed") or study.seed)
    else:
        seed = int(raw.get("seed") or (study.seed + len(batches) + 1))
    found = _plan(
        db,
        {
            "factors": factors,
            "method": method,
            "samples": raw.get("samples") or 10,
            "seed": seed,
            "recipe": study.recipe,
            "constraints": study.constraints or [],
            "table": table,
            "offset": _sobol_drawn(db, study, seed) if method == "sobol" else 0,
        },
    )
    if found.too_many:
        limit = settings_store.doe_max_points(db)
        raise AppError(
            code("DOE", 3),
            f"추가할 설계점이 {found.kept}개입니다. "
            f"한 번에 최대 {limit}개까지 추가할 수 있습니다.",
        )
    if method == "table" and found.rejected:
        raise AppError(
            code("DOE", 23),
            f"표의 {found.rejected}개 행이 제약을 위반합니다. 해당 행을 제외하거나 제약을 "
            "수정하십시오.",
        )
    existing = points(db, study)
    names = [str(one["name"]) for one in study.factors]

    def same(row: dict[str, Any]) -> str:
        return json.dumps([row.get(name) for name in names], ensure_ascii=False, default=str)

    seen = {same(one.params) for one in existing}
    fresh: list[dict[str, Any]] = []
    skipped = 0
    for row in found.rows:
        signature = same(row)
        # 표는 사람이 고른 점이라 겹쳐도 둔다 — 줄 번호가 설계점 번호여야 한다.
        if signature in seen and method != "table":
            skipped += 1
            continue
        seen.add(signature)
        fresh.append(row)
    first = max((one.number for one in existing), default=0) + 1
    summary: dict[str, Any] = {
        "number": len(batches) + 2,
        "method": method,
        "samples": int(raw.get("samples") or len(fresh)),
        "seed": seed,
        "factors": factors,
        "from": first,
        "to": first + len(fresh) - 1,
        "added": len(fresh),
        "skipped": skipped,
        "rejected": found.rejected,
    }
    if method == "sobol":
        # 다음에 더할 때 여기서 잇는다.
        summary["next"] = found.next_index
    if dry_run:
        return study, summary
    if not fresh:
        raise AppError(
            code("DOE", 27),
            f"추가할 새 설계점이 없습니다. {skipped}개가 기존 설계점과 같습니다. 범위 또는 "
            "시드를 변경하십시오.",
        )
    for offset, row in enumerate(fresh):
        db.add(
            DoePoint(study_id=study.id, number=first + offset, params=row, status="pending")
        )
    summary["at"] = datetime.now(UTC).isoformat()
    summary["requested_by"] = requester.display_name or requester.email
    if key:
        summary["idempotency_key"] = key
    study.batches = [*batches, summary]
    study.point_count = (study.point_count or 0) + len(fresh)
    db.flush()
    fresh_job = jobs.enqueue(
        db,
        kind=JOB_KIND,
        requested_by=requester,
        work_id=study.work_id,
        input={"study_id": str(study.id), "only": "new"},
        options={},
    )
    study.job_id = fresh_job.id
    db.commit()
    db.refresh(study)
    return study, summary


def rerun_study(
    db: Session, study: DoeStudy, *, requester: User, only: str = "all"
) -> DoeStudy:
    """스냅샷으로 **설계점 파일을 다시 만든다.** 새 스터디가 아니라 같은 스터디다.

    왜 있어야 하나: 폴더는 수명이 있고(공유 폴더 30일, 서버 보관 폴더도 기한이 있다) 파일이
    치워지면 내려받기도 「보내기」 도 못 한다. 그런데 **다시 만들 재료는 DB 에 다 있다** —
    레시피 · 인자 · 시드 · 조건이 스냅샷으로 박혀 있으니 같은 것이 그대로 나온다. 이력이
    의미를 가지려면 이 길이 있어야 한다.

    `only="failed"` 는 실패한 점만 — 범위를 고쳐 다시 돌리는 게 아니라(그건 새 스터디다),
    같은 값으로 한 번 더 해 보는 것이다. 파일이 사라진 점은 `ok` 였어도 다시 만든다.
    """
    if only not in ("all", "failed"):
        raise AppError(code("DOE", 16), "only는 all 또는 failed여야 합니다.")
    job = db.get(Job, study.job_id) if study.job_id else None
    if job is not None and job.status in ("queued", "running"):
        raise AppError(
            code("DOE", 17),
            "아직 생성 중입니다. 생성이 완료된 후 다시 생성할 수 있습니다.",
        )
    # 폴더 경로가 비어 있던 옛 줄도 여기서 제 자리를 얻는다.
    if not study.local_dir:
        study.local_dir = str(
            files.study_dir(filestore.root() / "doe", study.name, str(study.id))
        )
    # 다시 만들 점은 먼저 pending 으로 — 안 그러면 화면이 옛 결과를 진행으로 보여 준다.
    folder = Path(study.local_dir)
    for point in points(db, study):
        if _needs_build(folder, point, only):
            point.status = "pending"
            point.error = ""
    fresh = jobs.enqueue(
        db,
        kind=JOB_KIND,
        requested_by=requester,
        work_id=study.work_id,
        input={"study_id": str(study.id), "only": only},
        options={},
    )
    study.job_id = fresh.id
    db.commit()
    db.refresh(study)
    return study


def export_stale(study: DoeStudy) -> bool:
    """보낸 뒤에 점을 더했나 — 그러면 공유 폴더의 표가 옛것이다."""
    if not study.exported_at:
        return False
    added = [
        datetime.fromisoformat(str(one["at"])) for one in study.batches or [] if one.get("at")
    ]
    return bool(added) and max(added) > study.exported_at


def local_ready(study: DoeStudy) -> bool:
    """서버 보관 폴더에 **쓸 만한 것이 있나.** 표가 있으면 있는 것이다.

    이것을 DB 칸으로 두지 않는 까닭: 폴더는 청소 · 백업 복원 · 사람 손으로도 바뀐다. 두 곳에
    적으면 어긋나는 날이 오고, 그때 화면은 있다고 하는데 내려받기는 없다고 한다."""
    return bool(study.local_dir) and (Path(study.local_dir) / "manifest.csv").exists()


def delete_study(db: Session, study: DoeStudy) -> None:
    """스터디와 **서버 보관 폴더**를 지운다. 공유 폴더의 사본은 **남긴다.**

    둘을 다르게 다루는 까닭은 누가 읽느냐다. 서버 보관 폴더는 우리 것이고 이 줄이 사라지면
    아무도 찾을 수 없는 쓰레기가 된다. 공유 폴더는 해석이 이미 열어 보고 있을 수 있고 제
    결과를 덧붙여 두었을 수도 있다 — 남의 도구가 읽는 파일을 말없이 지우지 않는다."""
    if study.local_dir:
        shutil.rmtree(Path(study.local_dir), ignore_errors=True)
    db.delete(study)
    db.commit()


def export_study(db: Session, study: DoeStudy) -> DoeStudy:
    """서버 보관 폴더를 공유 폴더로 **복사**한다. 다시 누르면 덮어쓴다(같은 이름 폴더).

    만들기가 끝나야 보낸다 — 만드는 중에 보내면 해석이 반쪽짜리 표를 읽는다."""
    job = db.get(Job, study.job_id) if study.job_id else None
    if job is None or job.status not in ("done", "failed"):
        raise AppError(
            code("DOE", 9), "아직 생성 중입니다. 생성이 완료된 후 내보낼 수 있습니다."
        )
    source = Path(study.local_dir)
    if not (source / "manifest.csv").exists():
        # 둘을 갈라 말한다 — 「없다」 는 같아도 할 일이 다르다. 만들다 만 것이면 기다릴 일,
        # 치워진 것이면 「다시 만들기」 를 누를 일이다.
        made = any(one.status == "ok" for one in points(db, study))
        raise AppError(
            code("DOE", 10),
            "서버 보관 폴더가 정리되었습니다. ‘재생성’을 먼저 실행하십시오."
            if made
            else "내보낼 파일이 없습니다. 생성된 설계점이 없습니다.",
        )
    root = check_root()
    target = files.study_dir(root, study.name, str(study.id))
    try:
        shutil.copytree(source, target, dirs_exist_ok=True)
    except OSError as failure:
        raise AppError(
            code("DOE", 11),
            f"공유 폴더에 쓰지 못했습니다: {files.windows_path(target)} ({failure.strerror})",
        ) from failure
    study.export_dir = str(target)
    study.exported_at = datetime.now(UTC)
    # **다시 보내면 「다 읽었다」 는 무효다.** 안 그러면 방금 보낸 폴더가 다음 청소에 곧바로
    # 치워진다 — 해석이 아직 열어 보지도 않았는데(시험이 잡았다).
    study.released_at = None
    db.commit()
    db.refresh(study)
    return study


def set_keep(db: Session, study: DoeStudy, keep: bool) -> DoeStudy:
    """영구보관을 켜고 끈다 — **기한보다 사람의 뜻이 세다.**"""
    study.keep_forever = keep
    db.commit()
    db.refresh(study)
    return study


def release(db: Session, study: DoeStudy) -> DoeStudy:
    """해석 쪽이 **다 읽었다**고 알린다(오케스트레이터가 부른다).

    「성공했다」 가 아니라 「더 안 읽는다」 는 뜻이다 — 실패해서 다시 돌릴 생각이면 알리지
    않는다. 알린 폴더는 기한을 기다리지 않고 먼저 치운다.
    """
    study.released_at = datetime.now(UTC)
    db.commit()
    db.refresh(study)
    return study


def expired_exports(db: Session, *, now: datetime | None = None) -> list[DoeStudy]:
    """치울 때가 된 것 — **내보낸 폴더가 있고**, 영구보관이 아니고, 기한이 지났거나 다 읽힌 것.

    기한(`doe_export_ttl_days`)이 0 이면 **아무것도 자동으로 지우지 않는다** — 자동 삭제를 끄는
    스위치가 하나는 있어야 한다.
    """
    now = now or datetime.now(UTC)
    days = settings_store.get_int(db, "doe_export_ttl_days")
    rows = db.scalars(
        select(DoeStudy).where(
            DoeStudy.export_dir != "",
            DoeStudy.keep_forever.is_(False),
        )
    ).all()
    out = []
    for study in rows:
        if study.released_at is not None:
            out.append(study)
            continue
        if days <= 0:
            continue
        sent = study.exported_at or study.created_at
        if sent is not None and (now - sent).days >= days:
            out.append(study)
    return out


def cleanup_exports(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
    """공유 폴더의 **사본만** 지운다. 서버 보관 폴더 · DB · 설정은 그대로.

    지워도 「보내기」 를 다시 누르면 같은 폴더가 다시 선다 — 그래서 이것은 파괴적인 일이
    아니다. 되돌릴 수 없는 것은 해석 쪽이 그 폴더에 **덧붙여 둔 것**(결과 파일)인데, 그래서
    「다 읽었다」 를 알린 것과 기한이 지난 것만 집는다.
    """
    removed = []
    for study in expired_exports(db):
        folder = Path(study.export_dir)
        if not dry_run:
            shutil.rmtree(folder, ignore_errors=True)
            study.export_dir = ""
            study.exported_at = None
        removed.append({"id": str(study.id), "name": study.name, "folder": str(folder)})
    if removed and not dry_run:
        db.commit()
    return {"removed": removed, "count": len(removed), "dry_run": dry_run}


def expired_locals(db: Session, *, now: datetime | None = None) -> list[DoeStudy]:
    """서버 보관 폴더를 치울 때가 된 것.

    공유 폴더보다 **한 단계 더 조심한다** — 여기가 복사원이라, 지우면 「보내기」 가 곧바로
    막힌다(「다시 만들기」 로 돌아오기는 한다). 그래서 셋을 다 보고 고른다:

    - **아직 공유 폴더에 나가 있으면 건드리지 않는다**(`export_dir`). 해석이 읽는 중일 때
      복사원을 치워 두면, 다시 보내 달라는 말에 답할 길이 없다. 공유 폴더 청소가 먼저 돌아
      그 칸을 비우면 그때 차례가 온다.
    - **만드는 중이면 건드리지 않는다.** 작업이 쓰고 있는 폴더다.
    - 영구보관과 기한 0 은 공유 폴더와 같은 뜻이다.
    """
    now = now or datetime.now(UTC)
    days = settings_store.get_int(db, "doe_local_ttl_days")
    if days <= 0:
        return []
    rows = db.scalars(
        select(DoeStudy).where(
            DoeStudy.local_dir != "",
            DoeStudy.export_dir == "",
            DoeStudy.keep_forever.is_(False),
        )
    ).all()
    out = []
    for study in rows:
        job = db.get(Job, study.job_id) if study.job_id else None
        if job is not None and job.status in ("queued", "running"):
            continue
        # 마지막으로 쓴 때 — 내보낸 적이 있으면 그때, 없으면 만든 때.
        touched = study.exported_at or study.created_at
        if touched is not None and (now - touched).days >= days:
            out.append(study)
    return out


def cleanup_locals(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
    """서버 보관 폴더의 **파일만** 지운다. DB 의 스터디 · 설계점 · 스냅샷은 그대로.

    그래서 화면은 그대로 뜬다 — 3D 는 어차피 레시피로 다시 만들고(`point_mesh`), 표는 DB 에서
    다시 그린다(`manifest.csv` 라우터). 없어지는 것은 STEP 과 점 파일뿐이고, 그것은
    「다시 만들기」(`rerun_study`) 가 스냅샷으로 되살린다.

    `local_dir` 은 **비우지 않는다** — 다시 만들 자리가 거기다. 폴더가 있나 없나는 파일이
    말하게 둔다(`local_ready`); 그 상태를 DB 에도 적으면 언젠가 둘이 어긋난다.
    """
    removed = []
    for study in expired_locals(db):
        folder = Path(study.local_dir)
        if not dry_run:
            shutil.rmtree(folder, ignore_errors=True)
        removed.append({"id": str(study.id), "name": study.name, "folder": str(folder)})
    return {"removed": removed, "count": len(removed), "dry_run": dry_run}


def _person(db: Session, user_id: uuid.UUID | None) -> dict[str, str]:
    """이름과 계정. 없으면 빈 칸이지 거짓말은 안 한다."""
    user = db.get(User, user_id) if user_id else None
    if user is None:
        return {"name": "", "email": ""}
    return {"name": user.display_name or "", "email": user.email or ""}


def _owner_of(db: Session, study: DoeStudy) -> dict[str, str]:
    """이 DOE 가 **누구 것인가.** 대행이면 대행 대상인 사람이다."""
    return _person(db, study.owner_id)


def _shape_params(study: DoeStudy, row: dict[str, Any]) -> dict[str, Any]:
    """설계점 한 줄에서 **형상을 바꾸는 값만**(레시피 `params` · 조건의 식으로 간다). 재료
    인자는 재료 이름이라 레시피에 넣으면 「모르는 이름」 으로 형상이 깨진다."""
    return engine.shape_values(row, study.factors)


def _point_conditions(study: DoeStudy, row: dict[str, Any]) -> dict[str, Any]:
    """이 설계점의 조건 — 재료 인자가 고른 재료를 그 바디에 바꿔 끼운 사본."""
    conditions: dict[str, Any] = study.conditions or {}
    for name, bodies in engine.material_factors(study.factors).items():
        if row.get(name) is not None:
            conditions = condition_model.with_material(conditions, bodies, str(row[name]))
    # 고르기 인자 — 칸 하나를 이 점의 값으로(접촉 종류 · 구속 종류 · 해석 종류 …).
    for one in engine.non_shape_factors(study.factors, "choice"):
        if one["name"] in row:
            conditions = condition_model.with_choice(
                conditions, one["target"], row[one["name"]]
            )
    return conditions


def _with_scales(
    study: DoeStudy, row: dict[str, Any], resolved: dict[str, Any]
) -> dict[str, Any]:
    """배율 인자 — 풀린 조건에서 그 바디 재료의 옮긴 값에 배율을 곱한다(원본은 그대로)."""
    for one in engine.non_shape_factors(study.factors, "scale"):
        factor = row.get(one["name"])
        if factor is not None and float(factor) != 1.0:
            resolved = condition_model.with_scale(
                resolved, list(one.get("bodies") or []), str(one["property"]), float(factor)
            )
    return resolved


def _deck_conditions(
    conditions: dict[str, Any], factors: list[dict[str, Any]]
) -> dict[str, Any]:
    """덱을 뽑을 재료들 — 재료 인자의 **후보**도 넣는다. 후보는 조건에서 어디에도 안 붙은
    「담아 둔 재료」 라 그대로 두면 덱이 안 뽑히는데, 어느 설계점에서는 붙는다."""
    materials = (conditions or {}).get("materials") or []
    if not materials:
        return conditions
    out = deepcopy(conditions)
    for one in factors or []:
        if one.get("mode") != "material":
            continue
        for choice in one.get("values") or []:
            try:
                index = condition_model.material_index(out, str(choice))
            except condition_model.ConditionError:
                continue
            item = out["materials"][index]
            where = condition_model.applied_bodies(item.get("apply_to", []))
            item["apply_to"] = [
                *where,
                *[b for b in one.get("bodies") or [] if b not in where],
            ]
    return out


def _decks_for_point(
    decks: list[dict[str, Any]], conditions: dict[str, Any]
) -> list[dict[str, Any]]:
    """폴더에 한 벌 둔 덱 중 **이 점에서 붙은 것**만, 이 점의 바디로. 덱 번호(`mid`)는 조건의
    `materials[mid-1]` 과 짝이다."""
    materials = conditions.get("materials") or []
    out = []
    for deck in decks:
        mid = int(deck.get("mid") or 0)
        if not 0 < mid <= len(materials):
            continue
        material = materials[mid - 1]
        where = condition_model.applied_bodies(material.get("apply_to", []))
        # 배율을 곱한 재료는 덱의 값이 그 점의 값과 다르다 — 싣지 않는다(중립 물성이 정본).
        if where and not (material.get("converted") or {}).get("scaled"):
            out.append({**deck, "apply_to": where})
    return out


def _write_decks(folder: Path, conditions: dict[str, Any] | None) -> list[dict[str, Any]]:
    """고른 솔버 덱을 `materials/` 에 쓴다. 점 파일이 가리킬 **목록**을 돌려준다.

    **재료마다 덱 안의 번호(`mid`)를 1 부터 매긴다** — 한 해석에 재료가 여럿이면 서로
    달라야 한다. 그 번호는 한 벌이 다 모여야 정해지므로 고를 때가 아니라 여기서 뽑는다.

    못 뽑아도 넘어간다(덤이다) — 대신 `notes` 에 왜인지 적어 폴더에 남긴다."""
    from app.modules.materials import decks as deck_maker

    materials = (conditions or {}).get("materials") or []
    if not any((one or {}).get("deck_formats") for one in materials):
        return []
    system = str(((conditions or {}).get("units") or {}).get("system") or "")
    out: list[dict[str, Any]] = []
    notes: list[str] = []
    for mid, material in enumerate(materials, start=1):
        # **담아만 둔 재료는 건너뛴다** — 어느 바디에도 안 붙었으니 해석이 쓸 일이 없다.
        # 번호(`mid`)는 그래도 자리대로 둔다: 조건의 `materials[i]` 와 `m{i+1}` 이 늘 짝이어야
        # 받는 쪽이 덱과 중립 물성을 이을 수 있다.
        # 스냅샷은 받은 그대로라 칸이 없을 수 있다 — 없으면 모델의 기본값(「전체」)과
        # 같게 읽는다.
        where = condition_model.applied_bodies(
            material.get("apply_to", condition_model.ALL_BODIES)
        )
        if not where:
            continue
        made = deck_maker.build(material, system, mid)
        notes.extend(made["notes"])
        for deck in made["decks"]:
            name = f"m{mid}-{deck['format']}.{deck_maker.extension(deck['format'])}"
            (folder / "materials").mkdir(parents=True, exist_ok=True)
            (folder / "materials" / name).write_text(deck["text"], encoding="utf-8")
            out.append(
                {
                    "apply_to": where,
                    "material": (material.get("ref") or {}).get("name") or "",
                    "format": deck["format"],
                    "units": deck["units"],
                    "mid": mid,
                    "file": f"materials/{name}",
                }
            )
    if notes:
        (folder / "materials").mkdir(parents=True, exist_ok=True)
        (folder / "materials" / "README.txt").write_text(
            "일부 솔버 덱을 생성하지 못했습니다. 중립 물성(점 파일의 conditions.materials)은\n"
            "그대로 포함되어 있습니다. 생성하지 못한 사유:\n\n"
            + "\n".join(f"- {one}" for one in notes)
            + "\n",
            encoding="utf-8",
        )
    return out


def _builder(recipe: dict[str, Any]) -> follow.Build:
    """덮어쓸 변수만 바꿔 형상을 만든다 — 나머지 식(「=길이 * 0.5」)은 그대로 따라 풀린다."""

    def build(overrides: dict[str, float]) -> tuple[Any, dict[str, list[int]] | None]:
        made = evaluate(
            parse({**recipe, "params": {**(recipe.get("params") or {}), **overrides}}),
            resolve_file=resolve_import,
            resolve_component=resolve_component,
        )
        return made.shape, made.tags

    return build


def _mark_drift(topo: dict[str, Any], drifted: dict[str, float]) -> None:
    """예측한 자리에서 먼 것을 집은 그룹은 **「못 풀었다」 로 돌린다** — 딴 면을 집었을 수
    있다.

    영역에서 빼고 `unresolved` 에 넣는다. 말없이 딴 면에 하중이 걸리는 것보다, 받는 쪽이 그
    설계점을 건너뛰게 하는 편이 낫다. 얼마나 멀었는지는 `drift` 에 남긴다."""
    if not drifted:
        return
    topo["drift"] = [{"name": name, "distance": gap} for name, gap in drifted.items()]
    for name in drifted:
        topo["regions"].pop(name, None)
        if name not in topo["unresolved"]:
            topo["unresolved"].append(name)


def _region_definitions(conditions: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """조건의 이름표를 **영역 정의**로 — 내보낼 때 그 이름으로 좌표가 나간다.

    조건이 없으면 None 을 돌려 기본 영역(`fixed_base` · `bolt_holes`)으로 간다. 사람이 이름표를
    지었으면 그것이 곧 해석이 부를 이름이다 — 우리가 다시 이름 짓지 않는다.
    """
    names = (conditions or {}).get("named_selections") or []
    if not names:
        return None
    # **바디 이름표는 면으로 풀지 않는다.** 영역은 면의 지문이고 바디는 덩어리다 — 섞으면
    # 바디마다 「못 풀었다」 가 하나씩 쌓이고, 그 표가 「이 점을 해석에 쓸 수 있나」 를
    # 말하는 자리라 못 믿게 된다. 바디는 점 파일의 `bodies` 가 이름으로 들고 있다.
    return [
        {"name": one["name"], "select": one.get("select") or {}}
        for one in names
        if one.get("name") and one.get("entity", "face") != "body"
    ]


def _interference_of(shape: Any) -> dict[str, Any] | None:
    """결과가 이름표 붙은 묶음(조립)일 때만 — 구성품이 하나면 검사할 쌍이 없다(None)."""
    from app.core.interference import check_pairs
    from app.core.recipe.evaluate import _labeled_children

    children = _labeled_children(shape)
    if len(children) < 2:
        return None
    report = check_pairs(
        [(str(child.label), child) for child in children], cad.DEFAULT_INTERFERENCE_TOLERANCE
    )
    return report.summary()


def _tracking(
    recipe: dict[str, Any], conditions: dict[str, Any] | None, factors: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]] | None, dict[str, float], dict[tuple[int, int], follow.Track]]:
    """영역 정의와 **치수를 따라가는 자** — 스터디마다 한 번 잰다.

    **좌표가 든 선택 규칙은 치수를 따라간다**(core/recipe/follow.py) — 변수마다 조금씩 바꿔 그
    면이 얼마나 움직이는지 **한 번** 재 두고, 설계점마다 그만큼 옮겨 찾는다. 못 재면 따라가지
    않을 뿐 스터디는 돈다(예전과 같다)."""
    definitions = _region_definitions(conditions)
    base_values: dict[str, float] = {}
    tracks: dict[tuple[int, int], follow.Track] = {}
    if definitions:
        try:
            base_values = params.resolve_params(recipe)
            # 재료 · 고르기 · 배율 인자는 형상을 안 바꾸므로 잴 것이 없다 — 치수 인자만.
            shape_factors = [
                str(one["name"]) for one in factors if one.get("mode") not in engine.NON_SHAPE
            ]
            tracks = follow.measure(
                follow.resolved(definitions, base_values),
                base_values,
                shape_factors,
                _builder(recipe),
                skip=follow.written_near(definitions),
            )
        except (RecipeError, RecipeValidationError, params.ExpressionError):
            tracks = {}
    return definitions, base_values, tracks


class ShapePoint:
    """설계점 하나의 형상과 거기서 바로 나오는 것 — 영역 지문 · 겹침."""

    def __init__(
        self,
        evaluation: Any,
        topology_doc: dict[str, Any],
        interference: dict[str, Any] | None,
        moved: list[dict[str, Any]] | None = None,
    ) -> None:
        self.evaluation = evaluation
        self.topology = topology_doc
        self.interference = interference
        self.moved = moved
        """이 점의 값으로 옮긴 영역 정의 — 측정값(거리)이 같은 그룹을 다시 찾는다."""


def _shape_point(
    recipe: dict[str, Any],
    values: dict[str, Any],
    definitions: list[dict[str, Any]] | None,
    tracks: dict[tuple[int, int], follow.Track],
    base_values: dict[str, float],
) -> ShapePoint:
    """`recipe`(이 점의 값을 이미 덮은 것)로 형상을 만들고 영역을 찾는다. 만들기 작업과 「미리
    만들어 보기」 가 **같은 길**을 간다 — 다르면 미리 본 것이 실제와 어긋난다.

    **영역 지문을 STEP 옆에 나란히 쓴다.** STEP 은 이름표를 못 나르므로, 해석이 「어느 면이
    고정면인가」 를 물을 곳은 이 파일뿐이다. 설계점마다 좌표가 다르므로 점마다 한 장이다
    (topology.py 머리말). **조건의 이름표가 `divide_face` 패치를 가리킬 수 있다.** 그 번호는 이
    평가 안에서만 뜻이 있으므로 평가가 찾아 준 것을 그대로 넘긴다. 선택 규칙의 식은 **이
    설계점의 값으로** 푼다 — 그다음 좌표를 따라 옮긴다."""
    evaluation = evaluate(
        parse(recipe), resolve_file=resolve_import, resolve_component=resolve_component
    )
    moved = (
        follow.follow(
            follow.resolved(definitions, params.resolve_params(recipe)),
            tracks,
            base_values,
            values,
        )
        if definitions
        else definitions
    )
    topo = topology.document(evaluation.shape, moved, tags=evaluation.tags)
    if moved and tracks:
        _mark_drift(
            topo,
            follow.drift(
                moved,
                tracks,
                evaluation.shape,
                evaluation.tags,
                follow.tolerance_for(evaluation.shape),
            ),
        )
    # 조립이면 구성품끼리 겹치는지 — 변수를 바꾸다 부품이 판에 파묻히는 것을 잡는다. 형상이
    # 같으면 겹침도 같다.
    return ShapePoint(evaluation, topo, _interference_of(evaluation.shape), moved)


def _checking(
    recipe: dict[str, Any], checks: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """점검 기준과 **기준 형상**(도면 그대로)의 잰 값 — 설계점마다 견줄 바디 · 면 수.

    도면이 그대로는 안 만들어지면(드물다) 견주지 않을 뿐 점검은 한다."""
    limits = checking.thresholds(checks)
    if not limits["enabled"]:
        return limits, None
    try:
        made = evaluate(
            parse(recipe), resolve_file=resolve_import, resolve_component=resolve_component
        )
        return limits, checking.inspect(made.shape, limits)
    except Exception:  # 기준이 없으면 견주지 않는다 — 점검 자체는 점마다 한다.
        return limits, None


def _inspect(
    shape: Any, limits: dict[str, Any], reference: dict[str, Any] | None
) -> dict[str, Any] | None:
    """설계점 하나를 잰다 — 꺼 두었으면 None. 재다가 깨지면 그 사실을 경고로 남긴다(형상은
    만들어졌으니 점을 실패로 돌리지 않는다)."""
    if not limits["enabled"]:
        return None
    try:
        return checking.compare(checking.inspect(shape, limits), reference)
    except Exception as failure:
        return {
            "warnings": [f"형상 점검을 수행하지 못했습니다: {str(failure)[:120]}"],
            "notes": [],
        }


def _measure_point(
    measures: list[dict[str, Any]],
    made: ShapePoint | None,
    geometric: dict[str, float | None] | None,
    recipe: dict[str, Any],
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """점 하나의 측정값 — (형상에서 잰 것, 식까지 채운 전부). 형상이 같은 점은 앞의 것을
    그대로 받는다(`geometric`)."""
    if not measures:
        return {}, {}
    if geometric is None:
        geometric = (
            measuring.geometric(
                made.evaluation.shape,
                measures,
                topology_doc=made.topology,
                definitions=made.moved,
                tags=made.evaluation.tags,
            )
            if made is not None
            else {}
        )
    try:
        variables = params.resolve_params(recipe)
    except (params.ExpressionError, ArithmeticError, ValueError):
        variables = {}
    return geometric, measuring.derived(measures, variables, geometric)


def _measures(
    raw: list[dict[str, Any]] | None,
    recipe: dict[str, Any],
    conditions: dict[str, Any] | None,
    factors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """측정값 정의를 **만들기 전에** 본다 — 이름이 열과 겹치나, 선택 그룹 · 바디가 있나, 식이
    아는 이름만 부르나."""
    if not raw:
        return []
    try:
        variables = set(params.resolve_params(recipe))
    except params.ExpressionError:
        variables = set((recipe.get("params") or {}).keys())
    regions = {
        str(one.get("name"))
        for one in (conditions or {}).get("named_selections") or []
        if one.get("entity", "face") != "body"
    }
    try:
        return measuring.parse(
            raw,
            taken={str(one.get("name")) for one in factors},
            variables=variables,
            regions=regions,
            bodies=_body_names(recipe) if any(one.get("body") for one in raw) else None,
        )
    except measuring.MeasureError as failure:
        raise AppError(code("DOE", 28), str(failure)) from failure


def _point_warnings(geometry: dict[str, Any] | None) -> list[str]:
    found = list(((geometry or {}).get("quality") or {}).get("warnings") or [])
    mid_error = (geometry or {}).get("mid_error")
    if mid_error:
        found.append(f"중간면: {mid_error}")
    return found


def _with_values(recipe: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """도면에 이 점의 형상 값을 덮는다."""
    return {**recipe, "params": {**(recipe.get("params") or {}), **values}}


def _build_shape(task: dict[str, Any]) -> dict[str, Any]:
    """형상 하나를 만들어 STEP 을 쓰고, 형상에서 나오는 것(영역 · 겹침 · 좌표계 · 점검 ·
    측정값)을 돌려준다. **다른 프로세스에서 돈다** — 받는 것도 주는 것도 사전 · 목록뿐이고
    DB 는 만지지 않는다(도면이 부르는 부품 · 가져온 STEP 은 제 연결로 찾는다).

    점마다 다른 것(조건 · 점 파일 · DB)은 부른 쪽이 붙인다 — 같은 형상을 여러 점이 나눠
    쓴다."""
    started = time.perf_counter()
    try:
        made = _shape_point(
            task["recipe"],
            task["values"],
            task["definitions"],
            task["tracks"],
            task["base_values"],
        )
        path = Path(task["step_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        shapes.write_step(made.evaluation.shape, path)
        mid: dict[str, Any] | None = None
        if task.get("midsurface"):
            # 셸 해석용 중간면 — 판이 아니면 실패가 아니라 그 점의 알림이다.
            from app.core.recipe.midsurface import MidSurfaceError, midsurface
            from app.core.recipe.midsurface import attach as attach_mid

            try:
                # 파트마다 따로 — 판이 아닌 파트(강체 지그 블록)는 그 파트만 `failed` 에
                # 남는다.
                surface = midsurface(
                    made.evaluation.shape,
                    task.get("mid_only"),
                    strict=False,
                    single_name=condition_model.ALL_BODIES,
                )
                summary = surface.summary()
                if surface.bodies:
                    mid_path = path.with_name(f"{path.stem}_mid.step")
                    shapes.write_step(surface.shape, mid_path)
                    mid = {"name": mid_path.name, "summary": summary}
                    # 쉘 파트에 걸린 영역을 중간면 기준으로도(지문마다 `mid`) — 쉘 요소에
                    # 하중 · 구속을 거는 자리다.
                    attach_mid(
                        made.topology["regions"],
                        made.evaluation.shape,
                        surface,
                        made.moved,
                        made.evaluation.tags,
                    )
                else:
                    reasons = "; ".join(
                        f"{one['name']}: {one['error']}" for one in summary["failed"]
                    )
                    mid = {"error": reasons[:300], "failed": summary["failed"]}
            except MidSurfaceError as failure:
                mid = {"error": str(failure)[:300]}
        geometric = (
            measuring.geometric(
                made.evaluation.shape,
                task["measures"],
                topology_doc=made.topology,
                definitions=made.moved,
                tags=made.evaluation.tags,
            )
            if task["measures"]
            else {}
        )
        return {
            "ok": True,
            "topology": made.topology,
            "interference": made.interference,
            "frames": made.evaluation.frames,
            "quality": _inspect(made.evaluation.shape, task["limits"], task["reference"]),
            "measures": geometric,
            "midsurface": mid,
            "ms": int((time.perf_counter() - started) * 1000),
        }
    except (RecipeError, RecipeValidationError, ValueError, RuntimeError) as failure:
        return {
            "ok": False,
            "error": str(failure)[:500],
            "ms": int((time.perf_counter() - started) * 1000),
        }


def _workers() -> int:
    """설계점을 몇 프로세스로 나눠 만드나 — 설정(`DOE_WORKERS`)이 0 이면 코어 수에 맞춘다
    (하나는 웹 · DB 몫으로 남기고 넷까지)."""
    configured = int(get_settings().doe_workers or 0)
    if configured > 0:
        return configured
    return max(1, min(4, (os.cpu_count() or 2) - 1))


def _pool_context() -> Any:
    """새 프로세스를 띄우는 길 — 리눅스는 **forkserver**: build123d 를 한 번 읽어 둔 깨끗한
    프로세스에서 갈라 나오므로 빨리 뜨고, 웹 · DB 연결을 물려받지 않는다. 없으면 spawn."""
    import multiprocessing

    if "forkserver" in multiprocessing.get_all_start_methods():
        context = multiprocessing.get_context("forkserver")
        context.set_forkserver_preload(["app.modules.doe.services"])
        return context
    return multiprocessing.get_context("spawn")


def _built_shapes(
    tasks: list[tuple[str, str, dict[str, Any]]], workers: int
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """만들 형상들 — 끝나는 차례대로 내준다. 일꾼이 하나거나 형상이 하나면 이 프로세스에서
    차례로(띄우는 값이 더 든다). 도중에 멈추면(부른 쪽의 오류) 남은 일은 거둔다."""
    if workers <= 1 or len(tasks) < 2:
        for key, relative, task in tasks:
            yield key, relative, _build_shape(task)
        return
    pool = ProcessPoolExecutor(
        max_workers=min(workers, len(tasks)), mp_context=_pool_context()
    )
    try:
        futures = {
            pool.submit(_build_shape, task): (key, relative) for key, relative, task in tasks
        }
        for future in as_completed(futures):
            key, relative = futures[future]
            yield key, relative, future.result()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def run_job(
    input: dict[str, Any], options: dict[str, Any], out_dir: Path, progress: registry.Progress
) -> registry.Outcome:
    """Job kind="doe" — 점마다 형상을 만들어 **서버 보관 폴더**에 STEP 을 쓴다.

    작업 함수는 웹을 모르지만 **DB 는 본다** — 설계점이 수십 개라 결과를 그때그때 적어야
    화면이 진행을 보여 줄 수 있다(다 끝나고 한꺼번에 적으면 5 분 동안 빈 표를 본다).

    `input["only"] == "failed"` 면 실패한 점만 다시 한다. 다만 **파일이 사라진 점은 `ok`
    였어도 다시 만든다** — 폴더가 치워진 뒤의 「다시 만들기」 가 이 길로 오고, 그때 반쪽짜리
    폴더를 내주면 안 된다. 건너뛴 점도 표에는 제 줄을 그대로 쓴다(표는 늘 온전해야 한다).

    **같은 형상은 한 번만 만든다.** 조건만 훑으면(압력 2 · 3 MPa) 설계점마다 형상이 똑같다 —
    그것을 N 벌 만들어 N 벌 쓰면 시간도 파일도 N 배다. 만들기 전에 지문으로 가려내고
    (`shape_digest`), 둘 이상이 나눠 쓰는 형상은 `shapes/<지문>.step` 에 한 벌만 둔다.

    **형상은 여러 프로세스가 나눠 만든다**(`doe_workers`, 기본은 코어 수에 맞춰 넷까지) —
    만드는 것이 거의 전부라 점이 많으면 그만큼 빨라진다. DB · 조건 · 점 파일은 이 프로세스가
    붙인다."""
    del options, out_dir
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        study = db.get(DoeStudy, uuid.UUID(str(input["study_id"])))
        if study is None:
            raise registry.UserFacingError("실험계획이 존재하지 않습니다.")
        folder = Path(study.local_dir)
        (folder / "points").mkdir(parents=True, exist_ok=True)
        factor_names = [one["name"] for one in study.factors]
        measure_list = list(study.measures or [])
        columns = files.manifest_columns(
            factor_names,
            [one["name"] for one in measure_list],
            midsurface="midsurface" in (study.outputs or []),
        )
        rows: list[dict[str, Any]] = []
        made = 0
        failed = 0
        # **물성 이름 사전은 한 번만 가져온다.** 설계점마다 부르면 MatNexus 가 우리 때문에
        # 바쁘다. 못 가져와도 값은 나간다 — 표준 열쇠만 안 붙는다(덤이다).
        from app.shared.clients import matnexus as _matnexus

        names = _matnexus.property_keys()
        # **솔버 덱은 스터디마다 한 번.** 설계점이 달라도 물성은 같다 — 점마다 뽑으면 같은
        # 파일을 200번 만든다. 폴더 하나에 한 벌 두고 점 파일이 그것을 가리킨다.
        decks = _write_decks(folder, _deck_conditions(study.conditions, study.factors))
        only = str(input.get("only") or "all")
        all_points = points(db, study)
        # **만들기 전에** 어느 점끼리 형상이 같은지 안다 — 식을 푸는 것은 산수라 거저다.
        digests = {
            one.number: shape_digest(
                {
                    **study.recipe,
                    "params": {
                        **(study.recipe.get("params") or {}),
                        **_shape_params(study, one.params),
                    },
                }
            )
            for one in all_points
        }
        # 둘 이상이 나눠 쓰는 것만 `shapes/` 로 뺀다 — 형상 훑기(흔한 쪽)에서는 이름이 예전
        # 그대로 `points/pNNNN.step` 이고, 이름이 바뀌면 그것이 곧 「나눠 쓴다」 는 뜻이다.
        shared = {one for one, many in Counter(digests.values()).items() if one and many > 1}
        # **좌표가 든 선택 규칙은 치수를 따라간다**(core/recipe/follow.py) — 변수마다 조금씩
        # 바꿔 그 면이 얼마나 움직이는지 **한 번** 재 두고, 설계점마다 그만큼 옮겨 찾는다.
        # 못 재면 따라가지 않을 뿐 스터디는 돈다(예전과 같다).
        definitions, base_values, tracks = _tracking(
            study.recipe, study.conditions, study.factors
        )
        limits, reference = _checking(study.recipe, study.checks)
        # **만들 점을 형상 지문으로 묶는다** — 형상마다 한 번만 만들고, 여럿이면 여러
        # 프로세스로 나눠 만든다(`doe_workers`). 형상이 나오는 대로 그 형상을 쓰는 점들을
        # 마무리한다(조건 · 점 파일 · DB · 표). 만들지 않는 점은 표에 제 줄을 그대로 쓴다.
        groups: dict[str, list[DoePoint]] = {}
        for point in all_points:
            if _needs_build(folder, point, only):
                digest = digests.get(point.number, "")
                groups.setdefault(digest or f"#{point.number}", []).append(point)
                continue
            if point.status == "failed":
                # 점을 더할 때 건드리지 않은 실패 — 표에는 그대로 실패로 적는다.
                failed += 1
                rows.append(
                    files.manifest_row(
                        point.number,
                        point.params,
                        factor_names,
                        status="failed",
                        error=point.error,
                    )
                )
                continue
            made += 1
            rows.append(
                files.manifest_row(
                    point.number,
                    point.params,
                    factor_names,
                    status="ok",
                    step_file=point.step_file,
                    point_file=point.point_file,
                    unresolved=(point.geometry or {}).get("topology_unresolved"),
                    interference=(point.geometry or {}).get("interference"),
                    warnings=_point_warnings(point.geometry),
                    measures=(point.geometry or {}).get("measures"),
                    mid_file=(point.geometry or {}).get("mid_file") or "",
                )
            )
        tasks: list[tuple[str, str, dict[str, Any]]] = []
        for key, members in groups.items():
            first = members[0]
            digest = digests.get(first.number, "")
            # 둘 이상이 나눠 쓰는 형상만 `shapes/<지문>.step` — 아니면 예전 이름 그대로.
            relative = (
                f"shapes/{digest}.step"
                if digest in shared
                else f"points/p{first.number:04d}.step"
            )
            values = _shape_params(study, first.params)
            tasks.append(
                (
                    key,
                    relative,
                    {
                        "recipe": _with_values(study.recipe, values),
                        "values": values,
                        "definitions": definitions,
                        "tracks": tracks,
                        "base_values": base_values,
                        "limits": limits,
                        "reference": reference,
                        "measures": measure_list,
                        "midsurface": "midsurface" in (study.outputs or []),
                        # 쉘로 푸는 파트만 — 없으면(중간면만 고른 스터디) 판 모양 파트 전부.
                        "mid_only": condition_model.shell_parts(study.conditions) or None,
                        "step_path": str(folder / relative),
                    },
                )
            )
        #: 사람이 멈추라고 했으면(진행을 적다가 안다) 그때까지 만든 점의 표를 쓰고 멈춘다.
        stopped: registry.Cancelled | None = None
        try:
            for key, relative, result in _built_shapes(tasks, _workers()):
                for order, point in enumerate(groups[key]):
                    try:
                        if not result["ok"]:
                            raise RuntimeError(result["error"])
                        point.step_file = relative
                        topo = deepcopy(result["topology"])
                        interference = deepcopy(result["interference"])
                        cad_frames = deepcopy(result["frames"])
                        found = deepcopy(result["quality"])
                        recipe = _with_values(study.recipe, _shape_params(study, point.params))
                        measured: dict[str, float | None] = {}
                        if measure_list:
                            try:
                                variables = params.resolve_params(recipe)
                            except (params.ExpressionError, ArithmeticError, ValueError):
                                variables = {}
                            measured = measuring.derived(
                                measure_list, variables, result["measures"]
                            )
                        point.status = "ok"
                        point.error = ""
                        if measured:
                            # 형상에서 바로 나오는 값 — 해석 쪽이 목표 · 제약으로 쓴다.
                            topo["measures"] = measured
                        mid_file, mid_error = "", ""
                        mid = result.get("midsurface")
                        if mid and mid.get("name"):
                            # 형상 STEP 곁에 — 나눠 쓰는 형상이면 `shapes/` 에 같이 있다.
                            mid_file = str(Path(relative).with_name(mid["name"]))
                            topo["midsurface"] = {"step_file": mid_file, **mid["summary"]}
                        elif mid:
                            mid_error = str(mid.get("error") or "")
                            topo["midsurface"] = {
                                "error": mid_error,
                                **({"failed": mid["failed"]} if mid.get("failed") else {}),
                            }
                        if found is not None:
                            # 메시가 막힐 자리(얇은 벽 · 짧은 모서리 · 좁은 면 · 쪼개진 바디) —
                            # 해석이 200점 중에서 하나씩 찾게 두지 않는다.
                            topo["quality"] = found
                        # **이 점이 무엇인가**를 파일이 스스로 말하게 한다 — 결과가 우리에게
                        # 돌아오지 않으므로, 해석 쪽은 파일만 보고 「이 결과가 두께 8 짜리」 를
                        # 알아야 한다.
                        topo["point"] = {
                            "number": point.number,
                            "study": {
                                "id": str(study.id),
                                "name": study.name,
                                "method": study.method,
                                "seed": study.seed,
                            },
                            "params": point.params,
                            # **`point.step_file` 을 그대로 쓴다.** 여기서 경로를 다시 지으면
                            # 어긋난다 — 나눠 쓰는 형상은 `shapes/` 에 있는데 `points/` 라고
                            # 적어 두고 있었다(살아 있는 서버로 한 바퀴 돌려 보다 잡았다,
                            # 2026-09-24). 해석 쪽이 형상을 찾을 곳은 이 칸뿐이다.
                            "step_file": point.step_file,
                        }
                        # **점 하나 = 파일 하나.** 영역과 조건은 늘 짝으로 읽히므로 나눠 두면
                        # 「하나는 있고 하나는 없는」 상태가 생길 자리만 는다.
                        if study.conditions:
                            # 값은 mm · N · t 로 적혔고, 여기서 내보내기 단위계로 옮긴다.
                            # 재료 인자면 이 점의 재료를 바꿔 끼운 조건으로 — 치수는 형상 값만.
                            # **식은 도면 변수 전체에 이 점의 값을 덮어** 푼다 — 인자로 안 준
                            # 변수(압력처럼 형상에 안 쓰는 것)를 부르면 모든 점이 「모르는
                            # 이름」 으로 실패했다.
                            topo["conditions"] = _with_scales(
                                study,
                                point.params,
                                condition_model.resolve(
                                    _point_conditions(study, point.params),
                                    {
                                        **(study.recipe.get("params") or {}),
                                        **_shape_params(study, point.params),
                                    },
                                    names,
                                ),
                            )
                        # **좌표계** — 도면의 것은 이 점의 치수로 푼 것, 조건의 것은 식을 이
                        # 점의 값으로 풀고 면에 붙인 것은 이 점의 영역에서 얻는다. 조건의 `cs`
                        # 가 이름으로 가리킨다. 그룹을 못 풀어 좌표계를 못 정하면 「못 풀었다」
                        # — 조용히 전역으로 바꾸면 성분이 딴 방향으로 걸린다.
                        condition_side, missing = frames.condition_frames(
                            (topo.get("conditions") or {}).get("coordinate_systems") or [],
                            topo["regions"],
                        )
                        # **길이 단위를 파일이 스스로 말한다.** 형상(STEP) · 영역은 도면의 mm
                        # 이고, 좌표계 원점은 조건의 값과 같은 계로 옮긴다 — 원격점 · 회전축
                        # 자리가 mm 로 남으면 SI 로 푼 조건과 1000 배 어긋난다.
                        system = str(
                            ((topo.get("conditions") or {}).get("units") or {}).get("system")
                            or ""
                        )
                        placed, frame_length = frames.in_system(
                            [*cad_frames, *condition_side], system
                        )
                        topo["length_units"] = {
                            "geometry": "mm",
                            "regions": "mm",
                            # 중간면의 두께 · 넓이 · 무게중심 · 경계상자도 도면의 mm 다 — 쉘
                            # 두께를 해석 계로 읽으면 SI 에서 1000 배 틀린다.
                            "midsurface": "mm",
                            "coordinate_systems": frame_length,
                        }
                        if placed:
                            topo["coordinate_systems"] = placed
                        for name in missing:
                            if name not in topo["unresolved"]:
                                topo["unresolved"].append(name)
                        # **솔버 덱은 폴더에 한 벌**이고 점마다 같다 — 점 파일은 가리키기만
                        # 한다. 재료를 훑으면 점마다 어느 덱이 어느 바디에 붙는지가 다르다.
                        point_decks = _decks_for_point(decks, topo.get("conditions") or {})
                        if point_decks:
                            topo["material_decks"] = point_decks
                        point_name = f"p{point.number:04d}.json"
                        (folder / "points" / point_name).write_text(
                            json.dumps(topo, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        point.point_file = f"points/{point_name}"
                        point.geometry = {
                            "interference": interference,
                            # manifest.csv 를 나중에 다시 그릴 때(내려받기 API)도
                            # 같은 값을 적어야 한다.
                            "topology_unresolved": topo["unresolved"],
                            "quality": found,
                            "measures": measured or None,
                            "mid_file": mid_file or None,
                            "mid_error": mid_error or None,
                        }
                        made += 1
                        rows.append(
                            files.manifest_row(
                                point.number,
                                point.params,
                                factor_names,
                                status="ok",
                                step_file=point.step_file,
                                point_file=point.point_file,
                                unresolved=topo["unresolved"],
                                interference=point.geometry["interference"],
                                warnings=_point_warnings(point.geometry),
                                measures=measured,
                                mid_file=mid_file,
                            )
                        )
                    except (
                        RecipeError,
                        RecipeValidationError,
                        ValueError,
                        RuntimeError,
                    ) as failure:
                        point.status = "failed"
                        point.error = str(failure)[:500]
                        failed += 1
                        rows.append(
                            files.manifest_row(
                                point.number,
                                point.params,
                                factor_names,
                                status="failed",
                                error=point.error,
                            )
                        )
                    db.commit()
                    progress(
                        f"point-{point.number}",
                        int(result.get("ms") or 0) if order == 0 else 0,
                        f"{made + failed}/{study.point_count}",
                    )
        except registry.Cancelled as stop:
            stopped = stop
            # 못 만든 점도 표에 제 줄을 둔다 — 「다시 만들기」 가 그 점들을 잇는다.
            written = {int(row["point"]) for row in rows}
            for point in all_points:
                if point.number not in written:
                    rows.append(
                        files.manifest_row(
                            point.number,
                            point.params,
                            factor_names,
                            status="pending",
                            error=(
                                "취소되어 중단되었습니다. "
                                "‘재생성’으로 이어서 생성할 수 있습니다."
                            ),
                        )
                    )
        # 여러 프로세스가 끝나는 차례대로 왔다 — 표는 번호 차례로.
        rows.sort(key=lambda row: int(row["point"]))
        files.write_manifest(folder, columns, rows)
        files.write_study(
            folder,
            {
                "id": str(study.id),
                "name": study.name,
                "description": study.description,
                "method": study.method,
                "samples": study.samples,
                "seed": study.seed,
                "factors": study.factors,
                "constraints": study.constraints or [],
                # 점마다 잰 값의 정의 — 표의 측정값 열이 무엇인지.
                "measures": study.measures or [],
                # 만든 뒤 **더한** 묶음 — 방식 · 시드 · 범위 · 번호 구간. 첫 묶음은 위의
                # 칸이다.
                "batches": study.batches or [],
                # 형상 점검의 기준(mm) — 표의 `warnings` 가 무엇에 견준 것인지.
                "checks": checking.thresholds(study.checks),
                "recipe": study.recipe,
                "conditions": study.conditions,
                # **누가 시켰나.** 「폴더 하나가 자기를 설명한다」 는 원칙을 이 칸이 어기고
                # 있었다 — 해석하는 사람이 폴더를 열고 누구에게 물어야 할지 몰랐다.
                # 기계(오케스트레이터)가 만들면 더 그렇다.
                "owner": _owner_of(db, study),
                # **누가 실제로 돌렸나** — 기계가 대행했으면 여기가 그 서비스 계정이다.
                # 폴더를 연 사람이 「이게 뭐고 누구에게 물어야 하나」 를 폴더만 보고 알아야
                # 한다: 물어볼 사람은 owner 이고, 다시 돌릴 쪽은 requested_by 다.
                "requested_by": (
                    _person(db, study.requested_by_id) if study.requested_by_id else None
                ),
            },
        )
        files.write_conditions(folder, study.conditions)
        files.write_readme(
            folder,
            {
                "name": study.name,
                "description": study.description,
                "method": study.method,
                "seed": study.seed,
                "factors": study.factors,
                "constraints": study.constraints or [],
                "outputs": list(study.outputs or []),
            },
            study.point_count,
        )
        if stopped is not None:
            raise stopped
        return registry.Outcome(
            summary={
                "points": study.point_count,
                "ok": made,
                "failed": failed,
                "folder": files.windows_path(folder),
            }
        )
    finally:
        db.close()
