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
