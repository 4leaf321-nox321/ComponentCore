"""STEP 이름 그대로 올린 작업의 바디 이름이 **DOE 점 파일의 모든 자리에서 같다**(2026-11-18).

v0.30.0 부터 새로 올린 STEP 은 이름 그대로 읽는다 — 공백 · 점 · 괄호 · 작은따옴표가
남는다. 받는 쪽(SimEngBay)은 `bodies[].name` · `materials[].apply_to` ·
`body_settings[].name` · `midsurface.bodies[].name` 을 **서로 견줘** 짝짓는다. 하나라도 옛
규칙(`_`)이거나 앞뒤 공백이 남으면 짝이 끊긴다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from build123d import Box, Compound, Location, Shape
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core import export
from tests.api.conftest import Signed

#: STEP 에 적힌 이름 → 올린 뒤의 바디 이름(앞뒤 공백은 지운다, 가운데는 그대로).
NAMES = {
    "  덮개 판 v1.2  ": "덮개 판 v1.2",
    "볼트 M6 (A'급)": "볼트 M6 (A'급)",
}


@pytest.fixture
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _named(shape: Shape, label: str, at: tuple[float, float, float]) -> Shape:
    one = shape.moved(Location(at))
    one.label = label
    return one


def _upload(client: TestClient, who: Signed, tmp_path: Path) -> dict[str, Any]:
    plate, bolt = NAMES
    whole = Compound(
        children=[
            _named(Box(40, 30, 2), plate, (0, 0, 0)),
            _named(Box(6, 6, 12), bolt, (30, 0, 7)),
        ]
    )
    step = export.write_step(whole, tmp_path / "names.step")
    with step.open("rb") as stream:
        got = client.post(
            "/api/works/from-step",
            files={"file": ("names.step", stream, "application/step")},
            headers=who.headers,
        )
    assert got.status_code == 201, got.text
    work = got.json()
    assert work["current"]["job"]["status"] == "done", work["current"]["job"]["error"]
    return dict(work)


def test_새_이름이_점_파일의_모든_자리에서_같다(
    client: TestClient, member: Signed, tmp_path: Path, export_root: Path
) -> None:
    work = _upload(client, member, tmp_path)
    plate, bolt = NAMES.values()
    labels = [one.get("label") for one in work["current"]["recipe"]["nodes"]]
    assert labels[:2] == [plate, bolt], "피처 트리의 이름도 같다"

    material = {
        "ref": {"source": "matnexus", "name": "SPCC", "material_id": "m-0"},
        "payload": {"density_si": 7850.0},
        "deck_formats": ["ansys"],
    }
    made = client.post(
        "/api/doe",
        json={
            "name": "이름 그대로",
            "recipe": work["current"]["recipe"],
            "conditions": {
                "materials": [
                    {**material, "apply_to": [plate]},
                    {**material, "apply_to": [bolt]},
                ],
                "body_settings": [
                    {"name": plate, "representation": "shell"},
                    {"name": bolt, "behavior": "rigid"},
                ],
            },
        },
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    study = made.json()
    sent = client.post(f"/api/doe/{study['id']}/export", headers=member.headers)
    assert sent.status_code == 200, sent.text
    folder = next(export_root.iterdir())
    point = json.loads((folder / "points" / "p0001.json").read_text("utf-8"))

    names = [one["name"] for one in point["bodies"]]
    assert names == [plate, bolt], "앞뒤 공백은 지우고 가운데는 그대로"
    assert all(one["step_product"].isascii() for one in point["bodies"])
    conditions = point["conditions"]
    assert [one["apply_to"] for one in conditions["materials"]] == [[plate], [bolt]]
    assert [one["name"] for one in conditions["body_settings"]] == [plate, bolt]
    (mid,) = point["midsurface"]["bodies"]
    assert mid["name"] == plate
    step_products = {one["name"]: one["step_product"] for one in point["bodies"]}
    assert mid["step_product"] == step_products[plate], "중간면 셸의 이름도 같은 파트의 것"
