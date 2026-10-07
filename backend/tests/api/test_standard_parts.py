"""규격 부품 — 관리자가 공용 부품에 규격 사양(종류 · 품번 · 쓰는 버전 · 치수)을 붙이면, 지그
생성기가 요구에 맞는 받침 · 위치 핀 · 토글 클램프를 골라 놓고 부품표에 품번 · 수량을 남긴다.

시험 DB 는 한 번 도는 동안 공유된다 — 여기서 붙인 사양이 뒤의 지그 시험에 섞이지 않게 끝나면
걷어 낸다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.modules.parts.models import Part
from tests.api.conftest import Signed
from tests.api.test_works import _plate, _work
from tests.unit.test_core_standard import CLAMP, PIN, SUPPORT


@pytest.fixture(autouse=True)
def _clean_library(db: Session) -> Iterator[None]:
    yield
    db.execute(update(Part).values(standard=None))
    db.commit()


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201, 202), response.text
    return response.json()


def _catalog(client: TestClient, who: Signed, name: str, recipe: dict[str, Any]) -> str:
    """사내에서 그린 규격품 — 작업으로 그리고 공용 부품으로 올린다."""
    work = _ok(
        client.post("/api/works", json={"name": name, "recipe": recipe}, headers=who.headers)
    )
    return str(
        _ok(
            client.post(f"/api/works/{work['id']}/promote/part", json={}, headers=who.headers)
        )["part_id"]
    )


def _register(client: TestClient, admin: Signed, part: str, spec: dict[str, Any]) -> Any:
    return client.put(f"/api/parts/{part}/standard", json=spec, headers=admin.headers)


def _library(client: TestClient, member: Signed, admin: Signed) -> dict[str, str]:
    made = {}
    for item in (SUPPORT, PIN, CLAMP):
        part = _catalog(client, member, item.name, item.recipe)
        _ok(
            _register(
                client,
                admin,
                part,
                {"kind": item.kind, "part_no": item.part_no, "version": 1, **item.spec},
            )
        )
        made[item.kind] = part
    return made


def test_관리자만_규격_사양을_붙이고_형상이_기준을_지키는지_본다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    part = _catalog(client, member, SUPPORT.name, SUPPORT.recipe)
    spec = {"kind": "support", "part_no": "SUP-16", "version": 1, **SUPPORT.spec}
    refused = _register(client, member, part, spec)
    assert refused.status_code == 403

    saved = _ok(_register(client, admin, part, {**spec, "maker": "사내"}))
    assert saved["standard"]["part_no"] == "SUP-16" and saved["standard"]["kind"] == "support"
    assert "reach" not in saved["standard"]  # 이 종류가 쓰는 칸만 남긴다

    # 종류에 필요한 칸이 비면 · 변수가 레시피에 없으면 · 기준(원점)을 어기면 거절한다.
    missing = _register(client, admin, part, {"kind": "support", "part_no": "X", "version": 1})
    assert missing.status_code == 422
    wrong_param = _register(client, admin, part, {**spec, "height_param": "없는변수"})
    assert wrong_param.status_code == 400
    assert "없는변수" in " ".join(wrong_param.json()["error"]["details"]["problems"])
    off = {**SUPPORT.recipe, "nodes": [{**SUPPORT.recipe["nodes"][0], "at": [30, 0, 5]}]}
    shifted = _catalog(client, member, "어긋난 받침", off)
    bad = _register(client, admin, shifted, {**spec, "part_no": "SUP-BAD"})
    assert bad.status_code == 400
    problems = " ".join(bad.json()["error"]["details"]["problems"])
    assert "z=0" in problems and "원점" in problems

    # 규격 부품만 거른다 — 종류로도.
    listed = _ok(client.get("/api/parts?standard=any", headers=member.headers))
    assert [one["id"] for one in listed["items"]] == [part]
    assert _ok(client.get("/api/parts?standard=clamp", headers=member.headers))["items"] == []
    cleared = _ok(client.delete(f"/api/parts/{part}/standard", headers=admin.headers))
    assert cleared["standard"] is None
    # 뗀 것은 SQL NULL — JSON null 이면 「규격 부품」 필터에 남는다.
    assert _ok(client.get("/api/parts?standard=any", headers=member.headers))["items"] == []


def test_지그_생성기가_규격품을_골라_놓고_부품표를_남긴다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    made = _library(client, member, admin)
    # 구멍을 Ø8.5 로 — 규격 핀 Ø8.4 가 들어간다(템플릿은 Ø8 이라 안 맞는다고 거절한다).
    plate: dict[str, Any] = dict(_plate(client, member))
    for node in plate["nodes"]:
        if node["op"] == "hole":
            node["diameter"] = 8.5
    product = _work(client, member, plate)
    preview = _ok(
        client.post(
            "/api/works/jig-from-part/preview",
            json={"source": f"work:{product['id']}", "options": {"support_count": 4}},
            headers=member.headers,
        )
    )
    bom = {row["part_no"]: row["count"] for row in preview["plan"]["bom"]}
    assert bom.get("SUP-16") == 4 and "PIN-8.4" in bom and "TC-60" in bom
    assert preview["interference"]["ok"] is True
    # 끄면 즉석 도형 — 부품표가 비고 받침은 옵션의 지름이다.
    plain = _ok(
        client.post(
            "/api/works/jig-from-part/preview",
            json={"source": f"work:{product['id']}", "options": {"standard_parts": False}},
            headers=member.headers,
        )
    )
    assert plain["plan"]["bom"] == []

    # 만들고 첫 버전으로 — 레시피가 규격품을 그 버전으로 가리키고, 평가 · 간섭 검사가 돈다.
    run = _ok(
        client.post(
            "/api/works/jig-from-part",
            json={"source": f"work:{product['id']}", "options": {"support_count": 4}},
            headers=member.headers,
        )
    )
    jig, job = run["work"], run["job"]
    assert job["status"] == "done", job["error"]
    assert {row["part_no"] for row in job["summary"]["plan"]["bom"]} == {
        "SUP-16",
        "PIN-8.4",
        "TC-60",
    }
    version = _ok(
        client.post(
            f"/api/works/{jig['id']}/jig-runs/{job['id']}/adopt", headers=member.headers
        )
    )
    support = next(one for one in version["recipe"]["nodes"] if one["id"] == "받침_1")
    assert support["op"] == "component" and support["source"] == f"part:{made['support']}@1"
    assert version["job"]["status"] == "done", version["job"]["error"]
    report = _ok(
        client.post(f"/api/works/{jig['id']}/jig-check", json={}, headers=member.headers)
    )
    assert report["available"] is True and report["ok"] is True, report["items"]


def test_클램프_사양에_고정_나사와_구멍_자리를_적는다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    part = _catalog(client, member, CLAMP.name, CLAMP.recipe)
    spec = {"kind": "clamp", "part_no": "TC-60", "version": 1, **CLAMP.spec}
    holes = [[-15, -10], [-15, 10], [15, -10], [15, 10]]
    saved = _ok(
        _register(client, admin, part, {**spec, "mount_thread": "M5", "mount_holes": holes})
    )
    assert saved["standard"]["mount_thread"] == "M5"
    assert saved["standard"]["mount_holes"] == holes
    # 비우면 칸이 남지 않는다(예전 사양과 같은 모양).
    plain = _ok(_register(client, admin, part, spec))
    assert "mount_thread" not in plain["standard"] and "mount_holes" not in plain["standard"]

    # 나사만 · 자리만 · 표에 없는 나사 · 베이스(40 x 30) 밖 자리는 거절한다.
    for bad in (
        {"mount_thread": "M5"},
        {"mount_holes": holes},
        {"mount_thread": "M7", "mount_holes": holes},
        {"mount_thread": "M5", "mount_holes": [[25, 0]]},
    ):
        refused = _register(client, admin, part, {**spec, **bad})
        assert refused.status_code == 422, bad


def _code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def test_품번은_규격_부품_사이에서_하나다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    spec = {"kind": "support", "part_no": "SUP-16", "version": 1, **SUPPORT.spec}
    first = _catalog(client, member, SUPPORT.name, SUPPORT.recipe)
    second = _catalog(client, member, "받침 Ø16 또 하나", SUPPORT.recipe)
    _ok(_register(client, admin, first, spec))
    _ok(_register(client, admin, first, {**spec, "preference": 50}))  # 제 것은 고친다
    taken = _register(client, admin, second, spec)
    assert taken.status_code == 409 and _code(taken).endswith("PARTS-0011")


def test_규격_부품을_묶음으로_내보내고_품번으로_짝지어_가져온다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    made = _library(client, member, admin)
    plain = _catalog(client, member, "그냥 판", SUPPORT.recipe)

    # 관리자만 — 내보내기도 가져오기도.
    asked = {"ids": [made["support"], made["pin"]]}
    refused = client.post("/api/parts/standard/export", json=asked, headers=member.headers)
    assert refused.status_code == 403
    not_standard = client.post(
        "/api/parts/standard/export", json={"ids": [plain]}, headers=admin.headers
    )
    assert not_standard.status_code == 400 and _code(not_standard).endswith("PARTS-0012")

    bundle = _ok(client.post("/api/parts/standard/export", json=asked, headers=admin.headers))
    assert bundle["format"] == "compcore.standard-parts" and bundle["format_version"] == 1
    support, pin = bundle["items"]
    assert support["standard"]["part_no"] == "SUP-16" and "version" not in support["standard"]
    assert support["recipe"] == SUPPORT.recipe
    assert support["origin"] == {"part_id": made["support"], "version": 1}
    everything = _ok(client.post("/api/parts/standard/export", json={}, headers=admin.headers))
    assert {one["standard"]["part_no"] for one in everything["items"]} == {
        "SUP-16",
        "PIN-8.4",
        "TC-60",
    }

    def run(items: list[dict[str, Any]], dry_run: bool) -> Any:
        return client.post(
            f"/api/parts/standard/import?dry_run={str(dry_run).lower()}",
            json={**bundle, "items": items},
            headers=admin.headers,
        )

    # 같은 서버에 그대로 — 바꿀 것이 없다.
    same = _ok(run(bundle["items"], dry_run=False))
    assert [one["action"] for one in same["items"]] == ["same", "same"]
    assert member.headers and run(bundle["items"], dry_run=True).status_code == 200
    assert (
        client.post(
            "/api/parts/standard/import", json=bundle, headers=member.headers
        ).status_code
        == 403
    )

    # 새 품번 · 형상이 바뀐 핀 · 사양만 바뀐 받침 · 기준을 어긴 것 · 칸이 빈 것 · 묶음 안 중복.
    longer = {**PIN.recipe, "params": {"길이": 40}}
    shifted = {**SUPPORT.recipe, "nodes": [{**SUPPORT.recipe["nodes"][0], "at": [30, 0, 0]}]}
    items = [
        {
            **support,
            "standard": {**support["standard"], "part_no": "SUP-16-B"},
            "folder": "규격",
        },
        {**pin, "recipe": longer, "standard": {**pin["standard"], "length": 40}},
        {**support, "standard": {**support["standard"], "preference": 10}},
        {
            **support,
            "standard": {**support["standard"], "part_no": "SUP-BAD"},
            "recipe": shifted,
        },
        {**support, "standard": {"kind": "support", "part_no": "SUP-EMPTY"}},
        {**support, "standard": {**support["standard"], "part_no": "SUP-16-B"}},
    ]
    preview = _ok(run(items, dry_run=True))
    assert [one["action"] for one in preview["items"]] == [
        "create",
        "version",
        "spec",
        "skip",
        "skip",
        "skip",
    ]
    assert preview["items"][1]["version"] == 2 and preview["items"][0]["part_id"] is None
    assert "원점" in " ".join(preview["items"][3]["problems"])
    assert "top_diameter" in " ".join(preview["items"][4]["problems"])
    assert "같은 품번" in " ".join(preview["items"][5]["problems"])
    # 미리 보기는 아무것도 바꾸지 않는다.
    listed = _ok(client.get("/api/parts?standard=any", headers=member.headers))
    assert listed["total"] == 3

    done = _ok(run(items, dry_run=False))
    assert done["dry_run"] is False
    created = _ok(
        client.get(f"/api/parts/{done['items'][0]['part_id']}", headers=member.headers)
    )
    assert created["standard"]["part_no"] == "SUP-16-B" and created["standard"]["version"] == 1
    assert created["folder"] == "규격" and created["work_id"] is None
    assert created["current"]["job"]["status"] == "done"  # 평가해 3D 를 만든다
    assert "가져옴" in created["current"]["note"]
    moved_pin = _ok(client.get(f"/api/parts/{made['pin']}", headers=member.headers))
    assert moved_pin["current_version"] == 2 and moved_pin["standard"]["version"] == 2
    assert moved_pin["current"]["recipe"] == longer
    tuned = _ok(client.get(f"/api/parts/{made['support']}", headers=member.headers))
    assert tuned["standard"]["preference"] == 10 and tuned["current_version"] == 1

    # 다시 가져오면 바뀌는 것이 없다.
    again = _ok(run(items[:3], dry_run=False))
    assert [one["action"] for one in again["items"]] == ["same", "same", "same"]

    # 이 서버가 모르는 판은 읽지 않는다.
    newer = client.post(
        "/api/parts/standard/import",
        json={**bundle, "format_version": 2},
        headers=admin.headers,
    )
    assert newer.status_code == 400 and _code(newer).endswith("PARTS-0013")
