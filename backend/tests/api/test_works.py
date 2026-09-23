"""내 작업 — 그리기 · 버전 · STEP 가져오기 · 지그 생성 · 승격 · 내 공간 경계."""

from __future__ import annotations

from pathlib import Path

import pytest
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
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "CCR-WORKS-0005"


def test_부품에서_지그를_생성하면_지그_작업이_되고_거기서_승격한다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    """생성기는 지그의 시작점이다 — 부품 화면이 아니라 「새 작업 > 부품에서 지그 생성」."""
    work = _work(client, member, _plate(client, member))
    run = client.post(
        "/api/works/jig-from-part",
        json={"source": f"work:{work['id']}", "options": {"support_count": 3}},
        headers=member.headers,
    )
    assert run.status_code == 202, run.text
    made, job = run.json()["work"], run.json()["job"]
    # 지그 작업이 바로 생기고, 생성 작업은 그 지그 작업에 매달린다(부품 작업이 아니라).
    assert made["kind"] == "jig" and made["name"] == "시험 작업 지그"
    assert made["jig_options"]["support_count"] == 3 and made["current_version"] == 0
    assert job["kind"] == "jig" and job["status"] == "done", job["error"]
    assert job["work_id"] == made["id"]
    assert {one["kind"] for one in job["summary"]["plan"]["locators"]} == {"pin"}
    assert len(job["summary"]["plan"]["supports"]) == 3
    assert (
        client.get(f"/api/works/{work['id']}", headers=member.headers).json()["jig_run_count"]
        == 0
    )

    # 결과를 첫 버전으로 — 두 번 불러도 같은 버전.
    adopted = client.post(
        f"/api/works/{made['id']}/jig-runs/{job['id']}/adopt", headers=member.headers
    )
    assert adopted.status_code == 201, adopted.text
    version = adopted.json()
    assert version["number"] == 1 and version["source"] == "generated"
    # 결과는 STEP 덩어리가 아니라 **변수 있는 레시피** — 판 두께 · 받침 높이를 조립 → DOE 로
    # 훑는다.
    assert version["recipe"]["nodes"][0] == {
        "id": "바닥판",
        "op": "box",
        "length": "=판_길이",
        "width": "=판_너비",
        "height": "=판_두께",
        "at": [0, 0, 0],
        "align": ["center", "center", "max"],
    }
    assert {"판_두께", "받침_높이", "받침_지름"} <= set(version["recipe"]["params"])
    assert version["recipe"]["result"] == "지그"
    assert any(n["op"] == "pin" for n in version["recipe"]["nodes"])  # 구멍판이라 위치 핀
    assert version["job"]["status"] == "done"  # 그대로 평가된다 — 이어서 그릴 수 있다
    assert version["job"]["summary"]["bbox"]["size"][2] > 25  # 판 + 받침 + 클램프
    assert "받침 3" in version["note"]
    again = client.post(
        f"/api/works/{made['id']}/jig-runs/{job['id']}/adopt", headers=member.headers
    ).json()
    assert again["id"] == version["id"]
    seen = client.get(f"/api/works/{made['id']}", headers=member.headers).json()
    assert seen["current_version"] == 1 and seen["jig_run_count"] == 1
    # 부품이 아직 카탈로그에 없으니 잡는 부품은 비어 있다.
    assert seen["jig_for_part_id"] is None

    # 부품을 승격하고, 그 공용 부품에서 생성하면 잡는 부품이 이어진다.
    part = client.post(
        f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers
    ).json()
    from_catalog = client.post(
        "/api/works/jig-from-part",
        json={"source": f"part:{part['part_id']}", "name": "카탈로그 지그"},
        headers=member.headers,
    )
    assert from_catalog.status_code == 202, from_catalog.text
    assert from_catalog.json()["work"]["jig_for_part_id"] == part["part_id"]
    assert from_catalog.json()["job"]["status"] == "done"

    # 지그 작업의 승격은 도면 길(promote/jig-recipe) 하나다 — 카탈로그에서 누구나 본다.
    promoted = client.post(
        f"/api/works/{made['id']}/promote/jig-recipe",
        json={"note": "첫 지그", "part_id": part["part_id"]},
        headers=member.headers,
    )
    assert promoted.status_code == 201, promoted.text
    body = promoted.json()
    assert body["jig_version"] == 1 and body["part_id"] == part["part_id"]
    jig = client.get(f"/api/jigs/{body['jig_id']}", headers=admin.headers)
    assert jig.status_code == 200 and jig.json()["part_name"] == "시험 작업"
    got_part = client.get(f"/api/parts/{part['part_id']}", headers=admin.headers)
    assert got_part.status_code == 200 and got_part.json()["jig_count"] == 1

    # 같은 형상 버전은 두 번 못 올린다.
    same = client.post(
        f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers
    )
    assert same.status_code == 400 and same.json()["error"]["code"] == "CCR-WORKS-0010"

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
        == part["part_id"]
    )

    # 남의 부품을 고치는 길은 「내 공간으로 복사」 뿐.
    copied = client.post(
        f"/api/parts/{part['part_id']}/copy-to-work", json={"number": 1}, headers=admin.headers
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
        got = client.post(
            "/api/works/jig-from-part", json={"source": f"work:{work.id}"}, headers=headers
        )
        assert got.status_code == 400 and got.json()["error"]["code"] == "CCR-WORKS-0008"
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


def test_지그_생성_미리보기는_부품에_따라_달라진다(client: TestClient, member: Signed) -> None:
    """만들기 전에 계획과 메시를 본다 — 파일은 안 쓴다. 받침 · 핀은 부품 바닥 · 구멍에서
    나온다."""
    work = _work(client, member, _plate(client, member))
    got = client.post(
        "/api/works/jig-from-part/preview",
        json={"source": f"work:{work['id']}", "options": {"support_count": 3}},
        headers=member.headers,
    )
    assert got.status_code == 200, got.text
    body = got.json()
    assert len(body["plan"]["supports"]) == 3
    assert {one["kind"] for one in body["plan"]["locators"]} == {"pin"}  # 구멍판이라 핀
    assert body["interference"]["ok"] is True
    labels = {face["part"] for face in body["mesh"]["faces"]}
    assert "제품" in labels and "바닥판" in labels
    assert {one for one in labels if one.startswith("받침 ")} == {"받침 1", "받침 2", "받침 3"}
    assert any(one.startswith("위치 핀") for one in labels)
    assert any(one.startswith("클램프") for one in labels)

    # 옵션을 바꾸면 계획이 따라 바뀐다 — 미리보기가 규칙을 보여 주는 이유.
    four = client.post(
        "/api/works/jig-from-part/preview",
        json={"source": f"work:{work['id']}", "options": {"support_count": 4}},
        headers=member.headers,
    ).json()
    assert len(four["plan"]["supports"]) == 4
    # 작업은 안 생겼다.
    mine = client.get("/api/works", headers=member.headers).json()
    assert all(one["kind"] != "jig" for one in mine["items"])


def test_부품과_지그를_맞는_자리에_놓은_조립을_만든다(
    client: TestClient, member: Signed
) -> None:
    """생성기 좌표계(XY 중심 원점 · 판 윗면 z=0 · 부품은 받침 높이만큼)를 서버가 맞춘다."""
    part = _work(client, member, _plate(client, member))  # 0~100 x 0~60 x 0~12 (원점에서 그림)
    run = client.post(
        "/api/works/jig-from-part",
        json={"source": f"work:{part['id']}", "options": {"support_height": 25}},
        headers=member.headers,
    ).json()
    jig_work, job = run["work"], run["job"]
    client.post(
        f"/api/works/{jig_work['id']}/jig-runs/{job['id']}/adopt", headers=member.headers
    )

    made = client.post(
        "/api/works/assemble",
        json={"part_source": f"work:{part['id']}", "jig_work_id": jig_work["id"]},
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["work"]["kind"] == "assembly"
    assert body["placement"]["mode"] == "generated"
    part_min = client.post(
        "/api/cad/recipe/info", json={"recipe": _plate(client, member)}, headers=member.headers
    ).json()["summary"]["bbox"]["min"]
    size = client.post(
        "/api/cad/recipe/info", json={"recipe": _plate(client, member)}, headers=member.headers
    ).json()["summary"]["bbox"]["size"]
    expected = [-(part_min[0] + size[0] / 2), -(part_min[1] + size[1] / 2), -part_min[2] + 25]
    assert body["placement"]["translate"] == pytest.approx(expected, abs=0.01)
    recipe = body["work"]["current"]["recipe"]
    assert recipe["params"] == {"부품_높이": pytest.approx(expected[2], abs=0.01)}
    assert recipe["nodes"][0]["translate"][2] == "=부품_높이"  # 높이는 변수 — DOE 로 훑는다
    assert recipe["nodes"][1]["source"] == f"work:{jig_work['id']}"
    # 조립이 평가된다 — 두 구성품이 한 좌표계에.
    assert body["work"]["current"]["job"]["status"] == "done", body["work"]["current"]["job"]

    # 손으로 그린 지그(생성 기록 없음)는 윗면에 얹어 어림한다고 말한다.
    drawn = client.post(
        "/api/works",
        json={"name": "그린 지그", "kind": "jig", "recipe": BOX},
        headers=member.headers,
    ).json()
    guessed = client.post(
        "/api/works/assemble",
        json={"part_source": f"work:{part['id']}", "jig_work_id": drawn["id"]},
        headers=member.headers,
    ).json()
    assert guessed["placement"]["mode"] == "guessed"


def test_부분_수정으로_새_버전을_만들고_틀리면_고친_레시피와_함께_거절한다(
    client: TestClient, member: Signed
) -> None:
    work = _work(client, member)  # BOX
    got = client.post(
        f"/api/works/{work['id']}/patch",
        json={
            "ops": [
                {"op": "set_param", "name": "높이", "value": 30},
                {"op": "set_field", "id": "b", "field": "distance", "value": "=높이"},
            ],
            "note": "높이를 변수로",
        },
        headers=member.headers,
    )
    assert got.status_code == 202, got.text
    assert got.json()["number"] == 2 and got.json()["source"] == "ai"
    assert got.json()["recipe"]["params"] == {"높이": 30}
    assert got.json()["job"]["summary"]["bbox"]["size"][2] == 30

    bad = client.post(
        f"/api/works/{work['id']}/patch",
        json={
            "ops": [{"op": "set_field", "id": "b", "field": "height", "value": "=없는변수"}]
        },
        headers=member.headers,
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "CCR-WORKS-0030"
    assert bad.json()["error"]["details"]["problems"]
    # 버전은 안 늘었다.
    assert (
        client.get(f"/api/works/{work['id']}", headers=member.headers).json()[
            "current_version"
        ]
        == 2
    )


def test_면_기준_놓기가_translate_를_계산해_준다(client: TestClient, member: Signed) -> None:
    part = _work(client, member, _plate(client, member))
    recipe = {
        "nodes": [
            {
                "id": "판",
                "op": "box",
                "length": 120,
                "width": 80,
                "height": 15,
                "at": [0, 0, -7.5],
            },
            {
                "id": "부품",
                "op": "component",
                "source": f"work:{part['id']}",
                "translate": [5, 5, 5],
            },
            {"id": "조립", "op": "group", "targets": ["판", "부품"]},
        ]
    }
    got = client.post(
        "/api/cad/recipe/place",
        json={"recipe": recipe, "mover": "부품", "onto": "판", "face": "top", "offset": 2},
        headers=member.headers,
    )
    assert got.status_code == 200, got.text
    # 판 윗면 z=0 · 부품(XY 중심 원점, 바닥 z=0) → 바닥이 z=2 에 오게 tz = 2, XY 는 판 중심.
    # [5, 5, 5] 로 옮겨 둔 것은 상자에 이미 들어 있어 그만큼 빠진다.
    assert got.json()["translate"] == [0, 0, 2]
    assert got.json()["problems"] == []
    moved = next(n for n in got.json()["recipe"]["nodes"] if n["id"] == "부품")
    assert moved["translate"] == [0, 0, 2]


def test_찾기_꼬리표_복제_휴지통(client: TestClient, member: Signed) -> None:
    """작업이 수십 개를 넘으면 필요한 것들 — 이름으로 찾고, 꼬리표로 거르고, 복제하고,
    되살린다."""
    a = _work(client, member)
    b = client.post(
        "/api/works",
        json={"name": "모터 브래킷", "description": "진동 시험용", "recipe": BOX},
        headers=member.headers,
    ).json()
    # 꼬리표 — 전체를 바꾼다. 빈 것 · 중복은 걸러진다.
    tagged = client.patch(
        f"/api/works/{b['id']}",
        json={"tags": ["진동", " 진동 ", "", "P1"]},
        headers=member.headers,
    )
    assert tagged.status_code == 200 and tagged.json()["tags"] == ["진동", "P1"]
    assert client.get("/api/works/tags", headers=member.headers).json() == ["P1", "진동"]

    # 찾기 — 이름 · 설명. 꼬리표 · 종류로 거르기.
    found = client.get("/api/works", params={"q": "진동"}, headers=member.headers).json()
    assert [one["id"] for one in found["items"]] == [b["id"]]
    found = client.get("/api/works", params={"tag": "P1"}, headers=member.headers).json()
    assert [one["id"] for one in found["items"]] == [b["id"]]
    found = client.get("/api/works", params={"kind": "part"}, headers=member.headers).json()
    assert {one["id"] for one in found["items"]} >= {a["id"], b["id"]}

    # 복제 — 종류 · 꼬리표가 따라오고 버전은 1 부터.
    copy = client.post(f"/api/works/{b['id']}/duplicate", headers=member.headers)
    assert copy.status_code == 201, copy.text
    assert copy.json()["name"] == "모터 브래킷 사본" and copy.json()["tags"] == ["진동", "P1"]
    assert copy.json()["current_version"] == 1 and copy.json()["current"]["source"] == "copy"

    # 지우면 목록에서 빠지고 휴지통에 있다 — 되살리면 돌아온다.
    assert client.delete(f"/api/works/{b['id']}", headers=member.headers).status_code == 204
    assert b["id"] not in {
        one["id"] for one in client.get("/api/works", headers=member.headers).json()["items"]
    }
    trash = client.get("/api/works", params={"trashed": "true"}, headers=member.headers).json()
    assert [one["id"] for one in trash["items"]] == [b["id"]]
    assert trash["items"][0]["deleted_at"]
    back = client.post(f"/api/works/{b['id']}/restore", headers=member.headers)
    assert back.status_code == 200 and back.json()["deleted_at"] is None
    assert (
        client.post(f"/api/works/{b['id']}/restore", headers=member.headers).status_code == 400
    )


def test_해석_조건은_버전에_붙고_새_버전을_만들지_않는다(
    client: TestClient, member: Signed
) -> None:
    """조건은 **형상의 성질**이다 — 도면이 안 바뀌었는데 버전이 늘면 「무엇이 달라졌나」 를
    되짚을 수 없다."""
    work = _work(client, member)
    before = client.get(f"/api/works/{work['id']}/versions", headers=member.headers).json()

    conditions = {
        "named_selections": [
            {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
        ],
        "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
        "analysis": {"type": "modal", "modes": 6},
    }
    put = client.put(
        f"/api/works/{work['id']}/versions/1/conditions",
        json={"conditions": conditions},
        headers=member.headers,
    )
    assert put.status_code == 200, put.text
    assert put.json()["conditions"]["constraints"][0]["on"] == "바닥"

    after = client.get(f"/api/works/{work['id']}/versions", headers=member.headers).json()
    assert len(after) == len(before), "버전이 늘면 안 된다"
    again = client.get(f"/api/works/{work['id']}/versions/1", headers=member.headers).json()
    assert again["conditions"]["analysis"]["modes"] == 6

    # 없는 이름표를 가리키면 **지금** 막는다 — 내보낸 뒤 해석 쪽에서 0 개를 집으면 늦다.
    bad = client.put(
        f"/api/works/{work['id']}/versions/1/conditions",
        json={
            "conditions": {
                **conditions,
                "loads": [{"name": "누름", "type": "pressure", "on": "옆면", "magnitude": 1}],
            }
        },
        headers=member.headers,
    )
    assert bad.status_code == 400 and "이름표가 없습니다" in bad.json()["error"]["message"]

    # 조건의 칸 사양표 — 화면과 AI 가 같은 것을 본다.
    spec = client.get("/api/cad/conditions/schema", headers=member.headers).json()
    assert "bolt_pretension" in spec["groups"]["loads"]["types"]
