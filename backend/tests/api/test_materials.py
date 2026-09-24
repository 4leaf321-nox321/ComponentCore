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
    "owner_workspace_id": "99334981-ed64-45ff-a869-e2731a2972ee",
    "owner_workspace_name": "기본 부서",
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


def test_권한은_그쪽이_정한다_우리가_질의로_흉내_내지_않는다(
    client: TestClient, member: Signed, fake_matnexus: dict[str, Any]
) -> None:
    """**PAT 에 범위가 없고**(2026-09-24 재확인) 권한은 부서 소속으로 정해진다 — 무엇이
    보이나는 「이 토큰이 누구냐」 하나다.

    전에는 `scope=global` 을 박았다. 그 칸은 개편으로 **없어졌고**, MatNexus 는 모르는 질의를
    조용히 무시하므로 그 뒤로는 아무 필터도 아니었다. **살아 있는 척하는 이름을 다시 만들지
    않는다** — 그래서 이 시험은 그것이 안 나가는 것을 못 박는다."""
    got = client.get("/api/materials", params={"q": "SPCC"}, headers=member.headers)
    assert got.status_code == 200, got.text
    assert "scope" not in fake_matnexus["url"], "없어진 칸을 계속 보내면 안 된다"
    # 좁히지 않았으면 workspace 도 안 보낸다 — 그 계정이 보는 것을 그대로 본다.
    assert "workspace" not in fake_matnexus["url"]
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
    # **어느 부서 것인지**도 줄에 온다 — 두 부서에 같은 이름이 있을 수 있다.
    assert one["workspace"] == "기본 부서"


def test_부서를_정해_두면_그것만_묻는다(
    client: TestClient,
    member: Signed,
    fake_matnexus: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**권한이 아니라 좁히기다.** 토큰이 볼 수 있는 것보다 넓힐 수는 없다 — 부서가 여럿인
    계정으로 붙었는데 남의 부서 재료까지 쏟아질 때 쓴다."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "matnexus_workspace", "polymer")
    got = client.get("/api/materials", params={"q": "SPCC"}, headers=member.headers)
    assert got.status_code == 200, got.text
    assert "workspace=polymer" in fake_matnexus["url"]


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


def test_카탈로그는_통째로_갈아_끼운다(
    client: TestClient, admin: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """합치면 그쪽에서 지워진 재료가 사본에만 남고, 그것을 고르고 나서야 없다는 것을 안다.

    **사본 길만 본다** — 이 기계의 `.env` 에 MatNexus 가 붙어 있든 말든 같은 답이어야 한다.
    """
    monkeypatch.setattr(matnexus, "configured", lambda: False)
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
    assert gone.status_code == 404, gone.text


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


def test_무엇이_비었는지_이름을_댄다(
    client: TestClient, member: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**실제로 겪었다**(2026-09-24): 주소는 넣고 토큰만 비운 채 화면을 열었더니 「주소가
    없습니다」 라고 말했다 — 맞는 칸을 놔두고 엉뚱한 데를 보게 만든다."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "matnexus_base_url", "http://matnexus.test", raising=False)
    monkeypatch.setattr(settings, "matnexus_token", "", raising=False)

    got = client.get("/api/materials", headers=member.headers).json()
    assert got["fallback"] is True
    assert "MATNEXUS_TOKEN" in got["detail"]
    assert "MATNEXUS_BASE_URL" not in got["detail"], "채워 둔 칸을 탓하면 안 된다"

    monkeypatch.setattr(settings, "matnexus_base_url", "", raising=False)
    both = client.get("/api/materials", headers=member.headers).json()
    assert "MATNEXUS_BASE_URL" in both["detail"] and "MATNEXUS_TOKEN" in both["detail"]


def test_쪽과_갈래는_따로_묻는다_목록에서_뽑지_않는다(
    client: TestClient, member: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """탐색기의 첫 두 칸(쪽 · 갈래)은 **분류**에서 온다.

    검색 결과에서 뽑아 만들면 「앞 서른 줄에 있는 쪽」 만 보이고, 사람은 나머지가 없는 줄
    안다. 개수가 함께 오므로 빈 갈래를 눌러 보게 하지도 않는다."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json=[
                {"family": "Metal", "category": "Steel", "count": 110},
                {"family": "Polymer", "category": "EPDM", "count": 9},
            ],
        )

    monkeypatch.setattr(matnexus, "configured", lambda: True)
    monkeypatch.setattr(
        matnexus,
        "_client",
        lambda: httpx.Client(
            base_url="http://matnexus.test", transport=httpx.MockTransport(handler)
        ),
    )
    got = client.get("/api/materials/classifications", headers=member.headers)
    assert got.status_code == 200, got.text
    assert "/api/materials/classifications" in seen["url"]
    body = got.json()
    assert body["fallback"] is False
    assert body["items"][0] == {"family": "Metal", "category": "Steel", "count": 110}


def test_못_닿으면_사본에서_세어_준다(
    client: TestClient, member: Signed, admin: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """여기서 빈손을 주면 화면의 첫 칸이 비고, 사람은 재료가 하나도 없는 줄 안다 — 실은
    올려 둔 카탈로그에 있는데도."""
    upload = client.post(
        "/api/materials/catalog",
        files={
            "file": (
                "catalog.json",
                json.dumps([SPCC]).encode("utf-8"),
                "application/json",
            )
        },
        headers=admin.headers,
    )
    assert upload.status_code == 200, upload.text

    monkeypatch.setattr(matnexus, "configured", lambda: False)
    got = client.get("/api/materials/classifications", headers=member.headers)
    assert got.status_code == 200
    body = got.json()
    assert body["fallback"] is True and body["detail"]
    assert body["items"] == [{"family": "강판", "category": "냉연", "count": 1}]


#: 문헌 카탈로그가 주는 모양 — 등록 재료와 **다르다**(값이 `values[]` 에 한 줄씩).
EMC: dict[str, Any] = {
    "id": "8ec6d1a1-df90-41de-97b4-f7b73751bf4f",
    "name": "Epoxy Molding Compound (EMC)",
    "material_code": "PKG-EMC",
    "category": "composite",
    "subsystem": "packaging",
    "manufacturer": "Resonac Corporation",
    "material_class": "epoxy molding compound",
    "values": [
        {
            "property_key": "mechanical.youngs_modulus",
            "property_name": "영률",
            "value_num": 1.833e10,
            "unit": "Pa",
            "quality_tier": 1,
            "representative": True,
            "conditions": {"temperature_k": 298},
        },
        {
            "property_key": "physical.density",
            "property_name": "밀도",
            "value_num": 1990.0,
            "unit": "kg/m^3",
            "representative": True,
        },
        {
            "property_key": "chemical.outgassing_tml",
            "property_name": "아웃가싱 TML",
            "value_num": 0.008,
            "unit": "1",
            "representative": False,
        },
    ],
}


@pytest.fixture
def fake_catalog(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """가짜 문헌 카탈로그 — 목록에는 **값이 없고**, 상세에만 있다(진짜가 그렇다)."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.setdefault("urls", []).append(str(request.url))
        if request.url.path.endswith("/summary"):
            return httpx.Response(
                200,
                json={
                    "materials": 2663,
                    "subsystems": {"packaging": 116, "pcb": 182, "": 1835},
                    "categories": {"composite": 739, "metal": 320},
                },
            )
        if request.url.path.rstrip("/").endswith(str(EMC["id"])):
            return httpx.Response(200, json=EMC)
        목록 = {**EMC}
        목록.pop("values")
        return httpx.Response(200, json={"items": [목록], "total": 1})

    monkeypatch.setattr(matnexus, "configured", lambda: True)
    monkeypatch.setattr(
        matnexus,
        "_client",
        lambda: httpx.Client(
            base_url="http://matnexus.test", transport=httpx.MockTransport(handler)
        ),
    )
    yield seen


def test_문헌에서도_고를_수_있다_그리고_값은_고른_뒤에_온다(
    client: TestClient, member: Signed, fake_catalog: dict[str, Any]
) -> None:
    """**등록 재료와 다른 창고다.** 우리 조직이 등록한 것은 백 몇십 건이고 문헌은 2663건이라,
    고를 것이 훨씬 많다.

    목록에 값을 딸려 보내지 않는 까닭: 재료 하나에 값이 최대 786개(2.6 MB)다 — 2663건을
    값째로 끌면 한 번에 수십 MB 다."""
    목록 = client.get(
        "/api/materials",
        params={"source": "literature", "q": "EMC", "system": "mm_n_tonne"},
        headers=member.headers,
    )
    assert 목록.status_code == 200, 목록.text
    한줄 = 목록.json()["items"][0]
    assert 한줄["source"] == "literature"
    assert 한줄["name"] == "Epoxy Molding Compound (EMC)"
    # 문헌은 번호가 없는 것이 많아 **만든 곳**을 대신 보인다.
    assert 한줄["alias"] == "Resonac Corporation"
    assert 한줄["family"] == "packaging" and 한줄["category"] == "composite"
    assert not 한줄["payload"].get("values"), "목록에는 값이 안 온다"

    하나 = client.get(
        f"/api/materials/{EMC['id']}",
        params={"source": "literature", "system": "mm_n_tonne"},
        headers=member.headers,
    )
    assert 하나.status_code == 200, 하나.text
    got = 하나.json()
    # **대표값만 담는다** — 셋 중 둘이 representative 다.
    assert got["declared_count"] == 2
    푼것 = {one["key"]: one for one in got["converted"]["properties"]}
    assert 푼것["mechanical.youngs_modulus"]["points"][0]["value"] == pytest.approx(18330.0)
    assert 푼것["mechanical.youngs_modulus"]["unit"] == "MPa"
    assert 푼것["physical.density"]["points"][0]["value"] == pytest.approx(1.99e-09)
    # **조건과 등급이 값의 일부다** — 85°C 에서 잰 값을 상온 값으로 쓰면 틀린다.
    assert 푼것["mechanical.youngs_modulus"]["conditions"] == {"temperature_k": 298}
    assert 푼것["mechanical.youngs_modulus"]["tier"] == 1


def test_문헌_분류는_하위계와_갈래다(
    client: TestClient, member: Signed, fake_catalog: dict[str, Any]
) -> None:
    """등록 재료 쪽과 **같은 모양**으로 준다 — 화면이 칸 그리는 코드를 두 벌 안 쓰게."""
    got = client.get("/api/materials/catalog/classifications", headers=member.headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["total"] == 2663
    있는것 = {(one["family"], one["category"]): one["count"] for one in body["items"]}
    assert 있는것[("packaging", "")] == 116
    assert 있는것[("", "composite")] == 739
    # 이름 없는 하위계(1835건)는 칸에 안 올린다 — 누를 수 없는 줄이 된다.
    assert ("", "") not in 있는것


def test_문헌은_사본이_없으니_못_닿으면_빈손으로_말한다(
    client: TestClient, member: Signed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """등록 재료의 사본을 문헌인 척 내주면 **사람이 없는 것을 골랐다고 믿는다.**"""
    monkeypatch.setattr(matnexus, "configured", lambda: False)
    got = client.get("/api/materials", params={"source": "literature"}, headers=member.headers)
    assert got.status_code == 200
    assert got.json()["items"] == []
    assert got.json()["fallback"] is True
    assert "문헌 물성은 MatNexus 에만" in got.json()["detail"]
