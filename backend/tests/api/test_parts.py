"""공용 부품 카탈로그 — **꼬리표가 승격을 넘어온다.**"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import Signed

BOX = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 40, "height": 30}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 10},
    ]
}


def _made(client: TestClient, who: Signed, name: str, tags: list[str]) -> dict[str, object]:
    """꼬리표를 붙인 부품 작업 하나.

    **만들 때가 아니라 고칠 때 붙인다** — 화면이 그렇다(그리고 나서 꼬리표를 단다).
    """
    work = client.post(
        "/api/works",
        json={"name": name, "kind": "part", "recipe": BOX},
        headers=who.headers,
    )
    assert work.status_code == 201, work.text
    if tags:
        고침 = client.patch(
            f"/api/works/{work.json()['id']}", json={"tags": tags}, headers=who.headers
        )
        assert 고침.status_code == 200, 고침.text
    return dict(work.json())


def test_승격하면_꼬리표가_따라온다(client: TestClient, member: Signed) -> None:
    """**사람이 붙여 둔 것이 공용 공간으로 나가면서 없어지고 있었다** — 정작 남이 찾아야
    하는 자리에서.

    내 작업은 열두 개쯤이라 이름만 봐도 찾는다. 공용 카탈로그는 남의 것까지 쌓여서, 부품이
    수백 개가 되면 「EMC 관련 브래킷」 을 찾을 길이 이름 부분일치뿐이다.
    """
    work = _made(client, member, "센서 브래킷", ["브래킷", "EMC"])
    got = client.post(f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers)
    assert got.status_code in (200, 201), got.text

    part = next(
        one
        for one in client.get("/api/parts", headers=member.headers).json()["items"]
        if one["name"] == "센서 브래킷"
    )
    assert sorted(part["tags"]) == ["EMC", "브래킷"], "붙여 둔 것이 그대로 와야 한다"

    # **꼬리표로 거른다** — 공용 공간에서 태그가 쓸모 있는 자리가 이것이다.
    걸러진 = client.get("/api/parts?tag=EMC", headers=member.headers).json()
    assert part["id"] in [one["id"] for one in 걸러진["items"]]
    assert client.get("/api/parts?tag=없는것", headers=member.headers).json()["total"] == 0

    # 자동 완성 목록 — 내 작업의 `GET /works/tags` 와 **같은 모양**이다.
    assert set(client.get("/api/parts/tags", headers=member.headers).json()) >= {
        "EMC",
        "브래킷",
    }


def test_버전을_올릴_때도_새_꼬리표가_따라온다(client: TestClient, member: Signed) -> None:
    """첫 승격 뒤에 작업에 꼬리표를 더했으면 그것도 와야 한다.

    다만 **카탈로그에서 뺀 것을 되살리지는 않는다** — 거기서 지운 것은 뜻이 있다. 더하기만
    한다."""
    work = _made(client, member, "브래킷 둘", ["처음"])
    client.post(f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers)
    client.patch(
        f"/api/works/{work['id']}",
        json={"tags": ["처음", "나중"]},
        headers=member.headers,
    )
    # 같은 버전은 두 번 못 올린다 — 도면을 고쳐 새 버전을 만들고 다시 승격한다.
    다음 = client.post(
        f"/api/works/{work['id']}/versions",
        json={"recipe": {**BOX, "params": {"두께": 12}}},
        headers=member.headers,
    )
    assert 다음.status_code in (200, 201, 202), 다음.text
    두번째 = client.post(
        f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers
    )
    assert 두번째.status_code in (200, 201), 두번째.text

    part = next(
        one
        for one in client.get("/api/parts", headers=member.headers).json()["items"]
        if one["name"] == "브래킷 둘"
    )
    assert sorted(part["tags"]) == ["나중", "처음"]


def test_꼬리표가_없어도_그만이다(client: TestClient, member: Signed) -> None:
    """안 붙이고 승격하는 것이 흔한 길이다 — 빈 목록이지 없는 칸이 아니다."""
    work = _made(client, member, "이름만", [])
    client.post(f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers)
    part = next(
        one
        for one in client.get("/api/parts", headers=member.headers).json()["items"]
        if one["name"] == "이름만"
    )
    assert part["tags"] == []
