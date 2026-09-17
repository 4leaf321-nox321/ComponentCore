"""계정 API 의 요청·응답 형태."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_ID_FIELD = Field(min_length=3, max_length=254)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    status: str
    is_system_admin: bool
    must_change_password: bool
    created_at: datetime
    deleted_at: datetime | None


class CreateAccountRequest(BaseModel):
    """관리자가 직접 계정을 만든다. 임시 비밀번호는 응답에서 한 번만 나온다."""

    email: str = _ID_FIELD
    display_name: str = Field(min_length=1, max_length=100)
    is_system_admin: bool = False


class SystemAdminRequest(BaseModel):
    is_system_admin: bool


class TemporaryPasswordResponse(BaseModel):
    account: AccountOut
    temporary_password: str
    """이 응답에서 한 번만 나온다. 다시 볼 수 없다."""
