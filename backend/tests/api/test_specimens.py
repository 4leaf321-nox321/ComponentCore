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
    assert len(builtin) == 18  # 숏빔 전단(D2344 · ISO 14130) 포함
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


def test_제품에_정하중을_걸면_물성은_남고_시험_조건이_붙은_새_작업이_생긴다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    from tests.api.test_fixture_export import _material
    from tests.api.test_works import _plate

    product = _work(client, member, _plate(client, member))
    material = _material("M-000158", ["전체"])
    _ok(
        client.put(
            f"/api/works/{product['id']}/versions/1/conditions",
            json={"conditions": {"materials": [material]}},
            headers=member.headers,
        )
    )
    made = _ok(
        client.post(
            "/api/specimens/product-tests",
            json={"preset_id": "iec-62368-1-t5", "source": f"work:{product['id']}", "x": 15},
            headers=member.headers,
        )
    )
    assert "IEC 62368-1 T.5" in made["name"] and set(made["tags"]) == {
        "정하중 시험",
        "IEC 62368-1",
    }
    first = _ok(client.get(f"/api/works/{made['id']}/versions/1", headers=member.headers))
    assert first["job"]["status"] == "done", first["job"]
    rules = first["conditions"]
    assert [one["ref"]["code"] for one in rules["materials"]] == ["M-000158"]
    assert rules["loads"][0]["magnitude"] == "=시험_하중"
    params = first["recipe"]["params"]
    assert (params["시험_X"], params["시험_Y"]) == (15, 0)  # 준 칸은 그대로, 빈 칸은 가운데
    # 누르는 힘을 DOE 로 훑으면 설계점마다 풀린 값이 조건 파일로 나간다.
    study = _ok(
        client.post(
            "/api/doe",
            json={
                "name": "정하중 훑기",
                "recipe": first["recipe"],
                "conditions": rules,
                "factors": [{"name": "시험_하중", "mode": "list", "values": [100, 250]}],
            },
            headers=member.headers,
        )
    )
    _ok(client.post(f"/api/doe/{study['id']}/export", headers=member.headers))
    folder = next(export_root.iterdir())
    forces = sorted(
        json.loads((folder / "points" / f"p{n:04d}.json").read_text("utf-8"))["conditions"][
            "loads"
        ][0]["magnitude"]
        for n in (1, 2)
    )
    assert forces == [100, 250]


def test_제품_시험의_거절_사유(client: TestClient, member: Signed) -> None:
    box = _work(client, member)  # 기본 상자
    bend = client.post(
        "/api/specimens/product-tests",
        json={"preset_id": "astm-d790-16", "source": f"work:{box['id']}"},
        headers=member.headers,
    )
    assert bend.status_code == 400 and _code(bend).endswith("SPECIMENS-0005")
    # 아랫면이 평면이 아닌 제품(구) — 받침을 찾지 못한다고 말한다.
    ball = _work(
        client,
        member,
        {"version": 1, "nodes": [{"id": "구", "op": "sphere", "radius": 20}]},
    )
    refused = client.post(
        "/api/specimens/product-tests",
        json={"preset_id": "iec-60068-2-6-150-1g", "source": f"work:{ball['id']}"},
        headers=member.headers,
    )
    assert refused.status_code == 400 and "시험 받침면" in refused.json()["error"]["message"]


def test_정하중_진동도_사내_규격으로_복사해_쓴다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    """굽힘만 시편을 그려 보고, 제품 시험은 기준 상자에 걸어 본다 — 그 전에는 「시편을 만들 수
    없습니다」 로 사내 규격 저장이 막혔다(2026-10-05)."""
    from tests.api.test_works import _plate

    def copied(preset_id: str, **changes: Any) -> dict[str, Any]:
        base = dict(
            _ok(client.get(f"/api/specimens/presets/{preset_id}", headers=member.headers))[
                "preset"
            ]
        )
        base.pop("id")
        return {**base, "name": f"{base['name']} (사내)", **changes}

    force = copied("iec-62368-1-t5", setup={"force": 300, "probe_diameter": 20})
    made = _ok(
        client.post("/api/specimens/presets", json={"preset": force}, headers=admin.headers)
    )
    assert made["origin"] == "internal" and made["preset"]["setup"]["force"] == 300
    sine = copied("iec-60068-2-6-150-1g")
    _ok(client.post("/api/specimens/presets", json={"preset": sine}, headers=admin.headers))
    reversed_range = copied(
        "iec-60068-2-6-150-1g",
        setup={"freq_min": 200, "freq_max": 100, "acceleration_g": 1},
    )
    bad = client.post(
        "/api/specimens/presets", json={"preset": reversed_range}, headers=admin.headers
    )
    assert bad.status_code == 400 and "freq_min" in " ".join(
        bad.json()["error"]["details"]["problems"]
    )

    # 사내 규격으로 제품에 건다.
    product = _work(client, member, _plate(client, member))
    work = _ok(
        client.post(
            "/api/specimens/product-tests",
            json={"preset_id": made["id"], "source": f"work:{product['id']}"},
            headers=member.headers,
        )
    )
    first = _ok(client.get(f"/api/works/{work['id']}/versions/1", headers=member.headers))
    assert first["recipe"]["params"]["시험_하중"] == 300


def test_인장_전단_이음_시편은_치수를_바꿔_만든다(client: TestClient, member: Signed) -> None:
    preview = _ok(
        client.post(
            "/api/specimens/build",
            json={"preset_id": "astm-d638-type-i", "dimensions": {"gauge_width": 10}},
            headers=member.headers,
        )
    )
    assert preview["values"]["평행부_폭"] == 10 and preview["values"]["늘림"] > 0
    assert [one["name"] for one in preview["conditions"]["named_selections"]] == [
        "고정 그립",
        "당김 그립",
        "표점 구간",
    ]
    wide = client.post(
        "/api/specimens/build",
        json={"preset_id": "astm-d638-type-i", "dimensions": {"gauge_width": 30}},
        headers=member.headers,
    )
    assert wide.status_code == 400 and _code(wide).endswith("SPECIMENS-0004")
    assert "평행부 폭" in wide.json()["error"]["message"]
    work = _ok(
        client.post(
            "/api/specimens/works",
            json={"preset_id": "iso-4587", "name": "겹치기 이음"},
            headers=member.headers,
        )
    )
    assert set(work["tags"]) == {"접착 이음 시험", "ISO 4587"}
    first = _ok(client.get(f"/api/works/{work['id']}/versions/1", headers=member.headers))
    assert first["job"]["status"] == "done", first["job"]
    assert {one["type"] for one in first["conditions"]["contacts"]} == {"bonded"}


def test_제품에_3D_에서_고른_면으로_시험을_건다(client: TestClient, member: Signed) -> None:
    from tests.api.test_works import _plate

    product = _work(client, member, _plate(client, member))
    source = f"work:{product['id']}"
    seen = _ok(
        client.post(
            "/api/specimens/product-mesh", json={"source": source}, headers=member.headers
        )
    )
    top = next(one for one in seen["mesh"]["faces"] if one["normal"] == [0, 0, 1])
    pick = {"point": top["center"], "normal": top["normal"], "kind": top["kind"]}
    handle = _ok(
        client.post(
            "/api/specimens/product-tests",
            json={
                "preset_id": "iec-62368-1-8.8-handle",
                "source": source,
                "faces": {"support": [pick]},
            },
            headers=member.headers,
        )
    )
    rules = _ok(client.get(f"/api/works/{handle['id']}/versions/1", headers=member.headers))[
        "conditions"
    ]
    assert rules["loads"][0]["type"] == "acceleration"
    assert rules["named_selections"][-1]["select"]["normal"] == [0, 0, 1]
    unpicked = client.post(
        "/api/specimens/product-tests",
        json={"preset_id": "iec-62368-1-8.8-handle", "source": source},
        headers=member.headers,
    )
    assert unpicked.status_code == 400 and "3D에서" in unpicked.json()["error"]["message"]
    weightless = client.post(
        "/api/specimens/product-tests",
        json={"preset_id": "ista-stack-5x3", "source": source},
        headers=member.headers,
    )
    assert weightless.status_code == 400 and "무게" in weightless.json()["error"]["message"]
    stacked = _ok(
        client.post(
            "/api/specimens/product-tests",
            json={"preset_id": "ista-stack-5x3", "source": source, "mass": 1.5},
            headers=member.headers,
        )
    )
    params = _ok(client.get(f"/api/works/{stacked['id']}/versions/1", headers=member.headers))[
        "recipe"
    ]["params"]
    assert params["시험_무게"] == 1.5 and params["시험_단수"] == 5
    _ok(
        client.post(
            "/api/specimens/product-tests",
            json={"preset_id": "twist-example-6deg", "source": source},
            headers=member.headers,
        )
    )


def test_끝이_둥근_제품은_비트는_끝을_고르라고_말한다(
    client: TestClient, member: Signed
) -> None:
    """양 끝이 반원인 판 위에 상자 하나 — 「-X 를 보는 가장 가까운 평면」 은 상자의 옆면이라
    끝이 아니다."""
    rounded = _work(
        client,
        member,
        {
            "version": 1,
            "nodes": [
                {
                    "id": "윤곽",
                    "op": "sketch",
                    "shapes": [{"type": "slot", "length": 100, "width": 30}],
                },
                {"id": "판", "op": "extrude", "sketch": "윤곽", "distance": 5},
                {
                    "id": "턱",
                    "op": "box",
                    "length": 20,
                    "width": 10,
                    "height": 5,
                    "at": [0, 0, 5],
                    "align": ["center", "center", "min"],
                },
                {"id": "제품", "op": "union", "targets": ["판", "턱"]},
            ],
        },
    )
    refused = client.post(
        "/api/specimens/product-tests",
        json={"preset_id": "twist-example-6deg", "source": f"work:{rounded['id']}"},
        headers=member.headers,
    )
    assert (
        refused.status_code == 400
        and "끝에 평면이 없습니다" in refused.json()["error"]["message"]
    )


def test_새_시험도_사내_규격으로_복사해_쓴다(client: TestClient, admin: Signed) -> None:
    def copied(preset_id: str, **changes: Any) -> dict[str, Any]:
        base = dict(
            _ok(client.get(f"/api/specimens/presets/{preset_id}", headers=admin.headers))[
                "preset"
            ]
        )
        base.pop("id")
        return {**base, "name": f"{base['name']} (사내)", **changes}

    for preset_id in (
        "astm-d638-type-iv",
        "astm-d5766",
        "astm-d6484",
        "astm-e9-short",
        "astm-d5379",
        "astm-d1002",
        "astm-d5961-a",
        "astm-d7332-example",
        "iec-62368-1-8.7-mount",
        "iec-60335-1-cord-4kg",
        "un-38.3-t6-crush",
        "astm-d642-2700x3",
        "iec-60529-ipx8-1.5m",
        "twist-example-10deg",
        "iso-16750-3-shock-500",
        "astm-e1876-free",
    ):
        made = _ok(
            client.post(
                "/api/specimens/presets",
                json={"preset": copied(preset_id)},
                headers=admin.headers,
            )
        )
        assert made["origin"] == "internal"
    narrow = copied(
        "astm-d638-type-iv",
        specimen={**copied("astm-d638-type-iv")["specimen"], "radius": 1},
    )
    bad = client.post("/api/specimens/presets", json={"preset": narrow}, headers=admin.headers)
    assert bad.status_code == 400 and "반지름" in " ".join(
        bad.json()["error"]["details"]["problems"]
    )


def test_방향_하중과_압착은_고른_면과_방향으로_건다(
    client: TestClient, member: Signed
) -> None:
    from tests.api.test_works import _plate

    product = _work(client, member, _plate(client, member))
    source = f"work:{product['id']}"
    seen = _ok(
        client.post(
            "/api/specimens/product-mesh", json={"source": source}, headers=member.headers
        )
    )
    side = next(one for one in seen["mesh"]["faces"] if one["normal"] == [1, 0, 0])
    pick = {"point": side["center"], "normal": side["normal"], "kind": side["kind"]}
    pulled = _ok(
        client.post(
            "/api/specimens/product-tests",
            json={
                "preset_id": "iec-60335-1-cord-1kg",
                "source": source,
                "faces": {"load": [pick]},
                "direction": [0, 0, 1],
            },
            headers=member.headers,
        )
    )
    rules = _ok(client.get(f"/api/works/{pulled['id']}/versions/1", headers=member.headers))[
        "conditions"
    ]
    assert [(one["type"], one["direction"]) for one in rules["loads"]] == [
        ("force", [0.0, 0.0, 1.0]),
        ("moment", [0.0, 0.0, 1.0]),
    ]
    crushed = _ok(
        client.post(
            "/api/specimens/product-tests",
            json={
                "preset_id": "iec-62133-2-crush",
                "source": source,
                "faces": {"load": [pick]},
            },
            headers=member.headers,
        )
    )
    first = _ok(client.get(f"/api/works/{crushed['id']}/versions/1", headers=member.headers))
    assert first["job"]["status"] == "done", first["job"]
    support = next(
        one for one in first["conditions"]["named_selections"] if one["name"] == "시험 받침면"
    )
    assert support["select"]["normal"] == [-1.0, 0.0, 0.0]
    missing = client.post(
        "/api/specimens/product-tests",
        json={"preset_id": "usb-type-c-wrench-side", "source": source},
        headers=member.headers,
    )
    assert missing.status_code == 400 and "3D에서" in missing.json()["error"]["message"]
