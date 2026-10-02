from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    recipe: dict[str, Any]
    is_shared: bool = False
    tags: list[str] = Field(default_factory=list)
    """꼬리표 — 화면이 그때 보던 작업의 것을 건넨다(템플릿은 작업과의 연결을 안 남긴다)."""
    folder: str = Field(default="", max_length=255)
    """놓을 폴더 — 빈 것이 맨 위. 꼬리표처럼 화면이 그때 보던 작업의 것을 건넨다."""


class TemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    recipe: dict[str, Any] | None = None
    is_shared: bool | None = None
    folder: str | None = Field(default=None, max_length=255)
    """옮길 폴더 — 빈 문자열이면 맨 위로."""


class TemplateSummaryOut(BaseModel):
    """목록용 — 레시피 본문은 빼고 크기만. 목록에서 수십 개의 레시피를 내려보내지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    tags: list[str] = Field(default_factory=list)
    """꼬리표 — 저장할 때 받는다. 목록에서 이것으로 거른다(`?tag=`)."""
    description: str
    owner_id: uuid.UUID
    owner_name: str
    is_shared: bool
    mine: bool
    node_count: int
    folder: str = ""
    """놓인 폴더 — `고객A/2026`, 빈 것이 맨 위. 내 것과 공용이 같은 나무를 쓴다."""
    updated_at: datetime


class TemplateOut(TemplateSummaryOut):
    recipe: dict[str, Any]
