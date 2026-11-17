"""공용 조립 — 조립을 공용 공간에 올리고 남이 「내 작업 공간으로 복사」 해 연다(2026-11-17).

조립은 구성품을 **참조**로 든다(`work:` · `part:` · `jig:`). 내 작업(`work:`)은 남이 못
읽으므로 그대로 올리면 복사한 사람이 열지 못한다 — 올릴 때 공용 참조로 바꾸고, 공용에 없는 내
구성품은 함께 올린다. 공용 참조는 지금 버전으로 고정한다(등록된 조립의 모양이 바뀌지 않게).
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api.conftest import Signed, _login, make_user
from tests.api.test_assembly import BASE, PLATE, _work


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201, 202), response.text
    return response.json()


def _assembly(client: TestClient, who: Signed) -> dict[str, Any]:
    """판(내 작업) + 받침(이미 공용 부품으로 올린 것)."""
    plate = _work(client, who, "판", PLATE, "part")
    base = _work(client, who, "받침", BASE, "part")
    published = _ok(
        client.post(f"/api/works/{base['id']}/promote/part", json={}, headers=who.headers)
    )
    recipe = {
        "nodes": [
            {"id": "받침", "op": "component", "source": f"part:{published['part_id']}"},
            {
                "id": "판",
                "op": "component",
                "source": f"work:{plate['id']}",
                "translate": [0, 0, 20],
            },
            {"id": "조립", "op": "group", "targets": ["받침", "판"]},
        ]
    }
    made = _work(client, who, "판 + 받침", recipe, "assembly")
    return {"assembly": made, "plate": plate, "base_part": published["part_id"]}


def test_조립을_올리면_구성품이_공용_참조로_바뀌고_남이_복사해_연다(
    client: TestClient, member: Signed, db: Session
) -> None:
    made = _assembly(client, member)
    work_id = made["assembly"]["id"]
    plan = _ok(client.get(f"/api/works/{work_id}/promote/assembly", headers=member.headers))
    actions = {one["node"]: (one["action"], one["kind"]) for one in plan["components"]}
    assert actions == {"받침": ("pin", "part"), "판": ("register", "part")}
    assert all(
        one["target"] is None for one in plan["components"] if one["action"] == "register"
    )

    promoted = _ok(
        client.post(
            f"/api/works/{work_id}/promote/assembly",
            json={"name": "공용 판 조립"},
            headers=member.headers,
        )
    )
    assert promoted["part_version"] == 1
    catalog = _ok(client.get(f"/api/parts/{promoted['part_id']}", headers=member.headers))
    assert catalog["kind"] == "assembly"
    sources = [one.get("source") for one in catalog["current"]["recipe"]["nodes"]]
    assert sources[0] == f"part:{made['base_part']}@1", "공용 부품은 지금 버전으로 고정"
    assert sources[1].startswith("part:") and sources[1].endswith("@1"), "판은 함께 올라갔다"
    assert not any(str(one).startswith("work:") for one in sources)
    # 판 작업도 이제 공용 부품이 있다.
    plate = _ok(client.get(f"/api/works/{made['plate']['id']}", headers=member.headers))
    assert plate["promoted_part_id"] == sources[1].split(":")[1].split("@")[0]

    # 목록 — 부품 목록에는 안 섞이고, 조립 목록에만.
    parts = _ok(client.get("/api/parts", headers=member.headers))["items"]
    assemblies = _ok(client.get("/api/parts?kind=assembly", headers=member.headers))["items"]
    assert promoted["part_id"] not in [one["id"] for one in parts]
    assert [one["id"] for one in assemblies] == [promoted["part_id"]]

    # 남이 복사하면 조립 작업이 되고, 평가된다(모든 구성품을 연다).
    other = make_user(db, label="other", is_system_admin=False)
    headers = Signed(email=other.email, token=_login(client, other.email)).headers
    copied = client.post(
        f"/api/parts/{promoted['part_id']}/copy-to-work", json={}, headers=headers
    )
    assert copied.status_code == 201, copied.text
    work = copied.json()
    assert work["kind"] == "assembly"
    assert work["current"]["job"]["status"] == "done", work["current"]["job"]
    assert work["current"]["job"]["summary"]["solid_count"] == 2


def test_다시_올리면_이미_올린_구성품을_가리키고_같은_버전은_막는다(
    client: TestClient, member: Signed
) -> None:
    made = _assembly(client, member)
    work_id = made["assembly"]["id"]
    _ok(client.post(f"/api/works/{work_id}/promote/assembly", json={}, headers=member.headers))
    again = client.post(
        f"/api/works/{work_id}/promote/assembly", json={}, headers=member.headers
    )
    assert again.status_code == 400 and "이미" in again.json()["error"]["message"]
    # 조립을 고쳐 새 버전으로 — 판은 이미 공용에 있으니 그것을 가리킨다(reuse).
    current = _ok(client.get(f"/api/works/{work_id}", headers=member.headers))["current"]
    moved = {**current["recipe"]}
    moved["nodes"] = [
        *[one for one in moved["nodes"] if one["id"] != "판"],
    ]
    moved["nodes"].insert(
        1,
        {
            "id": "판",
            "op": "component",
            "source": f"work:{made['plate']['id']}",
            "translate": [0, 0, 25],
        },
    )
    _ok(
        client.post(
            f"/api/works/{work_id}/versions",
            json={"recipe": moved, "note": "판을 올림"},
            headers=member.headers,
        )
    )
    plan = _ok(client.get(f"/api/works/{work_id}/promote/assembly", headers=member.headers))
    assert {one["node"]: one["action"] for one in plan["components"]} == {
        "받침": "pin",
        "판": "reuse",
    }
    second = _ok(
        client.post(f"/api/works/{work_id}/promote/assembly", json={}, headers=member.headers)
    )
    assert second["part_version"] == 2


def test_조립은_부품으로_올리지_않고_부품은_조립으로_올리지_않는다(
    client: TestClient, member: Signed
) -> None:
    made = _assembly(client, member)
    as_part = client.post(
        f"/api/works/{made['assembly']['id']}/promote/part", json={}, headers=member.headers
    )
    assert as_part.status_code == 400 and "공용 조립으로 등록" in as_part.text
    plate = client.get(
        f"/api/works/{made['plate']['id']}/promote/assembly", headers=member.headers
    )
    assert plate.status_code == 400 and "조립 작업만" in plate.text
