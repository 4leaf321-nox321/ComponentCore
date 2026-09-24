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
    assert token.startswith("compcore_pat_")
    return token


def test_읽기_토큰은_읽기만(client: TestClient, member: Signed) -> None:
    token = _token(client, member, ["read"])
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/works", headers=headers).status_code == 200
    denied = client.post(
        "/api/works", json={"name": "x", "recipe": {"nodes": []}}, headers=headers
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "CCR-AUTH-0106"


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
    assert got.status_code == 400 and got.json()["error"]["code"] == "CCR-AUTH-0107"
    scopes = client.get("/api/auth/token-scopes", headers=member.headers).json()
    # `act_for_others` 는 대행 — 남의 이름으로 만드는 자격이라 따로 준다(DOE 시험 참고).
    assert set(scopes["scopes"]) == {"read", "write", "act_for_others"}
    # 뜻이 함께 온다 — 화면과 MCP 안내가 이것을 읽고 손으로 두 벌 적지 않는다.
    assert set(scopes["descriptions"]) == set(scopes["scopes"])
