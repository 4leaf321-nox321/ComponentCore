"""실험계획 — 조합을 만들고, 형상마다 STEP 을 공유 폴더에 쓴다."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed

#: 연결부(구멍 자리)는 숫자로 못 박고 튜닝부만 치수 이름으로 — DOE 의 전제다.
JIG = {
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
            "material": "aluminum",
        },
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    study = made.json()
    assert study["point_count"] == 3
    assert study["export_dir_windows"]

    got = client.get(f"/api/doe/{study['id']}", headers=member.headers).json()
    assert got["done"] == 3 and got["failed"] == 0
    masses = [point["metrics"]["mass_g"] for point in got["points"]]
    assert masses[0] < masses[1] < masses[2]  # 두꺼울수록 무겁다

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
    assert float(rows[0]["mass_g"]) > 0

    # 내려받는 표도 같은 값이다.
    csv_out = client.get(f"/api/doe/{study['id']}/manifest.csv", headers=member.headers)
    assert csv_out.status_code == 200 and "두께" in csv_out.text

    # 부등식 필터 — 값이 있는 점만, 조건을 만족하는 것만.
    kept = client.post(
        f"/api/doe/{study['id']}/filter",
        json=[{"key": "mass_g", "op": "lte", "value": masses[1]}],
        headers=member.headers,
    )
    assert kept.status_code == 200 and len(kept.json()) == 2


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
