"""남의 액세스 토큰 — 보고 하나만 폐기한다(시스템 관리자). StandardPlatform
`accounts/services.py` 의 「그 사람의 액세스 토큰」 그대로(ADR 0008) — 코어 API 화면(바깥
시스템에 준 `core:read` 토큰)이 같은 창(`TokenRevokeDialog`)으로 끊는다.

정지는 토큰을 그대로 두므로(다시 켜면 연동이 이어진다) 「계정은 살리고 이 연동만 끊는다」 는 이
길뿐이다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.accounts.services import get_account
from app.modules.auth import services as auth_services
from app.modules.auth.models import PersonalAccessToken
from app.modules.auth.schemas import PatOut
from app.modules.notifications import services as notifications
from app.shared import audit
from app.shared.errors import Conflict, NotFound, code
from app.shared.text import clean


def account_tokens(db: Session, user_id: uuid.UUID) -> list[PatOut]:
    """그 사람의 개인 토큰 — **폐기된 것까지.** 「언제 끊겼나」 도 이 목록이 답할 자리다."""
    return auth_services.list_pats(db, get_account(db, user_id))


def revoke_token(
    db: Session,
    *,
    user_id: uuid.UUID,
    token_id: uuid.UUID,
    actor: User,
    reason: str | None,
) -> PatOut:
    """남의 토큰 **하나**를 폐기한다. 이미 폐기된 것은 다시 폐기하지 않는다(409) — 처음
    폐기한 시각과 사람(감사 기록)을 덮지 않으려고. 다른 사람의 토큰 id 면 없는 것과 같이
    답한다(404)."""
    owner = get_account(db, user_id)
    pat = db.get(PersonalAccessToken, token_id)
    if pat is None or pat.user_id != owner.id:
        raise NotFound(code("ACCOUNTS", 11), f"{owner.email}의 토큰 중 해당 토큰이 없습니다.")
    if pat.revoked_at is not None:
        raise Conflict(
            code("ACCOUNTS", 12),
            f"이미 폐기된 토큰입니다. {pat.revoked_at:%Y-%m-%d %H:%M}(UTC)에 폐기되었습니다.",
            details={"revoked_at": pat.revoked_at.isoformat()},
        )
    pat.revoked_at = datetime.now(UTC)
    note = clean(reason or "") or None
    audit.record(
        db,
        action=audit.ACCOUNT_TOKEN_REVOKED,
        actor=actor,
        target_table="personal_access_tokens",
        target_id=pat.id,
        target_label=f"{owner.email} · {pat.name}",
        changes={
            "owner": owner.email,
            "owner_id": str(owner.id),
            "name": pat.name,
            "prefix": pat.prefix,
            "scopes": list(pat.scopes or []),
            "last_used_at": pat.last_used_at.isoformat() if pat.last_used_at else None,
        },
        reason=note,
    )
    if owner.id != actor.id:
        notifications.notify(
            db,
            user_id=owner.id,
            kind=notifications.ACCOUNT_TOKEN_REVOKED,
            title=f"액세스 토큰 ‘{pat.name}’이(가) 폐기되었습니다."[:200],
            body=(
                f"시스템 관리자({actor.display_name or actor.email})가 폐기했습니다. "
                "이 토큰을 사용하던 연동은 이제 인증에 실패합니다."
                + (f" 사유: {note}" if note else "")
            ),
            link="/me",
        )
    db.commit()
    db.refresh(pat)
    return PatOut.model_validate(pat)
