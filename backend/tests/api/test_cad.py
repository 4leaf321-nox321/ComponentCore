from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import Signed

BOX = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 40, "height": 30}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 10},
    ]
}


def test_스키마와_템플릿을_서버가_준다(client: TestClient, member: Signed) -> None:
    got = client.get("/api/cad/recipe/schema", headers=member.headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert "bracket" in body["templates"]
    assert body["template_labels"]["bracket"] == "L 브래킷"
    assert "$defs" in body["schema"]


def test_검증_미리보기_STEP(client: TestClient, member: Signed) -> None:
    check = client.post("/api/cad/recipe/check", json={"recipe": BOX}, headers=member.headers)
    assert check.json() == {"ok": True, "problems": []}

    bad = client.post(
        "/api/cad/recipe/check",
        json={
            "recipe": {"nodes": [{"id": "b", "op": "extrude", "sketch": "x", "distance": 1}]}
        },
        headers=member.headers,
    )
    assert bad.json()["ok"] is False and "앞에 없는 노드" in bad.json()["problems"][0]

    info = client.post("/api/cad/recipe/info", json={"recipe": BOX}, headers=member.headers)
    assert info.status_code == 200, info.text
    assert info.json()["summary"]["volume"] == 12000

    glb = client.post("/api/cad/recipe/preview", json={"recipe": BOX}, headers=member.headers)
    assert glb.status_code == 200 and glb.content[:4] == b"glTF"
    step = client.post("/api/cad/recipe/step", json={"recipe": BOX}, headers=member.headers)
    assert step.status_code == 200 and step.content.startswith(b"ISO-10303-21")


def test_만들지_못하는_레시피는_노드를_말한다(client: TestClient, member: Signed) -> None:
    recipe = {
        "nodes": [
            *BOX["nodes"],
            {"id": "f", "op": "fillet", "target": "b", "edges": "all", "radius": 100},
        ]
    }
    got = client.post("/api/cad/recipe/info", json={"recipe": recipe}, headers=member.headers)
    assert got.status_code == 400
    assert got.json()["error"]["code"] == "AJG-CAD-0003"
    assert got.json()["error"]["details"]["node_id"] == "f"
