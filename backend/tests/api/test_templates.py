"""템플릿 공간 — 내 것과 공용 두 자리, 그리고 복사."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api.conftest import Signed, _login, make_user

BOX = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 40, "height": 30}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 10},
    ]
}


def _names(response: Any) -> list[str]:
    return [one["name"] for one in response["items"]]


def _stranger(client: TestClient, db: Session) -> dict[str, str]:
    """관리자가 아닌 **남** — 관리자는 남의 것도 고칠 수 있어서 권한 시험에 못 쓴다."""
    user = make_user(db, label="stranger", is_system_admin=False)
    return {"Authorization": f"Bearer {_login(client, user.email)}"}


def test_내_것과_공용_두_자리(client: TestClient, member: Signed, admin: Signed) -> None:
    made = client.post(
        "/api/templates",
        json={"name": "내 상자", "recipe": BOX, "description": "40x30x10"},
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    template_id = made.json()["id"]
    assert made.json()["node_count"] == 2

    mine = client.get("/api/templates?scope=mine", headers=member.headers).json()
    assert _names(mine) == ["내 상자"] and mine["items"][0]["mine"] is True
    assert "recipe" not in mine["items"][0]  # 목록은 본문을 싣지 않는다

    # 남은 못 본다 — 공용으로 내놓아야 보인다.
    assert client.get("/api/templates?q=내 상자", headers=admin.headers).json()["total"] == 0
    shared = client.patch(
        f"/api/templates/{template_id}", json={"is_shared": True}, headers=member.headers
    )
    assert shared.status_code == 200 and shared.json()["is_shared"] is True

    seen = client.get("/api/templates?q=내 상자", headers=admin.headers).json()
    assert _names(seen) == ["내 상자"] and seen["items"][0]["mine"] is False
    # 자리로 나눠 본다.
    assert client.get("/api/templates?scope=mine", headers=admin.headers).json()["total"] == 0
    shared_seen = client.get("/api/templates?scope=shared&q=내 상자", headers=admin.headers)
    assert shared_seen.json()["total"] == 1
    assert client.get("/api/templates?scope=mine", headers=member.headers).json()["total"] == 1
    # 이름 · 설명으로 찾는다.
    assert client.get("/api/templates?q=상자", headers=member.headers).json()["total"] == 1
    assert client.get("/api/templates?q=없는것", headers=member.headers).json()["total"] == 0


def test_남의_공용_템플릿은_복사해서_쓴다(
    client: TestClient, member: Signed, db: Session
) -> None:
    made = client.post(
        "/api/templates",
        json={"name": "브래킷", "recipe": BOX, "is_shared": True},
        headers=member.headers,
    ).json()
    stranger = _stranger(client, db)

    # 남은 고치지도 지우지도 못한다.
    assert (
        client.patch(
            f"/api/templates/{made['id']}", json={"name": "뺏기"}, headers=stranger
        ).status_code
        == 403
    )
    assert client.delete(f"/api/templates/{made['id']}", headers=stranger).status_code == 403

    copied = client.post(f"/api/templates/{made['id']}/copy", headers=stranger)
    assert copied.status_code == 201
    assert copied.json()["name"] == "브래킷 (복사)"
    assert copied.json()["mine"] is True and copied.json()["is_shared"] is False
    assert copied.json()["recipe"] == BOX
    # 복사본은 내 자리에 있다.
    assert _names(client.get("/api/templates?scope=mine", headers=stranger).json()) == [
        "브래킷 (복사)"
    ]


def test_그리기에서_열_때는_레시피까지_준다(client: TestClient, member: Signed) -> None:
    made = client.post(
        "/api/templates", json={"name": "상자", "recipe": BOX}, headers=member.headers
    ).json()
    got = client.get(f"/api/templates/{made['id']}", headers=member.headers)
    assert got.status_code == 200 and got.json()["recipe"] == BOX


def test_틀린_레시피는_저장에서_거절(client: TestClient, member: Signed) -> None:
    bad = client.post(
        "/api/templates",
        json={"name": "x", "recipe": {"nodes": [{"id": "a", "op": "nope"}]}},
        headers=member.headers,
    )
    assert bad.status_code == 400 and bad.json()["error"]["details"]["problems"]


def test_지우면_사라진다(client: TestClient, member: Signed) -> None:
    made = client.post(
        "/api/templates", json={"name": "상자", "recipe": BOX}, headers=member.headers
    ).json()
    assert (
        client.delete(f"/api/templates/{made['id']}", headers=member.headers).status_code
        == 204
    )
    # 남들이 공용으로 둔 것이 섞이지 않게 내 자리만 본다.
    assert client.get("/api/templates?scope=mine", headers=member.headers).json()["total"] == 0
