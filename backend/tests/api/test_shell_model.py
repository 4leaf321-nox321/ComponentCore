"""해석용 셸 모델 — **시트 바디 STEP 을 올려 해석용으로 내보낸다**(2026-10-15).

올리기 → 저장 평가(셸 모델) → 조건(쉘 · 두께) → 해석용 내보내기(설계 하나) → 설계점의 중간면 ·
파트 목록. 지그는 입체가 있어야 하니 셸 모델로는 거절한다 — 그 말이 무엇을 하면 되는지 말한다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from build123d import Face, Vector
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core import export
from tests.api.conftest import Signed


@pytest.fixture
def export_root(tmp_path: Path) -> Iterator[Path]:
    """공유 폴더는 시험에서 임시 폴더로(`test_doe.py` 와 같다)."""
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _upload_sheet(client: TestClient, who: Signed, tmp_path: Path) -> dict[str, Any]:
    points = [
        [Vector(x, y, 3.0 * ((x - 20) / 20) ** 2) for x in (0, 10, 20, 30, 40)]
        for y in (0, 10, 20, 30)
    ]
    step = export.write_step(
        Face.make_surface_from_array_of_points(points), tmp_path / "skin.step"
    )
    with step.open("rb") as stream:
        got = client.post(
            "/api/works/from-step",
            files={"file": ("skin.step", stream, "application/step")},
            headers=who.headers,
        )
    assert got.status_code == 201, got.text
    work = got.json()
    job = work["current"]["job"]
    assert job["status"] == "done", job["error"]
    return dict(work)


def test_시트_STEP_을_올리면_셸_모델로_저장된다(
    client: TestClient, member: Signed, tmp_path: Path
) -> None:
    work = _upload_sheet(client, member, tmp_path)
    summary = work["current"]["job"]["summary"]
    assert summary["is_shell"] is True and summary["solid_count"] == 0
    assert any("셸 모델" in one for one in summary["warnings"])


def test_셸_모델을_해석용으로_내보내면_중간면과_두께가_나간다(
    client: TestClient, member: Signed, tmp_path: Path, export_root: Path
) -> None:
    work = _upload_sheet(client, member, tmp_path)
    recipe = work["current"]["recipe"]
    made = client.post(
        "/api/doe",
        json={
            "name": "덮개 셸",
            "recipe": recipe,
            "conditions": {
                "body_settings": [
                    {"name": "전체", "representation": "shell", "thickness": 1.2}
                ]
            },
        },
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    study = made.json()
    assert study["outputs"] == ["midsurface"]

    sent = client.post(f"/api/doe/{study['id']}/export", headers=member.headers)
    assert sent.status_code == 200, sent.text
    folder = next(export_root.iterdir())
    point = json.loads((folder / "points" / "p0001.json").read_text("utf-8"))
    (body,) = point["midsurface"]["bodies"]
    assert body["thickness"] == 1.2 and body["source"] == "sheet"
    assert (folder / point["midsurface"]["step_file"]).exists()
    (row,) = point["bodies"]
    assert row["kind"] == "sheet" and row["volume"] == 0 and row["area"] > 40 * 30


def test_두께를_안_적으면_설계점이_무엇이_빠졌는지_말한다(
    client: TestClient, member: Signed, tmp_path: Path, export_root: Path
) -> None:
    work = _upload_sheet(client, member, tmp_path)
    made = client.post(
        "/api/doe",
        json={
            "name": "두께 없는 셸",
            "recipe": work["current"]["recipe"],
            "conditions": {"body_settings": [{"name": "전체", "representation": "shell"}]},
        },
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    sent = client.post(f"/api/doe/{made.json()['id']}/export", headers=member.headers)
    assert sent.status_code == 200, sent.text
    folder = next(export_root.iterdir())
    point = json.loads((folder / "points" / "p0001.json").read_text("utf-8"))
    assert "두께" in json.dumps(point["midsurface"], ensure_ascii=False)


def test_두께는_쉘_파트에만_적는다(client: TestClient, member: Signed) -> None:
    plate = {"nodes": [{"id": "판", "op": "box", "length": 40, "width": 30, "height": 2}]}
    got = client.post(
        "/api/doe",
        json={
            "name": "솔리드에 두께",
            "recipe": plate,
            "conditions": {"body_settings": [{"name": "전체", "thickness": 2}]},
        },
        headers=member.headers,
    )
    assert got.status_code in (400, 422), got.text
    assert "쉘 파트에만" in got.text


def test_셸_모델로는_지그를_만들지_않는다(
    client: TestClient, member: Signed, tmp_path: Path
) -> None:
    """받아 두고 생성기가 「바닥에 평면이 없습니다」 로 실패하면 사람은 왜인지 모른다 — 걸기
    전에 무엇을 하면 되는지 말한다(미리 보기도 같다)."""
    work = _upload_sheet(client, member, tmp_path)
    got = client.post(
        "/api/works/jig-from-part",
        json={"source": f"work:{work['id']}"},
        headers=member.headers,
    )
    assert got.status_code == 400, got.text
    assert "셸 모델" in got.text and "thicken" in got.text
    preview = client.post(
        "/api/works/jig-from-part/preview",
        json={"source": f"work:{work['id']}"},
        headers=member.headers,
    )
    assert preview.status_code == 400, preview.text
    assert "셸 모델" in preview.text
