"""레시피 템플릿 — 「그리기」 의 출발점으로 저장한 레시피.

내장 템플릿(`core/recipe/templates.py`)은 코드에 있고, 여기는 사람이 저장한 것이다. 기본은 내
것이고 `is_shared` 를 켜면 누구나 고를 수 있다. 버전은 없다 — 템플릿은 시작점일 뿐이고, 고친
결과는 작업(work)으로 간다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecipeTemplate(Base):
    __tablename__ = "recipe_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    recipe: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    """켜면 로그인한 누구나 시작점으로 고른다. 고치는 것은 소유자뿐."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
