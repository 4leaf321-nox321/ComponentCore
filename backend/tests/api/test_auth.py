from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api.conftest import PASSWORD, Signed, make_user


def test_로그인_후_me(client: TestClient, member: Signed) -> None:
    got = client.get("/api/auth/me", headers=member.headers)
    assert got.status_code == 200, got.text
    assert got.json()["email"] == member.email


def test_틀린_비밀번호는_401_봉투(client: TestClient, db: Session) -> None:
    user = make_user(db, label="x", is_system_admin=False)
    got = client.post("/api/auth/login", json={"email": user.email, "password": "nope"})
    assert got.status_code == 401
    body = got.json()["error"]
    assert body["code"] == "CCR-AUTH-0001"
    assert body["request_id"]


def test_토큰_없이는_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_refresh_쿠키로_세션이_이어진다(client: TestClient, db: Session) -> None:
    user = make_user(db, label="r", is_system_admin=False)
    login = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert login.status_code == 200
    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["user"]["email"] == user.email
    # 로그아웃하면 쿠키가 지워져 더는 갱신되지 않는다.
    assert client.post("/api/auth/logout").status_code == 204
    assert client.post("/api/auth/refresh").status_code == 401


def test_비밀번호_변경은_세션을_끊는다(client: TestClient, db: Session) -> None:
    user = make_user(db, label="p", is_system_admin=False)
    login = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "another-one"},
        headers=headers,
    )
    assert changed.status_code == 204, changed.text
    assert client.post("/api/auth/refresh").status_code == 401
    again = client.post(
        "/api/auth/login", json={"email": user.email, "password": "another-one"}
    )
    assert again.status_code == 200


def test_계정_관리는_관리자만(client: TestClient, admin: Signed, member: Signed) -> None:
    assert client.get("/api/accounts", headers=member.headers).status_code == 403
    created = client.post(
        "/api/accounts",
        json={"email": "newbie", "display_name": "새 사람"},
        headers=admin.headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["temporary_password"]
    assert body["account"]["must_change_password"] is True
