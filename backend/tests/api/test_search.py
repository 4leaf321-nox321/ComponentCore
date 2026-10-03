"""찾기 규칙 한 곳(`shared/search.py`) — 내 작업 · 부품 · 지그 · 템플릿 · DOE 가 같은 답을
낸다.

낱말마다 AND, 이름 · 설명 · 꼬리표 · 만든 사람, `%` · `_` 는 글자 그대로. DOE 는 대상 작업의
이름 · 꼬리표로도 찾는다. 카탈로그 · 공개 DOE 는 시험 사이에 쌓이므로 이름 · 꼬리표 · 사람에
시험마다 다른 표를 붙인다.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api.conftest import Signed, _login, make_user

BOX: dict[str, Any] = {
    "params": {"두께": 6.0},
    "nodes": [{"id": "b", "op": "box", "length": 40, "width": 30, "height": "=두께"}],
}


def _token() -> str:
    return uuid.uuid4().hex[:6]


def _someone(client: TestClient, db: Session, name: str) -> Signed:
    """표시 이름이 남과 안 겹치는 사람 — 만든 사람 이름으로 찾는 것을 본다."""
    user = make_user(db, label=name, is_system_admin=False)
    return Signed(email=user.email, token=_login(client, user.email))


def _work(
    client: TestClient,
    who: Signed,
    name: str,
    *,
    description: str = "",
    tags: tuple[str, ...] = (),
) -> str:
    made = client.post(
        "/api/works",
        json={"name": name, "description": description, "recipe": BOX, "kind": "part"},
        headers=who.headers,
    )
    assert made.status_code == 201, made.text
    work_id = str(made.json()["id"])
    if tags:
        got = client.patch(
            f"/api/works/{work_id}", json={"tags": list(tags)}, headers=who.headers
        )
        assert got.status_code == 200, got.text
    return work_id


def _names(client: TestClient, who: Signed, path: str, **params: Any) -> list[str]:
    got = client.get(path, params=params, headers=who.headers)
    assert got.status_code == 200, got.text
    return sorted(one["name"] for one in got.json()["items"])


def test_낱말마다_AND_이름_설명_꼬리표_만든_사람(client: TestClient, member: Signed) -> None:
    t = _token()
    _work(client, member, f"브래킷 EMC{t}", description=f"알루미늄{t} 판", tags=(f"고객{t}",))
    _work(client, member, f"받침판{t}", description="강", tags=(f"EMC{t}", f"고객{t}"))
    _work(client, member, f"100% 가득{t}")
    _work(client, member, f"100 가득{t}")

    assert _names(client, member, "/api/works", q="브래킷") == [f"브래킷 EMC{t}"]
    # 이름에 있든 꼬리표에 있든 — 한 낱말은 어느 칸에 있어도 된다.
    assert _names(client, member, "/api/works", q=f"EMC{t}") == [
        f"받침판{t}",
        f"브래킷 EMC{t}",
    ]
    # 두 낱말은 둘 다 들어야 한다(설명 + 이름).
    assert _names(client, member, "/api/works", q=f"알루미늄{t} 브래킷") == [f"브래킷 EMC{t}"]
    assert _names(client, member, "/api/works", q=f"알루미늄{t} 받침") == []
    # 와일드카드는 글자다 — `100%` 는 `100 가득` 을 집지 않는다(낱말 `100` 은 둘 다 든다).
    assert _names(client, member, "/api/works", q=f"100% 가득{t}") == [f"100% 가득{t}"]
    assert _names(client, member, "/api/works", q=f"100 가득{t}") == [
        f"100 가득{t}",
        f"100% 가득{t}",
    ]
    # 꼬리표 칩(정확히 그 꼬리표)은 그대로.
    assert _names(client, member, "/api/works", tag=f"고객{t}") == [
        f"받침판{t}",
        f"브래킷 EMC{t}",
    ]


def test_카탈로그는_만든_사람과_물려받은_꼬리표로도_찾는다(
    client: TestClient, admin: Signed, db: Session
) -> None:
    t = _token()
    owner = _someone(client, db, f"검색주인{t}")
    work = _work(client, owner, f"센서{t} 브래킷", description="진동 시험", tags=(f"고객{t}",))
    up = client.post(f"/api/works/{work}/promote/part", json={}, headers=owner.headers)
    assert up.status_code in (200, 201), up.text
    jig = client.post(
        f"/api/works/{work}/promote/jig-recipe",
        json={"part_id": up.json()["part_id"]},
        headers=owner.headers,
    )
    assert jig.status_code == 201, jig.text

    # 남(관리자)이 부품을 찾는다 — 승격이 물려준 꼬리표와 올린 사람 이름으로도.
    assert _names(client, admin, "/api/parts", q=f"고객{t}") == [f"센서{t} 브래킷"]
    assert _names(client, admin, "/api/parts", q=f"검색주인{t}") == [f"센서{t} 브래킷"]
    assert _names(client, admin, "/api/parts", q=f"검색주인{t} 진동") == [f"센서{t} 브래킷"]
    assert _names(client, admin, "/api/parts", q=f"검색주인{t} 없는말") == []
    # 지그는 **부품 이름**으로도 — 「센서 브래킷의 지그」.
    assert _names(client, admin, "/api/jigs", q=f"센서{t}") == [f"센서{t} 브래킷 지그"]
    assert _names(client, admin, "/api/jigs", q=f"검색주인{t}") == [f"센서{t} 브래킷 지그"]


def test_DOE_는_대상_작업의_이름과_꼬리표로_찾는다(
    client: TestClient, admin: Signed, db: Session
) -> None:
    t = _token()
    owner = _someone(client, db, f"훑는이{t}")
    bracket = _work(client, owner, f"브래킷{t} EMC", tags=(f"고객{t}",))
    plate = _work(client, owner, f"받침판{t}")
    for name, work_id in ((f"두께 훑기{t}", bracket), (f"받침 두께{t}", plate)):
        made = client.post(
            "/api/doe",
            json={
                "name": name,
                "recipe": BOX,
                "factors": [{"name": "두께", "mode": "list", "values": [4, 6]}],
                "work_id": work_id,
                "conditions": {},
            },
            headers=owner.headers,
        )
        assert made.status_code == 201, made.text

    both = [f"두께 훑기{t}", f"받침 두께{t}"]
    assert _names(client, owner, "/api/doe", q=f"브래킷{t}") == [
        f"두께 훑기{t}"
    ]  # 대상 작업 이름
    assert _names(client, owner, "/api/doe", q="두께") == both
    assert _names(client, owner, "/api/doe", q=f"두께 받침판{t}") == [f"받침 두께{t}"]
    assert _names(client, owner, "/api/doe", tag=f"고객{t}") == [
        f"두께 훑기{t}"
    ]  # 대상 작업 꼬리표
    tags = client.get("/api/doe/tags", headers=owner.headers)
    assert tags.status_code == 200 and tags.json() == [f"고객{t}"]
    # 공개(read)라 남도 찾는다 — 만든 사람 이름으로도. 내 것만 보면 없다.
    assert _names(client, admin, "/api/doe", scope="all", q=f"훑는이{t} 브래킷") == [
        f"두께 훑기{t}"
    ]
    assert _names(client, admin, "/api/doe", q=f"브래킷{t}") == []
