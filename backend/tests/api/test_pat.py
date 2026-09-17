"""개인 토큰 — 기계 자격. 범위가 쓰기를 막는지, 폐기가 즉시인지."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import Signed


def _token(client: TestClient, who: Signed, scopes: list[str]) -> str:
    made = client.post(
        "/api/auth/tokens",
        json={"name": "시험 봇", "scopes": scopes},
        headers=who.headers,
    )
    assert made.status_code == 201, made.text
    token = str(made.json()["token"])
    assert token.startswith("autojig_pat_")
    return token


def test_읽기_토큰은_읽기만(client: TestClient, member: Signed) -> None:
    token = _token(client, member, ["read"])
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/works", headers=headers).status_code == 200
    denied = client.post(
        "/api/works", json={"name": "x", "recipe": {"nodes": []}}, headers=headers
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "AJG-AUTH-0106"


def test_쓰기_토큰으로_작업을_만들고_폐기하면_즉시_막힌다(
    client: TestClient, member: Signed
) -> None:
    token = _token(client, member, ["read", "write"])
    headers = {"Authorization": f"Bearer {token}"}
    recipe = {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rect", "width": 10, "height": 10}],
            },
            {"id": "b", "op": "extrude", "sketch": "s", "distance": 5},
        ]
    }
    made = client.post(
        "/api/works",
        json={"name": "봇이 만듦", "recipe": recipe, "source": "ai"},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    assert made.json()["current"]["source"] == "ai"
    # 사람 세션으로 보면 같은 사람의 작업이다.
    assert (
        client.get(f"/api/works/{made.json()['id']}", headers=member.headers).status_code
        == 200
    )

    tokens = client.get("/api/auth/tokens", headers=member.headers).json()
    assert len(tokens) == 1 and tokens[0]["scopes"] == ["read", "write"]
    assert (
        client.delete(
            f"/api/auth/tokens/{tokens[0]['id']}", headers=member.headers
        ).status_code
        == 204
    )
    assert client.get("/api/works", headers=headers).status_code == 401


def test_모르는_범위는_발급에서_거절(client: TestClient, member: Signed) -> None:
    got = client.post(
        "/api/auth/tokens", json={"name": "x", "scopes": ["admin"]}, headers=member.headers
    )
    assert got.status_code == 400 and got.json()["error"]["code"] == "AJG-AUTH-0107"
    scopes = client.get("/api/auth/token-scopes", headers=member.headers).json()
    assert set(scopes["scopes"]) == {"read", "write"}
