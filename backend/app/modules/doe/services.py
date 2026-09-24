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
import shutil
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import conditions as condition_model
from app.core import doe as engine
from app.core import export as shapes
from app.core.recipe import RecipeError, evaluate, parse, topology
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
from app.shared import filestore
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


def _samples(db: Session, raw: dict[str, Any]) -> int:
    """LHS 표본 수 — 상한은 관리자 설정. 넘으면 이유와 상한을 말한다."""
    samples = int(raw.get("samples") or 20)
    if raw.get("method", "factorial") == "lhs":
        limit = settings_store.doe_max_samples(db)
        if samples > limit:
            raise AppError(
                code("DOE", 14),
                f"LHS 표본 수 {samples} 는 상한 {limit} 을 넘습니다 — 관리자가 서버 설정에서 "
                "올릴 수 있습니다.",
            )
    return samples


def preview(db: Session, raw: dict[str, Any]) -> dict[str, Any]:
    """만들기 전에 **몇 개인지** 와 앞 몇 줄. 격자는 곱으로 늘어난다."""
    factors = _factors(raw.get("factors") or [])
    method = raw.get("method", "factorial")
    samples = _samples(db, raw)
    seed = int(raw.get("seed") or 1)
    total = engine.count(factors, method, samples)
    limit = settings_store.doe_max_points(db)
    rows: list[dict[str, float]] = []
    if total <= limit:
        rows = engine.build_points(
            factors, method=method, samples=samples, seed=seed, limit=limit
        )
    return {
        "count": total,
        "max": limit,
        "max_samples": settings_store.doe_max_samples(db),
        "too_many": total > limit,
        "points": rows[:20],
        "varying": [f.name for f in factors if f.varying],
    }


def _factors(raw: list[dict[str, Any]]) -> list[engine.Factor]:
    try:
        return engine.parse_factors(raw)
    except engine.DoeError as failure:
        raise AppError(code("DOE", 2), str(failure)) from failure


def _points(db: Session, raw: dict[str, Any]) -> list[dict[str, float]]:
    try:
        return engine.build_points(
            _factors(raw.get("factors") or []),
            method=raw.get("method", "factorial"),
            samples=_samples(db, raw),
            seed=int(raw.get("seed") or 1),
            limit=settings_store.doe_max_points(db),
        )
    except engine.DoeError as failure:
        raise AppError(code("DOE", 3), str(failure)) from failure


def _request_digest(
    *,
    recipe: dict[str, Any],
    factors: list[dict[str, Any]],
    method: str,
    samples: int,
    seed: int,
    conditions: dict[str, Any] | None,
    work_id: uuid.UUID | None,
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
    )


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
) -> tuple[DoeStudy, bool]:
    """스터디를 만들고 작업을 건다. 레시피와 **해석 조건**을 스냅샷으로 박는다.

    설계점은 **서버 보관 폴더**에 만든다. 공유 폴더로는 다 만들어진 뒤 「보내기」 로 간다 —
    해석이 읽는 폴더에 만들다 만 것이 보이면 안 된다.

    `idempotency_key` 를 주면 **두 번 불러도 한 벌**이다 — 이미 있으면 그것을 돌려준다
    (돌려준 것인지는 두 번째 값이 말한다). 기계는 재시도하고, 망이 끊겨 답을 못 받았을 뿐인데
    다시 걸면 스터디 둘 · 폴더 둘이 생겨 해석 쪽이 어느 것이 진짜인지 모른다.

    **열쇠를 우리가 지어 내지 않는다.** 「없으면 레시피 다이제스트로」 도 생각했지만, 그러면
    사람이 **같은 설정으로 한 벌 더** 만드는 정상적인 일이 막힌다(비교하려고 두 번 돌리는
    것은 흔하다). 열쇠를 안 주면 「멱등하지 않다」 는 뜻이고, 그것이 사람의 기본값이다.
    """
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
            )
            if digest_of(found) != asked:
                raise AppError(
                    code("DOE", 18),
                    f"같은 멱등 열쇠({idempotency_key})로 **다른 요청**이 왔습니다 — 이미 "
                    f"「{found.name}」 이 그 열쇠를 쓰고 있습니다. 열쇠를 바꾸거나 설정을 "
                    "맞추세요.",
                )
            return found, True
    try:
        parse(recipe)
    except RecipeValidationError as failure:
        raise AppError(
            code("DOE", 4),
            "레시피가 올바르지 않습니다",
            details={"problems": failure.problems},
        ) from failure
    params = recipe.get("params") or {}
    unknown = [one["name"] for one in factors if one.get("name") not in params]
    if unknown:
        known = ", ".join(sorted(params)) or "(없음)"
        raise AppError(
            code("DOE", 5),
            f"레시피에 없는 치수입니다: {', '.join(unknown)} — 있는 치수: {known}",
        )
    # **조건을 지금 검증한다.** 설계점 마흔 개를 만든 뒤에 「그런 이름표가 없다」 를 알면
    # 늦다 — 그때는 폴더에 반쪽짜리가 남는다.
    try:
        condition_model.parse(conditions)
    except condition_model.ConditionError as failure:
        raise AppError(code("DOE", 15), f"해석 조건: {failure}") from failure
    rows = _points(
        db, {"factors": factors, "method": method, "samples": samples, "seed": seed}
    )
    study = DoeStudy(
        name=name.strip(),
        description=description.strip(),
        owner_id=owner.id,
        idempotency_key=idempotency_key,
        work_id=work_id,
        recipe=recipe,
        conditions=conditions or {},
        factors=factors,
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
        requested_by=owner,
        work_id=work_id,
        input={"study_id": str(study.id)},
        options={},
    )
    study.job_id = job.id
    db.commit()
    db.refresh(study)
    return study, False


def get_study(db: Session, study_id: uuid.UUID, viewer: User) -> DoeStudy:
    study = db.get(DoeStudy, study_id)
    if study is None:
        raise NotFound(code("DOE", 6), "실험계획을 찾을 수 없습니다.")
    if study.owner_id != viewer.id and not viewer.is_system_admin:
        raise Forbidden(code("DOE", 7), "남의 실험계획입니다.")
    return study


def list_studies(
    db: Session, viewer: User, *, work_id: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[DoeStudy], int]:
    statement = select(DoeStudy).where(DoeStudy.owner_id == viewer.id)
    if work_id is not None:
        statement = statement.where(DoeStudy.work_id == work_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(
        statement.order_by(DoeStudy.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def points(db: Session, study: DoeStudy) -> list[DoePoint]:
    return list(
        db.scalars(
            select(DoePoint).where(DoePoint.study_id == study.id).order_by(DoePoint.number)
        ).all()
    )


#: 점 메시는 다시 계산하면 그만이라 DB 에 두지 않는다. 화면이 「하나씩 · 겹쳐 · 나란히」 넘길
#: 때 같은 점을 거듭 묻으므로 최근 것을 든다. 스냅샷은 바뀌지 않으니 (study, number) 로 족하다.
_MESH_CACHE: OrderedDict[tuple[uuid.UUID, int], dict[str, Any]] = OrderedDict()
_MESH_CACHE_SIZE = 64


def point_mesh(db: Session, study: DoeStudy, number: int) -> dict[str, Any]:
    """설계점 하나의 형상 — 스냅샷 레시피에 그 점의 값을 넣어 **다시 만든다.**

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
        raise NotFound(code("DOE", 12), f"설계점 {number} 이 없습니다.")
    if point.status != "ok":
        raise AppError(
            code("DOE", 13),
            "이 점은 형상이 없습니다 — " + (point.error or "아직 만드는 중입니다.")[:200],
        )
    recipe = {
        **study.recipe,
        "params": {**(study.recipe.get("params") or {}), **point.params},
    }
    evaluation = cad.build(recipe)
    made = {
        "number": number,
        "params": point.params,
        "summary": evaluation.summary(),
        "mesh": mesh(evaluation.shape),
    }
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
    }


def _needs_build(folder: Path, point: DoePoint, only: str) -> bool:
    """이 점을 다시 만들어야 하나 — 다 하라고 했거나, 실패했거나, **파일이 사라졌거나.**

    작업 함수와 「다시 만들기」 가 **같은 규칙을 본다.** 다르면 화면의 진행 표시가 건너뛴 점을
    두고 거짓말을 한다."""
    if only != "failed" or point.status != "ok":
        return True
    return not (point.step_file and (folder / point.step_file).exists())


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
        raise AppError(code("DOE", 16), "only 는 all 또는 failed 입니다.")
    job = db.get(Job, study.job_id) if study.job_id else None
    if job is not None and job.status in ("queued", "running"):
        raise AppError(code("DOE", 17), "아직 만드는 중입니다 — 끝나면 다시 만들 수 있습니다.")
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
        raise AppError(code("DOE", 9), "아직 만드는 중입니다 — 끝나면 보낼 수 있습니다.")
    source = Path(study.local_dir)
    if not (source / "manifest.csv").exists():
        # 둘을 갈라 말한다 — 「없다」 는 같아도 할 일이 다르다. 만들다 만 것이면 기다릴 일,
        # 치워진 것이면 「다시 만들기」 를 누를 일이다.
        made = any(one.status == "ok" for one in points(db, study))
        raise AppError(
            code("DOE", 10),
            "서버 보관 폴더가 정리되었습니다 — 「다시 만들기」 를 먼저 누르세요."
            if made
            else "보낼 것이 없습니다 — 설계점이 하나도 만들어지지 않았습니다.",
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


def _owner_of(db: Session, study: DoeStudy) -> dict[str, str]:
    """만든 사람 — 이름과 계정. 없으면 빈 칸이지 거짓말은 안 한다."""
    user = db.get(User, study.owner_id) if study.owner_id else None
    if user is None:
        return {"name": "", "email": ""}
    return {"name": user.display_name or "", "email": user.email or ""}


def _region_definitions(conditions: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """조건의 이름표를 **영역 정의**로 — 내보낼 때 그 이름으로 좌표가 나간다.

    조건이 없으면 None 을 돌려 기본 영역(`fixed_base` · `bolt_holes`)으로 간다. 사람이 이름표를
    지었으면 그것이 곧 해석이 부를 이름이다 — 우리가 다시 이름 짓지 않는다.
    """
    names = (conditions or {}).get("named_selections") or []
    if not names:
        return None
    return [
        {"name": one["name"], "select": one.get("select") or {}}
        for one in names
        if one.get("name")
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


def run_job(
    input: dict[str, Any], options: dict[str, Any], out_dir: Path, progress: registry.Progress
) -> registry.Outcome:
    """Job kind="doe" — 점마다 형상을 만들어 **서버 보관 폴더**에 STEP 을 쓴다.

    작업 함수는 웹을 모르지만 **DB 는 본다** — 설계점이 수십 개라 결과를 그때그때 적어야
    화면이 진행을 보여 줄 수 있다(다 끝나고 한꺼번에 적으면 5 분 동안 빈 표를 본다).

    `input["only"] == "failed"` 면 실패한 점만 다시 한다. 다만 **파일이 사라진 점은 `ok`
    였어도 다시 만든다** — 폴더가 치워진 뒤의 「다시 만들기」 가 이 길로 오고, 그때 반쪽짜리
    폴더를 내주면 안 된다. 건너뛴 점도 표에는 제 줄을 그대로 쓴다(표는 늘 온전해야 한다)."""
    del options, out_dir
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        study = db.get(DoeStudy, uuid.UUID(str(input["study_id"])))
        if study is None:
            raise registry.UserFacingError("실험계획이 사라졌습니다")
        folder = Path(study.local_dir)
        (folder / "points").mkdir(parents=True, exist_ok=True)
        factor_names = [one["name"] for one in study.factors]
        columns = files.manifest_columns(factor_names)
        rows: list[dict[str, Any]] = []
        made = 0
        failed = 0
        only = str(input.get("only") or "all")
        for point in points(db, study):
            started = time.perf_counter()
            if not _needs_build(folder, point, only):
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
                    )
                )
                continue
            recipe = {
                **study.recipe,
                "params": {**(study.recipe.get("params") or {}), **point.params},
            }
            try:
                evaluation = evaluate(
                    parse(recipe),
                    resolve_file=resolve_import,
                    resolve_component=resolve_component,
                )
                name = f"p{point.number:04d}.step"
                shapes.write_step(evaluation.shape, folder / "points" / name)
                point.status = "ok"
                point.step_file = f"points/{name}"
                # **영역 지문을 STEP 옆에 나란히 쓴다.** STEP 은 이름표를 못 나르므로, 해석이
                # 「어느 면이 고정면인가」 를 물을 곳은 이 파일뿐이다. 설계점마다 좌표가
                # 다르므로 점마다 한 장이다(topology.py 머리말).
                # **조건의 이름표가 `divide_face` 패치를 가리킬 수 있다.** 그 번호는 이
                # 평가 안에서만 뜻이 있으므로 평가가 찾아 준 것을 그대로 넘긴다.
                definitions = _region_definitions(study.conditions)
                topo = topology.document(evaluation.shape, definitions, tags=evaluation.tags)
                # **이 점이 무엇인가**를 파일이 스스로 말하게 한다 — 결과가 우리에게 돌아오지
                # 않으므로, 해석 쪽은 파일만 보고 「이 결과가 두께 8 짜리」 를 알아야 한다.
                topo["point"] = {
                    "number": point.number,
                    "study": {
                        "id": str(study.id),
                        "name": study.name,
                        "method": study.method,
                        "seed": study.seed,
                    },
                    "params": point.params,
                    "step_file": f"points/{name}",
                }
                # **점 하나 = 파일 하나.** 영역과 조건은 늘 짝으로 읽히므로 나눠 두면
                # 「하나는 있고 하나는 없는」 상태가 생길 자리만 는다.
                if study.conditions:
                    topo["conditions"] = condition_model.resolve(
                        study.conditions, point.params
                    )
                point_name = f"p{point.number:04d}.json"
                (folder / "points" / point_name).write_text(
                    json.dumps(topo, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                point.point_file = f"points/{point_name}"
                # 조립이면 구성품끼리 겹치는지 — 변수를 바꾸다 부품이 판에 파묻히는 것을
                # 잡는다.
                point.geometry = {
                    "interference": _interference_of(evaluation.shape),
                    # manifest.csv 를 나중에 다시 그릴 때(내려받기 API)도
                    # 같은 값을 적어야 한다.
                    "topology_unresolved": topo["unresolved"],
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
                    )
                )
            except (RecipeError, RecipeValidationError, ValueError, RuntimeError) as failure:
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
                int((time.perf_counter() - started) * 1000),
                f"{made + failed}/{study.point_count}",
            )
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
                "recipe": study.recipe,
                "conditions": study.conditions,
                # **누가 시켰나.** 「폴더 하나가 자기를 설명한다」 는 원칙을 이 칸이 어기고
                # 있었다 — 해석하는 사람이 폴더를 열고 누구에게 물어야 할지 몰랐다.
                # 기계(오케스트레이터)가 만들면 더 그렇다.
                "owner": _owner_of(db, study),
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
            },
            study.point_count,
        )
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
