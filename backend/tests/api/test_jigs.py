from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import Signed


def _create(client: TestClient, who: Signed, **extra: object) -> dict[str, object]:
    got = client.post(
        "/api/jigs/projects", json={"name": "시험 제품", **extra}, headers=who.headers
    )
    assert got.status_code == 201, got.text
    return dict(got.json())


def test_옵션_기본값을_서버가_준다(client: TestClient, member: Signed) -> None:
    got = client.get("/api/jigs/options", headers=member.headers)
    assert got.status_code == 200
    assert got.json()["defaults"]["support_height"] > 0
    assert "bracket" in got.json()["primitive_kinds"]


def test_제품_파일_없이_지그를_만든다(client: TestClient, member: Signed) -> None:
    project = _create(client, member)
    assert project["has_product_file"] is False

    run = client.post(
        f"/api/jigs/projects/{project['id']}/runs", json={}, headers=member.headers
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "done", body["error"]
    summary = body["summary"]
    assert summary["interference"]["ok"] is True
    assert len(summary["plan"]["supports"]) >= 3
    assert {"jig_step", "assembly_step", "jig_glb", "product_glb"} <= set(body["files"])

    step = client.get(
        f"/api/jigs/projects/{project['id']}/runs/{body['id']}/files/jig_step",
        headers=member.headers,
    )
    assert step.status_code == 200
    assert step.content.startswith(b"ISO-10303-21")


def test_기본_도형_스펙을_제품으로(client: TestClient, member: Signed) -> None:
    spec = {"kind": "plate_with_holes", "length": 100, "width": 60, "thickness": 12}
    project = _create(client, member, product_spec=spec)
    run = client.post(
        f"/api/jigs/projects/{project['id']}/runs",
        json={"options": {"support_count": 3, "export_gltf": False}},
        headers=member.headers,
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "done", body["error"]
    assert body["options"]["support_count"] == 3
    assert len(body["summary"]["plan"]["supports"]) == 3
    # 관통 구멍이 있으니 핀 로케이터가 잡힌다.
    kinds = {one["kind"] for one in body["summary"]["plan"]["locators"]}
    assert kinds == {"pin"}
    assert "jig_glb" not in body["files"]


def test_틀린_도형_스펙은_저장에서_거절(client: TestClient, member: Signed) -> None:
    got = client.post(
        "/api/jigs/projects",
        json={"name": "x", "product_spec": {"kind": "sphere"}},
        headers=member.headers,
    )
    assert got.status_code == 400
    assert got.json()["error"]["code"] == "AJG-JIGS-0003"


def test_STEP_을_올리고_돌린다(client: TestClient, member: Signed, tmp_path: object) -> None:
    # 코어로 STEP 하나를 만들어 올린다 — 진짜 파일 경로를 타는지 본다.
    from pathlib import Path

    from app.core import export, primitives

    step = export.write_step(
        primitives.build({"kind": "box", "length": 60, "width": 40, "height": 20}),
        Path(str(tmp_path)) / "box.step",
    )
    project = _create(client, member)
    with step.open("rb") as stream:
        uploaded = client.post(
            f"/api/jigs/projects/{project['id']}/product",
            files={"file": ("box.step", stream, "application/step")},
            headers=member.headers,
        )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["has_product_file"] is True
    assert uploaded.json()["product_filename"] == "box.step"

    run = client.post(
        f"/api/jigs/projects/{project['id']}/runs", json={}, headers=member.headers
    )
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "done", run.json()["error"]
    size = run.json()["summary"]["geometry"]["bbox"]["size"]
    assert [round(v) for v in size] == [60, 40, 20]


def test_STEP_아닌_파일은_거절(client: TestClient, member: Signed) -> None:
    project = _create(client, member)
    got = client.post(
        f"/api/jigs/projects/{project['id']}/product",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=member.headers,
    )
    assert got.status_code == 400
    assert got.json()["error"]["code"] == "AJG-JIGS-0004"


def test_남의_프로젝트는_못_고친다(client: TestClient, member: Signed, admin: Signed) -> None:
    project = _create(client, member)
    other = client.patch(
        f"/api/jigs/projects/{project['id']}", json={"name": "바꿈"}, headers=admin.headers
    )
    assert other.status_code == 200  # 시스템 관리자는 된다
    # 관리자가 만든 것을 일반 사용자가 고치면 403
    theirs = _create(client, admin)
    got = client.patch(
        f"/api/jigs/projects/{theirs['id']}", json={"name": "바꿈"}, headers=member.headers
    )
    assert got.status_code == 403


def test_CAD_작업대(client: TestClient, member: Signed) -> None:
    kinds = client.get("/api/cad/primitives", headers=member.headers)
    assert kinds.status_code == 200
    spec = kinds.json()["examples"]["bracket"]
    info = client.post("/api/cad/primitives/info", json={"spec": spec}, headers=member.headers)
    assert info.status_code == 200, info.text
    assert info.json()["volume"] > 0
    glb = client.post("/api/cad/primitives/glb", json={"spec": spec}, headers=member.headers)
    assert glb.status_code == 200
    assert glb.content[:4] == b"glTF"
    step = client.post("/api/cad/primitives/step", json={"spec": spec}, headers=member.headers)
    assert step.status_code == 200
    assert step.content.startswith(b"ISO-10303-21")
