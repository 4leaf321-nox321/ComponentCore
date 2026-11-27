from __future__ import annotations

from datetime import datetime
from typing import Any

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


class MaintenanceItemOut(BaseModel):
    """남은 일 하나 — 부서 홈이 보여 준다(StandardPlatform 그대로). 관리 화면에 들어가야만
    보이면 아무도 안 본다."""

    key: str
    label: str
    count: int
    link: str | None
    severity: str
    """info · warning. 경고는 색이 붙는다."""


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


class CapabilitiesOut(BaseModel):
    """받는 쪽 능력표의 복사본 — 관리 화면. 토큰은 싣지 않는다(설정이 됐는지만)."""

    configured: bool
    missing: str
    """비어 있는 .env 칸 — 「SIMENGBAY_TOKEN(토큰)」 처럼 이름을 댄다."""
    base_url: str
    source: str
    """복사본을 받은 바탕 주소 — 주소를 바꾼 뒤 갱신하지 않았으면 `base_url` 과 다르다."""
    fetched_at: datetime | None
    tables: list[Any] | None
    """받은 그대로(솔버마다 한 장). 받은 적이 없으면 None — 그때는 거르지 않는다."""
