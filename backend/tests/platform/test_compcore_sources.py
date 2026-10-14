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
from app.modules.workspaces.models import Workspace
from tests.platform.conftest import Signed, _login, _make_user
from tests.platform.test_ontology import _link, _make_object, _make_relation, _make_type


def _user_id(db: Session, who: Signed) -> uuid.UUID:
    user = db.scalar(select(User).where(User.email == who.email))
    assert user is not None
    return user.id


def _part(db: Session, owner: Signed, name: str) -> Part:
    row = Part(name=name, owner_id=_user_id(db, owner), folder="시험/고정구")
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


def _world(client: TestClient, admin: Signed) -> dict[str, str]:
    """CompCore 부품(원 표) · 받은 기본 모델 · 분류 — 「사용 부품」(기본 모델 → 부품, 여럿)과
    「분류」(부품 → 분류, 하나)."""
    parts = _make_type(
        client,
        admin,
        "cc_part",
        label="CompCore 부품",
        kind_class="system",
        system_source="part",
    )
    model = _make_type(client, admin, "model", label="기본 모델", key_policy="optional")
    klass = _make_type(client, admin, "klass", label="부품 분류", key_policy="optional")
    uses = _make_relation(
        client,
        admin,
        "uses_part",
        label="사용 부품",
        inverse_label="적용 모델",
        src_type_slugs=[model],
        dst_type_slugs=[parts],
    )
    classed = _make_relation(
        client,
        admin,
        "classed_as",
        label="분류",
        inverse_label="분류된 부품",
        cardinality="many_to_one",
        src_type_slugs=[parts],
        dst_type_slugs=[klass],
    )
    return {"parts": parts, "model": model, "klass": klass, "uses": uses, "classed": classed}


def test_부품_화면의_칸은_관계마다_서고_주인이_잇고_끊는다(
    client: TestClient, admin: Signed, member: Signed, db: Session, workspace: Workspace
) -> None:
    w = _world(client, admin)
    p5 = _make_object(client, admin, w["model"], label="P5 플립")
    _make_object(client, admin, w["model"], label="N10")
    hinge = _make_object(client, admin, w["klass"], label="힌지")
    bracket = _part(db, member, f"P5 플립 힌지 브래킷 {uuid.uuid4().hex[:4]}")

    got = client.get(f"/api/parts/{bracket.id}/ontology", headers=member.headers)
    assert got.status_code == 200, got.text
    rows = {one["relation"]: one for one in got.json()["rows"]}
    # 부품 쪽에서 본 말로 선다 — 기본 모델 → 부품 이면 「적용 모델」.
    assert rows[w["uses"]]["label"] == "적용 모델" and rows[w["uses"]]["incoming"] is True
    assert rows[w["uses"]]["single"] is False
    assert rows[w["classed"]]["label"] == "분류" and rows[w["classed"]]["single"] is True
    # 이름의 낱말로 추천한다 — 「P5 플립」 은 들고 「N10」 은 안 든다.
    suggested = [one["label"] for one in rows[w["uses"]]["suggestions"]]
    assert suggested == ["P5 플립"]
    assert [one["label"] for one in rows[w["classed"]]["suggestions"]] == ["힌지"]

    # **부품 주인이 잇는다** — 기본 모델이 든 부서의 관리자가 아니어도.
    linked = client.post(
        f"/api/parts/{bracket.id}/ontology/links",
        json={"relation": w["uses"], "object_id": p5["id"]},
        headers=member.headers,
    )
    assert linked.status_code == 200, linked.text
    rows = {one["relation"]: one for one in linked.json()["rows"]}
    assert [one["label"] for one in rows[w["uses"]]["items"]] == ["P5 플립"]
    assert rows[w["uses"]]["suggestions"] == []  # 이미 건 것은 다시 추천하지 않는다

    # 방향은 관계 정의대로 — 기본 모델 쪽 상세에서 「사용 부품」 으로 보인다.
    side = client.get(f"/api/objects/{w['model']}/{p5['id']}", headers=admin.headers).json()
    assert [(r["label"], r["object_label"]) for r in side["related"]] == [
        ("사용 부품", bracket.name)
    ]

    # 「하나만」 칸 — 하나를 걸면 더는 추천하지 않고, 둘째는 개수 제약이 막는다.
    one = client.post(
        f"/api/parts/{bracket.id}/ontology/links",
        json={"relation": w["classed"], "object_id": hinge["id"]},
        headers=member.headers,
    )
    assert one.status_code == 200, one.text
    rows = {r["relation"]: r for r in one.json()["rows"]}
    assert rows[w["classed"]]["suggestions"] == []
    other = _make_object(client, admin, w["klass"], label="브래킷")
    twice = client.post(
        f"/api/parts/{bracket.id}/ontology/links",
        json={"relation": w["classed"], "object_id": other["id"]},
        headers=member.headers,
    )
    assert twice.status_code == 409, twice.text

    # 남의 부품은 못 잇고 못 끊는다.
    stranger = _make_user(
        db, workspace, label="stranger", is_system_admin=False, role="member"
    )
    headers = {"Authorization": f"Bearer {_login(client, stranger.email)}"}
    denied = client.post(
        f"/api/parts/{bracket.id}/ontology/links",
        json={"relation": w["uses"], "object_id": p5["id"]},
        headers=headers,
    )
    assert denied.status_code == 403, denied.text
    link_id = rows[w["uses"]]["items"][0]["link_id"]
    assert (
        client.delete(
            f"/api/parts/{bracket.id}/ontology/links/{link_id}", headers=headers
        ).status_code
        == 403
    )

    # 주인이 끊으면 양쪽에서 사라진다.
    cut = client.delete(
        f"/api/parts/{bracket.id}/ontology/links/{link_id}", headers=member.headers
    )
    assert cut.status_code == 200, cut.text
    rows = {r["relation"]: r for r in cut.json()["rows"]}
    assert rows[w["uses"]]["items"] == []
    side = client.get(f"/api/objects/{w['model']}/{p5['id']}", headers=admin.headers).json()
    assert side["related"] == []
