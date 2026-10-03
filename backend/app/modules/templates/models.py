"""레시피 템플릿 — 「그리기」 의 출발점으로 저장한 레시피.

내장 템플릿(`core/recipe/templates.py`)은 코드에 있고, 여기는 사람이 저장한 것이다. 자리는 둘:
기본은 **내 것**이고 `is_shared` 를 켜면 **공용**이 되어 누구나 시작점으로 고른다(고치는 것은
소유자뿐, 남은 복사해서 쓴다). 버전은 없다 — 시작점일 뿐이고 고친 결과는 작업(work)으로 간다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecipeTemplate(Base):
    __tablename__ = "recipe_templates"
    __table_args__ = (
        # 찾기(`shared/search.py`)의 `ILIKE %낱말%` 이 타는 트라이그램 색인 — 마이그레이션
        # 0028. 모델에도 적어 둬야 `alembic check` 가 「지울 것」 으로 읽지 않는다.
        Index(
            "ix_recipe_templates_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_recipe_templates_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
        Index(
            "ix_recipe_templates_tags_trgm",
            text("(tags::text) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    """꼬리표 — 템플릿은 **작업과의 연결을 안 남기므로** 저장할 때 받는다(부품 · 지그는
    승격이 물려받는다)."""
    folder: Mapped[str] = mapped_column(String(255), default="", server_default="", index=True)
    """놓인 **폴더** — `고객A/2026` 같은 경로, 빈 것이 맨 위(`shared/folders.py`). 여럿이 함께
    쓰는 공간이라 옮기기는 주인 · 관리자만, 남의 것이 든 폴더의 이름은 관리자만 바꾼다."""
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
