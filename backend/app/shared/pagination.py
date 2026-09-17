"""목록 응답 — **상한을 서버가 강제한다.**"""

from __future__ import annotations

from pydantic import BaseModel

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
