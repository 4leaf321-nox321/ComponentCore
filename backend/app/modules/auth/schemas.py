"""인증 API 의 요청·응답 형태 — 프론트 타입의 원본이다.

cd backend  ; python scripts/export_openapi.py
cd frontend ; npm run api:types
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    """EmailStr 을 쓰지 않는다 — 사내 계정은 `admin` 같은 짧은 아이디를 쓴다."""
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    status: str
    is_system_admin: bool
    must_change_password: bool


class LoginResponse(BaseModel):
    access_token: str
    expires_in: int
    """초 단위."""
    user: UserOut


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)
