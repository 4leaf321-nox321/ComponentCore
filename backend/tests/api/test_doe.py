"""실험계획 — 조합을 만들고, 형상마다 STEP 을 공유 폴더에 쓴다."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed

#: 연결부(구멍 자리)는 숫자로 못 박고 튜닝부만 치수 이름으로 — DOE 의 전제다.
JIG: dict[str, Any] = {
    "params": {"두께": 6.0, "길이": 90.0},
    "nodes": [
        {
            "id": "연결판",
            "op": "box",
            "length": 60,
            "width": 60,
            "height": 12,
            "align": ["min", "center", "min"],
        },
        {
            "id": "볼트",
            "op": "hole",
            "target": "연결판",
            "at": [[10, -22], [50, 22]],
            "thread": "M6",
        },
        {
            "id": "튜닝보",
            "op": "box",
            "length": "=길이",
            "width": 40,
            "height": "=두께",
            "at": [60, 0, 0],
            "align": ["min", "center", "min"],
        },
        {"id": "지그", "op": "union", "targets": ["볼트", "튜닝보"]},
    ],
}


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    """공유 폴더는 시험에서 임시 폴더로 바꾼다 — 진짜 F: 드라이브에 쓰지 않는다."""
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def test_만들기_전에_몇_개인지_알려준다(client: TestClient, member: Signed) -> None:
    got = client.post(
        "/api/doe/preview",
        json={
            "factors": [
                {"name": "두께", "mode": "range", "start": 4, "end": 12, "steps": 5},
                {"name": "길이", "mode": "list", "values": [80, 100]},
            ]
        },
        headers=member.headers,
    )
    assert got.status_code == 200, got.text
    assert got.json()["count"] == 10 and got.json()["too_many"] is False
    assert got.json()["varying"] == ["두께", "길이"]

    too_many = client.post(
        "/api/doe/preview",
        json={
            "factors": [
                {"name": f"x{i}", "mode": "range", "start": 1, "end": 5, "steps": 5}
                for i in range(4)
            ]
        },
        headers=member.headers,
    )
    assert too_many.json()["count"] == 625 and too_many.json()["too_many"] is True


def test_설계점마다_STEP_을_공유_폴더에_쓴다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    made = client.post(
        "/api/doe",
        json={
            "name": "브래킷 튜닝",
            "description": "세트 공진에 맞추려고 두께를 훑는다",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [4, 8, 12]}],
        },
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    study = made.json()
    assert study["point_count"] == 3
    # 만들기는 서버 보관 폴더에 — 공유 폴더는 「보내기」 를 눌러야 채워진다.
    assert study["export_dir_windows"] == "" and study["exported_at"] is None

    got = client.get(f"/api/doe/{study['id']}", headers=member.headers).json()
    assert got["done"] == 3 and got["failed"] == 0
    # 표에는 바꾼 변수와 파일만 — 질량 · 크기도 해석 결과도 여기 담지 않는다.
    assert all("metrics" not in point for point in got["points"])
    assert not export_root.exists() or not any(export_root.iterdir())

    sent = client.post(f"/api/doe/{study['id']}/export", headers=member.headers)
    assert sent.status_code == 200, sent.text
    assert sent.json()["export_dir_windows"] and sent.json()["exported_at"]

    # 공유 폴더 — 해석이 읽는 것.
    folder = next(export_root.iterdir())
    assert (folder / "README.txt").exists()
    assert (folder / "study.json").exists()
    steps = sorted((folder / "points").glob("*.step"))
    assert [one.name for one in steps] == ["p0001.step", "p0002.step", "p0003.step"]
    assert steps[0].read_bytes().startswith(b"ISO-10303-21")

    rows = list(
        csv.DictReader((folder / "manifest.csv").read_text(encoding="utf-8-sig").splitlines())
    )
    assert [row["point"] for row in rows] == ["1", "2", "3"]
    assert [row["두께"] for row in rows] == ["4.0", "8.0", "12.0"]
    assert rows[0]["step_file"] == "points/p0001.step"
    assert list(rows[0].keys()) == [
        "point",
        "status",
        "두께",
        "step_file",
        "point_file",
        "unresolved",
        "interference",
        "error",
    ]

    # **영역 지문이 STEP 옆에 나란히 있다.** STEP 은 이름표를 못 나르므로 해석이 「어느 면이
    # 고정면인가」 를 물을 곳은 이 파일뿐이다.
    assert rows[0]["point_file"] == "points/p0001.json"
    assert rows[0]["unresolved"] == "", "영역을 못 풀면 그 이름이 여기 적힌다"
    # **폴더가 자기를 설명한다** — 해석하는 사람이 「이거 누구한테 물어보지」 로 막히지 않게.
    spec = json.loads((folder / "study.json").read_text(encoding="utf-8"))
    assert spec["owner"]["email"] == member.email
    assert spec["factors"] and spec["seed"] is not None, "무엇을 훑었나도 함께"

    topo = json.loads((folder / "points" / "p0001.json").read_text(encoding="utf-8"))
    assert topo["units"] == "mm"
    assert topo["regions"]["fixed_base"], "바닥 고정 모달의 자리"
    assert topo["bodies"][0]["volume"] > 0
    # 설계점마다 좌표가 다르다 — 그래서 점마다 한 장이다.
    other = json.loads((folder / "points" / "p0003.json").read_text(encoding="utf-8"))
    assert other["bodies"][0]["volume"] != topo["bodies"][0]["volume"]

    # 내려받는 표도 같은 값이다.
    csv_out = client.get(f"/api/doe/{study['id']}/manifest.csv", headers=member.headers)
    assert csv_out.status_code == 200 and "두께" in csv_out.text

    # **결과를 받는 길은 없다.** 설계점을 고르는 일은 해석 플랫폼이 한다 — 걸러 보기 ·
    # 파레토를 여기 두면 영원히 빈 답을 내는 코드가 된다(2026-09-23 결정).
    # 없는 API 는 404 가 아니라 405 로 온다 — 화면(SPA)을 서빙하는 GET 전용 잡이 경로를
    # 받아 내기 때문이다. 둘 다 「그런 API 가 없다」 는 뜻이라 함께 받는다.
    for gone in ("filter", "tradeoff"):
        answer = client.post(f"/api/doe/{study['id']}/{gone}", json=[], headers=member.headers)
        assert answer.status_code in (404, 405), gone


def test_깨지는_점이_있어도_나머지는_만든다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """얇은 두께에서 형상이 깨지는 일은 흔하다 — 거기서 멈추면 표가 끊긴다."""
    made = client.post(
        "/api/doe",
        json={
            "name": "끊기면 안 된다",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [-5, 6, 10]}],
        },
        headers=member.headers,
    ).json()
    got = client.get(f"/api/doe/{made['id']}", headers=member.headers).json()
    assert got["failed"] == 1 and got["done"] == 2
    broken = next(one for one in got["points"] if one["status"] == "failed")
    assert broken["error"]  # 왜 빠졌는지 적혀 있다
    client.post(f"/api/doe/{made['id']}/export", headers=member.headers)
    rows = list(
        csv.DictReader(
            (next(export_root.iterdir()) / "manifest.csv")
            .read_text(encoding="utf-8-sig")
            .splitlines()
        )
    )
    assert [row["status"] for row in rows] == ["failed", "ok", "ok"]


def test_레시피에_없는_치수는_미리_막는다(client: TestClient, member: Signed) -> None:
    got = client.post(
        "/api/doe",
        json={
            "name": "오타",
            "recipe": JIG,
            "factors": [{"name": "두깨", "mode": "list", "values": [4, 8]}],
        },
        headers=member.headers,
    )
    assert got.status_code == 400
    assert "레시피에 없는 치수" in got.json()["error"]["message"]


def test_설계점_상한은_관리자가_화면에서_바꾼다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    """.env 는 관리자가 손댈 수 없다 — 서버 설정 화면의 값이 .env 기본값을 덮는다."""
    factors = [{"name": "두께", "mode": "range", "start": 4, "end": 12, "steps": 5}]
    before = client.post(
        "/api/doe/preview", json={"factors": factors}, headers=member.headers
    ).json()
    assert before["count"] == 5 and not before["too_many"]

    changed = client.put(
        "/api/server/settings/doe_max_points", json={"value": 3}, headers=admin.headers
    )
    assert changed.status_code == 200, changed.text
    row = next(one for one in changed.json() if one["key"] == "doe_max_points")
    assert row["value"] == 3 and row["overridden"]

    after = client.post(
        "/api/doe/preview", json={"factors": factors}, headers=member.headers
    ).json()
    assert after["too_many"] and after["max"] == 3

    # 회원은 못 바꾼다 · 범위 밖은 거절 · None 이면 기본값으로.
    assert (
        client.put(
            "/api/server/settings/doe_max_points", json={"value": 9}, headers=member.headers
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/server/settings/doe_max_points", json={"value": 0}, headers=admin.headers
        ).status_code
        == 400
    )
    reset = client.put(
        "/api/server/settings/doe_max_points", json={"value": None}, headers=admin.headers
    ).json()
    assert not next(one for one in reset if one["key"] == "doe_max_points")["overridden"]


def test_값은_가공_단위로_맞춘다(client: TestClient, member: Signed) -> None:
    """구간을 셋으로 나누면 0.333… — 그런 치수는 가공할 수 없다. 기본 0.1, 인자마다 바꾼다."""
    got = client.post(
        "/api/doe/preview",
        json={
            "factors": [
                {"name": "a", "mode": "range", "start": 6, "end": 7, "steps": 4},
                {
                    "name": "b",
                    "mode": "range",
                    "start": 6,
                    "end": 7,
                    "steps": 4,
                    "resolution": 0.5,
                },
            ]
        },
        headers=member.headers,
    ).json()
    values_a = sorted({row["a"] for row in got["points"]})
    values_b = sorted({row["b"] for row in got["points"]})
    assert values_a == [6.0, 6.3, 6.7, 7.0]
    assert values_b == [6.0, 6.5, 7.0]  # 0.5 단위로 맞추니 넷이 셋으로 준다
    assert got["count"] == 12


def test_LHS_표본_수_상한도_관리자가_바꾼다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    factors = [{"name": "두께", "mode": "range", "start": 4, "end": 12, "steps": 5}]
    client.put(
        "/api/server/settings/doe_max_samples", json={"value": 30}, headers=admin.headers
    )
    too_many = client.post(
        "/api/doe/preview",
        json={"factors": factors, "method": "lhs", "samples": 31},
        headers=member.headers,
    )
    assert too_many.status_code == 400 and too_many.json()["error"]["code"] == "CCR-DOE-0014"
    ok = client.post(
        "/api/doe/preview",
        json={"factors": factors, "method": "lhs", "samples": 30},
        headers=member.headers,
    ).json()
    assert ok["count"] == 30 and ok["max_samples"] == 30
    # 전체 조합은 표본 수를 보지 않는다.
    grid = client.post(
        "/api/doe/preview", json={"factors": factors, "samples": 999}, headers=member.headers
    )
    assert grid.status_code == 200 and grid.json()["count"] == 5
    client.put(
        "/api/server/settings/doe_max_samples", json={"value": None}, headers=admin.headers
    )


def test_화면이_쓰는_수도_관리자가_바꾼다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    """목록 줄 수 · 형상 보기 수 — 관리자가 아닌 사람도 읽어야 화면이 그 수를 지킨다."""
    before = client.get("/api/server/display", headers=member.headers)
    assert before.status_code == 200
    assert before.json() == {"doe_gallery_max": 24, "list_page_size": 20}

    client.put(
        "/api/server/settings/doe_gallery_max", json={"value": 40}, headers=admin.headers
    )
    client.put(
        "/api/server/settings/list_page_size", json={"value": 50}, headers=admin.headers
    )
    after = client.get("/api/server/display", headers=member.headers).json()
    assert after == {"doe_gallery_max": 40, "list_page_size": 50}

    # 회원은 바꾸지 못한다 — 읽기만.
    denied = client.put(
        "/api/server/settings/list_page_size", json={"value": 5}, headers=member.headers
    )
    assert denied.status_code == 403

    for key in ("doe_gallery_max", "list_page_size"):
        client.put(f"/api/server/settings/{key}", json={"value": None}, headers=admin.headers)


def test_해석_조건을_붙여_훑으면_점마다_풀려_나간다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """**조건도 CAD 치수와 같은 자리에서 훑는다.** 받는 쪽은 `"=압력"` 을 풀 수 없으므로
    점마다 풀린 값이 파일로 나가야 한다."""
    conditions = {
        "named_selections": [
            {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
        ],
        "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
        "loads": [
            {
                "name": "누름",
                "type": "pressure",
                "on": "바닥",
                "magnitude": "=압력",
                "unit": "MPa",
                "direction": "normal",
            }
        ],
        "analysis": {"type": "modal", "modes": 6},
    }
    made = client.post(
        "/api/doe",
        json={
            "name": "조건까지 훑기",
            "recipe": {**JIG, "params": {**JIG["params"], "압력": 2.0}},
            "conditions": conditions,
            # 형상(두께)과 조건(압력)을 함께 훑는다 — 변수가 같은 자리에 있으니 된다.
            "factors": [
                {"name": "두께", "mode": "list", "values": [6, 10]},
                {"name": "압력", "mode": "list", "values": [2, 3]},
            ],
        },
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    study = made.json()
    assert study["point_count"] == 4
    assert study["conditions"]["loads"][0]["magnitude"] == "=압력", "스냅샷은 식을 그대로"

    sent = client.post(f"/api/doe/{study['id']}/export", headers=member.headers)
    assert sent.status_code == 200, sent.text
    folder = next(export_root.iterdir())

    # 스터디 한 장 — 사람이 읽는 정본. 식이 그대로 있다.
    spec = json.loads((folder / "conditions.json").read_text(encoding="utf-8"))
    assert spec["loads"][0]["magnitude"] == "=압력"

    # 점마다 **풀린** 값. 두께 · 압력 조합이 그대로 보인다.
    풀린 = {}
    for number in (1, 2, 3, 4):
        # **점 하나 = 파일 하나** — 영역과 조건이 한 자리에 있다.
        point_file = folder / "points" / f"p{number:04d}.json"
        topo = json.loads(point_file.read_text(encoding="utf-8"))
        one = topo["conditions"]
        풀린[number] = (topo["point"]["params"]["두께"], one["loads"][0]["magnitude"])
        # 이름표는 셀렉터 그대로 — 좌표는 topology 가 든다(설계점마다 다르니까).
        assert one["named_selections"][0]["select"] == {"what": "faces", "role": "bottom"}
        # **영역 이름은 사람이 지은 이름표다.** 조건이 붙으면 기본 이름(`fixed_base`)이
        # 아니라 그 이름으로 나간다 — 해석 쪽이 부를 이름을 우리가 다시 짓지 않는다.
        assert topo["regions"]["바닥"], "조건이 가리킬 면이 실제로 풀렸다"
        assert "fixed_base" not in topo["regions"]
        # **이 점이 무엇인가**를 파일이 스스로 말한다 — 결과가 우리에게 안 돌아오므로.
        assert topo["point"]["number"] == number
        assert topo["point"]["study"]["name"] == "조건까지 훑기"

    assert sorted(풀린.values()) == [(6.0, 2.0), (6.0, 3.0), (10.0, 2.0), (10.0, 3.0)]


def test_없는_이름표를_가리키는_조건은_만들기_전에_막는다(
    client: TestClient, member: Signed
) -> None:
    """설계점 마흔 개를 만든 뒤에 알면 늦다 — 폴더에 반쪽짜리가 남는다."""
    bad = client.post(
        "/api/doe",
        json={
            "name": "막혀야 한다",
            "recipe": JIG,
            "conditions": {
                "constraints": [{"name": "고정", "type": "fixed_support", "on": "없다"}]
            },
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
        },
        headers=member.headers,
    )
    assert bad.status_code == 400
    assert "이름표가 없습니다" in bad.json()["error"]["message"]


def test_공유_폴더는_전달_큐다_기한이_지나면_사본만_치운다(
    client: TestClient, member: Signed, admin: Signed, export_root: Path
) -> None:
    """**지우는 것은 되돌릴 수 없다** — 그래서 지워도 되는 것만 지운다. 사본을 지워도
    「보내기」 를 다시 누르면 같은 폴더가 다시 선다."""
    made = client.post(
        "/api/doe",
        json={
            "name": "치워질 것",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
        },
        headers=member.headers,
    )
    study = made.json()
    client.post(f"/api/doe/{study['id']}/export", headers=member.headers)
    folder = next(export_root.iterdir())
    assert folder.exists()

    # 기한 전에는 아무것도 안 치운다.
    from app.database import SessionLocal
    from app.modules.doe import services

    with SessionLocal() as db:
        assert services.cleanup_exports(db)["count"] == 0
    assert folder.exists()

    # 해석이 「다 읽었다」 고 알리면 기한을 기다리지 않는다.
    released = client.post(f"/api/doe/{study['id']}/release", headers=member.headers)
    assert released.status_code == 200 and released.json()["released_at"]

    with SessionLocal() as db:
        got = services.cleanup_exports(db)
    assert got["count"] == 1
    assert not folder.exists(), "공유 폴더의 사본은 치워진다"

    # **설계점과 레시피는 남는다** — 다시 보낼 수 있다.
    again = client.get(f"/api/doe/{study['id']}", headers=member.headers).json()
    assert again["point_count"] == 1 and again["export_dir_windows"] == ""
    resent = client.post(f"/api/doe/{study['id']}/export", headers=member.headers)
    assert resent.status_code == 200 and next(export_root.iterdir()).exists()
    # **다시 보내면 「다 읽었다」 는 무효다.** 안 그러면 방금 보낸 폴더가 다음 청소에 곧바로
    # 치워진다 — 해석이 아직 열어 보지도 않았는데.
    assert resent.json()["released_at"] is None
    with SessionLocal() as db:
        assert services.cleanup_exports(db)["count"] == 0


def test_영구보관은_기한보다_세다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    made = client.post(
        "/api/doe",
        json={
            "name": "남길 것",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
        },
        headers=member.headers,
    )
    study = made.json()
    client.post(f"/api/doe/{study['id']}/export", headers=member.headers)

    kept = client.post(f"/api/doe/{study['id']}/keep", headers=member.headers)
    assert kept.status_code == 200 and kept.json()["keep_forever"] is True

    # 영구보관이면 「다 읽었다」 를 알려도 안 치운다 — 사람의 뜻이 규칙보다 세다.
    client.post(f"/api/doe/{study['id']}/release", headers=member.headers)
    from app.database import SessionLocal
    from app.modules.doe import services

    with SessionLocal() as db:
        assert services.cleanup_exports(db)["count"] == 0
    assert next(export_root.iterdir()).exists()


def test_서버_보관_폴더도_기한이_있고_치워져도_다시_만들_수_있다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    """**이력이 남는다는 말이 헛말이 되지 않게.**

    설계점 파일은 두 폴더 모두 수명이 있다. 그런데 다시 만들 재료(레시피 · 인자 · 시드 ·
    조건)는 스냅샷으로 DB 에 남으므로, 파일이 치워져도 화면은 그대로 뜨고 「다시 만들기」 가
    같은 것을 되살린다. 그 길이 있어야 지우는 것이 안전하다 — 그래서 한 시험에 둔다.
    """
    from datetime import UTC, datetime, timedelta

    from app.database import SessionLocal
    from app.modules.doe import services
    from app.modules.doe.models import DoeStudy

    made = client.post(
        "/api/doe",
        json={
            "name": "되살아날 것",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6, 8]}],
        },
        headers=member.headers,
    ).json()
    study_id = made["id"]
    assert made["local_ready"] is True

    client.put(
        "/api/server/settings/doe_local_ttl_days", json={"value": 30}, headers=admin.headers
    )

    with SessionLocal() as db:
        # **아직 공유 폴더에 나가 있으면 안 치운다** — 복사원을 먼저 지우면 「다시 보내
        # 달라」 에 답할 길이 없다.
        row = db.get(DoeStudy, __import__("uuid").UUID(study_id))
        assert row is not None
        folder = Path(row.local_dir)
        row.created_at = datetime.now(UTC) - timedelta(days=90)
        row.export_dir = "/어딘가/공유"
        db.commit()
        assert services.cleanup_locals(db)["count"] == 0, "나가 있는 것은 안 치운다"

        row = db.get(DoeStudy, __import__("uuid").UUID(study_id))
        assert row is not None
        row.export_dir = ""
        db.commit()
        assert services.cleanup_locals(db)["count"] == 1
    assert not folder.exists(), "서버 보관 폴더의 파일은 치워진다"

    # **화면은 그대로 뜬다** — 표는 DB 에서, 3D 는 레시피로 다시 만든다.
    got = client.get(f"/api/doe/{study_id}", headers=member.headers).json()
    assert got["point_count"] == 2 and got["done"] == 2
    assert got["local_ready"] is False, "파일이 없다는 것을 화면에 말해 준다"
    표 = client.get(f"/api/doe/{study_id}/manifest.csv", headers=member.headers)
    형상 = client.get(f"/api/doe/{study_id}/points/1/mesh", headers=member.headers)
    assert 표.status_code == 200 and 형상.status_code == 200

    # 「보내기」 는 막히고, **무엇을 하라는지 말한다.**
    blocked = client.post(f"/api/doe/{study_id}/export", headers=member.headers)
    assert blocked.status_code == 400
    assert "다시 만들기" in blocked.json()["error"]["message"]

    # 다시 만들면 같은 파일이 같은 자리에 선다 — 그리고 보낼 수 있다.
    again = client.post(f"/api/doe/{study_id}/rerun", headers=member.headers)
    assert again.status_code == 200, again.text
    assert again.json()["local_ready"] is True and again.json()["done"] == 2
    assert (folder / "manifest.csv").exists()
    assert sorted(one.name for one in (folder / "points").glob("*.step")) == [
        "p0001.step",
        "p0002.step",
    ]
    sent = client.post(f"/api/doe/{study_id}/export", headers=member.headers)
    assert sent.status_code == 200


def test_실패한_점만_다시_할_수_있다_성한_것은_안_건드린다(
    client: TestClient, member: Signed
) -> None:
    """같은 값으로 한 번 더 해 보는 것이다 — 범위를 고칠 생각이면 새 스터디다.

    성한 점을 다시 만들지 않는 것이 요점이다: 수천 점짜리에서 하나가 깨졌다고 전부 다시
    만들면 몇 시간이 든다."""
    made = client.post(
        "/api/doe",
        json={
            "name": "실패만 다시",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [-5, 6]}],
        },
        headers=member.headers,
    ).json()
    assert made["failed"] == 1 and made["done"] == 1

    from app.database import SessionLocal
    from app.modules.doe.models import DoeStudy

    with SessionLocal() as db:
        row = db.get(DoeStudy, __import__("uuid").UUID(made["id"]))
        assert row is not None
        step = Path(row.local_dir) / "points" / "p0002.step"
    before = step.stat().st_mtime_ns

    got = client.post(f"/api/doe/{made['id']}/rerun?only=failed", headers=member.headers)
    assert got.status_code == 200, got.text
    assert got.json()["failed"] == 1 and got.json()["done"] == 1
    assert step.stat().st_mtime_ns == before, "성한 점은 다시 만들지 않는다"
    # 표는 그래도 온전하다 — 건너뛴 점도 제 줄을 쓴다.
    rows = list(
        csv.DictReader(
            (step.parent.parent / "manifest.csv").read_text(encoding="utf-8-sig").splitlines()
        )
    )
    assert [row["status"] for row in rows] == ["failed", "ok"]

    엉뚱 = client.post(f"/api/doe/{made['id']}/rerun?only=엉뚱", headers=member.headers)
    assert 엉뚱.status_code == 422


def test_스터디를_지우면_서버_보관_폴더도_지우고_공유_폴더는_남긴다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """누가 읽느냐가 다르다 — 서버 보관 폴더는 우리 것이라 줄이 사라지면 찾을 수 없는
    쓰레기가 되고, 공유 폴더는 해석이 제 결과를 덧붙여 두었을 수 있다."""
    made = client.post(
        "/api/doe",
        json={
            "name": "지울 것",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
        },
        headers=member.headers,
    ).json()
    client.post(f"/api/doe/{made['id']}/export", headers=member.headers)

    from app.database import SessionLocal
    from app.modules.doe.models import DoeStudy

    with SessionLocal() as db:
        row = db.get(DoeStudy, __import__("uuid").UUID(made["id"]))
        assert row is not None
        local = Path(row.local_dir)
    shared = next(export_root.iterdir())
    assert local.exists() and shared.exists()

    assert client.delete(f"/api/doe/{made['id']}", headers=member.headers).status_code == 204
    assert not local.exists(), "우리 것은 치운다"
    assert shared.exists(), "남의 도구가 읽는 것은 말없이 지우지 않는다"


def test_같은_열쇠로_두_번_불러도_한_벌이다(client: TestClient, member: Signed) -> None:
    """**기계는 재시도한다.** 망이 끊겨 답을 못 받았을 뿐인데 다시 걸면 스터디 둘 · 폴더 둘이
    생기고, 해석 쪽은 어느 것이 진짜인지 모른다."""
    body = {
        "name": "한 벌",
        "recipe": JIG,
        "factors": [{"name": "두께", "mode": "list", "values": [6]}],
        "idempotency_key": "orch-2026-09-24-001",
    }
    first = client.post("/api/doe", json=body, headers=member.headers)
    assert first.status_code == 201, first.text

    again = client.post("/api/doe", json=body, headers=member.headers)
    # **201 이 아니라 200** — 기계가 「새로 생겼나」 를 그 자리에서 알아야 한다.
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]

    # 같은 열쇠에 **다른 요청**이면 거절한다 — 열쇠를 재사용한 쪽이 엉뚱한 스터디를
    # 제가 시킨 것으로 믿으면 그것이야말로 사고다.
    bad = client.post(
        "/api/doe",
        json={**body, "factors": [{"name": "두께", "mode": "list", "values": [8]}]},
        headers=member.headers,
    )
    assert bad.status_code == 400
    assert "다른 요청" in bad.json()["error"]["message"]

    # **열쇠를 안 주면 멱등하지 않다** — 같은 설정으로 한 벌 더 만드는 것은 정상이다.
    plain = {k: v for k, v in body.items() if k != "idempotency_key"}
    one = client.post("/api/doe", json=plain, headers=member.headers)
    two = client.post("/api/doe", json=plain, headers=member.headers)
    assert one.status_code == 201 and two.status_code == 201
    assert one.json()["id"] != two.json()["id"]


def test_진행만_묻는_자리가_따로_있다(client: TestClient, member: Signed) -> None:
    """「끝났나」 만 보려고 설계점 200줄을 되풀이해 받게 하지 않는다."""
    made = client.post(
        "/api/doe",
        json={
            "name": "진행 보기",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [-5, 6]}],
        },
        headers=member.headers,
    ).json()

    got = client.get(f"/api/doe/{made['id']}/status", headers=member.headers)
    assert got.status_code == 200, got.text
    state = got.json()
    assert state["points_total"] == 2 and state["done"] == 1 and state["failed"] == 1
    assert state["pending"] == 0 and state["running"] is False
    assert state["files_ready"] is True and state["folder"] is None
    # **표는 없다.** 이 자리의 존재 이유가 그것이다.
    assert "points" not in state


def test_한_번_부르면_폴더까지(client: TestClient, member: Signed, export_root: Path) -> None:
    """오케스트레이터가 쓰는 자리 — 만들고 · 기다리고 · 보낸다. 다음 단계로 바로 간다."""
    got = client.post(
        "/api/doe/run",
        json={
            "name": "한 번에",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6, 8]}],
            "idempotency_key": "orch-run-1",
        },
        headers=member.headers,
    )
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["done"] == 2 and body["failed"] == 0
    # 공유 폴더 경로가 답에 있다 — 이것 하나로 해석을 걸 수 있다.
    assert body["export_dir_windows"] and body["exported_at"]
    assert (next(export_root.iterdir()) / "manifest.csv").exists()

    # **재시도해도 한 벌** — 이 도구는 오래 기다리므로 중간에 끊기는 일이 정상이다.
    again = client.post(
        "/api/doe/run",
        json={
            "name": "한 번에",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6, 8]}],
            "idempotency_key": "orch-run-1",
        },
        headers=member.headers,
    )
    assert again.status_code == 200 and again.json()["id"] == body["id"]
    assert len(list(export_root.iterdir())) == 1, "폴더가 둘이 되면 안 된다"


def test_보내지_말라면_안_보낸다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """조건만 바꿔 가며 쌓아 둘 때 — 만들기는 하되 해석에 넘기지 않는다."""
    got = client.post(
        "/api/doe/run?export=false",
        json={
            "name": "쌓아 두기",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
            "idempotency_key": "orch-run-2",
        },
        headers=member.headers,
    )
    assert got.status_code == 200, got.text
    assert got.json()["done"] == 1
    assert got.json()["export_dir_windows"] == ""
    # 공유 폴더에 아무것도 안 생긴다 — 폴더 자체가 안 서 있을 수도 있다.
    assert not export_root.exists() or list(export_root.iterdir()) == []


def test_기다려_주는_자리는_끝나면_바로_돌아온다(client: TestClient, member: Signed) -> None:
    """부르는 쪽마다 폴링 루프를 만들지 않게. 끝을 보장하지는 않는다 — 상한까지만 문다."""
    made = client.post(
        "/api/doe",
        json={
            "name": "기다리기",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
        },
        headers=member.headers,
    ).json()
    got = client.post(f"/api/doe/{made['id']}/wait?seconds=5", headers=member.headers)
    assert got.status_code == 200, got.text
    assert got.json()["running"] is False and got.json()["waited_out"] is False
    # 상한은 2분 — 오래 물면 프록시가 먼저 끊고, 그때 「실패」 와 「아직」 을 구별 못 한다.
    너무김 = client.post(f"/api/doe/{made['id']}/wait?seconds=999", headers=member.headers)
    assert 너무김.status_code == 422


def _pat(client: TestClient, who: Signed, scopes: list[str]) -> dict[str, str]:
    """이 사람 자격의 **기계 토큰**. 범위는 관리자가 토큰을 만들 때 준다."""
    made = client.post(
        "/api/auth/tokens",
        json={"name": "오케스트레이터", "scopes": scopes},
        headers=who.headers,
    )
    assert made.status_code == 201, made.text
    return {"Authorization": f"Bearer {made.json()['token']}"}


def test_기계가_대행하면_소유자는_사람이고_누가_돌렸는지도_남는다(
    client: TestClient, member: Signed, admin: Signed, db: Any
) -> None:
    """**PAT 으로 만들면 소유자가 서비스 계정이 된다** — 그러면 정작 사람이 제 활동에서 못
    찾고 403 을 받는다. 그래서 「누구를 위해」 를 밝히게 한다.

    둘을 한 칸에 욱여넣지 않는다: 소유자는 사람(내 DOE 목록), 부른 쪽은 기계(누가 돌렸나)."""
    machine = _pat(client, admin, ["read", "write", "act_for_others"])
    got = client.post(
        "/api/doe",
        json={
            "name": "기계가 만든 것",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
            "on_behalf_of": member.email,
        },
        headers=machine,
    )
    assert got.status_code == 201, got.text
    body = got.json()
    assert body["owner_name"] == "member", "소유자는 대행 대상인 사람"
    assert body["requested_by_name"] == "admin", "누가 돌렸는지도 남는다"

    # **사람이 제 활동에서 찾는다** — 이것이 대행의 이유다.
    mine = client.get("/api/doe", headers=member.headers).json()
    assert [one["id"] for one in mine["items"]] == [body["id"]]

    # **대행한 기계는 제가 만든 것을 제가 몰 수 있다.** 소유자는 사람이지만 돌리고 · 보내고
    # · 「다 읽었다」 고 알리는 것은 기계다 — 이것이 없으면 오케스트레이터가 반 바퀴에서 선다.
    assert client.post(f"/api/doe/{body['id']}/export", headers=machine).status_code == 200
    assert client.post(f"/api/doe/{body['id']}/release", headers=machine).status_code == 200

    # 폴더도 둘 다 말한다 — 폴더를 연 사람이 「누구에게 물어야 하나」 를 알아야 한다.
    from app.database import SessionLocal
    from app.modules.doe.models import DoeStudy

    with SessionLocal() as fresh:
        row = fresh.get(DoeStudy, __import__("uuid").UUID(body["id"]))
        assert row is not None
        written = json.loads((Path(row.local_dir) / "study.json").read_text(encoding="utf-8"))
    assert written["owner"]["email"] == member.email
    assert written["requested_by"]["email"] == admin.email


def test_대행은_아무_토큰이나_못_한다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    """**남의 이름을 빌리는 일이다.** 자격은 사람이 아니라 그 토큰에 붙는다."""
    plain = _pat(client, admin, ["read", "write"])
    got = client.post(
        "/api/doe",
        json={
            "name": "몰래",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
            "on_behalf_of": member.email,
        },
        headers=plain,
    )
    assert got.status_code == 403
    assert "대행" in got.json()["error"]["message"]

    # 사람 세션에도 범위가 없다 — 제 이름으로 만들면 된다.
    사람 = client.post(
        "/api/doe",
        json={
            "name": "몰래",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
            "on_behalf_of": member.email,
        },
        headers=admin.headers,
    )
    assert 사람.status_code == 403

    # 없는 사람 이름으로도 못 만든다.
    없는사람 = client.post(
        "/api/doe",
        json={
            "name": "없는 사람",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
            "on_behalf_of": "nobody@example.local",
        },
        headers=_pat(client, admin, ["read", "write", "act_for_others"]),
    )
    assert 없는사람.status_code == 400


def test_읽기는_공개_쓰기는_소유자(client: TestClient, member: Signed, admin: Signed) -> None:
    """DOE 는 이 조직의 설계 이력이다 — 옆 사람이 같은 훑기를 다시 도는 것이 더 큰 손해다.

    그렇다고 남의 것을 해석에 넘기거나 지울 수 있으면 「읽기 공개」 가 「모두가 주인」 이 된다.
    """
    made = client.post(
        "/api/doe",
        json={
            "name": "남의 것",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6]}],
        },
        headers=admin.headers,
    ).json()
    assert made["visibility"] == "read", "기본은 공개"

    # 남이 **본다** — 상세도 진행도.
    assert client.get(f"/api/doe/{made['id']}", headers=member.headers).status_code == 200
    assert (
        client.get(f"/api/doe/{made['id']}/status", headers=member.headers).status_code == 200
    )
    # 내 활동에는 안 섞인다 — 찾는 것은 다른 물음이다.
    assert client.get("/api/doe", headers=member.headers).json()["total"] == 0
    # (다른 시험이 만든 공개 스터디도 함께 보인다 — 그것이 `all` 의 뜻이다.)
    찾기 = client.get("/api/doe?scope=all&limit=200", headers=member.headers).json()
    남의것 = next(one for one in 찾기["items"] if one["id"] == made["id"])
    assert 남의것["owner_name"] == "admin"

    # **고치지는 못한다.**
    for path in ("export", "release", "rerun", "keep"):
        블록 = client.post(f"/api/doe/{made['id']}/{path}", headers=member.headers)
        assert 블록.status_code == 403, path
    assert client.delete(f"/api/doe/{made['id']}", headers=member.headers).status_code == 403

    # 감추면 남이 못 본다 — 기본이 공개이고 감추는 것이 예외다.
    감추기 = f"/api/doe/{made['id']}/visibility?value=private"
    숨김 = client.post(감추기, headers=admin.headers)
    assert 숨김.status_code == 200 and 숨김.json()["visibility"] == "private"
    assert client.get(f"/api/doe/{made['id']}", headers=member.headers).status_code == 403
    뒤에 = client.get("/api/doe?scope=all&limit=200", headers=member.headers).json()
    assert made["id"] not in [one["id"] for one in 뒤에["items"]]


def test_조건만_훑으면_형상은_한_벌만_만든다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """**압력 2 · 3 MPa 를 훑으면 STEP 이 전부 같다.** 그것을 N 벌 만들어 N 벌 쓰면 시간도
    파일도 N 배다.

    지문은 **식을 다 푼 노드**에서 나오므로, 아무 노드도 안 쓰는 치수(`압력`)는 지문에 안
    들어간다 — 만들어 보기 전에 같다는 것을 안다.
    """
    recipe = {**JIG, "params": {**JIG["params"], "압력": 2.0}}
    made = client.post(
        "/api/doe",
        json={
            "name": "조건만 훑기",
            "recipe": recipe,
            "factors": [{"name": "압력", "mode": "list", "values": [2, 3, 4]}],
            "conditions": {
                "named_selections": [
                    {"name": "윗면", "entity": "face", "select": {"role": "top"}}
                ],
                "loads": [
                    {
                        "name": "누름",
                        "type": "pressure",
                        "on": "윗면",
                        "magnitude": "=압력",
                    }
                ],
            },
        },
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["done"] == 3

    # 세 점이 **같은 STEP 한 벌**을 가리킨다.
    쓰는것 = {one["step_file"] for one in body["points"]}
    assert len(쓰는것) == 1, f"형상이 같은데 파일이 여럿이다: {쓰는것}"
    assert next(iter(쓰는것)).startswith("shapes/"), "나눠 쓰는 것은 이름이 그렇게 말한다"

    client.post(f"/api/doe/{body['id']}/export", headers=member.headers)
    folder = next(export_root.iterdir())
    assert len(list((folder / "shapes").glob("*.step"))) == 1
    assert list((folder / "points").glob("*.step")) == [], "점 폴더에는 형상이 없다"
    # 점 파일은 **점마다** 있다 — 조건이 다르니까.
    assert len(list((folder / "points").glob("*.json"))) == 3
    풀린값 = [
        json.loads(one.read_text(encoding="utf-8"))["conditions"]["loads"][0]["magnitude"]
        for one in sorted((folder / "points").glob("*.json"))
    ]
    assert 풀린값 == [2.0, 3.0, 4.0], "형상은 같아도 조건은 점마다 풀린다"

    # **점 파일이 가리키는 STEP 이 진짜로 있어야 한다.** 해석 쪽이 형상을 찾을 곳은 이 칸
    # 뿐인데, 여기서 경로를 다시 지어 `points/` 라고 적고 있었다(살아 있는 서버로 한 바퀴
    # 돌려 보다 잡았다). 표와 DB 는 맞았고 이 파일만 거짓말을 했다.
    for one in sorted((folder / "points").glob("*.json")):
        말한것 = json.loads(one.read_text(encoding="utf-8"))["point"]["step_file"]
        assert (folder / 말한것).exists(), f"{one.name} 이 없는 파일을 가리킨다: {말한것}"


def test_형상이_다르면_예전처럼_점마다_한_벌(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """겹침 제거가 **흔한 쪽을 바꾸지 않는다** — 치수 훑기는 파일 이름이 그대로다."""
    made = client.post(
        "/api/doe",
        json={
            "name": "치수 훑기",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [6, 8]}],
        },
        headers=member.headers,
    ).json()
    assert [one["step_file"] for one in made["points"]] == [
        "points/p0001.step",
        "points/p0002.step",
    ]
    client.post(f"/api/doe/{made['id']}/export", headers=member.headers)
    folder = next(one for one in export_root.iterdir() if one.name.startswith("치수"))
    assert not (folder / "shapes").exists(), "나눠 쓰는 것이 없으면 그 폴더도 없다"


def test_형상이_같은_점은_메시도_한_번만_만든다(client: TestClient, member: Signed) -> None:
    """나란히 보기로 스물넷을 열면 같은 것을 스물네 번 만들게 된다 — 조건 훑기에서는 전부
    같은 형상이다."""
    recipe = {**JIG, "params": {**JIG["params"], "압력": 2.0}}
    made = client.post(
        "/api/doe",
        json={
            "name": "메시 나눠 쓰기",
            "recipe": recipe,
            "factors": [{"name": "압력", "mode": "list", "values": [2, 3]}],
        },
        headers=member.headers,
    ).json()

    from app.modules.doe import services

    services._MESH_CACHE.clear()
    첫째 = client.get(f"/api/doe/{made['id']}/points/1/mesh", headers=member.headers).json()
    지문개수 = sum(1 for key in services._MESH_CACHE if isinstance(key[1], str))
    둘째 = client.get(f"/api/doe/{made['id']}/points/2/mesh", headers=member.headers).json()
    # 형상 지문은 하나뿐 — 둘째 점이 새 형상을 만들지 않았다.
    assert sum(1 for key in services._MESH_CACHE if isinstance(key[1], str)) == 지문개수 == 1
    # 그래도 **제 번호와 제 변수 값**을 말한다 — 화면이 어느 점인지 알아야 한다.
    assert 첫째["number"] == 1 and 둘째["number"] == 2
    assert 첫째["params"]["압력"] == 2.0 and 둘째["params"]["압력"] == 3.0
    assert 첫째["mesh"] == 둘째["mesh"]
