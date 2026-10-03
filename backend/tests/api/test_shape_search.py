"""형상으로 찾기 — 이름이 아니라 형상으로 내 작업 · 부품 · 지그를 찾는다.

색인은 버전을 평가하는 작업이 끝날 때 요약에 적히고(`core/shape_index.py`), 목록은 최신
버전의 색인으로 거른다(`shared/shape_search.py`). 그 전에 만든 버전은 관리자가 채운다.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.modules.jobs.models import Job
from tests.api.conftest import Signed


def _plate(length: float, holes: int, thread: str | None = None) -> dict[str, Any]:
    hole: dict[str, Any] = {
        "id": "h",
        "op": "hole",
        "target": "p",
        "at": [[-length / 2 + 10 + 12 * i, 0] for i in range(holes)],
    }
    hole.update({"thread": thread} if thread else {"diameter": 6.6})
    return {
        "params": {"두께": 6.0},
        "nodes": [
            {"id": "p", "op": "box", "length": length, "width": 40, "height": "=두께"},
            hole,
        ],
    }


BENT = {
    "nodes": [
        {
            "id": "m",
            "op": "sheet_metal",
            "thickness": 2,
            "width": 30,
            "path": [[0, 25], [0, 0], [50, 0]],
            "bend_radius": 3,
        }
    ]
}


def _work(client: TestClient, who: Signed, name: str, recipe: dict[str, Any]) -> str:
    made = client.post(
        "/api/works",
        json={"name": name, "recipe": recipe, "kind": "part"},
        headers=who.headers,
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _names(client: TestClient, who: Signed, path: str, **query: Any) -> set[str]:
    got = client.get(path, params=query, headers=who.headers)
    assert got.status_code == 200, got.text
    return {one["name"] for one in got.json()["items"]}


def test_내_작업을_형상으로_거른다(client: TestClient, member: Signed) -> None:
    _work(client, member, "짧은 판", _plate(80, 2))
    _work(client, member, "긴 판", _plate(200, 4))
    _work(client, member, "나사 판", _plate(120, 4, thread="M6"))
    _work(client, member, "굽힌 판", BENT)
    everything = {"짧은 판", "긴 판", "나사 판", "굽힌 판"}
    assert _names(client, member, "/api/works") == everything

    # ① 레시피로 — 들어 있는 것 · 나사 · 변수.
    assert _names(client, member, "/api/works", has="sheet_metal") == {"굽힌 판"}
    assert _names(client, member, "/api/works", has="hole") == everything - {"굽힌 판"}
    assert _names(client, member, "/api/works", thread="m6") == {"나사 판"}
    assert _names(client, member, "/api/works", param="두께") == everything - {"굽힌 판"}

    # ② 치수로 — 상자 안에 드나(방향 무관) · 부피 · 구멍 지름과 개수.
    assert _names(client, member, "/api/works", fits="130x50x10") == {"짧은 판", "나사 판"}
    # 두 변만 주면 큰 두 변만 견준다 — 굽힌 판(약 52 x 30 x 27)도 90 x 45 에 든다.
    assert _names(client, member, "/api/works", fits="45 x 90") == {"짧은 판", "굽힌 판"}
    assert _names(client, member, "/api/works", hole=6.6, holes=4) == {"긴 판", "나사 판"}
    assert _names(client, member, "/api/works", hole=6.6) == everything - {"굽힌 판"}
    assert _names(client, member, "/api/works", holes=3) == {"긴 판", "나사 판"}
    small = _names(client, member, "/api/works", volume_max=25000)
    assert small == {"짧은 판", "굽힌 판"}
    # 조건은 모두 맞아야 — 나사가 있고 상자 안에 들어도 구멍이 5 개 이상인 것은 없다.
    assert _names(client, member, "/api/works", thread="M6", hole=6.6, holes=5) == set()
    assert (
        client.get("/api/works", params={"fits": "크게"}, headers=member.headers).status_code
        == 400
    )

    # 목록 한 줄에도 형상이 붙는다 — 크기 · 구멍을 열지 않고 본다.
    rows = client.get("/api/works", params={"has": "sheet_metal"}, headers=member.headers)
    shape = rows.json()["items"][0]["shape"]
    assert (
        shape["ops"] == ["sheet_metal"]
        and shape["hole_count"] == 0
        and len(shape["dims"]) == 3
    )


def test_부품_카탈로그와_채우기(
    client: TestClient, member: Signed, admin: Signed, db: Session
) -> None:
    work = _work(client, member, "카탈로그 판", _plate(150, 3, thread="M6"))
    promoted = client.post(f"/api/works/{work}/promote/part", json={}, headers=member.headers)
    assert promoted.status_code in (200, 201), promoted.text
    found = _names(client, member, "/api/parts", thread="M6", fits="160x50x10")
    assert "카탈로그 판" in found
    assert "카탈로그 판" not in _names(client, member, "/api/parts", fits="100x50x10")

    # 이 기능 전에 만든 버전 흉내 — 요약에서 색인을 지운다. 그러면 형상 조건에서 빠진다.
    job_id = client.get(f"/api/works/{work}", headers=member.headers).json()["current"]["job"][
        "id"
    ]
    job = db.get(Job, job_id)
    assert job is not None and job.summary is not None
    job.summary = {key: value for key, value in job.summary.items() if key != "shape"}
    flag_modified(job, "summary")
    db.commit()
    assert "카탈로그 판" not in _names(client, member, "/api/parts", thread="M6")

    # 관리자가 채운다 — 남긴 STEP 에서 색인을 다시 뽑는다(레시피에서 나사 · 변수도).
    assert client.get("/api/server/shape-index", headers=member.headers).status_code == 403
    status = client.get("/api/server/shape-index", headers=admin.headers)
    assert status.json()["missing"] >= 1
    for _ in range(20):
        got = client.post("/api/server/shape-index?limit=50", headers=admin.headers).json()
        if got["remaining"] == 0:
            break
    assert got["remaining"] == 0
    assert "카탈로그 판" in _names(
        client, member, "/api/parts", thread="M6", hole=6.6, holes=3
    )


def test_지그_카탈로그도(client: TestClient, member: Signed) -> None:
    made = client.post(
        "/api/works",
        json={"name": "굽힌 받침", "recipe": BENT, "kind": "jig"},
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    up = client.post(
        f"/api/works/{made.json()['id']}/promote/jig-recipe", json={}, headers=member.headers
    )
    assert up.status_code == 201, up.text
    assert "굽힌 받침 지그" in _names(client, member, "/api/jigs", has="sheet_metal")
    assert "굽힌 받침 지그" not in _names(client, member, "/api/jigs", has="frame")
