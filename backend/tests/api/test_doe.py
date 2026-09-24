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
