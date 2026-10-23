"""태그로 쓰는 타입 — 관리자가 고른다(ADR 0011).

온톨로지 정의(`object_types`)에 칸을 더하지 않고 표를 따로 둔다. 정의는 StandardPlatform 에서
들인 모양이고 허브가 관리하는 타입도 있다 — 그 정의는 여기서 못 고치지만, 「이 설치에서는 그
타입을 태그로 고른다」 는 이 설치가 정할 일이다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 태그의 선 — 붙인 행(작업 · 부품 · 지그의 원 표) → 객체. 다른 모듈이 「이 관계는 태그다」 를
#: 가릴 때 이 값을 본다(기준정보 칸은 태그를 줄로 세우지 않는다).
TAG_RELATION = "cc_tagged"
#: 타입을 안 고르고 붙인 이름이 가는 곳 — 「일반 태그」. 옛 글자 꼬리표도 여기로 옮겼다.
DEFAULT_TAG_TYPE = "cc_tag"

#: 태그 타입이 받는 것.
#:
#:   pick  있는 객체에서 고르기만 — 정해 둔 목록(고객사 · 시험 규격)
#:   grow  고르거나, **붙이는 사람 누구나** 새 객체를 만든다 — 태그로 자라는 어휘
TAG_MODES = ("pick", "grow")


class TagType(Base):
    __tablename__ = "tag_types"

    type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("object_types.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mode: Mapped[str] = mapped_column(String(10), default="pick", server_default="pick")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
