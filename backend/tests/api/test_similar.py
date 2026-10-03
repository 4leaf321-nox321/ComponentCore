"""닮은 형상 찾기(`POST /search/similar`) — 최신 버전의 형상 색인끼리 견준다.

카탈로그는 시험 사이에 쌓이므로 시험마다 다른 이름표(`t`)를 붙이고 그 이름의 것만 본다.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.modules.jobs.models import Job
from tests.api.conftest import Signed

FOUR: list[list[float]] = [[-40, -20], [40, -20], [40, 20], [-40, 20]]


def _plate(length: float, holes: list[list[float]], thread: str = "M6") -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {"id": "p", "op": "box", "length": length, "width": 60, "height": 10}
    ]
    if holes:
        nodes.append({"id": "h", "op": "hole", "target": "p", "thread": thread, "at": holes})
    return {"nodes": nodes}


def _work(client: TestClient, who: Signed, name: str, recipe: dict[str, Any]) -> str:
    made = client.post(
        "/api/works",
        json={"name": name, "recipe": recipe, "kind": "part"},
        headers=who.headers,
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _similar(client: TestClient, who: Signed, **body: Any) -> Any:
    got = client.post("/api/search/similar", json=body, headers=who.headers)
    assert got.status_code == 200, got.text
    return got.json()


def _mine(answer: dict[str, Any], t: str) -> list[dict[str, Any]]:
    return [one for one in answer["items"] if t in one["name"]]


def test_내_작업과_카탈로그에서_닮은_것을_점수_순으로(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    t = uuid.uuid4().hex[:6]
    base = _work(client, member, f"기준 판{t}", _plate(100, FOUR))
    _work(client, member, f"길이 110 판{t}", _plate(110, FOUR))
    _work(client, member, f"구멍 둘 판{t}", _plate(100, FOUR[:2]))
    _work(client, member, f"구멍 없는 판{t}", _plate(100, []))
    _work(
        client,
        member,
        f"ㄱ자 판금{t}",
        {
            "nodes": [
                {
                    "id": "m",
                    "op": "sheet_metal",
                    "thickness": 3,
                    "width": 60,
                    "path": [[0, 60], [0, 0], [100, 0]],
                    "bend_radius": 3,
                }
            ]
        },
    )
    # 기준 판을 부품으로 올리고 그 부품의 지그를 하나 둔다 — 「비슷한 부품의 지그」.
    copy = _work(client, member, f"복사 판{t}", _plate(100, FOUR))
    part = client.post(f"/api/works/{copy}/promote/part", json={}, headers=member.headers)
    assert part.status_code in (200, 201), part.text
    part_id = part.json()["part_id"]
    jig_work = client.post(
        "/api/works",
        json={"name": f"받침{t}", "recipe": _plate(140, []), "kind": "jig"},
        headers=member.headers,
    ).json()["id"]
    jig = client.post(
        f"/api/works/{jig_work}/promote/jig-recipe",
        json={"part_id": part_id},
        headers=member.headers,
    )
    assert jig.status_code == 201, jig.text

    got = _similar(client, member, source=f"work:{base}", limit=50)
    rows = _mine(got, t)
    names = [one["name"] for one in rows]
    # 자기 자신은 빠지고, 닮은 순 — 판금 ㄱ자는 맨 뒤.
    assert f"기준 판{t}" not in names
    assert names.index(f"길이 110 판{t}") < names.index(f"구멍 둘 판{t}")
    assert names.index(f"구멍 둘 판{t}") < names.index(f"구멍 없는 판{t}")
    assert names[-1] in (f"ㄱ자 판금{t}", f"받침{t} 지그")
    best = rows[0]
    assert best["score"] > 0.9 and "크기 비슷" in best["why"] and "구멍 같음" in best["why"]
    assert set(best["parts"]) >= {"size", "proportion", "fill", "holes", "ops", "solids"}
    # 같은 모양의 부품(복사 판에서 올린 것)이 카탈로그에서 나오고, 그 부품의 지그가 붙는다.
    catalog = next(one for one in rows if one["source"].startswith("part:"))
    assert catalog["source"] == f"part:{part_id}" and catalog["score"] == 1.0
    assert [one["name"] for one in catalog["jigs"]] == [f"받침{t} 지그"]

    # 부품에서 물으면 — 자기 자신과 **같은 버전**(그 부품을 올린 작업)은 빠진다.
    from_part = _similar(client, member, source=f"part:{part_id}", limit=50)
    assert f"복사 판{t}" not in [one["name"] for one in _mine(from_part, t)]
    assert f"기준 판{t}" in [one["name"] for one in _mine(from_part, t)]
    # 남(관리자)이 물으면 남의 작업은 안 보이고 카탈로그만 — 부품 자신은 빠지니 그 지그가
    # 남는다.
    other = _similar(client, admin, source=f"part:{part_id}", limit=50)
    assert {one["source"].split(":")[0] for one in _mine(other, t)} == {"jig"}
    assert _mine(other, t)[0]["part_name"] == f"복사 판{t}"

    # 저장 전 레시피로도 — 새로 그리기 전에 「이미 있나」.
    fresh = _similar(client, member, recipe=_plate(105, FOUR), where=["works"], limit=50)
    assert fresh["reference"]["source"] is None
    assert {one["source"].split(":")[0] for one in fresh["items"]} == {"work"}
    assert _mine(fresh, t)[0]["name"] in (f"기준 판{t}", f"복사 판{t}", f"길이 110 판{t}")


def test_묻는_것이_틀리면_말한다(
    client: TestClient, member: Signed, admin: Signed, db: Session
) -> None:
    t = uuid.uuid4().hex[:6]
    work = _work(client, member, f"판{t}", _plate(100, FOUR))
    bad = client.post(
        "/api/search/similar", json={"source": "chair:1"}, headers=member.headers
    )
    assert bad.status_code == 400 and "work:<id>" in bad.json()["error"]["message"]
    both = client.post(
        "/api/search/similar",
        json={"source": f"work:{work}", "recipe": _plate(10, [])},
        headers=member.headers,
    )
    assert both.status_code == 422
    # 남의 작업은 견줄 수 없다.
    other = client.post(
        "/api/search/similar", json={"source": f"work:{work}"}, headers=admin.headers
    )
    assert other.status_code == 200  # 관리자는 볼 수 있다
    # 색인이 없는 버전(이 기능 전)은 그렇다고 말한다.
    job_id = client.get(f"/api/works/{work}", headers=member.headers).json()["current"]["job"][
        "id"
    ]
    job = db.get(Job, job_id)
    assert job is not None and job.summary is not None
    job.summary = {key: value for key, value in job.summary.items() if key != "shape"}
    flag_modified(job, "summary")
    db.commit()
    missing = client.post(
        "/api/search/similar", json={"source": f"work:{work}"}, headers=member.headers
    )
    assert (
        missing.status_code == 400 and "형상 색인 채우기" in missing.json()["error"]["message"]
    )
