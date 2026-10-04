"""시험 규격 — 공개 규격(코드)과 사내 규격(DB)을 한 목록으로 보이고, 프리셋으로 시편 · 시험
지그 · 해석 조건이 붙은 내 작업을 만든다. 굽힘 지그 생성은 고른 규격의 규칙을 따른다.

시험 DB 는 한 번 도는 동안 공유된다 — 여기서 더한 사내 규격은 끝나면 지운다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.specimens.models import SpecimenPreset
from tests.api.conftest import Signed
from tests.api.test_works import _work


@pytest.fixture(autouse=True)
def _clean_presets(db: Session) -> Iterator[None]:
    yield
    db.execute(update(SpecimenPreset).values(deleted_at=datetime.now(UTC)))
    db.commit()


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201, 202, 204), response.text
    return response.json() if response.status_code != 204 else None


def _code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def _d790(client: TestClient, who: Signed) -> dict[str, Any]:
    return dict(_ok(client.get("/api/specimens/presets/astm-d790-16", headers=who.headers)))


def test_공개_규격은_누구나_보고_검토_전임을_말한다(
    client: TestClient, member: Signed
) -> None:
    listed = _ok(client.get("/api/specimens/presets?test=bending", headers=member.headers))
    builtin = [one for one in listed if one["origin"] == "builtin"]
    assert len(builtin) == 13
    assert {one["standard"] for one in builtin} >= {"ASTM D790", "ISO 178", "ASTM D6272"}
    assert all(
        one["preset"]["verified"] is False and one["preset"]["source"] for one in builtin
    )
    d790 = _d790(client, member)
    assert d790["preset"]["setup"]["span"] == {"to_thickness": 16.0, "value": None}
    missing = client.get("/api/specimens/presets/없는-규격", headers=member.headers)
    assert missing.status_code == 404 and _code(missing).endswith("SPECIMENS-0001")


def test_사내_규격은_관리자만_더하고_고치며_값을_검사한다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    base = _d790(client, member)["preset"]
    mine = {**base, "standard": "사내 굽힘 A", "name": "사내 굽힘 A (두께 2)"}
    mine["specimen"] = {**base["specimen"], "thickness": 2.0}
    asked = {"preset": mine}
    refused = client.post("/api/specimens/presets", json=asked, headers=member.headers)
    assert refused.status_code == 403

    made = _ok(client.post("/api/specimens/presets", json=asked, headers=admin.headers))
    assert made["origin"] == "internal" and made["preset"]["id"] == made["id"]
    assert made["updated_by_name"]
    listed = _ok(client.get("/api/specimens/presets", headers=member.headers))
    assert [one["id"] for one in listed if one["origin"] == "internal"] == [made["id"]]

    # 틀린 값은 어느 칸이 왜인지 — 4점인데 하중 간격이 없다.
    broken = {**mine, "setup": {**mine["setup"], "points": 4}}
    bad = client.post("/api/specimens/presets", json={"preset": broken}, headers=admin.headers)
    assert bad.status_code == 400 and _code(bad).endswith("SPECIMENS-0002")
    assert "load_span" in " ".join(bad.json()["error"]["details"]["problems"])

    # 공개 규격은 고칠 수 없다 — 복사해 사내 규격으로.
    builtin = client.put(
        "/api/specimens/presets/astm-d790-16", json=asked, headers=admin.headers
    )
    assert builtin.status_code == 400 and _code(builtin).endswith("SPECIMENS-0003")

    changed = {**mine, "verified": True, "source": "사내 시험법 TM-12 3.2절"}
    fixed = _ok(
        client.put(
            f"/api/specimens/presets/{made['id']}",
            json={"preset": changed},
            headers=admin.headers,
        )
    )
    assert fixed["preset"]["verified"] is True and fixed["preset"]["source"].startswith("사내")
    _ok(client.delete(f"/api/specimens/presets/{made['id']}", headers=admin.headers))
    gone = client.get(f"/api/specimens/presets/{made['id']}", headers=member.headers)
    assert gone.status_code == 404


def test_규격으로_시편_작업을_만들면_지그와_해석_조건이_붙는다(
    client: TestClient, member: Signed
) -> None:
    preview = _ok(
        client.post(
            "/api/specimens/build",
            json={"preset_id": "astm-d6272-16", "thickness": 4},
            headers=member.headers,
        )
    )
    assert preview["recipe"]["params"]["두께"] == 4
    assert preview["conditions"]["analysis"]["type"] == "static"
    assert any("검토" in one or "대조" in one for one in preview["notes"])

    work = _ok(
        client.post(
            "/api/specimens/works",
            json={"preset_id": "astm-d790-16", "folder": "시험"},
            headers=member.headers,
        )
    )
    assert work["name"] == "ASTM D790 3점 굽힘 (16:1)" and work["folder"] == "시험"
    assert set(work["tags"]) == {"굽힘 시험", "ASTM D790"}
    versions = _ok(client.get(f"/api/works/{work['id']}/versions", headers=member.headers))
    first = versions[-1] if versions[-1]["number"] == 1 else versions[0]
    full = _ok(
        client.get(
            f"/api/works/{work['id']}/versions/{first['number']}", headers=member.headers
        )
    )
    assert full["job"]["status"] == "done", full["job"]
    assert {one["name"] for one in full["conditions"]["named_selections"]} >= {
        "지지 롤러",
        "로딩 노즈",
    }

    # 지그 없이 시편만 — 조건도 비운다.
    alone = _ok(
        client.post(
            "/api/specimens/works",
            json={"preset_id": "iso-178", "fixture": False, "name": "시편만"},
            headers=member.headers,
        )
    )
    assert alone["name"] == "시편만"


def test_굽힘_지그_생성은_고른_규격의_규칙을_따른다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    bar = {
        "version": 1,
        "nodes": [
            {
                "id": "bar",
                "op": "box",
                "length": 127,
                "width": 12.7,
                "height": 3.2,
                "align": ["center", "center", "min"],
            }
        ],
    }
    product = _work(client, member, bar)

    def preview(options: dict[str, Any]) -> Any:
        return client.post(
            "/api/works/jig-from-part/preview",
            json={
                "source": f"work:{product['id']}",
                "options": {"kind": "bending", **options},
            },
            headers=member.headers,
        )

    d790 = _ok(preview({"bending_preset": "astm-d790-16"}))
    rollers = d790["plan"]["rollers"]
    assert sorted(one["position"][0] for one in rollers) == [-25.6, 25.6]  # 16 x 3.2 / 2
    four = _ok(preview({"bending_preset": "astm-d6272-16"}))
    assert [one["label"] for one in four["plan"]["noses"]] == ["로딩_노즈_1", "로딩_노즈_2"]
    assert four["interference"]["ok"] is True

    # 사내 규격도 같은 길 — 서버가 규칙을 값으로 넘긴다.
    base = _d790(client, member)["preset"]
    mine = {**base, "standard": "사내", "name": "사내 32:1", "setup": {**base["setup"]}}
    mine["setup"]["span"] = {"to_thickness": 32}
    made = _ok(
        client.post("/api/specimens/presets", json={"preset": mine}, headers=admin.headers)
    )
    inner = _ok(preview({"bending_preset": made["id"]}))
    assert sorted(one["position"][0] for one in inner["plan"]["rollers"]) == [-51.2, 51.2]

    missing = preview({"bending_preset": "없는-규격"})
    assert missing.status_code == 404


@pytest.fixture
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def test_규격_시편으로_DOE_를_돌리면_조건의_변수가_설계점마다_풀린다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """형상에 안 쓰이는 변수(`마찰계수`)도 DOE 의 인자이고, 다른 변수의 식(`처짐` ← `변형률` ·
    `지지_간격` · `두께`)은 따라간다 — 설계점마다 풀린 값이 조건 파일로 나간다(2026-10-04
    사용자 질문)."""
    work = _ok(
        client.post(
            "/api/specimens/works", json={"preset_id": "astm-d790-16"}, headers=member.headers
        )
    )
    first = _ok(client.get(f"/api/works/{work['id']}/versions/1", headers=member.headers))
    made = _ok(
        client.post(
            "/api/doe",
            json={
                "name": "굽힘 두께 · 마찰",
                "recipe": first["recipe"],
                "conditions": first["conditions"],
                "factors": [
                    {"name": "두께", "mode": "list", "values": [3.2, 4.0]},
                    {"name": "마찰계수", "mode": "list", "values": [0.1, 0.3]},
                ],
            },
            headers=member.headers,
        )
    )
    assert made["point_count"] == 4
    _ok(client.post(f"/api/doe/{made['id']}/export", headers=member.headers))
    folder = next(export_root.iterdir())
    seen = set()
    for number in (1, 2, 3, 4):
        point = json.loads((folder / "points" / f"p{number:04d}.json").read_text("utf-8"))
        thickness = point["point"]["params"]["두께"]
        friction = point["point"]["params"]["마찰계수"]
        rules = point["conditions"]
        press = next(one for one in rules["constraints"] if one["name"] == "노즈 가압")
        span = 16 * thickness  # 지지_간격 = 간격비 * 두께 — 식 변수도 따라온다
        assert press["z"] == pytest.approx(-0.05 * span**2 / (6 * thickness), rel=1e-6)
        frictions = [one["friction"] for one in rules["contacts"]]
        assert frictions == pytest.approx([friction, friction])
        for name in ("지지 롤러", "로딩 노즈", "시편 중앙", "시편 아랫면"):
            assert point["regions"][name], f"{name}: 설계점 {number}에서 면을 못 찾았다"
        seen.add((thickness, friction))
    assert seen == {(3.2, 0.1), (3.2, 0.3), (4.0, 0.1), (4.0, 0.3)}
