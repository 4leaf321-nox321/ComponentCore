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
    assert bad.json()["ok"] is False and "앞에 없는 피처" in bad.json()["problems"][0]

    info = client.post("/api/cad/recipe/info", json={"recipe": BOX}, headers=member.headers)
    assert info.status_code == 200, info.text
    assert info.json()["summary"]["volume"] == 12000

    glb = client.post("/api/cad/recipe/preview", json={"recipe": BOX}, headers=member.headers)
    assert glb.status_code == 200 and glb.content[:4] == b"glTF"
    step = client.post("/api/cad/recipe/step", json={"recipe": BOX}, headers=member.headers)
    assert step.status_code == 200 and step.content.startswith(b"ISO-10303-21")


def test_STL_과_2D_도면으로도_받는다(client: TestClient, member: Signed) -> None:
    stl = client.post("/api/cad/recipe/stl", json={"recipe": BOX}, headers=member.headers)
    assert stl.status_code == 200 and stl.content.startswith(b"STL Exported")  # 바이너리 STL

    # 입체는 높이 절반에서 자른 단면이 2D 가 된다.
    dxf = client.post("/api/cad/recipe/dxf", json={"recipe": BOX}, headers=member.headers)
    assert dxf.status_code == 200 and b"SECTION" in dxf.content[:4000]

    svg = client.post("/api/cad/recipe/svg", json={"recipe": BOX}, headers=member.headers)
    assert svg.status_code == 200 and svg.content.lstrip().startswith(b"<?xml")
    assert b"mm" in svg.content[:400]

    # 스케치만 있어도 2D 는 나온다 — 도면은 원래 2D 다.
    sketch_only = {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rounded_rect", "width": 40, "height": 30, "radius": 5}],
            }
        ]
    }
    flat = client.post(
        "/api/cad/recipe/dxf", json={"recipe": sketch_only}, headers=member.headers
    )
    assert flat.status_code == 200 and len(flat.content) > 1000


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


def test_스케치만_있어도_미리보기는_보이고_저장은_거절(
    client: TestClient, member: Signed
) -> None:
    """처음부터 그리면 반드시 「스케치만 있는」 순간을 지난다 — 그때 빨간 오류가 뜨면 안
    된다."""
    sketch_only = {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rect", "width": 40, "height": 30}],
            }
        ]
    }
    info = client.post(
        "/api/cad/recipe/info", json={"recipe": sketch_only}, headers=member.headers
    )
    assert info.status_code == 200, info.text
    summary = info.json()["summary"]
    assert (
        summary["is_sketch"] is True and summary["solid_count"] == 0 and summary["volume"] == 0
    )
    assert summary["warnings"] and "돌출" in summary["warnings"][0]
    mesh = client.post(
        "/api/cad/recipe/mesh", json={"recipe": sketch_only}, headers=member.headers
    )
    assert mesh.status_code == 200 and len(mesh.json()["mesh"]["faces"]) == 1
    # STEP 과 저장은 입체여야 한다.
    step = client.post(
        "/api/cad/recipe/step", json={"recipe": sketch_only}, headers=member.headers
    )
    assert step.status_code == 400 and step.json()["error"]["details"]["node_id"] == "s"
    work = client.post(
        "/api/works", json={"name": "2D", "recipe": sketch_only}, headers=member.headers
    )
    assert work.status_code == 201  # 모양은 맞으니 저장은 되고
    assert (
        work.json()["current"]["job"]["status"] == "failed"
    )  # 평가가 「입체를 만드세요」 로 실패한다


def test_치수를_훑어_고르고_보_공진을_가늠한다(client: TestClient, member: Signed) -> None:
    """지그를 세트의 공진에 맞추는 흐름 — 연결부는 그대로, 튜닝부만 바꿔 가며 고른다."""
    jig = {
        "params": {"튜닝_두께": 6.0},
        "nodes": [
            {
                "id": "연결판",
                "op": "box",
                "length": 60,
                "width": 60,
                "height": 12,
                "align": ["min", "center", "min"],
            },
            {
                "id": "볼트",
                "op": "hole",
                "target": "연결판",
                "at": [[10, -22], [50, 22]],
                "thread": "M6",
            },
            {
                "id": "튜닝보",
                "op": "box",
                "length": 90,
                "width": 40,
                "height": "=튜닝_두께",
                "at": [60, 0, 0],
                "align": ["min", "center", "min"],
            },
            {"id": "지그", "op": "union", "targets": ["볼트", "튜닝보"]},
        ],
    }
    swept = client.post(
        "/api/cad/recipe/sweep",
        json={
            "recipe": jig,
            "param": "튜닝_두께",
            "values": [4, 6, 10],
            "material": "aluminum",
        },
        headers=member.headers,
    )
    assert swept.status_code == 200, swept.text
    rows = swept.json()["results"]
    assert [row["튜닝_두께"] for row in rows] == [4, 6, 10]
    masses = [row["geometry"]["mass"]["mass_g"] for row in rows]
    assert masses[0] < masses[1] < masses[2]  # 두꺼울수록 무겁다
    # 연결부는 어떤 값에서도 그대로다 — 구멍 자리가 같다.
    holes = [sorted(tuple(h["at"]) for h in row["geometry"]["holes"]) for row in rows]
    assert holes[0] == holes[1] == holes[2]

    missing = client.post(
        "/api/cad/recipe/sweep",
        json={"recipe": jig, "param": "없는치수", "values": [1]},
        headers=member.headers,
    )
    assert missing.status_code == 400 and "없습니다" in missing.json()["error"]["message"]

    tuned = client.post(
        "/api/cad/beam-frequency",
        json={"target_hz": 440, "length_mm": 90, "width_mm": 40, "added_mass_g": 120},
        headers=member.headers,
    )
    assert tuned.status_code == 200
    assert 10 < tuned.json()["thickness_mm"] < 11
    assert "가늠값" in tuned.json()["accuracy"]

    too_high = client.post(
        "/api/cad/beam-frequency",
        json={"target_hz": 500000, "length_mm": 200, "width_mm": 20},
        headers=member.headers,
    )
    assert too_high.status_code == 400 and "짧게" in too_high.json()["error"]["message"]
