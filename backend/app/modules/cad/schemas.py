from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PrimitiveRequest(BaseModel):
    spec: dict[str, Any] = Field(default_factory=lambda: {"kind": "box"})
    """`core/primitives.py` 의 스펙. kind 와 치수."""


class PrimitiveInfoOut(BaseModel):
    kind: str
    bbox_size: tuple[float, float, float]
    volume: float
    face_count: int


class PrimitiveKindsOut(BaseModel):
    kinds: list[str]
    examples: dict[str, dict[str, Any]]
    """종류별 기본 치수 — 화면 폼의 초깃값."""
