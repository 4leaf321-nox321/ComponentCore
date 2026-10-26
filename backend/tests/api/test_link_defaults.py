"""CompCore 기본 기준정보 관계 꾸러미(`objects/link_defaults.py`) — 만들 수 있는 것만 만들고,
이미 있는 것(같은 slug · 같은 두 타입을 잇는 관계)은 건드리지 않는다.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.api.conftest import Signed


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201, 202), response.text
    return response.json()


def _status(client: TestClient, admin: Signed) -> dict[str, Any]:
    rows = _ok(client.get("/api/ontology/link-defaults", headers=admin.headers))
    return {one["slug"]: one for one in rows}


def _type(client: TestClient, admin: Signed, slug: str, label: str) -> None:
    _ok(
        client.post(
            "/api/ontology/types",
            json={"slug": slug, "label": label, "key_policy": "optional"},
            headers=admin.headers,
        )
    )


def test_출발_타입이_생긴_것만_만들고_다시_불러도_같다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    assert client.get("/api/ontology/link-defaults", headers=member.headers).status_code == 403
    before = _status(client, admin)
    assert {slug: one["status"] for slug, one in before.items()} == {
        "uses_part": "missing",
        "design_part": "missing",
        "verify_jig": "missing",
    }
    assert "SP 기준정보" in before["uses_part"]["note"]
    assert (before["uses_part"]["target_type"], before["verify_jig"]["target_type"]) == (
        "cc_part",
        "cc_jig",
    )
    nothing = _ok(client.post("/api/ontology/link-defaults", headers=admin.headers))
    assert (nothing["created"], nothing["snapshot_id"]) == ([], None)

    # SP 기준정보를 받아 기본 모델이 생겼다 — 그것에서 나가는 둘만 만든다.
    _type(client, admin, "base_model", "기본 모델")
    ready = _status(client, admin)
    assert [ready[slug]["status"] for slug in ("uses_part", "verify_jig", "design_part")] == [
        "ready",
        "ready",
        "missing",
    ]
    assert (
        client.post("/api/ontology/link-defaults", headers=member.headers).status_code == 403
    )
    made = _ok(client.post("/api/ontology/link-defaults", headers=admin.headers))
    assert made["created"] == ["uses_part", "verify_jig"] and made["snapshot_id"]
    relations = {
        one["slug"]: one
        for one in _ok(client.get("/api/ontology/relation-types", headers=admin.headers))
    }
    assert relations["uses_part"]["src_type_slugs"] == ["base_model"]
    assert relations["uses_part"]["dst_type_slugs"] == ["cc_part"]
    assert relations["verify_jig"]["inverse_label"] == "대상 모델"

    # 부품 · 지그 화면의 「기준정보」 칸이 선다.
    parts = _ok(client.get("/api/parts/ontology/kinds", headers=member.headers))
    jigs = _ok(client.get("/api/jigs/ontology/kinds", headers=member.headers))
    assert "적용 모델" in [one["label"] for one in parts]
    assert "대상 모델" in [one["label"] for one in jigs]

    again = _ok(client.post("/api/ontology/link-defaults", headers=admin.headers))
    assert again["created"] == []
    assert {one["slug"]: one["status"] for one in again["items"]}["uses_part"] == "exists"


def test_관리자가_고친_것과_다른_이름으로_만든_것은_그대로_둔다(
    client: TestClient, admin: Signed
) -> None:
    # 앞 시험이 기본 모델 · uses_part 를 만들어 두었다(파일 안의 시험끼리는 이어진다).
    _ok(
        client.patch(
            "/api/ontology/relation-types/uses_part",
            json={"inverse_label": "적용 제품"},
            headers=admin.headers,
        )
    )
    _type(client, admin, "part", "서비스 부품")
    _ok(
        client.post(
            "/api/ontology/relation-types",
            json={
                "slug": "svc_design",
                "label": "설계",
                "inverse_label": "서비스 품번",
                "src_type_slugs": ["part"],
                "dst_type_slugs": ["cc_part"],
            },
            headers=admin.headers,
        )
    )
    rows = _status(client, admin)
    assert rows["uses_part"]["status"] == "exists"
    assert "적용 제품" in rows["uses_part"]["note"]
    assert rows["design_part"]["status"] == "exists"
    assert "svc_design" in rows["design_part"]["note"]

    made = _ok(client.post("/api/ontology/link-defaults", headers=admin.headers))
    assert made["created"] == []
    relations = {
        one["slug"]: one
        for one in _ok(client.get("/api/ontology/relation-types", headers=admin.headers))
    }
    assert relations["uses_part"]["inverse_label"] == "적용 제품", (
        "고친 말이 되돌아가지 않는다"
    )
    assert "design_part" not in relations
