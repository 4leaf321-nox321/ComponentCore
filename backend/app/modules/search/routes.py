"""찾기 — 닮은 형상."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.cad import services as cad
from app.modules.search import services
from app.modules.search.schemas import SimilarRequest
from app.shared.auth import current_user

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/similar")
def similar(
    payload: SimilarRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """**닮은 형상** — 내 작업 · 부품 · 지그의 최신 버전 중 `source`(또는 저장 전 `recipe`)와
    닮은 것을 점수 순으로. 줄마다 성분별 닮음(`parts` — 크기 · 비율 · 꽉 찬 정도 · 구멍 ·
    연산 · 덩어리 수)과 「왜」(`why`). 부품이면 **그 부품의 지그**(`jigs`)도 — 지그를 새로
    만들기 전에 다시 쓸 길이다. 작업은 내 것만, 부품 · 지그는 누구나 보는 카탈로그에서.

    색인이 없는 버전(이 기능 전)은 견주지 못한다 — 관리자가 서버 화면에서 채운다."""
    cad.require_references(db, payload.recipe, user)
    return services.similar(
        db,
        user,
        source=payload.source,
        recipe=payload.recipe,
        where=list(payload.where),
        limit=payload.limit,
    )
