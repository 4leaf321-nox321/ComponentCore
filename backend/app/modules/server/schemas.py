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
