from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- 레시피 ---------------------------------------------------------------------


class RecipeRequest(BaseModel):
    recipe: dict[str, Any]


class RecipeProblemsOut(BaseModel):
    ok: bool
    problems: list[str]
    """비어 있으면 통과. 있으면 어느 칸이 왜 틀렸는지."""


class RecipeInfoOut(BaseModel):
    """레시피를 실제로 만들어 본 결과(요약). 화면 미리보기가 glTF 와 함께 받는다."""

    summary: dict[str, Any]


class RecipeSchemaOut(BaseModel):
    schema_: dict[str, Any] = Field(alias="schema")
    """노드 종류와 칸 — JSON Schema. 편집기가 폼을 그리고 AI 프롬프트가 읽는다."""
    templates: dict[str, dict[str, Any]]
    template_labels: dict[str, str]

    model_config = ConfigDict(populate_by_name=True)


# --- 템플릿 -------------------------------------------------------------------


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


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID
    owner_name: str
    recipe: dict[str, Any]
    is_shared: bool
    mine: bool
    updated_at: datetime
