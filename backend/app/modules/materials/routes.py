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
    """물성 탐색기가 쓰는 목록.

    **무엇이 보이나는 MatNexus 가 정한다**(2026-09-24 권한 개편) — 그쪽은 부서 트리로 권한을
    나누고, 우리 토큰의 계정이 속한 부서의 재료가 보인다. 우리가 질의로 그것을 흉내 내지
    않는다(예전의 `scope=global` 은 개편으로 사라졌고, 그 뒤로는 아무 필터도 아니었다).
    좁히려면 `.env` 의 `MATNEXUS_WORKSPACE`(부서 slug).

    줄마다 **어느 부서 것인지**(`workspace`)가 함께 온다 — 두 부서에 같은 이름이 있을 수 있다.

    못 닿으면 올려 둔 카탈로그로 넘어가고, **넘어갔다는 사실을 답에 적는다**(`fallback`)."""
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
