"""시험 지그(강체)에는 재료가 붙어 나가고, 재료가 빈 파트는 내보낼 때 경고한다(SimEngBay 의
요청, 2026-10-23 — 「CAD 가 재료를 지정하지 않은 파트가 있습니다: 롤러_1, 롤러_2, 로딩_노즈」).
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.specimens import fixture_material
from app.modules.materials import services as materials
from app.shared.errors import NotFound, code
from tests.api.conftest import Signed

PLATE = {"nodes": [{"id": "판", "op": "box", "length": 40, "width": 30, "height": 2}]}
ROLLERS = ["롤러_1", "롤러_2", "로딩_노즈"]


@pytest.fixture
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _materials(body: dict[str, Any]) -> list[dict[str, Any]]:
    return list((body.get("conditions") or {}).get("materials") or [])


def test_시편_작업의_지그에는_기본_강재가_실린다(client: TestClient, member: Signed) -> None:
    made = client.post(
        "/api/specimens/works", json={"preset_id": "iso-178"}, headers=member.headers
    )
    assert made.status_code == 201, made.text
    rows = _materials(made.json()["current"])
    assert [(one["apply_to"], one["ref"]["source"]) for one in rows] == [
        (ROLLERS, "compcore-default")
    ]
    assert rows[0]["payload"]["density"] == 7850.0


def test_설치가_정한_재료로_바꿔_끼운다(
    client: TestClient, member: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "fixture_material_code", "M-000777")
    asked: list[str] = []

    def found(_db: Any, code_or_id: str, **_kw: Any) -> dict[str, Any]:
        asked.append(code_or_id)
        return {
            "code": "M-000777",
            "id": "uuid-777",
            "name": "SKD11 지그강",
            "source": "matnexus",
            "payload": {"code": "M-000777", "density": 7700, "density_unit": "kg/m3"},
        }

    monkeypatch.setattr(materials, "one", found)
    got = client.post(
        "/api/specimens/build", json={"preset_id": "iso-178"}, headers=member.headers
    )
    assert got.status_code == 200, got.text
    rows = _materials(got.json())
    assert asked == ["M-000777"]
    assert [
        (one["apply_to"], one["ref"]["code"], one["ref"]["material_id"]) for one in rows
    ] == [(ROLLERS, "M-000777", "uuid-777")]
    assert rows[0]["ref"]["source"] == "matnexus" and rows[0]["payload"]["density"] == 7700
    assert any("SKD11 지그강" in one for one in got.json()["notes"])
    assert not any("일반 구조용 강" in one for one in got.json()["notes"])


def test_설치_재료를_못_찾으면_기본_강재를_두고_말한다(
    client: TestClient, member: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "fixture_material_code", "M-404")

    def missing(_db: Any, code_or_id: str, **_kw: Any) -> dict[str, Any]:
        raise NotFound(code("MATERIALS", 3), f"재료({code_or_id})를 찾을 수 없습니다.")

    monkeypatch.setattr(materials, "one", missing)
    got = client.post(
        "/api/specimens/build", json={"preset_id": "iso-178"}, headers=member.headers
    )
    assert got.status_code == 200, got.text
    assert _materials(got.json())[0]["ref"]["source"] == "compcore-default"
    assert any("M-404" in one and "기본 강재" in one for one in got.json()["notes"])


def _warnings(
    client: TestClient, who: Signed, root: Path, name: str, conditions: dict[str, Any]
) -> str:
    made = client.post(
        "/api/doe",
        json={"name": name, "recipe": PLATE, "conditions": conditions},
        headers=who.headers,
    )
    assert made.status_code == 201, made.text
    study = made.json()["id"]
    sent = client.post(f"/api/doe/{study}/export", headers=who.headers)
    assert sent.status_code == 200, sent.text
    folder = next(one for one in root.iterdir() if one.name.startswith(name))
    rows = list(
        csv.DictReader((folder / "manifest.csv").read_text(encoding="utf-8-sig").splitlines())
    )
    # 내려받는 표(다시 그린 것)도 재료 경고는 같은 말을 한다.
    again = client.get(f"/api/doe/{study}/manifest.csv", headers=who.headers)
    assert again.status_code == 200
    assert ("재료가 없는 파트" in again.text) == ("재료가 없는 파트" in rows[0]["warnings"])
    return rows[0]["warnings"]


def test_재료가_빈_파트는_내보낼_때_경고한다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    bare = _warnings(client, member, export_root, "빈판", {"units": {"system": "si"}})
    assert "재료가 없는 파트: 전체" in bare
    steel = fixture_material.material(["전체"])
    covered = _warnings(client, member, export_root, "강판", {"materials": [steel]})
    assert "재료가 없는 파트" not in covered
