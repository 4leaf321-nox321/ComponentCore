"""올려 둔 물성 카탈로그 — **MatNexus 에 못 닿을 때의 길.**

폐쇄망 · 점검 · 방화벽 때문에 물성을 못 고르면 작업이 멈춘다. 그래서 MatNexus 가 주는
내보내기 파일(`GET /materials/export`, 값은 SI 그대로)을 올려 두고 그것으로 고른다.

**고른 뒤에는 차이가 없다.** 조건에 실리는 것은 어차피 그때 뜬 payload 스냅샷이다 —
살아 있는 API 에서 왔든 올려 둔 파일에서 왔든 같은 모양이다. 다른 것은 `source` 한 칸뿐이고,
그것은 「언제 받은 것인가」 를 되짚으라고 남긴다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CatalogMaterial(Base):
    """올려 둔 파일 안의 재료 한 줄. MatNexus 가 정본이고 이것은 **사본**이다."""

    __tablename__ = "catalog_materials"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    """MatNexus 의 불변 번호(`M-000123`). **이름이 아니라 이것으로 짝짓는다** — 이름은
    기준정보 개명에 따라 바뀌지만 번호는 안 바뀐다(그쪽 주석)."""
    name: Mapped[str] = mapped_column(String(200), index=True)
    family: Mapped[str] = mapped_column(String(60), default="", server_default="")
    category: Mapped[str] = mapped_column(String(60), default="", server_default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    """MatNexus 응답 **그대로**. 우리가 고치지 않는다."""
    source_file: Mapped[str] = mapped_column(Text, default="", server_default="")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
