"""관리자가 바꾸는 서버 설정의 목록과 읽기 · 쓰기.

새 설정은 `KNOWN` 에 한 줄 더한다 — 이름 · 설명 · 범위 · .env 기본값. 모르는 키는 받지 않는다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.server.models import ServerSetting
from app.shared.errors import AppError, code


@dataclass(frozen=True)
class Known:
    key: str
    label: str
    description: str
    default: Callable[[], int]
    minimum: int
    maximum: int


KNOWN: dict[str, Known] = {
    "doe_max_points": Known(
        key="doe_max_points",
        label="실험계획 설계점 상한",
        description=(
            "한 번에 만드는 설계점 수. 점마다 형상을 평가하고 STEP 을 쓰므로(점당 수백 ms ~ "
            "수 초) 너무 크면 한 요청이 서버를 오래 잡는다."
        ),
        default=lambda: get_settings().doe_max_points,
        minimum=1,
        maximum=5000,
    ),
    "doe_max_samples": Known(
        key="doe_max_samples",
        label="DOE LHS 표본 수 상한",
        description=(
            "라틴 하이퍼큐브로 뽑을 수 있는 표본 수. 설계점 상한이 먼저 걸리므로 보통 그와 "
            "같거나 그보다 크게 둔다."
        ),
        default=lambda: get_settings().doe_max_samples,
        minimum=1,
        maximum=20000,
    ),
}


def get_int(db: Session, key: str) -> int:
    """설정값 — DB 에 있으면 그것, 없으면 .env 기본값."""
    known = KNOWN[key]
    row = db.get(ServerSetting, key)
    if row is None or row.value is None:
        return known.default()
    return int(row.value)


def doe_max_points(db: Session) -> int:
    return get_int(db, "doe_max_points")


def doe_max_samples(db: Session) -> int:
    return get_int(db, "doe_max_samples")


def listing(db: Session) -> list[dict[str, Any]]:
    out = []
    for known in KNOWN.values():
        row = db.get(ServerSetting, known.key)
        out.append(
            {
                "key": known.key,
                "label": known.label,
                "description": known.description,
                "value": get_int(db, known.key),
                "default": known.default(),
                "overridden": row is not None and row.value is not None,
                "minimum": known.minimum,
                "maximum": known.maximum,
                "updated_at": row.updated_at if row else None,
            }
        )
    return out


def set_int(db: Session, key: str, value: int | None, *, by: uuid.UUID) -> None:
    """값을 넣는다. None 이면 덮어쓴 것을 지워 .env 기본값으로 돌아간다."""
    known = KNOWN.get(key)
    if known is None:
        raise AppError(code("SERVER", 1), f"모르는 설정입니다: {key}")
    if value is not None and not (known.minimum <= value <= known.maximum):
        raise AppError(
            code("SERVER", 2),
            f"「{known.label}」 은 {known.minimum} ~ {known.maximum} 사이여야 합니다",
        )
    row = db.get(ServerSetting, key)
    if row is None:
        row = ServerSetting(key=key, value=value, updated_by=by)
        db.add(row)
    else:
        row.value = value
        row.updated_by = by
    db.commit()
