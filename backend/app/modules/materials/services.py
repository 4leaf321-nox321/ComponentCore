"""물성 고르기 — **살아 있는 API 먼저, 없으면 올려 둔 카탈로그.**

둘을 한 창구로 합친다. 화면은 「어디서 왔나」(`source`)만 보고, 고르는 방법은 같다 —
물성이 어디서 오는지에 따라 사람이 다른 일을 하게 만들면 그 차이를 매번 설명해야 한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.materials.models import CatalogMaterial
from app.shared.clients import matnexus
from app.shared.errors import AppError, NotFound, code


def _row(payload: dict[str, Any], source: str) -> dict[str, Any]:
    """화면이 목록에 그리는 한 줄 — **payload 는 통째로 함께 간다.**

    요약 칸(밀도 · 푸아송비)을 따로 뽑는 것은 목록을 읽기 쉬우라고다. 조건에 실리는 것은
    요약이 아니라 `payload` 다 — 우리가 고른 몇 개가 아니라 그쪽이 준 전부.
    """
    return {
        "code": str(payload.get("code") or ""),
        "id": str(payload.get("id") or ""),
        "name": str(payload.get("record_name") or payload.get("name") or ""),
        "alias": payload.get("alias") or "",
        "family": payload.get("family") or "",
        "category": payload.get("category") or "",
        "grade": payload.get("grade") or "",
        "density": payload.get("density"),
        "density_unit": payload.get("density_unit") or "",
        "poisson_ratio": payload.get("poisson_ratio"),
        "declared_count": len(payload.get("declared_properties") or []),
        "source": source,
        "payload": payload,
    }


def _from_catalog(db: Session, query: str, family: str, limit: int) -> list[dict[str, Any]]:
    stmt = select(CatalogMaterial)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(CatalogMaterial.name.ilike(like), CatalogMaterial.code.ilike(like))
        )
    if family:
        stmt = stmt.where(CatalogMaterial.family == family)
    rows = db.scalars(stmt.order_by(CatalogMaterial.name).limit(limit)).all()
    return [_row(one.payload, "catalog") for one in rows]


def search(
    db: Session, *, query: str = "", family: str = "", limit: int = 30
) -> dict[str, Any]:
    """MatNexus 에 묻고, 못 닿으면 올려 둔 카탈로그로 넘어간다.

    **못 닿았다는 사실을 숨기지 않는다**(`fallback` · `detail`). 조용히 옛 사본을 주면 사람은
    어제 받은 값을 오늘 것으로 믿는다.
    """
    if matnexus.configured():
        try:
            live = matnexus.search(query=query, family=family, limit=limit)
            return {"items": [_row(one, "matnexus") for one in live], "fallback": False}
        except matnexus.MatNexusUnavailable as failure:
            return {
                "items": _from_catalog(db, query, family, limit),
                "fallback": True,
                "detail": str(failure),
            }
    return {
        "items": _from_catalog(db, query, family, limit),
        "fallback": True,
        "detail": "MatNexus 주소가 없습니다 — 올려 둔 카탈로그로 고릅니다",
    }


def one(db: Session, code_or_id: str) -> dict[str, Any]:
    """재료 하나 — 살아 있는 쪽이 우선, 없으면 사본."""
    if matnexus.configured():
        try:
            return _row(matnexus.get(code_or_id), "matnexus")
        except matnexus.MatNexusUnavailable:
            pass
    row = db.scalar(select(CatalogMaterial).where(CatalogMaterial.code == code_or_id))
    if row is None:
        raise NotFound(code("MATERIALS", 3), f"그런 재료가 없습니다: {code_or_id}")
    return _row(row.payload, "catalog")


def load_catalog(db: Session, payload: Any, *, filename: str) -> dict[str, Any]:
    """MatNexus 의 내보내기 파일을 받아 **통째로 갈아 끼운다.**

    합치지 않는다 — 지워진 재료가 사본에만 남으면, 없는 것을 고르고 나서야 안다. 그쪽이 준
    한 벌이 그대로 이쪽의 한 벌이다.
    """
    rows = payload.get("materials") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise AppError(
            code("MATERIALS", 4),
            "물성 카탈로그 파일이 아닙니다 — MatNexus 의 「내보내기」 JSON 이어야 합니다",
        )
    kept: list[CatalogMaterial] = []
    for item in rows:
        if not isinstance(item, dict) or not item.get("code"):
            continue
        kept.append(
            CatalogMaterial(
                id=uuid.uuid4(),
                code=str(item["code"]),
                name=str(item.get("record_name") or item.get("name") or item["code"]),
                family=str(item.get("family") or ""),
                category=str(item.get("category") or ""),
                payload=item,
                source_file=filename,
                fetched_at=datetime.now(UTC),
            )
        )
    if not kept:
        raise AppError(code("MATERIALS", 5), "파일에서 재료를 하나도 읽지 못했습니다")
    db.query(CatalogMaterial).delete()
    db.add_all(kept)
    db.commit()
    return {"loaded": len(kept), "file": filename}


def status(db: Session) -> dict[str, Any]:
    """관리자 화면이 보는 한 줄 — 닿나, 사본은 몇 건이고 언제 받은 것인가."""
    count = db.scalar(select(func.count()).select_from(CatalogMaterial)) or 0
    newest = db.scalar(select(func.max(CatalogMaterial.fetched_at)))
    return {
        **matnexus.ping(),
        "catalog_count": int(count),
        "catalog_fetched_at": newest.isoformat() if newest else None,
    }
