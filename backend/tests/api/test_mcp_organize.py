"""MCP 로 **정리하기** — 폴더 · 꼬리표 · 이름 · 휴지통 · 템플릿 · 카탈로그, 그리고 점을 더한
DOE.

사람이 목록 화면에서 하는 일을 AI 도 해야 한다(「이 작업들 고객A 폴더로 옮겨 줘」). 진짜 앱에
붙여 권한 · 검증까지 통째로 돈다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed

# 도구를 진짜 앱에 붙이는 손(`_asgi_transport`)과 기계 자격(`bot`)은 그쪽 것을 쓴다 — 픽스처는
# 이름으로 찾으므로 들여오기만 하면 된다(아래 시험의 인자 `bot` 이 그것이다).
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


def _paths(listing: dict[str, Any]) -> dict[str, int]:
    return {one["path"]: one["count"] for one in listing["folders"]}


def test_내_작업을_폴더로_정리하고_휴지통에서_되살린다(bot: Bot) -> None:  # noqa: F811
    first = bot.call(server.create_work, "브래킷", BOX)
    second = bot.call(server.create_work, "받침", BOX)
    a, b = first["work_id"], second["work_id"]

    # 이름 · 꼬리표 · 폴더 · 종류를 한 번에 — 도면은 그대로다.
    got = bot.call(server.update_work, a, tags=["고객A"], folder="고객A/2026", kind="jig")
    assert got == {
        "work_id": a,
        "name": "브래킷",
        "kind": "jig",
        "folder": "고객A/2026",
        "tags": ["고객A"],
    }
    assert "바꿀 칸이 없습니다" in bot.call(server.update_work, a)["error"]
    assert bot.call(server.list_tags)["tags"] == ["고객A"]

    moved = bot.call(server.move_to_folder, "works", [b], "고객A")
    assert moved == {"moved": 1}
    tree = bot.call(server.list_folders)
    assert _paths(tree)["고객A"] == 1 and _paths(tree)["고객A/2026"] == 1
    assert tree["years"] and tree["years"][0]["count"] >= 2
    listed = bot.call(server.list_works, folder="고객A", tag="고객A")
    assert [w["work_id"] for w in listed["works"]] == [a]
    assert listed["works"][0]["kind"] == "jig" and listed["works"][0]["tags"] == ["고객A"]

    # 폴더 지우기 = 위로 합치기 — 작업은 남는다.
    assert bot.call(server.rename_folder, "works", "고객A/2026", "고객A") == {"moved": 1}
    assert "고객A/2026" not in _paths(bot.call(server.list_folders))

    copy = bot.call(server.duplicate_work, a, "브래킷 변형")
    assert copy["name"] == "브래킷 변형" and copy["folder"] == "고객A"
    assert copy["with_conditions"] is False

    # 해석 조건까지 — 같은 조건으로 변형을 훑을 때.
    conditions = {
        "named_selections": [
            {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
        ],
        "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
    }
    assert "error" not in bot.call(server.set_conditions, a, conditions)
    with_conditions = bot.call(server.duplicate_work, a, "조건 & 함께", with_conditions=True)
    assert with_conditions["name"] == "조건 & 함께"  # 이름의 & · 공백이 주소를 깨지 않는다
    copied = bot.call(server.get_version, with_conditions["work_id"], 1)
    assert copied["conditions"]["constraints"] == conditions["constraints"]
    plain = bot.call(server.duplicate_work, a, "도면만")
    assert not (bot.call(server.get_version, plain["work_id"], 1).get("conditions") or {})

    assert bot.call(server.delete_work, copy["work_id"]) == {"ok": True, "message": "완료"}
    trashed = bot.call(server.list_works, trashed=True)
    assert [w["work_id"] for w in trashed["works"]] == [copy["work_id"]]
    assert bot.call(server.restore_work, copy["work_id"])["restored"] is True
    assert bot.call(server.get_work, copy["work_id"])["folder"] == "고객A"

    assert "space 는" in bot.call(server.list_folders, "drawings")["error"]


def test_템플릿과_카탈로그도_폴더로_정리한다(bot: Bot) -> None:  # noqa: F811
    saved = bot.call(server.save_template, "판", BOX, folder="판금")
    tid = saved["id"]
    listed = bot.call(server.list_templates, folder="판금")
    assert [t["id"] for t in listed["templates"]] == [tid]
    assert listed["templates"][0]["mine"] is True and listed["templates"][0]["shared"] is False

    shared = bot.call(server.update_template, tid, shared=True, folder="판금/브래킷")
    assert shared == {"id": tid, "name": "판", "shared": True, "folder": "판금/브래킷"}
    assert "판금/브래킷" in _paths(bot.call(server.list_folders, "templates", "shared"))
    copied = bot.call(server.copy_template, tid)
    assert copied["folder"] == "판금/브래킷" and copied["id"] != tid

    work = bot.call(server.create_work, "블록", BOX, folder="고객B")
    part = bot.call(server.promote_part, work["work_id"])
    part_id = part["part_id"]
    # 처음 승격하면 작업의 폴더를 물려받는다.
    assert bot.call(server.list_parts, folder="고객B")["parts"][0]["id"] == part_id
    renamed = bot.call(
        server.update_catalog_item, "parts", part_id, name="블록 v1", folder="공용/블록"
    )
    assert renamed == {"id": part_id, "name": "블록 v1", "folder": "공용/블록"}
    assert bot.call(server.list_parts, query="블록 v1")["total"] == 1
    assert bot.call(server.move_to_folder, "parts", [part_id], "보관") == {"moved": 1}
    assert _paths(bot.call(server.list_folders, "parts"))["보관"] >= 1
    assert (
        "템플릿은 update_template"
        in bot.call(server.update_catalog_item, "templates", tid, name="x")["error"]
    )


def test_점을_더한_DOE_는_다시_보내야_한다고_말한다(bot: Bot) -> None:  # noqa: F811
    made = bot.call(
        server.doe_create,
        "두께",
        BOX,
        [{"name": "두께", "mode": "list", "values": [8, 10]}],
        conditions={},
    )
    study_id = made["id"]
    assert bot.call(server.doe_export, study_id)["folder"]
    assert bot.call(server.doe_status, study_id)["export_stale"] is False

    more = bot.call(
        server.doe_extend,
        study_id,
        method="factorial",
        factors=[{"name": "두께", "mode": "list", "values": [12]}],
    )
    assert more["batch"]["added"] == 1 and more["points_total"] == 3
    status = bot.call(server.doe_status, study_id)
    assert status["export_stale"] is True and status["batches"] == 1
    points = bot.call(server.doe_points, study_id)
    assert points["export_stale"] is True
    assert points["batches"] == [
        {"number": 2, "method": "factorial", "seed": 2, "from": 3, "to": 3, "added": 1}
    ]
    bot.call(server.doe_export, study_id)
    assert bot.call(server.doe_status, study_id)["export_stale"] is False


def test_DOE_계획_도구가_제약_미리보기_표_측정값을_나른다(bot: Bot) -> None:  # noqa: F811
    factors = [{"name": "두께", "mode": "range", "start": 0, "end": 20, "steps": 5}]
    preview = bot.call(server.doe_preview, factors, constraints=["두께 >= 5"], recipe=BOX)
    assert preview["count"] == 4 and preview["rejected"] == 1 and preview["hits"] == [1]
    assert "rejected_points" not in preview  # AI 에게는 무겁다 — 수만 준다

    probe = bot.call(server.doe_probe, BOX, factors, conditions={})
    by_label = {one["label"]: one for one in probe["points"]}
    assert (
        by_label["중심"]["status"] == "ok"
        and by_label["전체 최소, ‘두께’ 최소"]["status"] == "failed"
    )

    made = bot.call(
        server.doe_create,
        "표",
        BOX,
        [],
        method="table",
        table=[{"두께": 6.5}, {"두께": 9}],
        measures=[
            {"name": "부피", "kind": "volume"},
            {"name": "질량", "kind": "expr", "expr": "부피 * 0.001"},
        ],
        conditions={},
    )
    assert made.get("point_count") == 2, made
    points = bot.call(server.doe_points, made["id"])["points"]
    assert [p["params"]["두께"] for p in points] == [6.5, 9.0]
    assert points[0]["measures"] == {"부피": pytest.approx(7800), "질량": pytest.approx(7.8)}
    assert points[0]["warnings"] == []


def test_멈추기와_워커_상태(bot: Bot) -> None:  # noqa: F811
    settings = get_settings()
    settings.jobs_inline = False
    try:
        made = bot.call(
            server.doe_create,
            "멈출 것",
            BOX,
            [{"name": "두께", "mode": "list", "values": [8, 10]}],
            conditions={},
        )
        stopped = bot.call(server.doe_cancel, made["id"])
        assert stopped["job"]["status"] == "cancelled" and stopped["done"] == 0
        again = bot.call(server.cancel_job, made["job"]["id"])
        assert "이미 종료된 작업" in again["error"]
    finally:
        settings.jobs_inline = True
    # 워커 상태는 관리자만 — 사람에게 무엇이 막혔는지 그대로 전한다.
    assert "error" in bot.call(server.worker_status)


def test_판금_전개도_요약(bot: Bot) -> None:  # noqa: F811
    sheet = {
        "nodes": [
            {
                "id": "m",
                "op": "sheet_metal",
                "thickness": 2,
                "width": 40,
                "path": [[0, 30], [0, 0], [40, 0]],
                "bend_radius": 4,
            }
        ]
    }
    got = bot.call(server.recipe_unfold, sheet)
    assert got["thickness"] == 2 and len(got["bends"]) == 1
    assert got["bends"][0]["radius"] == 4 and got["bends"][0]["angle"] == 90


def test_도면_요약과_그림(bot: Bot) -> None:  # noqa: F811
    plate = {
        "nodes": [
            {"id": "p", "op": "box", "length": 80, "width": 50, "height": 10},
            {"id": "h", "op": "hole", "target": "p", "diameter": 8, "at": [[20, 15]]},
        ]
    }
    got = bot.call(server.recipe_drawing, plate, title="받침판", material="SS400")
    summary, picture = got
    assert summary["sheet"] == "A3" and len(summary["holes"]) == 1
    assert summary["holes"][0]["spec"].startswith("Ø8")
    assert picture.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_형상으로_찾기(bot: Bot) -> None:  # noqa: F811
    plate = {
        "nodes": [
            {"id": "p", "op": "box", "length": 90, "width": 40, "height": 5},
            {
                "id": "h",
                "op": "hole",
                "target": "p",
                "thread": "M6",
                "at": [[-30, 0], [30, 0]],
            },
        ]
    }
    bot.call(server.create_work, "M6 판", plate)
    got = bot.call(server.find_by_shape, where="works", thread="M6", fits="100x50")
    rows = got["works"]["items"]
    assert [one["name"] for one in rows] == ["M6 판"]
    assert rows[0]["source"].startswith("work:") and rows[0]["shape"]["threads"] == ["M6"]
    assert (
        bot.call(server.find_by_shape, where="works", has=["sheet_metal"])["works"]["total"]
        == 0
    )
    assert "error" in bot.call(server.find_by_shape, where="모두")


def test_중간면_요약(bot: Bot) -> None:  # noqa: F811
    sheet = {
        "nodes": [
            {
                "id": "m",
                "op": "sheet_metal",
                "thickness": 2,
                "width": 40,
                "path": [[0, 30], [0, 0], [40, 0]],
                "bend_radius": 4,
            }
        ]
    }
    got = bot.call(server.recipe_midsurface, sheet)
    assert got["bodies"][0]["thickness"] == 2 and got["bodies"][0]["faces"] == 3
    cube = {"nodes": [{"id": "c", "op": "box", "length": 10, "width": 10, "height": 10}]}
    assert "판이 아닙니다" in bot.call(server.recipe_midsurface, cube)["error"]


def test_구속_윤곽_풀어_보기(bot: Bot) -> None:  # noqa: F811
    shape = {
        "type": "constrained",
        "points": {"a": [0, 0], "b": [9, 1], "c": [0, 8]},
        "segments": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
            {"from": "c", "to": "a"},
        ],
        "constraints": [
            {"type": "fix", "points": ["a"]},
            {"type": "horizontal", "segments": [0]},
            {"type": "vertical", "segments": [2]},
            {"type": "length", "segments": [0], "value": "=밑변"},
            {"type": "length", "segments": [2], "value": 5},
        ],
    }
    got = bot.call(server.sketch_solve, shape, {"밑변": 12})
    assert got["points"]["b"] == [12, 0] and got["points"]["c"] == [0, 5] and got["free"] == 0


def test_닮은_형상(bot: Bot) -> None:  # noqa: F811
    def plate(length: float) -> dict[str, Any]:
        return {
            "nodes": [{"id": "p", "op": "box", "length": length, "width": 50, "height": 8}]
        }

    base = bot.call(server.create_work, "닮음 기준판", plate(90))
    bot.call(server.create_work, "닮음 비교판", plate(95))
    got = bot.call(server.find_similar, source=f"work:{base['work_id']}", where=["works"])
    names = [one["name"] for one in got["items"]]
    assert "닮음 비교판" in names and "닮음 기준판" not in names
    first = next(one for one in got["items"] if one["name"] == "닮음 비교판")
    assert first["score"] > 0.9 and "크기 유사" in first["why"]
    assert "error" in bot.call(server.find_similar)


def test_관리자만_남의_작업을_둘러본다(
    bot: Bot,  # noqa: F811
    client: TestClient,
    admin: Signed,
) -> None:
    made = bot.call(server.create_work, "둘러볼 작업", BOX)
    # 일반 사용자의 자격 — 거절된다(조용히 내 것만 주지 않는다).
    assert "error" in bot.call(server.list_works, owner="all")

    token = client.post(
        "/api/auth/tokens",
        json={"name": "관리자 Claude", "scopes": ["read"]},
        headers=admin.headers,
    ).json()["token"]
    boss = Bot(str(token))
    mine = bot.call(server.list_works)["works"]
    owner = next(one for one in mine if one["work_id"] == made["work_id"])
    assert "owner" not in owner  # 내 것만 볼 때는 붙이지 않는다
    seen = boss.call(server.list_works, owner="all", query="둘러볼")["works"]
    row = next(one for one in seen if one["work_id"] == made["work_id"])
    assert row["owner"] == "member"
