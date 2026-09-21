from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DiskOut(BaseModel):
    path: str
    total_bytes: int
    free_bytes: int
    used_percent: float


class TableCountOut(BaseModel):
    label: str
    count: int


class ServerStatusOut(BaseModel):
    app_name: str
    app_slug: str
    version: str
    app_env: str
    database_url_safe: str
    schema_head: str | None
    schema_current: str | None
    schema_behind: bool
    disk: DiskOut | None
    counts: list[TableCountOut]
    build123d_version: str
    started_at: datetime


class DisplayOut(BaseModel):
    """화면이 읽는 설정 — 관리자가 아닌 사람도 본다(목록 줄 수 · 형상 보기 수)."""

    doe_gallery_max: int
    list_page_size: int


class SettingOut(BaseModel):
    key: str
    label: str
    description: str
    value: int
    default: int
    overridden: bool
    minimum: int
    maximum: int
    updated_at: datetime | None


class SettingUpdateRequest(BaseModel):
    """`value` 가 None 이면 덮어쓴 것을 지워 .env 기본값으로."""

    value: int | None
