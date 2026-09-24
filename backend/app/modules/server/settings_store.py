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
    "doe_gallery_max": Known(
        key="doe_gallery_max",
        label="실험계획 형상 보기 — 한 번에 그리는 수",
        description=(
            "겹쳐 보기 · 나란히에서 한 번에 화면에 올리는 형상 수. 넘게 고르면 쪽으로 나눠 "
            "넘긴다. 브라우저가 그리는 양이라 크게 잡으면 느려지고, 겹쳐 보기는 열둘을 넘으면 "
            "색이 돌아 서로 구별이 안 된다."
        ),
        default=lambda: get_settings().doe_gallery_max,
        minimum=1,
        maximum=100,
    ),
    "list_page_size": Known(
        key="list_page_size",
        label="목록 한 쪽에 보이는 줄 수",
        description=(
            "실험계획 · 내 작업 · 부품 · 지그 · 템플릿 · 실행 기록 목록이 한 쪽에 보여 주는 "
            "줄 수. 크게 잡으면 한 화면에 많이 보이지만 목록을 받는 데 오래 걸린다."
        ),
        default=lambda: get_settings().list_page_size,
        minimum=5,
        maximum=200,
    ),
    "doe_export_ttl_days": Known(
        key="doe_export_ttl_days",
        label="실험계획 공유 폴더 보관 기한(일)",
        description=(
            "해석이 읽는 공유 폴더에 스터디 폴더를 며칠 두는가. 지나면 "
            "**공유 폴더의 사본만** 지운다 — 서버 보관 폴더와 설정은 남아서 「보내기」 를 "
            "다시 누르면 같은 폴더가 다시 선다. 0 이면 자동 삭제를 안 한다. 스터디마다 "
            "「영구보관」 을 켜면 기한과 무관하게 남는다."
        ),
        default=lambda: get_settings().doe_export_ttl_days,
        minimum=0,
        maximum=3650,
    ),
    "doe_local_ttl_days": Known(
        key="doe_local_ttl_days",
        label="실험계획 서버 보관 폴더 보관 기한(일)",
        description=(
            "서버가 설계점 파일(STEP · 점 파일)을 며칠 두는가. 지나면 **파일만** 지운다 — "
            "스터디와 설계점 목록 · 레시피 스냅샷은 남으므로 화면은 그대로 뜨고, "
            "「다시 만들기」 를 누르면 같은 파일이 다시 선다. 공유 폴더보다 길게 잡는다 "
            "(여기가 「보내기」 의 복사원이다). 0 이면 자동 삭제를 안 한다. 스터디마다 "
            "「영구보관」 을 켜면 두 폴더 모두 기한과 무관하게 남는다."
        ),
        default=lambda: get_settings().doe_local_ttl_days,
        minimum=0,
        maximum=3650,
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


def display(db: Session) -> dict[str, int]:
    """화면이 쓰는 값 — 관리자가 아니어도 읽어야 목록 · 형상 보기가 그 수를 지킨다."""
    return {
        "doe_gallery_max": get_int(db, "doe_gallery_max"),
        "list_page_size": get_int(db, "list_page_size"),
    }


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
