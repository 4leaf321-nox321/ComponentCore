"""내 작업 — 그리기 · 버전 · STEP 가져오기 · 지그 생성 · 승격 · 내 공간 경계."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.conftest import Signed

BOX = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 40, "height": 30}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 10},
    ]
}


def _plate(client: TestClient, who: Signed) -> dict[str, object]:
    templates = client.get("/api/cad/recipe/schema", headers=who.headers).json()["templates"]
    return dict(templates["plate_with_holes"])


def _work(
    client: TestClient, who: Signed, recipe: dict[str, object] | None = None
) -> dict[str, object]:
    got = client.post(
        "/api/works", json={"name": "시험 작업", "recipe": recipe or BOX}, headers=who.headers
    )
    assert got.status_code == 201, got.text
    return dict(got.json())


def test_작업과_버전(client: TestClient, member: Signed) -> None:
    work = _work(client, member)
    assert work["current_version"] == 1
    job = work["current"]["job"]  # type: ignore[index]
    assert job["kind"] == "cad" and job["status"] == "done", job["error"]
    assert {one["kind"] for one in job["artifacts"]} == {"model_step", "model_glb"}

    taller = {
        "nodes": [BOX["nodes"][0], {"id": "b", "op": "extrude", "sketch": "s", "distance": 20}]
    }
    v2 = client.post(
        f"/api/works/{work['id']}/versions",
        json={"recipe": taller, "note": "높이 20"},
        headers=member.headers,
    )
    assert v2.status_code == 202, v2.text
    assert v2.json()["number"] == 2 and v2.json()["job"]["summary"]["volume"] == 24000

    back = client.post(f"/api/works/{work['id']}/versions/1/restore", headers=member.headers)
    assert back.status_code == 202 and back.json()["number"] == 3
    numbers = [
        one["number"]
        for one in client.get(
            f"/api/works/{work['id']}/versions", headers=member.headers
        ).json()
    ]
    assert numbers == [3, 2, 1]


def test_내_공간은_남이_못_본다(
    client: TestClient, member: Signed, admin: Signed, db: object
) -> None:
    from sqlalchemy.orm import Session

    from tests.api.conftest import _login, make_user

    work = _work(client, member)
    other = make_user(db, label="other", is_system_admin=False)  # type: ignore[arg-type]
    token = _login(client, other.email)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/works/{work['id']}", headers=headers).status_code == 403
    assert client.get(f"/api/works/{work['id']}", headers=admin.headers).status_code == 200
    # 목록도 내 것만.
    mine = client.get("/api/works", headers=headers).json()
    assert all(one["owner_id"] != work["owner_id"] for one in mine["items"])
    # 작업물도 마찬가지 — 승격되기 전에는 남이 못 받는다.
    artifact = work["current"]["job"]["artifacts"][0]["id"]  # type: ignore[index]
    assert (
        client.get(f"/api/artifacts/{artifact}/download", headers=headers).status_code == 403
    )
    assert isinstance(db, Session)


def test_STEP_을_올리면_import_step_버전(
    client: TestClient, member: Signed, tmp_path: Path
) -> None:
    from app.core import export, primitives

    step = export.write_step(
        primitives.build({"kind": "box", "length": 60, "width": 40, "height": 20}),
        tmp_path / "box.step",
    )
    work = _work(client, member)
    with step.open("rb") as stream:
        got = client.post(
            f"/api/works/{work['id']}/import-step",
            files={"file": ("box.step", stream, "application/step")},
            headers=member.headers,
        )
    assert got.status_code == 202, got.text
    version = got.json()
    assert version["number"] == 2 and version["source"] == "import"
    assert version["recipe"]["nodes"][0]["op"] == "import_step"
    # 평가 작업이 그 STEP 을 읽어 냈다.
    assert version["job"]["status"] == "done", version["job"]["error"]
    assert [round(v) for v in version["job"]["summary"]["bbox"]["size"]] == [60, 40, 20]

    bad = client.post(
        f"/api/works/{work['id']}/import-step",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=member.headers,
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "AJG-WORKS-0005"


def test_지그_생성과_승격(client: TestClient, member: Signed, admin: Signed) -> None:
    work = _work(client, member, _plate(client, member))
    run = client.post(
        f"/api/works/{work['id']}/jig-runs",
        json={"options": {"support_count": 3}},
        headers=member.headers,
    )
    assert run.status_code == 202, run.text
    job = run.json()
    assert job["kind"] == "jig" and job["status"] == "done", job["error"]
    assert {one["kind"] for one in job["summary"]["plan"]["locators"]} == {"pin"}
    assert len(job["summary"]["plan"]["supports"]) == 3
    # 옵션이 작업에 남는다.
    assert (
        client.get(f"/api/works/{work['id']}", headers=member.headers).json()["jig_options"][
            "support_count"
        ]
        == 3
    )

    # 지그를 승격한다 — 제품(형상 v1)이 부품에 없으니 함께 올라간다.
    promoted = client.post(
        f"/api/works/{work['id']}/promote/jig",
        json={"job_id": job["id"], "note": "첫 지그"},
        headers=member.headers,
    )
    assert promoted.status_code == 201, promoted.text
    body = promoted.json()
    assert (
        body["jig_version"] == 1
        and body["part_version"] == 1
        and body["part_promoted_now"] is True
    )

    # 카탈로그에서 누구나 본다 — 남(관리자로 대신)이 부품과 지그와 그 STEP 을 받는다.
    part = client.get(f"/api/parts/{body['part_id']}", headers=admin.headers)
    assert (
        part.status_code == 200
        and part.json()["current_version"] == 1
        and part.json()["jig_count"] == 1
    )
    jig = client.get(f"/api/jigs/{body['jig_id']}", headers=admin.headers)
    assert jig.status_code == 200
    assert (
        jig.json()["part_name"] == "시험 작업" and jig.json()["current"]["part_version"] == 1
    )
    step = next(
        one for one in jig.json()["current"]["job"]["artifacts"] if one["kind"] == "jig_step"
    )
    assert (
        client.get(f"/api/artifacts/{step['id']}/download", headers=admin.headers).status_code
        == 200
    )

    # 같은 생성은 두 번 못 올린다. 같은 형상 버전도.
    again = client.post(
        f"/api/works/{work['id']}/promote/jig",
        json={"job_id": job["id"]},
        headers=member.headers,
    )
    assert again.status_code == 400 and again.json()["error"]["code"] == "AJG-WORKS-0013"
    same = client.post(
        f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers
    )
    assert same.status_code == 400 and same.json()["error"]["code"] == "AJG-WORKS-0010"

    # 형상을 고쳐 다시 승격하면 부품 v2.
    v2 = client.post(
        f"/api/works/{work['id']}/versions",
        json={"recipe": BOX, "note": "상자로"},
        headers=member.headers,
    )
    assert v2.status_code == 202
    part_v2 = client.post(
        f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers
    )
    assert part_v2.status_code == 201 and part_v2.json()["number"] == 2
    assert (
        client.get(f"/api/works/{work['id']}", headers=member.headers).json()[
            "promoted_part_id"
        ]
        == body["part_id"]
    )

    # 남의 부품을 고치는 길은 「내 공간으로 복사」 뿐.
    copied = client.post(
        f"/api/parts/{body['part_id']}/copy-to-work", json={"number": 1}, headers=admin.headers
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["owner_id"] != work["owner_id"]
    assert copied.json()["current"]["source"] == "copy"


def test_형상_없는_작업은_지그를_못_건다(client: TestClient, member: Signed) -> None:
    # 버전 없는 작업은 API 로는 못 만든다 — 마이그레이션이 만든 옛 작업이 그렇다. 직접 만든다.
    from sqlalchemy.orm import Session

    from app.database import SessionLocal
    from app.modules.works.models import Work
    from tests.api.conftest import make_user

    db: Session = SessionLocal()
    try:
        owner = make_user(db, label="empty", is_system_admin=False)
        work = Work(name="빈 작업", owner_id=owner.id)
        db.add(work)
        db.commit()
        from tests.api.conftest import _login

        headers = {"Authorization": f"Bearer {_login(client, owner.email)}"}
        got = client.post(f"/api/works/{work.id}/jig-runs", json={}, headers=headers)
        assert got.status_code == 400 and got.json()["error"]["code"] == "AJG-WORKS-0008"
    finally:
        db.close()
    assert member


def test_STEP_에서_작업_시작(client: TestClient, member: Signed, tmp_path: Path) -> None:
    from app.core import export, primitives

    step = export.write_step(
        primitives.build({"kind": "cylinder", "radius": 10, "height": 30}),
        tmp_path / "peg.step",
    )
    with step.open("rb") as stream:
        got = client.post(
            "/api/works/from-step",
            files={"file": ("peg.step", stream, "application/step")},
            headers=member.headers,
        )
    assert got.status_code == 201, got.text
    work = got.json()
    assert work["name"] == "peg" and work["current_version"] == 1
    assert work["current"]["source"] == "import"
    assert work["current"]["job"]["status"] == "done", work["current"]["job"]["error"]


def test_손으로_그린_지그도_지그_카탈로그로(client: TestClient, member: Signed) -> None:
    """생성기가 만들 수 없는 지그(공진 튜닝 시험 지그 같은 것)는 **그린다** — 그린 것이니
    변수를 심을 수 있고, 그대로 지그로 올라가야 한다."""
    jig = {
        "params": {"튜닝_두께": 6.0},
        "nodes": [
            {"id": "연결판", "op": "box", "length": 60, "width": 60, "height": 12},
            {
                "id": "튜닝보",
                "op": "box",
                "length": 90,
                "width": 40,
                "height": "=튜닝_두께",
                "at": [75, 0, 0],
            },
            {"id": "지그", "op": "union", "targets": ["연결판", "튜닝보"]},
        ],
    }
    work = client.post(
        "/api/works", json={"name": "튜닝 지그", "recipe": jig}, headers=member.headers
    ).json()
    assert work["current"]["job"]["status"] == "done"

    promoted = client.post(
        f"/api/works/{work['id']}/promote/jig-recipe",
        json={"note": "1차 시제"},
        headers=member.headers,
    )
    assert promoted.status_code == 201, promoted.text
    assert promoted.json()["jig_version"] == 1
    assert promoted.json()["part_id"] is None  # 홀로 선 지그 — 부품은 나중에 이어도 된다

    listed = client.get("/api/jigs", headers=member.headers).json()
    assert any(one["name"] == "튜닝 지그 지그" for one in listed["items"])

    # 두 번째 버전도 같은 지그에 쌓인다.
    again = client.post(
        f"/api/works/{work['id']}/promote/jig-recipe", json={}, headers=member.headers
    )
    assert again.status_code == 201 and again.json()["jig_version"] == 2
    assert again.json()["jig_id"] == promoted.json()["jig_id"]


def test_부품이든_지그든_그리는_법은_같고_종류만_다르다(
    client: TestClient, member: Signed
) -> None:
    """종류는 **무엇을 그렸나**를 말할 뿐이다 — 그리기 · 변수 · 실험계획은 똑같이 쓰고,
    승격할 곳과 덤으로 쓰는 도구만 갈린다."""
    box = {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rect", "width": 20, "height": 10}],
            },
            {"id": "b", "op": "extrude", "sketch": "s", "distance": 5},
        ]
    }
    part = client.post(
        "/api/works", json={"name": "브래킷", "recipe": box}, headers=member.headers
    ).json()
    assert part["kind"] == "part"  # 기본은 부품

    jig = client.post(
        "/api/works",
        json={"name": "튜닝 지그", "recipe": box, "kind": "jig"},
        headers=member.headers,
    ).json()
    assert jig["kind"] == "jig" and jig["current"]["job"]["status"] == "done"

    # 지그 작업은 지그 카탈로그로 간다 — 「무엇으로 올릴까」 를 묻지 않는다.
    promoted = client.post(
        f"/api/works/{jig['id']}/promote/jig-recipe", json={}, headers=member.headers
    )
    assert promoted.status_code == 201

    # 그리다 보니 지그였으면 종류를 바꾼다.
    changed = client.patch(
        f"/api/works/{part['id']}", json={"kind": "jig"}, headers=member.headers
    )
    assert changed.status_code == 200 and changed.json()["kind"] == "jig"
    bad = client.patch(
        f"/api/works/{part['id']}", json={"kind": "치구"}, headers=member.headers
    )
    assert bad.status_code == 400 and "모르는 종류" in bad.json()["error"]["message"]


def test_지그_작업에_이어_둔_부품이_승격까지_따라간다(
    client: TestClient, member: Signed
) -> None:
    box = {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rect", "width": 20, "height": 10}],
            },
            {"id": "b", "op": "extrude", "sketch": "s", "distance": 5},
        ]
    }
    product = client.post(
        "/api/works", json={"name": "제품", "recipe": box}, headers=member.headers
    ).json()
    part = client.post(
        f"/api/works/{product['id']}/promote/part", json={}, headers=member.headers
    ).json()

    jig = client.post(
        "/api/works",
        json={
            "name": "지그",
            "recipe": box,
            "kind": "jig",
            "jig_for_part_id": part["part_id"],
        },
        headers=member.headers,
    ).json()
    assert jig["jig_for_part_id"] == part["part_id"]
    assert jig["jig_for_part_name"] == "제품"

    promoted = client.post(
        f"/api/works/{jig['id']}/promote/jig-recipe", json={}, headers=member.headers
    ).json()
    # 따로 고르지 않아도 어느 부품의 지그인지 이어진다.
    assert promoted["part_id"] == part["part_id"]
