"""MCP 로도 같은 일을 — 태그(온톨로지 객체) · 재료가 빈 파트 · 시편 노트 · STEP 올리기 · VOC ·
재료 상태 · 카탈로그 버전 · DOE 공개 범위(2026-10-25, MCP 연결 점검에서 빠진 것들).

진짜 앱에 붙여 권한 · 검증까지 통째로 돈다(`test_mcp_tools` 의 손).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed
from tests.api.test_mcp_tools import Bot, _asgi_transport, bot, server  # noqa: F401

BOX = {
    "params": {"두께": 10.0},
    "nodes": [{"id": "b", "op": "box", "length": 40, "width": 30, "height": "=두께"}],
}


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def test_태그를_타입째_붙이고_떼고_부품에도_붙인다(bot: Bot) -> None:  # noqa: F811
    kinds = bot.call(server.tag_types)
    assert kinds[0]["slug"] == "cc_tag" and kinds[0]["can_create"] is True

    work = bot.call(server.create_work, "센서 판", BOX)["work_id"]
    got = bot.call(server.tag_add, "work", work, label="MCP-EMC")
    assert [one["label"] for one in got] == ["MCP-EMC"], got
    # 같은 말은 새로 만들지 않고 고른다 — 후보에 많이 쓴 것부터 나온다.
    found = bot.call(server.tag_candidates, "cc_tag", "MCP-EMC")
    assert [(one["label"], one["uses"]) for one in found] == [("MCP-EMC", 1)]
    assert bot.call(server.tags_get, "work", work)[0]["object_id"] == found[0]["object_id"]

    # 공용 부품에도 — 등록한 사람이라 붙인다.
    promoted = bot.call(server.promote_part, work)
    assert "error" not in promoted, promoted
    part = promoted["part_id"]
    tagged = bot.call(server.tag_add, "part", part, object_id=found[0]["object_id"])
    assert [one["label"] for one in tagged] == ["MCP-EMC"]
    left = bot.call(server.tag_remove, "part", part, found[0]["object_id"])
    assert left == []
    assert "tag_remove" in server.DESTRUCTIVE_TOOLS

    # 잘못된 kind · 빈 이름은 부르기 전에 막고, 관리 설정은 관리자만.
    assert "error" in bot.call(server.tags_get, "doe", work)
    assert "error" in bot.call(server.tag_add, "work", work)
    assert "error" in bot.call(server.tag_settings)
    # DOE 의 태그 이름(대상 작업의 것)도 고른다.
    assert bot.call(server.list_tags, "doe")["tags"] == []


def test_재료가_빈_파트는_DOE_답에_보인다(bot: Bot) -> None:  # noqa: F811
    work = bot.call(server.create_work, "재료 없는 판", BOX)["work_id"]
    ran = bot.call(
        server.doe_run,
        "재료 없는 판",
        BOX,
        [{"name": "두께", "mode": "list", "values": [8, 12]}],
        "mcp-bare-1",
        work_id=work,
        conditions={"units": {"system": "si"}},
        wait_seconds=60,
    )
    assert "error" not in ran, ran
    assert ran["unmaterialed"] == ["전체"] and "SimEngBay" in ran["unmaterialed_hint"]
    status = bot.call(server.doe_status, ran["study_id"])
    assert status["unmaterialed"] == ["전체"] and status["unmaterialed_hint"]
    points = bot.call(server.doe_points, ran["study_id"])
    assert all("재료가 없는 파트: 전체" in one["warnings"] for one in points["points"])

    # 공개 범위 — 나와 관리자만.
    hidden = bot.call(server.doe_visibility, ran["study_id"], True)
    assert hidden["visibility"] == "private", hidden


def test_시편_미리보기와_만든_뒤의_노트(bot: Bot) -> None:  # noqa: F811
    seen = bot.call(server.preview_specimen, "iso-178")
    assert "error" not in seen, seen
    assert seen["values"] and seen["nodes"] > 0
    assert [one["source"] for one in seen["conditions"]["materials"]] == ["compcore-default"]
    assert any("기본 재료" in one for one in seen["notes"])

    made = bot.call(server.create_specimen_work, "iso-178")
    assert any("기본 재료" in one for one in made["notes"]), made.get("notes")


def _ticket(command: str) -> tuple[str, str]:
    """돌려준 curl 에서 표와 주소(경로 + 쿼리)를 꺼낸다 — 시험은 셸 대신 클라이언트로
    올린다."""
    ticket = re.search(r"X-Upload-Ticket: ([^']+)'", command)
    url = re.search(r"'(http://testserver[^']+)'$", command)
    assert ticket and url, command
    return ticket.group(1), url.group(1).removeprefix("http://testserver")


@pytest.fixture
def public_url() -> Iterator[None]:
    settings = get_settings()
    before = settings.mcp_public_url
    settings.mcp_public_url = "http://testserver/mcp"
    yield
    settings.mcp_public_url = before


def test_STEP_을_표로_올려_작업을_만들고_새_버전을_붙인다(
    bot: Bot,  # noqa: F811
    client: TestClient,
    member: Signed,
    tmp_path: Path,
    public_url: None,
) -> None:
    from app.core import export, primitives

    step = export.write_step(
        primitives.build({"kind": "box", "length": 60, "width": 40, "height": 20}),
        tmp_path / "상자.step",
    )
    body = step.read_bytes()

    prepared = bot.call(server.step_upload_prepare, str(step), name="받은 상자")
    assert "error" not in prepared, prepared
    assert "curl -sS -T" in prepared["curl"] and prepared["expires_in_seconds"] == 300
    ticket, path = _ticket(prepared["curl"])
    made = client.put(path, content=body, headers={"X-Upload-Ticket": ticket})
    assert made.status_code == 201, made.text
    work = made.json()
    assert work["name"] == "받은 상자" and work["current_version"] == 1
    assert work["current"]["recipe"]["nodes"][0]["op"] == "import_step"
    # 한 번 쓴 표는 다시 못 쓴다.
    again = client.put(path, content=body, headers={"X-Upload-Ticket": ticket})
    assert again.status_code == 401

    # 있는 작업의 새 버전 — 주인만.
    second = bot.call(server.step_upload_prepare, str(step), work_id=work["id"])
    ticket, path = _ticket(second["curl"])
    # 문이 다르다 — STEP 표로 첨부를 올리지 못한다.
    wrong = client.put(
        "/api/attachments/upload?filename=x.step",
        content=body,
        headers={"X-Upload-Ticket": ticket},
    )
    assert wrong.status_code == 401
    versioned = client.put(path, content=body, headers={"X-Upload-Ticket": ticket})
    assert versioned.status_code == 201, versioned.text
    assert versioned.json()["current_version"] == 2

    refused = bot.call(server.step_upload_prepare, str(tmp_path / "notes.txt"))
    assert "error" in refused


def test_VOC_를_내고_말을_보태고_고치고_지운다(bot: Bot) -> None:  # noqa: F811
    made = bot.call(
        server.voc_create, "DOE 내보내기가 멈춤", "200점에서 멈춥니다.", page_path="/doe"
    )
    assert "error" not in made, made
    item = made["id"]
    listed = bot.call(server.voc_list, query="내보내기가 멈춤")
    assert [one["id"] for one in listed["items"]] == [item]
    assert bot.call(server.voc_list, status="모름")["error"]

    talked = bot.call(server.voc_event, item, note="재현 조건을 덧붙입니다.")
    assert talked["events"][-1]["note"] == "재현 조건을 덧붙입니다."
    detail = bot.call(server.voc_get, item)
    assert detail["body"] == "200점에서 멈춥니다." and isinstance(detail["allowed"], list)
    assert "error" in bot.call(server.voc_event, item)

    fixed = bot.call(server.voc_update, item, title="DOE 내보내기가 200점에서 멈춤")
    assert fixed["title"] == "DOE 내보내기가 200점에서 멈춤"
    assert set(bot.call(server.voc_summary)) >= {"waiting", "to_confirm"}
    assert "voc_delete" in server.DESTRUCTIVE_TOOLS
    bot.call(server.voc_delete, item)
    assert bot.call(server.voc_list, query="200점에서 멈춤")["items"] == []


def test_재료_상태와_카탈로그_버전(bot: Bot) -> None:  # noqa: F811
    status = bot.call(server.condition_material_status)
    assert isinstance(status, dict) and "error" not in status, status

    work = bot.call(server.create_work, "버전 판", BOX)["work_id"]
    part = bot.call(server.promote_part, work)["part_id"]
    versions = bot.call(server.list_catalog_versions, "parts", part)
    assert [one["number"] for one in versions["versions"]] == [1]
    assert "error" in bot.call(server.list_catalog_versions, "works", part)


def test_태그_객체로_목록을_거른다(bot: Bot) -> None:  # noqa: F811
    """`list_tags(typed=True)` 의 `object_id` 를 목록 도구의 `tag_id` 로 — 이름 거르개와 달리
    그 객체가 붙은 것만."""
    first = bot.call(server.create_work, "거르개 판 하나", BOX)["work_id"]
    second = bot.call(server.create_work, "거르개 판 둘", BOX)["work_id"]
    tagged = bot.call(server.tag_add, "work", first, label="MCP-거르개")
    bot.call(server.tag_add, "work", second, label="MCP-다른것")
    used = bot.call(server.list_tags, "works", typed=True)
    assert "error" not in used, used
    mine = {one["label"]: one for one in used["tags"]}
    assert mine["MCP-거르개"]["object_id"] == tagged[0]["object_id"]
    assert mine["MCP-거르개"]["uses"] == 1 and mine["MCP-거르개"]["type_slug"] == "cc_tag"
    listed = bot.call(server.list_works, tag_id=tagged[0]["object_id"])
    assert [one["work_id"] for one in listed["works"]] == [first], listed
    assert "error" in bot.call(server.list_tags, "voc", typed=True)


def test_템플릿도_태그를_객체로(bot: Bot) -> None:  # noqa: F811
    saved = bot.call(server.save_template, "MCP 판 템플릿", BOX, tags=["MCP-템플릿"])
    assert "error" not in saved, saved
    assert saved["tags"] == ["MCP-템플릿"]
    got = bot.call(server.tag_add, "template", saved["id"], label="MCP-더함")
    assert [one["label"] for one in got] == ["MCP-템플릿", "MCP-더함"]
    used = bot.call(server.list_tags, "templates", typed=True)
    picked = next(one for one in used["tags"] if one["label"] == "MCP-더함")
    listed = bot.call(server.list_templates, tag_id=picked["object_id"])
    assert [one["id"] for one in listed["templates"]] == [saved["id"]], listed
    changed = bot.call(server.update_template, saved["id"], tags=["MCP-더함"])
    assert "error" not in changed, changed
    assert [one["label"] for one in bot.call(server.tags_get, "template", saved["id"])] == [
        "MCP-더함"
    ]


def test_비슷한_태그를_찾아_합친다(
    bot: Bot,  # noqa: F811
    client: TestClient,
    admin: Signed,
) -> None:
    work = bot.call(server.create_work, "합칠 판", BOX)["work_id"]
    bot.call(server.tag_add, "work", work, label="MCP굽힘시험")
    bot.call(server.tag_add, "work", work, label="MCP굽힘 시험")
    # 관리 기능이라 관리자 토큰으로만.
    assert "error" in bot.call(server.tag_similar)
    made = client.post(
        "/api/auth/tokens",
        json={"name": "관리 손", "scopes": ["read", "write"]},
        headers=admin.headers,
    )
    assert made.status_code == 201, made.text
    boss = Bot(made.json()["token"])
    [group] = [
        one
        for one in boss.call(server.tag_similar)["groups"]
        if {m["label"] for m in one["members"]} == {"MCP굽힘시험", "MCP굽힘 시험"}
    ]
    keep = group["keep"]
    rest = [one["object_id"] for one in group["members"] if one["object_id"] != keep]
    assert "error" in boss.call(server.tag_merge, keep, [])
    merged = boss.call(server.tag_merge, keep, rest)
    assert (merged["merged"], merged["dropped"]) == (1, 1), merged
    assert len(bot.call(server.tags_get, "work", work)) == 1
    assert "tag_merge" in server.DESTRUCTIVE_TOOLS
