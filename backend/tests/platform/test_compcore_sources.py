"""CompCore 의 부품 · 지그가 온톨로지의 **원 표**가 된다(ADR 0008 — `parts/system.py` ·
`jigs/system.py`).

SP 에서 받은 제품 같은 객체가 부품 **그 자체**를 가리키고, 부품 쪽 상세에서 그 선이 보이나 —
행을 복제하지 않으므로 부품 이름을 바꾸면 온톨로지도 따라오고, 지운 부품은 없는 것이 되나.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.jigs.models import Jig
from app.modules.parts.models import Part
from tests.platform.conftest import Signed
from tests.platform.test_ontology import _link, _make_object, _make_relation, _make_type


def _part(db: Session, owner: Signed, name: str) -> Part:
    user = db.scalar(select(User).where(User.email == owner.email))
    assert user is not None
    row = Part(name=name, owner_id=user.id, folder="시험/고정구")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_원_표_목록에_부품과_지그가_있다(client: TestClient, admin: Signed) -> None:
    got = client.get("/api/ontology/schema", headers=admin.headers)
    assert got.status_code == 200, got.text
    assert {one["key"] for one in got.json()["system_sources"]} >= {"part", "jig"}


def test_제품이_부품을_가리키면_부품_쪽에서도_보인다(
    client: TestClient, admin: Signed, member: Signed, db: Session
) -> None:
    parts = _make_type(
        client,
        admin,
        "cc_part",
        label="CompCore 부품",
        kind_class="system",
        system_source="part",
    )
    product = _make_type(client, admin, "product", label="제품", key_policy="optional")
    uses = _make_relation(
        client,
        admin,
        "uses_part",
        label="사용 부품",
        inverse_label="쓰는 제품",
        src_type_slugs=[product],
        dst_type_slugs=[parts],
    )
    bracket = _part(db, admin, f"브래킷-{uuid.uuid4().hex[:6]}")
    phone = _make_object(client, admin, product, label="스마트폰 A")

    made = _link(client, admin, product, phone["id"], uses, str(bracket.id))
    assert made.status_code == 201, made.text
    assert made.json()["object_label"] == bracket.name

    # 부품 쪽 상세 — 평범한 멤버도 본다(부품은 공용 공간이다).
    side = client.get(f"/api/objects/{parts}/{bracket.id}", headers=member.headers)
    assert side.status_code == 200, side.text
    body = side.json()
    assert body["object"]["label"] == bracket.name
    assert [(r["label"], r["object_label"]) for r in body["related"]] == [
        ("쓰는 제품", "스마트폰 A")
    ]

    # 이름은 원 표의 것이다 — 바꾸면 온톨로지도 그 이름을 본다.
    bracket.name = "브래킷 개정"
    db.commit()
    again = client.get(f"/api/objects/{product}/{phone['id']}", headers=member.headers).json()
    assert [r["object_label"] for r in again["related"]] == ["브래킷 개정"]

    # 지운 부품은 없는 것이다.
    bracket.deleted_at = datetime.now(UTC)
    db.commit()
    gone = client.get(f"/api/objects/{parts}/{bracket.id}", headers=member.headers)
    assert gone.status_code == 404, gone.text


def test_지그도_찾아서_고른다(client: TestClient, admin: Signed, db: Session) -> None:
    jigs = _make_type(
        client,
        admin,
        "cc_jig",
        label="CompCore 지그",
        kind_class="system",
        system_source="jig",
    )
    user = db.scalar(select(User).where(User.email == admin.email))
    assert user is not None
    marker = uuid.uuid4().hex[:6]
    row = Jig(name=f"굽힘 지그 {marker}", owner_id=user.id, folder="")
    db.add(row)
    db.commit()
    listed = client.get(f"/api/objects/{jigs}", params={"q": marker}, headers=admin.headers)
    assert listed.status_code == 200, listed.text
    assert [one["id"] for one in listed.json()["items"]] == [str(row.id)]
