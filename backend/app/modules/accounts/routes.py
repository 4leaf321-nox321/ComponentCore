"""계정 라우터 — 전부 시스템 관리자 전용이다. 자기 정보는 auth 모듈의 /auth/me 가 다룬다."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts import services, tokens
from app.modules.accounts.models import User
from app.modules.accounts.schemas import (
    AccountOut,
    CreateAccountRequest,
    SystemAdminRequest,
    TemporaryPasswordResponse,
    TokenRevokeRequest,
)
from app.modules.auth.schemas import PatOut
from app.shared.auth import require_system_admin

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(
    status: str | None = Query(default=None, pattern="^(active|suspended)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[AccountOut]:
    users = services.list_accounts(db, status=status, limit=limit, offset=offset)
    return [services.account_out(user) for user in users]


@router.post("", response_model=TemporaryPasswordResponse, status_code=201)
def create_account(
    payload: CreateAccountRequest,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TemporaryPasswordResponse:
    user, temporary = services.create_account(
        db,
        email=payload.email,
        display_name=payload.display_name,
        is_system_admin=payload.is_system_admin,
    )
    return TemporaryPasswordResponse(
        account=services.account_out(user), temporary_password=temporary
    )


@router.post("/{account_id}/suspend", response_model=AccountOut)
def suspend(
    account_id: uuid.UUID,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    return services.account_out(
        services.set_status(db, user_id=account_id, status="suspended", actor=admin)
    )


@router.post("/{account_id}/activate", response_model=AccountOut)
def activate(
    account_id: uuid.UUID,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    return services.account_out(
        services.set_status(db, user_id=account_id, status="active", actor=admin)
    )


@router.post("/{account_id}/system-admin", response_model=AccountOut)
def set_system_admin(
    account_id: uuid.UUID,
    payload: SystemAdminRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    return services.account_out(
        services.set_system_admin(
            db, user_id=account_id, grant=payload.is_system_admin, actor=admin
        )
    )


@router.post("/{account_id}/reset-password", response_model=TemporaryPasswordResponse)
def reset_password(
    account_id: uuid.UUID,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TemporaryPasswordResponse:
    temporary = services.reset_password(db, user_id=account_id)
    return TemporaryPasswordResponse(
        account=services.account_out(services.get_account(db, account_id)),
        temporary_password=temporary,
    )


@router.delete("/{account_id}", response_model=AccountOut)
def delete_account(
    account_id: uuid.UUID,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    return services.account_out(services.delete_account(db, user_id=account_id, actor=admin))


@router.get("/{account_id}/tokens", response_model=list[PatOut])
def account_tokens(
    account_id: uuid.UUID,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[PatOut]:
    """그 사람의 액세스 토큰 — 이름 · 범위 · 만료 · 최종 사용, **폐기된 것까지.**
    평문은 없다."""
    return tokens.account_tokens(db, account_id)


@router.post("/{account_id}/tokens/{token_id}/revoke", response_model=PatOut)
def revoke_account_token(
    account_id: uuid.UUID,
    token_id: uuid.UUID,
    payload: TokenRevokeRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> PatOut:
    """남의 토큰 하나를 폐기한다 — 계정은 그대로 두고 그 연동만 끊는다(감사 기록 ·
    주인 알림)."""
    return tokens.revoke_token(
        db, user_id=account_id, token_id=token_id, actor=admin, reason=payload.reason
    )
