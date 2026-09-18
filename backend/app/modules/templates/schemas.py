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


class TemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    recipe: dict[str, Any] | None = None
    is_shared: bool | None = None


class TemplateSummaryOut(BaseModel):
    """목록용 — 레시피 본문은 빼고 크기만. 목록에서 수십 개의 레시피를 내려보내지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID
    owner_name: str
    is_shared: bool
    mine: bool
    node_count: int
    updated_at: datetime


class TemplateOut(TemplateSummaryOut):
    recipe: dict[str, Any]
