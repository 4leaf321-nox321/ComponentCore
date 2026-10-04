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
            "한 번에 생성하는 설계점 수의 상한입니다. 설계점마다 형상을 평가하고 STEP 파일을 "
            "기록하므로(설계점당 수백 ms~수 초) 값이 너무 크면 하나의 요청이 서버를 오래 "
            "점유합니다."
        ),
        default=lambda: get_settings().doe_max_points,
        minimum=1,
        maximum=5000,
    ),
    "doe_gallery_max": Known(
        key="doe_gallery_max",
        label="실험계획 형상 보기: 한 번에 표시하는 형상 수",
        description=(
            "겹쳐 보기와 나란히 보기에서 한 번에 화면에 표시하는 형상 수입니다. 이보다 많이 "
            "선택하면 페이지로 나누어 표시합니다. 브라우저에서 렌더링하므로 값이 크면 "
            "느려지며, 겹쳐 보기에서 12개를 넘으면 색상이 반복되어 형상을 구별하기 "
            "어렵습니다."
        ),
        default=lambda: get_settings().doe_gallery_max,
        minimum=1,
        maximum=100,
    ),
    "list_page_size": Known(
        key="list_page_size",
        label="목록 페이지당 행 수",
        description=(
            "실험계획, 내 작업, 부품, 지그, 템플릿, 실행 기록 목록의 페이지당 행 수입니다. "
            "값이 크면 한 화면에 많은 항목이 표시되지만 목록을 불러오는 시간이 길어집니다."
        ),
        default=lambda: get_settings().list_page_size,
        minimum=5,
        maximum=200,
    ),
    "doe_export_ttl_days": Known(
        key="doe_export_ttl_days",
        label="실험계획 공유 폴더 보관 기한(일)",
        description=(
            "해석에서 읽는 공유 폴더에 스터디 폴더를 보관하는 기간입니다. 기한이 지나면 공유 "
            "폴더의 사본만 삭제합니다. 서버 보관 폴더와 설정은 유지되므로 ‘내보내기’를 다시 "
            "실행하면 같은 폴더가 다시 생성됩니다. 0이면 자동으로 삭제하지 않습니다. "
            "스터디별로 ‘영구보관’을 설정하면 기한과 관계없이 보관됩니다."
        ),
        default=lambda: get_settings().doe_export_ttl_days,
        minimum=0,
        maximum=3650,
    ),
    "doe_local_ttl_days": Known(
        key="doe_local_ttl_days",
        label="실험계획 서버 보관 폴더 보관 기한(일)",
        description=(
            "서버에 설계점 파일(STEP, 점 파일)을 보관하는 기간입니다. 기한이 지나면 파일만 "
            "삭제합니다. 스터디, 설계점 목록, 레시피 스냅샷은 유지되므로 화면은 그대로 "
            "표시되며, ‘다시 생성’을 실행하면 같은 파일이 다시 생성됩니다. 공유 폴더보다 길게 "
            "설정하십시오(서버 보관 폴더가 ‘내보내기’의 원본입니다). 0이면 자동으로 삭제하지 "
            "않습니다. 스터디별로 ‘영구보관’을 설정하면 두 폴더 모두 기한과 관계없이 "
            "보관됩니다."
        ),
        default=lambda: get_settings().doe_local_ttl_days,
        minimum=0,
        maximum=3650,
    ),
    "doe_max_samples": Known(
        key="doe_max_samples",
        label="DOE LHS 표본 수 상한",
        description=(
            "라틴 하이퍼큐브로 추출할 수 있는 표본 수의 상한입니다. 설계점 상한이 먼저 "
            "적용되므로 보통 설계점 상한과 같거나 더 크게 설정합니다."
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
        raise AppError(code("SERVER", 1), f"알 수 없는 설정({key})입니다.")
    if value is not None and not (known.minimum <= value <= known.maximum):
        raise AppError(
            code("SERVER", 2),
            f"‘{known.label}’ 값은 {known.minimum}~{known.maximum} 사이여야 합니다.",
        )
    row = db.get(ServerSetting, key)
    if row is None:
        row = ServerSetting(key=key, value=value, updated_by=by)
        db.add(row)
    else:
        row.value = value
        row.updated_by = by
    db.commit()
