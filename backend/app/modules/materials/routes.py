"""물성 — **고르는 창구 하나.** 뒤에 MatNexus 가 있든 올려 둔 사본이 있든 같은 길이다."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.materials import services
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, code

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("")
def search_materials(
    q: str = Query(default="", max_length=120),
    family: str = Query(default="", max_length=60),
    limit: int = Query(default=30, ge=1, le=200),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """물성 탐색기가 쓰는 목록 — **전역 재료만** 본다.

    MatNexus 의 PAT 에는 범위가 없어서, 서비스 계정으로 부르면서 작업공간 재료까지 보여 주면
    그쪽 권한 구분이 이쪽에서 무너진다. 못 닿으면 올려 둔 카탈로그로 넘어가고, **넘어갔다는
    사실을 답에 적는다**(`fallback`)."""
    return services.search(db, query=q, family=family, limit=limit)


@router.get("/status")
def material_status(
    _: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """닿나 · 사본은 몇 건이고 언제 받은 것인가."""
    return services.status(db)


@router.post("/catalog")
async def upload_catalog(
    file: UploadFile = File(...),
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """MatNexus 의 「내보내기」 JSON 을 올린다 — **폐쇄망 · 점검 때의 길.**

    통째로 갈아 끼운다. 합치면 그쪽에서 지워진 재료가 사본에만 남고, 그것을 고르고
    나서야 없다는 것을 안다."""
    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as failure:
        raise AppError(
            code("MATERIALS", 6), f"JSON 을 읽지 못했습니다: {failure}"
        ) from failure
    return services.load_catalog(db, payload, filename=file.filename or "")


@router.get("/{code_or_id}")
def get_material(
    code_or_id: str, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """재료 하나 — `payload` 는 **받은 그대로**다. 우리가 고치지 않는다."""
    return services.one(db, code_or_id)
