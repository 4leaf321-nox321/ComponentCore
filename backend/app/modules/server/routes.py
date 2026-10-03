"""서버 상태 — 지금 뭐가 깔렸나, DB 는 맞춰져 있나, 무엇이 얼마나 쌓였나."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schema_version, version
from app.config import get_settings
from app.database import Base, engine, get_db
from app.modules.accounts.models import User
from app.modules.jigs.models import Jig
from app.modules.jobs import services as jobs
from app.modules.jobs.models import Artifact, Job
from app.modules.parts.models import Part
from app.modules.server import settings_store, shape_fill
from app.modules.server.schemas import (
    DiskOut,
    DisplayOut,
    ServerStatusOut,
    SettingOut,
    SettingUpdateRequest,
    TableCountOut,
)
from app.modules.works.models import Work
from app.shared.auth import current_user, require_system_admin

router = APIRouter(prefix="/server", tags=["server"])

STARTED_AT = datetime.now(UTC)


def _safe_url(url: str) -> str:
    if "@" not in url:
        return url
    head, tail = url.rsplit("@", 1)
    if ":" in head:
        return f"{head.rsplit(':', 1)[0]}:***@{tail}"
    return f"{head}@{tail}"


def _build123d_version() -> str:
    try:
        import build123d

        return str(build123d.__version__)
    except Exception:  # pragma: no cover
        return "unavailable"


@router.get("/status", response_model=ServerStatusOut)
def status(
    _: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> ServerStatusOut:
    settings = get_settings()
    head = schema_version.code_head()
    current = schema_version.db_revision(engine)

    disk: DiskOut | None = None
    try:
        usage = shutil.disk_usage(settings.filestore_dir)
        disk = DiskOut(
            path=str(settings.filestore_dir),
            total_bytes=usage.total,
            free_bytes=usage.free,
            used_percent=round((usage.total - usage.free) / usage.total * 100, 1),
        )
    except OSError:
        disk = None

    def count(table: type[Base]) -> int:
        return int(db.scalar(select(func.count()).select_from(table)) or 0)

    return ServerStatusOut(
        app_name=settings.app_name,
        app_slug=settings.app_slug,
        version=version.current(),
        app_env=settings.app_env,
        database_url_safe=_safe_url(settings.database_url),
        schema_head=head,
        schema_current=current,
        schema_behind=bool(head and current and head != current),
        disk=disk,
        counts=[
            TableCountOut(label="계정", count=count(User)),
            TableCountOut(label="내 작업", count=count(Work)),
            TableCountOut(label="부품", count=count(Part)),
            TableCountOut(label="지그", count=count(Jig)),
            TableCountOut(label="작업", count=count(Job)),
            TableCountOut(label="작업물", count=count(Artifact)),
        ],
        build123d_version=_build123d_version(),
        started_at=STARTED_AT,
    )


@router.get("/workers")
def workers(
    _: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """워커 — 살아 있나(마지막 신호) · 무엇을 하나 · 줄이 얼마나 긴가.

    `state` 는 idle · busy · stopping · stopped, 그리고 신호가 2분 넘게 끊긴 것은 **lost**(죽은
    것으로 본다 — 잡고 있던 작업은 워커 루프가 되살린다). 살아 있는 워커가 없는데 줄이 서
    있으면(`alive` 0, `queue.queued` > 0) 작업이 영영 안 돈다 — 화면이 그것을 크게 말한다."""
    return jobs.workers_overview(db)


@router.get("/shape-index")
def shape_index_status(
    _: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """형상 색인이 **없는** 최신 버전 수 — 이 기능 전에 만든 것. 형상으로 찾으면 빠진다."""
    return {"missing": shape_fill.missing(db)}


@router.post("/shape-index")
def fill_shape_index(
    limit: int = Query(default=20, ge=1, le=200),
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """형상 색인을 `limit` 개까지 채운다 — 그 버전이 남긴 STEP 에서. 남은 것(`remaining`)이
    0 이 될 때까지 다시 부른다."""
    return shape_fill.fill(db, limit=limit)


@router.get("/display", response_model=DisplayOut)
def display_settings(
    _: User = Depends(current_user), db: Session = Depends(get_db)
) -> DisplayOut:
    """화면이 쓰는 수 — 목록 한 쪽 줄 수, 실험계획 형상 보기의 한 번에 그리는 수."""
    return DisplayOut(**settings_store.display(db))


@router.get("/settings", response_model=list[SettingOut])
def list_settings(
    _: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> list[SettingOut]:
    """관리자가 화면에서 바꾸는 값들 — 지금 값 · .env 기본값 · 허용 범위."""
    return [SettingOut(**one) for one in settings_store.listing(db)]


@router.put("/settings/{key}", response_model=list[SettingOut])
def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[SettingOut]:
    settings_store.set_int(db, key, payload.value, by=user.id)
    return [SettingOut(**one) for one in settings_store.listing(db)]
