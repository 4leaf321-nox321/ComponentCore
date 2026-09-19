"""서버 상태 — 지금 뭐가 깔렸나, DB 는 맞춰져 있나, 무엇이 얼마나 쌓였나."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schema_version, version
from app.config import get_settings
from app.database import Base, engine, get_db
from app.modules.accounts.models import User
from app.modules.jigs.models import Jig
from app.modules.jobs.models import Artifact, Job
from app.modules.parts.models import Part
from app.modules.server import settings_store
from app.modules.server.schemas import (
    DiskOut,
    ServerStatusOut,
    SettingOut,
    SettingUpdateRequest,
    TableCountOut,
)
from app.modules.works.models import Work
from app.shared.auth import require_system_admin

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
