"""서버 설정 — 관리자가 **화면에서** 바꾸는 값.

.env 는 서버를 다시 띄워야 하고 관리자가 손댈 수 없다. 여기 있는 값이 .env 의 기본값을
덮는다."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServerSetting(Base):
    __tablename__ = "server_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    # NULL 은 「기본값으로 돌림」 이다 — 줄을 지우지 않고 비워 두면 .env 의 값을 다시 쓴다.
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
