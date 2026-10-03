from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Where = Literal["works", "parts", "jigs"]


def _everywhere() -> list[Where]:
    return ["works", "parts", "jigs"]


class SimilarRequest(BaseModel):
    """무엇과 닮은 것을 찾나 — 이미 있는 것(`source`) 또는 아직 저장 안 한 레시피(`recipe`)."""

    source: str | None = Field(default=None, max_length=80)
    """`work:<id>` · `part:<id>` · `jig:<id>` — 그 **최신 버전**의 형상과 견준다."""
    recipe: dict[str, Any] | None = None
    """저장 전의 레시피 — 만들어 보고 색인을 뽑아 견준다(새로 그리기 전에 「이미 있나」)."""
    where: list[Where] = Field(default_factory=_everywhere)
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def _one(self) -> SimilarRequest:
        if (self.source is None) == (self.recipe is None):
            raise ValueError("source · recipe 중 하나만 줍니다")
        if not self.where:
            raise ValueError("where: works · parts · jigs 중 하나 이상")
        return self
