"""받는 쪽 능력표의 **복사본** — 관리자가 「갱신」 을 누를 때 받아 두고, 저장 · 내보내기가
그것으로 거른다(`docs/해석-확장-설계.md` 5장).

서버 설정 표(`server_settings`)의 한 줄(`KEY`)에 둔다 — 값은 `{"tables": [받은 그대로],
"source": 바탕 주소}`, 받은 때와 사람은 그 줄의 `updated_at` · `updated_by`. 화면에서 바꾸는
정수 설정(`settings_store.KNOWN`)이 아니므로 설정 목록에는 나오지 않고 `set_int` 로 바꿀 수도
없다.

- **받은 그대로** 둔다 — 지금 읽지 않는 키(v2 판의 `follows`)도 남아, CompCore 가 그것을 읽게
  된 뒤 다시 받지 않아도 된다. 둘 때 한 번 읽어 보고(`capabilities.read`) 모양이 틀리면 두지
  않는다.
- 받지 못하면 **있던 복사본을 그대로 둔다** — 받는 쪽이 잠깐 꺼졌다고 거르기가 사라지지 않게.
- 복사본이 없으면(`None`) 거르지 않는다 — 능력표가 생기기 전과 같다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.conditions import capabilities
from app.modules.server.models import ServerSetting
from app.shared.clients import simengbay
from app.shared.errors import AppError, code

KEY = "simengbay_capabilities"


def _row(db: Session) -> ServerSetting | None:
    row = db.get(ServerSetting, KEY)
    return row if row is not None and isinstance(row.value, dict) else None


def raw(db: Session) -> list[Any] | None:
    """받아 둔 그대로 — 화면이 솔버 목록 · 표를 그린다. 없으면 `None`."""
    row = _row(db)
    if row is None:
        return None
    tables = row.value.get("tables")
    return tables if isinstance(tables, list) else None


def tables(db: Session) -> list[capabilities.Table] | None:
    """거르는 데 쓰는 표 — 없으면 `None`(거르지 않는다). 둘 때 읽어 본 것이라 틀릴 일은 없지만,
    틀리면 거르지 않는 쪽으로 간다 — 복사본 때문에 저장이 막히면 사람이 고칠 길이 없다."""
    got = raw(db)
    if got is None:
        return None
    try:
        return capabilities.read(got)
    except capabilities.CapabilityError:
        return None


def fetched_at(db: Session) -> datetime | None:
    row = _row(db)
    return row.updated_at if row is not None else None


def status(db: Session) -> dict[str, Any]:
    """관리 화면 — 설정이 됐나(무엇이 비었나), 어디서 언제 받았나, 받은 표."""
    row = _row(db)
    return {
        "configured": simengbay.configured(),
        "missing": simengbay.missing(),
        "base_url": simengbay.base_url(),
        "source": str(row.value.get("source") or "") if row is not None else "",
        "fetched_at": row.updated_at if row is not None else None,
        "tables": raw(db),
    }


def refresh(db: Session, *, by: uuid.UUID) -> dict[str, Any]:
    """받아 와 복사본을 바꾼다. 못 받거나 모양이 틀리면 **있던 것을 두고** 까닭을 말한다."""
    try:
        got = simengbay.capabilities()
    except simengbay.SimEngBayUnavailable as failure:
        raise AppError(code("SERVER", 3), str(failure), status=502) from failure
    try:
        capabilities.read(got)
    except capabilities.CapabilityError as failure:
        raise AppError(
            code("SERVER", 4),
            f"SimEngBay의 능력표가 약속한 모양이 아닙니다: {failure} 받아 둔 능력표는 그대로 "
            "둡니다.",
            status=502,
        ) from failure
    value = {"tables": got, "source": simengbay.base_url()}
    row = db.get(ServerSetting, KEY)
    if row is None:
        db.add(ServerSetting(key=KEY, value=value, updated_by=by))
    else:
        row.value = value
        row.updated_by = by
        # 받은 것이 같아도 받은 때는 새로 — 「언제 마지막으로 확인했나」 가 이 줄의 뜻이다.
        row.updated_at = datetime.now(UTC)
    db.commit()
    return status(db)
