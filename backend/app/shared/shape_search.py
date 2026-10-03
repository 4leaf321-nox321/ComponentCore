"""형상으로 찾기 — 내 작업 · 부품 · 지그 목록을 **최신 버전의 형상 색인**으로 거른다.

색인은 버전을 평가한 작업의 요약(`jobs.summary.shape`, `core/shape_index.py`)에 있다. 목록은
「그 항목의 현재 버전 → 그 버전의 작업」 을 따라가 색인을 본다 — 형상을 다시 만들지 않는다.
색인이 없는 버전(이 기능 전에 만든 것)은 형상 조건을 주면 빠진다 — 서버 화면의 「형상 색인
채우기」 가 메운다.

조건(모두 주면 모두 맞아야):

- `has` — 들어 있는 것(`core/shape_index.FEATURES` 의 낱말 또는 연산 이름). 여럿이면 다.
- `thread` — 나사 호칭(M6), `param` — 변수 이름.
- `fits` — 「이 상자 안에 드나」(`100x60x30`, 놓인 방향과 상관없이 — 작은 변끼리 견준다).
- `volume_min` · `volume_max` — 부피(mm³).
- `hole` — 구멍 지름(± `hole_tol`), `holes` — 그 지름의 구멍이 몇 개 이상(지름 없이 주면
  모든 구멍의 수).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import Query
from sqlalchemy import Float, cast, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement, Select

from app.core.shape_index import FEATURES
from app.modules.jobs.models import Job
from app.shared.errors import AppError, code

_BAD = code("SEARCH", 1)
#: 변 하나 — 숫자. 변 사이는 x · X · 곱하기 기호(U+00D7) · *.
_SIDE = r"(\d+(?:\.\d+)?)"
_BY = r"\s*[xX\u00d7*]\s*"
_BOX = re.compile(rf"^\s*{_SIDE}{_BY}{_SIDE}(?:{_BY}{_SIDE})?\s*$")


@dataclass
class ShapeFilter:
    has: list[str] = field(default_factory=list)
    thread: str = ""
    param: str = ""
    fits: tuple[float, ...] | None = None
    volume_min: float | None = None
    volume_max: float | None = None
    hole: float | None = None
    hole_tol: float = 0.1
    holes: int | None = None

    @property
    def active(self) -> bool:
        return bool(
            self.has
            or self.thread
            or self.param
            or self.fits
            or self.volume_min is not None
            or self.volume_max is not None
            or self.hole is not None
            or self.holes is not None
        )


def _box(text: str) -> tuple[float, ...] | None:
    """`100x60x30` · `100x60`(두 변 — 판처럼 두께는 묻지 않는다) → 큰 변부터."""
    if not text.strip():
        return None
    found = _BOX.match(text)
    if not found:
        raise AppError(_BAD, f"fits: 「100x60x30」 꼴이어야 합니다 — 받은 값 {text!r}")
    values = [float(one) for one in found.groups() if one is not None]
    return tuple(sorted(values, reverse=True))


def shape_query(
    has: list[str] = Query(default=[], max_length=12),
    thread: str = Query(default="", max_length=12),
    param: str = Query(default="", max_length=40),
    fits: str = Query(default="", max_length=40),
    volume_min: float | None = Query(default=None, ge=0),
    volume_max: float | None = Query(default=None, ge=0),
    hole: float | None = Query(default=None, gt=0, le=10000),
    hole_tol: float = Query(default=0.1, ge=0, le=10),
    holes: int | None = Query(default=None, ge=1, le=10000),
) -> ShapeFilter:
    """목록 API 가 함께 받는 형상 조건 — `Depends(shape_query)`."""
    words = [one.strip() for one in has if one.strip()]
    return ShapeFilter(
        has=words,
        thread=thread.strip().upper(),
        param=param.strip(),
        fits=_box(fits),
        volume_min=volume_min,
        volume_max=volume_max,
        hole=hole,
        hole_tol=hole_tol,
        holes=holes,
    )


#: 「그 지름 범위의 구멍이 n 개 이상인 줄이 있나」 — 변수는 `$lo` · `$hi` · `$n`.
_HOLE_PATH = "$[*] ? (@.d >= $lo && @.d <= $hi && @.n >= $n)"


def _conditions(flt: ShapeFilter) -> list[ColumnElement[bool]]:
    """색인이 없는(null) 버전은 어느 조건에도 맞지 않는다 — 비교가 NULL 이 된다."""
    shape = Job.summary["shape"]
    out: list[ColumnElement[bool]] = []
    for word in flt.has:
        ops = FEATURES.get(word, (word,))
        out.append(or_(*[shape["ops"].contains([op]) for op in ops]))
    if flt.thread:
        out.append(shape["threads"].contains([flt.thread]))
    if flt.param:
        out.append(shape["params"].contains([flt.param]))
    if flt.fits:
        # 큰 변부터 견준다 — 두 변만 주면 큰 두 변만(판의 두께는 묻지 않는다).
        for rank, limit in enumerate(flt.fits):
            side = Job.summary[("shape", "dims", str(2 - rank))].astext
            out.append(cast(side, Float) <= limit + 1e-6)
    volume = cast(Job.summary[("shape", "volume")].astext, Float)
    if flt.volume_min is not None:
        out.append(volume >= flt.volume_min)
    if flt.volume_max is not None:
        out.append(volume <= flt.volume_max)
    if flt.hole is not None:
        bounds = {
            "lo": flt.hole - flt.hole_tol,
            "hi": flt.hole + flt.hole_tol,
            "n": flt.holes or 1,
        }
        out.append(
            func.jsonb_path_exists(
                shape["holes"],
                cast(literal(_HOLE_PATH), JSONPATH),
                literal(bounds, JSONB),
            )
        )
    elif flt.holes is not None:
        out.append(cast(Job.summary[("shape", "hole_count")].astext, Float) >= flt.holes)
    return out


def narrowed(
    base: Select[Any],
    flt: ShapeFilter,
    *,
    model: Any,
    version: Any,
    owner: Any,
) -> Select[Any]:
    """`base` 에 형상 조건을 — `model` 의 현재 버전(`version` 에서 `owner` 칸이 model 을
    가리키고 번호가 `current_version`)의 작업 요약으로."""
    if not flt.active:
        return base
    latest = (
        select(literal(1))
        .select_from(version)
        .join(Job, Job.id == version.job_id)
        .where(owner == model.id, version.number == model.current_version, *_conditions(flt))
    )
    return base.where(exists(latest))


def latest_shape(db: Session, job_id: Any) -> dict[str, Any] | None:
    """목록 한 줄에 붙이는 형상 — 그 버전의 작업 요약에서(없으면 None)."""
    if job_id is None:
        return None
    summary = db.scalar(select(Job.summary).where(Job.id == job_id))
    shape = (summary or {}).get("shape")
    if not isinstance(shape, dict) or "size" not in shape:
        return None  # 색인이 없거나 STEP 을 못 열어 비워 둔 것
    return {key: value for key, value in shape.items() if key not in ("version", "area")}
