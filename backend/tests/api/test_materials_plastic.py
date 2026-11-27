"""MatNexus 물성 카드에서 소성 곡선 받기 — 확정 카드만, 방향은 재료마다 사용자가 고른다.

MatNexus 는 흉내 낸다. 모양은 그쪽 개발 서버의 실제 응답 그대로다(2026-11-28 — 인장 카드의
`blocks.table.rows` 가 `{plastic_strain, true_stress}`, `?units=mm_n_tonne` 이면 응력이 MPa).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.shared.clients import matnexus
from tests.api.conftest import Signed

MATERIAL = "6c296526-322f-494d-a792-ea7b4ade4694"


def _card(card_id: str, status: str, orientation: str) -> dict[str, Any]:
    return {
        "id": card_id,
        "code": f"C-{card_id}",
        "material_id": MATERIAL,
        "label": f"인장 {orientation}",
        "test_type_key": "tensile",
        "orientation": orientation,
        "status": status,
        "point_count": 3,
        "published_at": "2026-11-01T00:00:00Z" if status == "published" else None,
        "blocks": {
            "elastic": {"values": {"youngs_modulus": 205e9}},
            "table": {"rows": [{"plastic_strain": 0.0, "true_stress": 250e6}]},
        },
    }


CARDS = [
    _card("c1", "published", "MD"),
    _card("c2", "draft", "TD"),
    _card("c3", "deprecated", "MD"),
]


def _export(card_id: str, system: str) -> dict[str, Any]:
    assert system == "mm_n_tonne", "입력 계로 받는다"
    return {
        "schema": "matnexus.property-card/1",
        "units": {"stress": "MPa", "system": system},
        "blocks": {
            "elastic": {"values": {"youngs_modulus": 205000.0}},
            "table": {
                "rows": [
                    {"plastic_strain": 0.0, "true_stress": 250.0},
                    {"plastic_strain": 0.01, "true_stress": 270.0},
                    {"plastic_strain": 0.05, "true_stress": 300.0},
                ]
            },
        },
    }


@pytest.fixture
def mnx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matnexus, "plastic_cards", lambda material_id: CARDS)
    monkeypatch.setattr(
        matnexus, "card", lambda card_id: next(one for one in CARDS if one["id"] == card_id)
    )
    monkeypatch.setattr(matnexus, "card_export", _export)


def test_재료의_소성_카드를_방향마다_쓸_수_있나와_함께_보인다(
    client: TestClient, member: Signed, mnx: None
) -> None:
    got = client.get(f"/api/materials/{MATERIAL}/plastic-cards", headers=member.headers).json()
    assert [(one["orientation"], one["status"], one["usable"]) for one in got["items"]] == [
        ("MD", "published", True),
        ("TD", "draft", False),
        ("MD", "deprecated", False),
    ]
    assert "확정(published)된 카드만" in got["items"][1]["why"]
    assert "내려진 카드" in got["items"][2]["why"]


def test_확정_카드의_곡선을_입력_계로_받아_출처와_함께_넣는다(
    client: TestClient, member: Signed, mnx: None
) -> None:
    got = client.get("/api/materials/plastic-cards/c1", headers=member.headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["model"] == "multilinear_isotropic"
    plastic = body["plastic"]
    assert plastic["table"] == [[0.0, 250.0], [0.01, 270.0], [0.05, 300.0]]
    assert plastic["source"] == "matnexus"
    card = plastic["card"]
    assert (card["id"], card["orientation"], card["status"], card["youngs_modulus"]) == (
        "c1",
        "MD",
        "published",
        205000.0,
    )
    assert card["stress_unit"] == "MPa" and card["fetched_at"]
    refused = client.get("/api/materials/plastic-cards/c2", headers=member.headers)
    assert refused.status_code == 400 and "초안입니다" in refused.json()["error"]["message"]


def test_matnexus_에_못_닿으면_빈_목록과_까닭(
    client: TestClient, member: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(material_id: str) -> list[dict[str, Any]]:
        raise matnexus.MatNexusUnavailable("MatNexus에 연결하지 못했습니다: timed out")

    monkeypatch.setattr(matnexus, "plastic_cards", down)
    got = client.get(f"/api/materials/{MATERIAL}/plastic-cards", headers=member.headers).json()
    assert got == {"items": [], "note": "MatNexus에 연결하지 못했습니다: timed out"}
