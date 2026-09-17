"""API 시험이 쓰는 준비물 — **진짜 앱을 부른다.**"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security

PASSWORD = "test-account-password"


@dataclass(frozen=True)
class Signed:
    email: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def make_user(db: Session, *, label: str, is_system_admin: bool) -> User:
    user = User(
        email=f"{label}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=security.hash_password(PASSWORD),
        display_name=label,
        status="active",
        is_system_admin=is_system_admin,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def admin(client: TestClient, db: Session) -> Signed:
    user = make_user(db, label="admin", is_system_admin=True)
    return Signed(email=user.email, token=_login(client, user.email))


@pytest.fixture
def member(client: TestClient, db: Session) -> Signed:
    """관리자가 **아닌** 사람. 권한 시험에는 이 사람이 필요하다."""
    user = make_user(db, label="member", is_system_admin=False)
    return Signed(email=user.email, token=_login(client, user.email))
