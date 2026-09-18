"""조립 — 부품과 지그를 가져다 서로 위치시킨다.

부품과 지그는 **서로 아무 관계 없는** 각자의 도면이다. 둘을 잇는 자리가 조립이고, 조립에서
구성품의 치수를 조립의 변수로 움직일 수 있어야 실험계획이 뜻을 갖는다.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.api.conftest import Signed

PLATE: dict[str, Any] = {
    "params": {"두께": 10.0},
    "nodes": [
        {
            "id": "판",
            "op": "box",
            "length": 80,
            "width": 50,
            "height": "=두께",
            "align": ["center", "center", "min"],
        }
    ],
}
BASE: dict[str, Any] = {
    "params": {"높이": 20.0},
    "nodes": [
        {
            "id": "받침",
            "op": "box",
            "length": 100,
            "width": 70,
            "height": "=높이",
            "align": ["center", "center", "min"],
        }
    ],
}


def _work(
    client: TestClient, who: Signed, name: str, recipe: dict[str, Any], kind: str
) -> dict[str, Any]:
    made = client.post(
        "/api/works", json={"name": name, "recipe": recipe, "kind": kind}, headers=who.headers
    )
    assert made.status_code == 201, made.text
    got: dict[str, Any] = made.json()
    return got


def test_조립은_부품과_지그를_가져다_놓는다(client: TestClient, member: Signed) -> None:
    part = _work(client, member, "센서 브래킷", PLATE, "part")
    jig = _work(client, member, "시험 지그", BASE, "jig")

    assembly = {
        "params": {"지그_높이": 25.0, "부품_두께": 8.0},
        "nodes": [
            {
                "id": "지그",
                "op": "component",
                "source": f"work:{jig['id']}",
                "params": {"높이": "=지그_높이"},
            },
            {
                "id": "부품",
                "op": "component",
                "source": f"work:{part['id']}",
                "params": {"두께": "=부품_두께"},
                "translate": [0, 0, "=지그_높이"],
            },
            {"id": "조립", "op": "group", "targets": ["지그", "부품"]},
        ],
    }
    made = _work(client, member, "브래킷 + 지그", assembly, "assembly")
    assert made["kind"] == "assembly"
    summary = made["current"]["job"]["summary"]
    assert summary["solid_count"] == 2  # 붙지 않는다 — 둘은 따로 남는다
    assert summary["bbox"]["size"] == [100.0, 70.0, 33.0]  # 지그 25 위에 부품 8

    # 조립의 변수를 바꾸면 구성품 치수까지 따라 움직인다 — 실험계획이 뜻을 갖는 까닭.
    swept = client.post(
        "/api/cad/recipe/sweep",
        json={
            "recipe": assembly,
            "param": "지그_높이",
            "values": [25, 40],
            "material": "aluminum",
        },
        headers=member.headers,
    )
    assert swept.status_code == 200, swept.text
    sizes = [row["geometry"]["bbox"]["size"][2] for row in swept.json()["results"]]
    assert sizes == [33.0, 48.0]


def test_구성품이_바뀌면_조립도_따라간다(client: TestClient, member: Signed) -> None:
    """**살아 있는 레시피**를 가져온다 — STEP 을 박아 넣는 것과 다른 점이다."""
    part = _work(client, member, "판", PLATE, "part")
    assembly = _work(
        client,
        member,
        "판 하나 조립",
        {
            "nodes": [
                {"id": "부품", "op": "component", "source": f"work:{part['id']}"},
                {"id": "조립", "op": "group", "targets": ["부품"]},
            ]
        },
        "assembly",
    )
    assert assembly["current"]["job"]["summary"]["bbox"]["size"] == [80.0, 50.0, 10.0]

    # 부품을 고쳐 새 버전을 만들면(길이 120) 조립을 다시 평가할 때 따라온다.
    nodes: list[dict[str, Any]] = PLATE["nodes"]
    bigger = {**PLATE, "nodes": [{**nodes[0], "length": 120}]}
    client.post(
        f"/api/works/{part['id']}/versions",
        json={"recipe": bigger, "source": "manual", "note": "길게"},
        headers=member.headers,
    )
    again = client.post(
        "/api/cad/recipe/info",
        json={"recipe": assembly["current"]["recipe"]},
        headers=member.headers,
    )
    assert again.json()["summary"]["bbox"]["size"] == [120.0, 50.0, 10.0]


def test_없는_구성품은_어느_피처에서_왜인지_말한다(client: TestClient, member: Signed) -> None:
    got = client.post(
        "/api/cad/recipe/info",
        json={
            "recipe": {
                "nodes": [
                    {
                        "id": "없는것",
                        "op": "component",
                        "source": "part:00000000-0000-0000-0000-000000000000",
                    }
                ]
            }
        },
        headers=member.headers,
    )
    assert got.status_code == 400
    assert got.json()["error"]["details"]["node_id"] == "없는것"
    assert "찾지 못했습니다" in got.json()["error"]["message"]
