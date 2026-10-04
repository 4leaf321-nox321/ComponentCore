"""내 작업의 **폴더 · 연도** — 경로로 놓고, 폴더째 옮기고, 그 아래까지 거른다."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.modules.works.models import Work
from tests.api.conftest import Signed


def _work(client: TestClient, who: Signed, name: str, folder: str = "") -> dict[str, Any]:
    got = client.post(
        "/api/works",
        json={"name": name, "kind": "assembly", "folder": folder},
        headers=who.headers,
    )
    assert got.status_code == 201, got.text
    return dict(got.json())


def _names(client: TestClient, who: Signed, **params: Any) -> list[str]:
    page = client.get("/api/works", params={"limit": 100, **params}, headers=who.headers)
    assert page.status_code == 200, page.text
    return sorted(one["name"] for one in page.json()["items"])


def test_폴더_경로는_한_모양으로_적힌다(client: TestClient, member: Signed) -> None:
    made = _work(client, member, "가", " /고객A//2026/ ")
    assert made["folder"] == "고객A/2026"
    deep = "/".join(f"단{i}" for i in range(9))
    bad = client.post(
        "/api/works", json={"name": "깊음", "kind": "assembly", "folder": deep},
        headers=member.headers,
    )  # fmt: skip
    assert bad.status_code == 400 and "8단계" in bad.json()["error"]["message"]


def test_폴더로_거르고_하위까지_또는_바로_그_폴더만(
    client: TestClient, member: Signed
) -> None:
    _work(client, member, "맨위")
    _work(client, member, "가", "고객A")
    _work(client, member, "나", "고객A/2026")
    _work(client, member, "다", "고객B")
    _work(client, member, "라", "고객A_비슷")  # LIKE 의 _ 를 글자로 읽는지
    assert _names(client, member, folder="고객A") == ["가", "나"]
    assert _names(client, member, folder="고객A", subfolders=False) == ["가"]
    assert _names(client, member, folder="", subfolders=False) == ["맨위"]
    assert _names(client, member) == ["가", "나", "다", "라", "맨위"]

    folders = client.get("/api/works/folders", headers=member.headers).json()
    assert folders == [
        {"path": "", "count": 1},
        {"path": "고객A", "count": 1},
        {"path": "고객A/2026", "count": 1},
        {"path": "고객A_비슷", "count": 1},
        {"path": "고객B", "count": 1},
    ]


def test_폴더째_옮기고_합치고_지우면_위로(client: TestClient, member: Signed) -> None:
    _work(client, member, "가", "고객A")
    _work(client, member, "나", "고객A/2026/검사")
    _work(client, member, "다", "보관")
    moved = client.post(
        "/api/works/folders/rename", json={"path": "고객A", "to": "보관/고객A"},
        headers=member.headers,
    )  # fmt: skip
    assert moved.json() == {"moved": 2}
    paths = [
        one["path"] for one in client.get("/api/works/folders", headers=member.headers).json()
    ]
    assert paths == ["", "보관", "보관/고객A", "보관/고객A/2026", "보관/고객A/2026/검사"]
    # 폴더 지우기 = 위 폴더로 합치기 — 작업은 그대로 있다.
    gone = client.post(
        "/api/works/folders/rename", json={"path": "보관/고객A", "to": "보관"},
        headers=member.headers,
    )  # fmt: skip
    assert gone.json() == {"moved": 2}
    assert _names(client, member, folder="보관", subfolders=False) == ["가", "다"]
    assert _names(client, member, folder="보관/2026/검사") == ["나"]
    # 제 하위로는 못 옮긴다.
    loop = client.post(
        "/api/works/folders/rename", json={"path": "보관", "to": "보관/안"},
        headers=member.headers,
    )  # fmt: skip
    assert loop.status_code == 400


def test_여럿을_골라_옮기고_남의_것은_못_옮긴다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    a = _work(client, member, "가")
    b = _work(client, member, "나")
    done = client.post(
        "/api/works/move", json={"ids": [a["id"], b["id"]], "folder": "2026/프로젝트"},
        headers=member.headers,
    )  # fmt: skip
    assert done.json() == {"moved": 2}
    assert _names(client, member, folder="2026") == ["가", "나"]
    theirs = _work(client, admin, "남의 것")
    refused = client.post(
        "/api/works/move", json={"ids": [a["id"], theirs["id"]], "folder": "훔침"},
        headers=member.headers,
    )  # fmt: skip
    assert refused.status_code in (403, 404)
    assert _names(client, member, folder="훔침") == []
    # 작업 화면에서 하나만 옮기기 — PATCH.
    patched = client.patch(
        f"/api/works/{a['id']}", json={"folder": "보관"}, headers=member.headers
    )
    assert patched.json()["folder"] == "보관"


def test_만든_해로_거르고_해마다_센다(client: TestClient, member: Signed, db: Session) -> None:
    old = _work(client, member, "작년")
    _work(client, member, "올해")
    db.execute(
        update(Work)
        .where(Work.id == old["id"])
        .values(created_at=dt.datetime(2025, 6, 1, 12, tzinfo=dt.UTC))
    )
    db.commit()
    years = client.get("/api/works/years", headers=member.headers).json()
    this_year = dt.datetime.now(dt.UTC).year
    assert {"year": 2025, "count": 1} in years and years[0]["year"] == this_year
    assert _names(client, member, year=2025) == ["작년"]
    summary = client.get("/api/works", params={"year": 2025}, headers=member.headers).json()
    assert summary["items"][0]["created_at"].startswith("2025-06-01")


@pytest.mark.parametrize("path", ["", "/"])
def test_맨_위는_옮길_수_없다(client: TestClient, member: Signed, path: str) -> None:
    got = client.post(
        "/api/works/folders/rename", json={"path": path or "/", "to": "어디"},
        headers=member.headers,
    )  # fmt: skip
    assert got.status_code == 400


def test_만든_순서로도_받는다(client: TestClient, member: Signed) -> None:
    first = _work(client, member, "먼저")
    _work(client, member, "나중")
    # 먼저 만든 것을 고치면 「고친 순」 으로는 앞에 오고, 「만든 순」 으로는 뒤에 남는다.
    client.patch(
        f"/api/works/{first['id']}", json={"description": "고침"}, headers=member.headers
    )
    updated = client.get("/api/works", headers=member.headers).json()["items"]
    created = client.get("/api/works", params={"order": "created"}, headers=member.headers)
    assert [one["name"] for one in updated] == ["먼저", "나중"]
    assert [one["name"] for one in created.json()["items"]] == ["나중", "먼저"]
