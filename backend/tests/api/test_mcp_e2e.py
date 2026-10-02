"""**MCP 만으로 끝에서 끝까지** — 도면 → 선택 그룹 · 조건 · 물성 → DOE(치수 · 재료 ·
조건 종류 · 물성 배율) → 공유 폴더. AI 가 밟는 순서 그대로, 도구만 부른다(화면 없이).

MatNexus 는 시험에서 닿지 않으므로 실제 줄 스냅샷(`tests/fixtures/matnexus`)으로 바꿔 끼운다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.config import get_settings
from tests.api.test_mcp_tools import (  # noqa: F401 — 픽스처를 이 모듈에서 쓴다
    Bot,
    _asgi_transport,
    bot,
    server,
)

MATNEXUS = Path(__file__).parents[1] / "fixtures" / "matnexus"
ROWS = {
    code: json.loads((MATNEXUS / f"{code}.json").read_text(encoding="utf-8"))
    for code in ("M-000138", "M-000158")
}


@pytest.fixture(autouse=True)
def matnexus_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.shared.clients import matnexus

    keys = json.loads((MATNEXUS / "property_keys.json").read_text(encoding="utf-8"))
    payloads = [row["payload"] for row in ROWS.values()]
    monkeypatch.setattr(matnexus, "configured", lambda: True)
    monkeypatch.setattr(
        matnexus,
        "search",
        lambda query="", family="", category="", limit=30: [
            one
            for one in payloads
            if not query or query.lower() in str(one.get("record_name", "")).lower()
        ],
    )
    monkeypatch.setattr(
        matnexus,
        "get",
        lambda code_or_id: next(
            (one for one in payloads if code_or_id in (one.get("code"), one.get("id"))), None
        ),
    )
    monkeypatch.setattr(matnexus, "property_keys", lambda: keys)
    monkeypatch.setattr(matnexus, "deck_formats", lambda material_id: [])


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


RECIPE: dict[str, Any] = {
    "params": {"두께": 5.0, "압력": 1.5, "모드수": 10},
    "nodes": [
        {
            "id": "받침판",
            "op": "box",
            "length": 100,
            "width": 60,
            "height": "=두께",
            "align": ["center", "center", "min"],
        },
        {
            "id": "블록",
            "op": "box",
            "length": 40,
            "width": 40,
            "height": 20,
            "at": [0, 0, "=두께"],
            "align": ["center", "center", "min"],
        },
        {"id": "조립", "op": "group", "targets": ["받침판", "블록"]},
    ],
}


def test_MCP_만으로_도면_조건_물성_DOE_까지(bot: Bot, export_root: Path) -> None:  # noqa: F811
    # 1) 도면 — 저장하고 바디를 안다.
    made = bot.call(server.create_work, "MCP 조립", RECIPE, note="바디 둘")
    assert "error" not in made, made
    work_id = made["work_id"]
    bodies = bot.call(server.recipe_bodies, RECIPE)
    assert [one["name"] for one in bodies["items"]] == ["받침판", "블록"]

    # 2) 사양표를 읽는다 — 받는 대상 · 단위.
    spec = bot.call(server.conditions_schema)
    assert spec["input_system"] == "mm_n_tonne"
    assert spec["groups"]["contacts"]["accepts"]["bonded"] == [{"entity": "face"}]

    # 3) 면을 찾는다 — 좌표를 짐작하지 않고 질의로. 바디 이름이 틀리면 있는 이름을 알려 준다.
    top = bot.call(
        server.recipe_find, RECIPE, {"what": "faces", "body": "받침판", "normal": "z"}
    )
    assert top["total"] == 1 and top["items"][0]["area"] == 6000
    typo = bot.call(server.recipe_find, RECIPE, {"what": "faces", "body": "받침"})
    assert typo["total"] == 0 and typo["bodies"] == ["받침판", "블록"]

    # 4) 물성 — 찾고, 받고, 조건에 넣을 항목을 그대로 쓴다.
    found = bot.call(server.material_search, "AL5052")
    assert [one["code"] for one in found["items"]] == ["M-000158"]
    assert "payload" not in found["items"][0]  # 목록은 가볍게
    aluminum = bot.call(server.material_get, "M-000158")
    steel = bot.call(server.material_get, "M-000138")
    assert aluminum["condition_item"]["payload"]["code"] == "M-000158"

    conditions: dict[str, Any] = {
        # 조립은 **바디와 방향으로** 고른다 — 좌표가 없어 두께를 훑어도 헛집지 않는다.
        "named_selections": [
            {"name": name, "entity": "face", "select": {"what": "faces", **rule}}
            for name, rule in (
                ("바닥", {"body": "받침판", "normal": [0, 0, -1]}),
                ("블록 윗면", {"body": "블록", "normal": [0, 0, 1]}),
                ("판 윗면", {"body": "받침판", "normal": [0, 0, 1]}),
                ("블록 아랫면", {"body": "블록", "normal": [0, 0, -1]}),
            )
        ],
        "materials": [
            {**steel["condition_item"], "apply_to": ["받침판"]},
            {**aluminum["condition_item"], "apply_to": ["블록"]},
        ],
        "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
        "loads": [
            {"name": "누름", "type": "pressure", "on": "블록 윗면", "magnitude": "=압력"}
        ],
        "contacts": [
            {
                "name": "블록-판",
                "type": "bonded",
                "source": "블록 아랫면",
                "target": "판 윗면",
                "friction": 0.2,
            }
        ],
        "analysis": {"type": "modal", "modes": "=모드수"},
    }
    saved = bot.call(server.set_conditions, work_id, conditions)
    assert "error" not in saved, saved
    # 받는 대상 규칙 — 틀리면 고칠 곳을 말한다.
    wrong = {**conditions, "contacts": [{**conditions["contacts"][0], "source": "없는그룹"}]}
    assert "error" in bot.call(server.set_conditions, work_id, wrong)

    # 5) 저장된 조건을 읽을 수 있다.
    work = bot.call(server.get_work, work_id)
    assert work["current"]["conditions"]["contacts"][0]["name"] == "블록-판"

    # 6) DOE — 조건을 따로 안 주면 작업의 조건이 실린다.
    #    치수 · 재료 · 접촉 종류 · 탄성계수 배율을 한꺼번에.
    factors = [
        {"name": "두께", "mode": "list", "values": [5, 8]},
        {
            "name": "블록 재료",
            "mode": "material",
            "bodies": ["블록"],
            "values": ["M-000158", "M-000138"],
        },
        {
            "name": "접촉 종류",
            "mode": "choice",
            "target": {"group": "contacts", "item": "블록-판", "field": "type"},
            "values": ["bonded", "frictional"],
        },
        {
            "name": "받침판 E 배율",
            "mode": "scale",
            "bodies": ["받침판"],
            "property": "탄성계수",
            "values": [0.9, 1.1],
        },
    ]
    preview = bot.call(server.doe_preview, factors)
    assert preview["count"] == 16, preview
    ran = bot.call(
        server.doe_run,
        "MCP 조건 훑기",
        RECIPE,
        factors,
        "mcp-e2e-1",
        work_id=work_id,
        wait_seconds=60,
    )
    assert "error" not in ran, ran
    assert ran["done"] == 16 and ran["failed"] == 0, ran
    assert ran["folder"], ran

    folder = next(export_root.iterdir())
    points = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((folder / "points").glob("p*.json"))
    ]
    assert len(points) == 16
    shapes = {one["point"]["step_file"] for one in points}
    assert len(shapes) == 2  # 두께 둘만 형상이 다르다
    for point in points:
        params = point["point"]["params"]
        resolved = point["conditions"]
        assert resolved["contacts"][0]["type"] == params["접촉 종류"]
        assert resolved["loads"][0]["magnitude"] == pytest.approx(1.5)
        assert resolved["analysis"]["modes"] == 10
        on_block = [m for m in resolved["materials"] if "블록" in m["apply_to"]]
        assert [m["ref"]["code"] for m in on_block] == [params["블록 재료"]]
        plate = next(m for m in resolved["materials"] if "받침판" in m["apply_to"])
        assert plate["converted"]["scaled"] == {"탄성계수": params["받침판 E 배율"]}
        assert point["unresolved"] == []
        # 그룹마다 그 면 하나 — 판 윗면에 블록 윗면이 섞이지 않는다.
        assert {name: len(faces) for name, faces in point["regions"].items()} == {
            "바닥": 1,
            "블록 윗면": 1,
            "판 윗면": 1,
            "블록 아랫면": 1,
        }

    # 7) 같은 열쇠로 다시 부르면 같은 한 벌(재시도).
    again = bot.call(
        server.doe_run, "MCP 조건 훑기", RECIPE, factors, "mcp-e2e-1", work_id=work_id
    )
    assert again.get("study_id") == ran.get("study_id"), (again, ran)
