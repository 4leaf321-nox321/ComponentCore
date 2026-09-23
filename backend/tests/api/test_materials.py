"""물성 고르기 — MatNexus 가 있을 때와 **없을 때**."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.shared.clients import matnexus
from tests.api.conftest import Signed

#: MatNexus 가 주는 모양 그대로 — 우리가 고치지 않는다(단위가 값에 붙어 있다).
SPCC: dict[str, Any] = {
    "id": "8f0e…",
    "code": "M-000123",
    "record_name": "SPCC 1.2t",
    "alias": "냉연강판",
    "family": "강판",
    "category": "냉연",
    "grade": "SPCC",
    "density": 7850.0,
    "density_unit": "kg/m^3",
    "poisson_ratio": 0.3,
    "declared_properties": [
        {
            "item": "탄성계수",
            "si_unit": "Pa",
            "input_unit": "GPa",
            "scale": None,
            "points": [
                {"temperature_C": 22, "value_si": 2.06e11},
                {"temperature_C": 400, "value_si": 1.7e11},
            ],
        }
    ],
}


@pytest.fixture
def fake_matnexus(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """가짜 MatNexus — 우리가 **어떤 질의를 보내는지**도 이 자리에서 본다."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={"items": [SPCC], "total": 1})

    def client() -> httpx.Client:
        return httpx.Client(
            base_url="http://matnexus.test",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer mnx_pat_test"},
        )

    monkeypatch.setattr(matnexus, "configured", lambda: True)
    monkeypatch.setattr(matnexus, "_client", client)
    yield seen


def test_전역_재료만_묻는다(
    client: TestClient, member: Signed, fake_matnexus: dict[str, Any]
) -> None:
    """**PAT 에 범위가 없다.** 서비스 계정으로 부르면서 작업공간 재료까지 보여 주면 그쪽
    권한 구분이 이쪽에서 무너진다 — `scope` 는 사람이 바꿀 수 있는 칸이 아니다."""
    got = client.get("/api/materials", params={"q": "SPCC"}, headers=member.headers)
    assert got.status_code == 200, got.text
    assert "scope=global" in fake_matnexus["url"]
    assert "q=SPCC" in fake_matnexus["url"]
    assert fake_matnexus["auth"].startswith("Bearer mnx_pat_")

    body = got.json()
    assert body["fallback"] is False
    one = body["items"][0]
    assert one["code"] == "M-000123" and one["name"] == "SPCC 1.2t"
    # **값은 해석하지 않는다.** 받은 것이 payload 에 그대로 있다 — 단위도 온도 표도.
    assert one["payload"]["declared_properties"][0]["si_unit"] == "Pa"
    assert one["payload"]["declared_properties"][0]["points"][1]["value_si"] == 1.7e11
    assert one["density"] == 7850.0 and one["density_unit"] == "kg/m^3"


def test_못_닿으면_올려_둔_카탈로그로_넘어가고_그_사실을_말한다(
    client: TestClient, member: Signed, admin: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조용히 옛 사본을 주면 사람은 어제 받은 값을 오늘 것으로 믿는다."""
    upload = client.post(
        "/api/materials/catalog",
        files={
            "file": (
                "matnexus-export.json",
                io.BytesIO(json.dumps([SPCC]).encode()),
                "application/json",
            )
        },
        headers=admin.headers,
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["loaded"] == 1

    # 주소가 없다 — 닿을 데가 없는 상태.
    monkeypatch.setattr(matnexus, "configured", lambda: False)
    got = client.get("/api/materials", params={"q": "SPCC"}, headers=member.headers).json()
    assert got["fallback"] is True and got["detail"]
    assert got["items"][0]["source"] == "catalog"
    assert (
        got["items"][0]["payload"]["declared_properties"][0]["points"][0]["value_si"]
        == 2.06e11
    )

    # 한 건 읽기도 사본에서 — 고른 뒤에는 어디서 왔든 같은 모양이다.
    one = client.get("/api/materials/M-000123", headers=member.headers).json()
    assert one["source"] == "catalog" and one["payload"]["code"] == "M-000123"

    status = client.get("/api/materials/status", headers=member.headers).json()
    assert status["configured"] is False and status["catalog_count"] == 1


def test_카탈로그는_통째로_갈아_끼운다(client: TestClient, admin: Signed) -> None:
    """합치면 그쪽에서 지워진 재료가 사본에만 남고, 그것을 고르고 나서야 없다는 것을 안다."""
    first = json.dumps([SPCC, {**SPCC, "code": "M-000999", "record_name": "없어질 것"}])
    client.post(
        "/api/materials/catalog",
        files={"file": ("a.json", io.BytesIO(first.encode()), "application/json")},
        headers=admin.headers,
    )
    again = client.post(
        "/api/materials/catalog",
        files={
            "file": ("b.json", io.BytesIO(json.dumps([SPCC]).encode()), "application/json")
        },
        headers=admin.headers,
    )
    assert again.json()["loaded"] == 1
    gone = client.get("/api/materials/M-000999", headers=admin.headers)
    assert gone.status_code == 404


def test_카탈로그가_아닌_파일은_말해_준다(client: TestClient, admin: Signed) -> None:
    bad = client.post(
        "/api/materials/catalog",
        files={"file": ("x.json", io.BytesIO(b'{"hello": 1}'), "application/json")},
        headers=admin.headers,
    )
    assert bad.status_code == 400 and "내보내기" in bad.json()["error"]["message"]


def test_관리자만_올린다(client: TestClient, member: Signed) -> None:
    denied = client.post(
        "/api/materials/catalog",
        files={"file": ("x.json", io.BytesIO(b"[]"), "application/json")},
        headers=member.headers,
    )
    assert denied.status_code == 403
