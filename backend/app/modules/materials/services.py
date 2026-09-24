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

from app.core import conditions
from app.modules.materials.models import CatalogMaterial
from app.shared.clients import matnexus
from app.shared.errors import AppError, NotFound, code


def _row(payload: dict[str, Any], source: str, system: str = "") -> dict[str, Any]:
    """화면이 목록에 그리는 한 줄 — **payload 는 통째로 함께 간다.**

    요약 칸(밀도 · 푸아송비)을 따로 뽑는 것은 목록을 읽기 쉬우라고다. 조건에 실리는 것은
    요약이 아니라 `payload` 다 — 우리가 고른 몇 개가 아니라 그쪽이 준 전부.

    `system` 을 주면 **그 계로 환산한 값**(`converted`)을 나란히 싣는다. 화면이 제 손으로
    환산하지 않게 하려는 것이다 — 환산표를 두 벌(파이썬 · TS) 두면 어느 날 어긋나고,
    그때 화면이 보여 준 값과 내보낸 값이 달라진다. **내보낼 때와 같은 함수**를 쓴다.
    """
    made = {
        "code": str(payload.get("code") or ""),
        "id": str(payload.get("id") or ""),
        "name": str(payload.get("record_name") or payload.get("name") or ""),
        "alias": payload.get("alias") or "",
        "family": payload.get("family") or "",
        "category": payload.get("category") or "",
        "grade": payload.get("grade") or "",
        # **어느 부서 것인가**(2026-09-24 권한 개편). MatNexus 는 부서로 권한을 나누고, 두
        # 부서에 같은 이름의 재료가 있을 수 있다 — 어디서 온 것인지 안 보이면 고르는 사람이
        # 그 둘을 구별할 수 없다. 올려 둔 카탈로그에는 없을 수 있으니 빈 칸을 허용한다.
        "workspace": payload.get("owner_workspace_name") or "",
        "density": payload.get("density"),
        "density_unit": payload.get("density_unit") or "",
        "poisson_ratio": payload.get("poisson_ratio"),
        "declared_count": len(payload.get("declared_properties") or []),
        "source": source,
        "payload": payload,
    }
    if system:
        made["converted"] = conditions.converted_material(payload, system)
    return made


def _from_catalog(
    db: Session, query: str, family: str, category: str, limit: int, system: str = ""
) -> list[dict[str, Any]]:
    stmt = select(CatalogMaterial)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(CatalogMaterial.name.ilike(like), CatalogMaterial.code.ilike(like))
        )
    if family:
        stmt = stmt.where(CatalogMaterial.family == family)
    rows = db.scalars(stmt.order_by(CatalogMaterial.name).limit(limit)).all()
    out = [_row(one.payload, "catalog", system) for one in rows]
    # 갈래는 사본에 칸이 없다 — payload 에서 본다(그쪽이 준 것 그대로 싣고 있으므로 있다).
    if category:
        out = [one for one in out if one["category"] == category]
    return out


#: 문헌 재료 하나에 값이 **최대 786개**(2.6 MB)다. 설계점마다 점 파일에 실리므로 다 담을 수
#: 없다 — 그쪽이 「이것이 대표값」 이라고 표시해 둔 것만 담는다(중앙값 4개 · 최대 49개).
#: 대표가 하나도 없으면 그때는 전부 담는다(없는 것보다 낫다).
def _pick_values(values: list[Any]) -> list[Any]:
    rep = [one for one in values if isinstance(one, dict) and one.get("representative")]
    return rep or [one for one in values if isinstance(one, dict)]


def _catalog_row(payload: dict[str, Any], system: str = "") -> dict[str, Any]:
    """문헌 재료를 **목록 한 줄**로. 등록 재료와 같은 칸 이름을 쓴다 — 화면이 한 벌이면 된다.

    `payload` 는 그쪽이 준 그대로다(값까지 왔으면 값까지). 우리가 모양을 고치지 않는다."""
    made = {
        "code": str(payload.get("material_code") or payload.get("id") or ""),
        "id": str(payload.get("id") or ""),
        "name": str(payload.get("name") or ""),
        # 문헌 쪽은 별칭 대신 **만든 곳**이 사람에게 쓸모 있다.
        "alias": str(payload.get("manufacturer") or ""),
        "family": str(payload.get("subsystem") or ""),
        "category": str(payload.get("category") or ""),
        "grade": str(payload.get("grade") or payload.get("material_class") or ""),
        "workspace": "문헌",
        "density": None,
        "density_unit": "",
        "poisson_ratio": None,
        "declared_count": len(payload.get("values") or []),
        "source": "literature",
        "payload": payload,
    }
    if system:
        made["converted"] = conditions.converted_material(payload, system)
    return made


def _literature(
    query: str, subsystem: str, category: str, limit: int, system: str
) -> dict[str, Any]:
    """문헌 카탈로그에서 찾는다. **목록에는 값이 안 딸려 온다** — 2663건을 값째로 끌면
    한 번에 수십 MB다. 고른 뒤 `one()` 이 그 재료만 값까지 받는다."""
    rows = matnexus.catalog_search(
        query=query, subsystem=subsystem, category=category, limit=limit
    )
    return {"items": [_catalog_row(one, system) for one in rows], "fallback": False}


def catalog_classifications() -> dict[str, Any]:
    """문헌 카탈로그의 하위계 · 갈래와 개수 — 탐색기의 첫 두 칸."""
    summary = matnexus.catalog_summary()
    subsystems = summary.get("subsystems") or {}
    categories = summary.get("categories") or {}
    # 등록 재료 쪽과 **같은 모양**으로 내놓는다(`family` · `category` · `count`) — 화면이
    # 두 벌의 칸 그리기를 안 하게. 문헌 쪽은 둘이 교차하지 않으므로 각각 한 줄씩이다.
    items = [
        {"family": str(name), "category": "", "count": int(how_many)}
        for name, how_many in subsystems.items()
        if name
    ] + [
        {"family": "", "category": str(name), "count": int(how_many)}
        for name, how_many in categories.items()
    ]
    return {"items": items, "fallback": False, "total": summary.get("materials")}


def classifications(db: Session) -> dict[str, Any]:
    """쪽(族) · 갈래와 그 개수 — 화면이 좁혀 들어갈 두 칸.

    못 닿으면 **올려 둔 사본에서 같은 모양으로 세어 준다.** 여기서 빈손을 주면 화면의 첫
    칸이 비고, 사람은 재료가 하나도 없는 줄 안다 — 실은 카탈로그에 있는데도."""
    if matnexus.configured():
        try:
            return {"items": matnexus.classifications(), "fallback": False}
        except matnexus.MatNexusUnavailable as failure:
            detail = str(failure)
        except AppError as failure:
            detail = failure.message
    else:
        detail = f"{matnexus.missing()} — 올려 둔 카탈로그로 고릅니다"
    counted: dict[tuple[str, str], int] = {}
    for row in db.scalars(select(CatalogMaterial)).all():
        payload = row.payload or {}
        key = (str(payload.get("family") or ""), str(payload.get("category") or ""))
        counted[key] = counted.get(key, 0) + 1
    items = [
        {"family": family, "category": category, "count": how_many}
        for (family, category), how_many in sorted(counted.items())
    ]
    return {"items": items, "fallback": True, "detail": detail}


def search(
    db: Session,
    *,
    query: str = "",
    family: str = "",
    category: str = "",
    limit: int = 30,
    system: str = "",
    source: str = "registered",
) -> dict[str, Any]:
    """MatNexus 에 묻고, 못 닿으면 올려 둔 카탈로그로 넘어간다.

    `source` 가 창고를 가른다: `registered`(우리 조직이 등록한 135건) · `literature`(데이터
    시트 · 논문에서 모은 문헌 카탈로그 2663건). **둘은 값의 모양도 다르다** — payload 는
    그대로 나르고, 한 모양이 필요한 쪽은 `converted` 를 본다.

    **못 닿았다는 사실을 숨기지 않는다**(`fallback` · `detail`). 조용히 옛 사본을 주면 사람은
    어제 받은 값을 오늘 것으로 믿는다.
    """
    if source == "literature":
        # **문헌은 올려 둔 사본이 없다.** 못 닿으면 못 닿았다고 말한다 — 등록 재료의 사본을
        # 문헌인 척 내주면 사람이 없는 것을 골랐다고 믿는다.
        if not matnexus.configured():
            return {
                "items": [],
                "fallback": True,
                "detail": f"{matnexus.missing()} — 문헌 물성은 MatNexus 에만 있습니다",
            }
        try:
            return _literature(query, family, category, limit, system)
        except matnexus.MatNexusUnavailable as failure:
            return {"items": [], "fallback": True, "detail": str(failure)}

    if matnexus.configured():
        try:
            live = matnexus.search(query=query, family=family, category=category, limit=limit)
            return {
                "items": [_row(one, "matnexus", system) for one in live],
                "fallback": False,
            }
        except matnexus.MatNexusUnavailable as failure:
            return {
                "items": _from_catalog(db, query, family, category, limit, system),
                "fallback": True,
                "detail": str(failure),
            }
    return {
        "items": _from_catalog(db, query, family, category, limit, system),
        "fallback": True,
        "detail": f"{matnexus.missing()} — 올려 둔 카탈로그로 고릅니다",
    }


def one(
    db: Session, code_or_id: str, *, system: str = "", source: str = "registered"
) -> dict[str, Any]:
    """재료 하나 — 살아 있는 쪽이 우선, 없으면 사본.

    **문헌은 여기서 값을 받는다.** 목록에는 값이 안 딸려 오므로(2663건을 값째로 끌면 수십
    MB 다) 고른 뒤 이 자리에서 그 재료만 받아 **대표값만** 담는다."""
    if source == "literature":
        full = matnexus.catalog_get(code_or_id)
        if not full:
            raise NotFound(code("MATERIALS", 3), f"그런 문헌 재료가 없습니다: {code_or_id}")
        picked = {**full, "values": _pick_values(full.get("values") or [])}
        return _catalog_row(picked, system)
    if matnexus.configured():
        try:
            live = matnexus.get(code_or_id)
            if live is not None:
                return _row(live, "matnexus", system)
        except matnexus.MatNexusUnavailable:
            pass
    row = db.scalar(select(CatalogMaterial).where(CatalogMaterial.code == code_or_id))
    if row is None:
        raise NotFound(code("MATERIALS", 3), f"그런 재료가 없습니다: {code_or_id}")
    return _row(row.payload, "catalog", system)


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
