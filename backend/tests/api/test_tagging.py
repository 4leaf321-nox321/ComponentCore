"""태그가 **온톨로지의 객체**다(ADR 0011) — 타입을 고르고 그 안에서 고르거나, 늘린다.

붙인 것은 선(`object_links`, `cc_tagged`)이고 이름은 따로 적지 않는다 — 객체 이름을 고치면
목록의 태그도 따라온다. 작업은 내 공간이라 남의 작업은 태그 객체 쪽에서도 안 보인다.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEntry
from app.modules.objects.models import ObjectInstance, ObjectLink
from app.modules.ontology.models import ObjectType
from app.modules.parts.models import Part
from app.modules.tagging.models import TAG_RELATION
from app.modules.works import system as works_system
from app.modules.workspaces.models import Workspace
from tests.api.conftest import Signed, make_user

BOX = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 40, "height": 30}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 10},
    ]
}


def _uniq(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:6]}"


def _work(client: TestClient, who: Signed, name: str = "브래킷") -> str:
    made = client.post(
        "/api/works", json={"name": name, "kind": "part", "recipe": BOX}, headers=who.headers
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _part(db: Session, owner: Signed, name: str) -> Part:
    from app.modules.accounts.models import User

    user = db.scalar(select(User).where(User.email == owner.email))
    assert user is not None
    row = Part(name=name, owner_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _tag(client: TestClient, who: Signed, target: str, row_id: Any, **body: Any) -> Any:
    return client.post(f"/api/tags/{target}/{row_id}", json=body, headers=who.headers)


def _type(client: TestClient, admin: Signed, label: str, **kw: Any) -> str:
    slug = _uniq("t")
    made = client.post(
        "/api/ontology/types",
        json={"slug": slug, "label": label, "kind_class": "reference", **kw},
        headers=admin.headers,
    )
    assert made.status_code == 201, made.text
    return slug


def _object(client: TestClient, admin: Signed, slug: str, label: str) -> str:
    made = client.post(f"/api/objects/{slug}", json={"label": label}, headers=admin.headers)
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _mode(client: TestClient, admin: Signed, slug: str, mode: str) -> Any:
    return client.put(f"/api/tags/settings/{slug}", json={"mode": mode}, headers=admin.headers)


def test_이름으로_붙이면_일반_태그가_자란다(
    client: TestClient, member: Signed, admin: Signed, db: Session
) -> None:
    """타입을 안 고르면 「일반 태그」 — 같은 이름은(대소문자 · 공백이 달라도) 같은 객체다. 남이
    단 같은 이름도 같은 객체다 — 그래야 태그가 묶음이 된다."""
    types = client.get("/api/tags/types", headers=member.headers)
    assert types.status_code == 200, types.text
    first = types.json()[0]
    assert (first["slug"], first["label"], first["is_default"]) == (
        "cc_tag",
        "일반 태그",
        True,
    )
    assert first["mode"] == "grow" and first["can_create"] is True

    word = _uniq("EMC")
    mine = _work(client, member)
    got = _tag(client, member, "work", mine, label=f"  {word}  ")
    assert got.status_code == 200, got.text
    assert [(one["label"], one["type_slug"]) for one in got.json()] == [(word, "cc_tag")]
    again = _tag(client, member, "work", mine, label=word.lower())
    assert [one["label"] for one in again.json()] == [word], "같은 이름은 한 번만 붙는다"

    theirs = _work(client, admin, "다른 사람의 판")
    other = _tag(client, admin, "work", theirs, label=word)
    assert other.json()[0]["object_id"] == got.json()[0]["object_id"]

    # 만든 객체는 **전역**이고, 누가 만들었는지 감사 기록에 남는다.
    row = db.get(ObjectInstance, uuid.UUID(got.json()[0]["object_id"]))
    assert row is not None and row.owner_workspace_id is None
    made = db.scalars(
        select(AuditEntry).where(
            AuditEntry.action == "object.create", AuditEntry.target_id == row.id
        )
    ).all()
    assert len(made) == 1 and made[0].reason == "태그로 만듦"

    # 고를 때는 많이 쓴 것부터.
    found = client.get(
        "/api/tags/types/cc_tag/objects", params={"q": word}, headers=member.headers
    ).json()
    assert [(one["label"], one["uses"]) for one in found] == [(word, 2)]


def test_고르기_타입은_있는_것만_늘리기_타입은_누구나(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    customers = _type(client, admin, "고객사")
    known = _object(client, admin, customers, "고객A")
    work = _work(client, member)

    # 태그로 안 쓰는 타입의 객체는 못 붙인다 — 관리자가 고른다.
    refused = _tag(client, member, "work", work, object_id=known)
    assert refused.status_code == 409 and "태그로 쓰는 타입이 아닙니다" in refused.text
    assert _mode(client, member, customers, "pick").status_code == 403
    assert _mode(client, admin, customers, "pick").status_code == 200

    picked = _tag(client, member, "work", work, object_id=known)
    assert picked.status_code == 200, picked.text
    assert [(one["label"], one["type_label"]) for one in picked.json()] == [
        ("고객A", "고객사")
    ]
    # 있는 이름은 고르기 타입에서도 이름으로 찾아진다 — 새로 만들지만 않는다.
    same = _tag(client, member, "work", work, type_slug=customers, label="고객a")
    assert same.status_code == 200 and len(same.json()) == 1
    fresh = _tag(client, member, "work", work, type_slug=customers, label="고객B")
    assert fresh.status_code == 409 and "고르기만 하는" in fresh.text

    # 늘리기로 바꾸면 붙이는 사람 누구나 만든다.
    assert _mode(client, admin, customers, "grow").status_code == 200
    grown = _tag(client, member, "work", work, type_slug=customers, label="고객B")
    assert grown.status_code == 200, grown.text
    assert [one["label"] for one in grown.json()] == ["고객A", "고객B"]
    listed = {
        one["slug"]: one
        for one in client.get("/api/tags/types", headers=member.headers).json()
    }
    assert listed[customers]["can_create"] is True

    # 입력 정책이 닫힌 타입은 「늘리기」 여도 관리자가 등록한 것만 — 까닭을 관리 화면이 본다.
    closed = _type(client, admin, "시험 규격", entry_policy="closed")
    assert _mode(client, admin, closed, "grow").status_code == 200
    rows = {
        one["slug"]: one
        for one in client.get("/api/tags/settings", headers=admin.headers).json()
    }
    assert rows[closed]["mode"] == "grow" and "입력 정책이 닫혀" in rows[closed]["note"]
    assert (
        _tag(client, member, "work", work, type_slug=closed, label="ISO 1").status_code == 409
    )

    # 「일반 태그」 는 끌 수 없다. 끈 타입의 태그는 붙은 채 남는다.
    assert _mode(client, admin, "cc_tag", "off").status_code == 409
    assert _mode(client, admin, customers, "off").status_code == 200
    kept = client.get(f"/api/tags/work/{work}", headers=member.headers).json()
    assert [one["label"] for one in kept] == ["고객A", "고객B"]


def test_부서_소유_객체는_태그가_아니다(
    client: TestClient, member: Signed, admin: Signed, db: Session
) -> None:
    """공용 부품의 태그가 보는 사람마다 다르면 안 된다 — 전역 객체만 붙는다."""
    teams = _type(client, admin, "팀 분류")
    assert _mode(client, admin, teams, "pick").status_code == 200
    place = Workspace(slug=_uniq("ws"), name="설계팀")
    db.add(place)
    db.flush()
    kind = db.scalar(select(ObjectType).where(ObjectType.slug == teams))
    assert kind is not None
    owned = ObjectInstance(type_id=kind.id, label="팀 전용", owner_workspace_id=place.id)
    db.add(owned)
    db.commit()
    got = _tag(client, admin, "work", _work(client, admin), object_id=str(owned.id))
    assert got.status_code == 404 and "부서 소유" in got.text


def test_남의_작업에는_못_붙이고_부품은_누구나_본다(
    client: TestClient, member: Signed, admin: Signed, db: Session
) -> None:
    theirs = _work(client, admin, "관리자의 판")
    assert client.get(f"/api/tags/work/{theirs}", headers=member.headers).status_code == 403
    assert _tag(client, member, "work", theirs, label="몰래").status_code == 403

    part = _part(db, admin, _uniq("공용 브래킷"))
    assert _tag(client, admin, "part", part.id, label="공용").status_code == 200
    seen = client.get(f"/api/tags/part/{part.id}", headers=member.headers)
    assert seen.status_code == 200 and [one["label"] for one in seen.json()] == ["공용"]
    assert _tag(client, member, "part", part.id, label="낙서").status_code == 403


def test_떼면_선만_없어지고_객체는_남는다(
    client: TestClient, member: Signed, db: Session
) -> None:
    work = _work(client, member)
    word = _uniq("떼기")
    tag = _tag(client, member, "work", work, label=word).json()[0]
    left = client.delete(f"/api/tags/work/{work}/{tag['object_id']}", headers=member.headers)
    assert left.status_code == 200 and left.json() == []
    assert db.get(ObjectInstance, uuid.UUID(tag["object_id"])) is not None
    gone = client.delete(f"/api/tags/work/{work}/{tag['object_id']}", headers=member.headers)
    assert gone.status_code == 404


def test_이름은_객체에서_온다_목록_거르개_찾기(
    client: TestClient, member: Signed, admin: Signed, db: Session
) -> None:
    """정본은 선 하나 — 객체 이름을 고치면 부품 목록의 태그 · 거르개 · 찾기가 다 따라온다."""
    word = _uniq("옛이름")
    part = _part(db, admin, _uniq("받침"))
    tag = _tag(client, admin, "part", part.id, label=word).json()[0]
    renamed = client.patch(
        f"/api/objects/cc_tag/{tag['object_id']}",
        json={"label": f"{word}-새"},
        headers=admin.headers,
    )
    assert renamed.status_code == 200, renamed.text

    got = client.get(f"/api/parts/{part.id}", headers=member.headers).json()
    assert got["tags"] == [f"{word}-새"]
    tagged = client.get("/api/parts", params={"tag": f"{word}-새"}, headers=member.headers)
    assert [one["id"] for one in tagged.json()["items"]] == [str(part.id)]
    found = client.get("/api/parts", params={"q": f"{word}-새"}, headers=member.headers)
    assert [one["id"] for one in found.json()["items"]] == [str(part.id)]
    assert f"{word}-새" in client.get("/api/parts/tags", headers=member.headers).json()


def test_태그_객체에서_내_작업은_보이고_남의_작업은_안_보인다(
    client: TestClient, member: Signed, db: Session
) -> None:
    """온톨로지 쪽에서 태그를 열면 무엇에 붙었는지 보인다 — 작업은 주인에게만. 선의 감사
    기록에도 작업 이름을 안 남긴다(태그 객체의 이력 · 알림으로 나간다)."""
    word = _uniq("공유태그")
    mine = _work(client, member, "내 비밀 판")
    tag = _tag(client, member, "work", mine, label=word).json()[0]
    stranger = make_user(db, label="stranger", is_system_admin=False)
    from tests.api.conftest import _login

    other = Signed(email=stranger.email, token=_login(client, stranger.email))
    theirs = _work(client, other, "남의 비밀 판")
    assert _tag(client, other, "work", theirs, label=word).status_code == 200

    def related(who: Signed) -> list[str]:
        got = client.get(f"/api/objects/cc_tag/{tag['object_id']}", headers=who.headers)
        assert got.status_code == 200, got.text
        return sorted(one["object_label"] for one in got.json()["related"])

    assert related(member) == ["내 비밀 판"]
    assert related(other) == ["남의 비밀 판"]

    link = db.scalar(
        select(ObjectLink).where(
            ObjectLink.src_id == uuid.UUID(mine), ObjectLink.relation == TAG_RELATION
        )
    )
    assert link is not None and link.src_type == "cc_work"
    entry = db.scalar(select(AuditEntry).where(AuditEntry.target_id == link.id))
    assert entry is not None and "비밀" not in entry.target_label

    # 요청 밖(작업 · 스크립트)에서 원 표를 읽으면 작업은 하나도 안 나온다.
    assert works_system.SYSTEM_SOURCE.lookup(db, [uuid.UUID(mine)]) == {}


def test_기준정보_칸에는_태그_줄이_없다(
    client: TestClient, admin: Signed, db: Session
) -> None:
    """태그는 제 자리가 있다 — 부품 화면의 「기준정보」 에 「태그」 줄로 또 서면 두 군데서
    고친다."""
    part = _part(db, admin, _uniq("판"))
    assert _tag(client, admin, "part", part.id, label="겹침").status_code == 200
    card = client.get(f"/api/parts/{part.id}/ontology", headers=admin.headers)
    assert card.status_code == 200, card.text
    assert TAG_RELATION not in {one["relation"] for one in card.json()["rows"]}


def test_승격과_복제가_타입을_고른_태그도_물려준다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    customers = _type(client, admin, "고객")
    assert _mode(client, admin, customers, "grow").status_code == 200
    work = _work(client, member, _uniq("센서 판"))
    _tag(client, member, "work", work, type_slug=customers, label="고객Z")
    _tag(client, member, "work", work, label="EMC")

    copy = client.post(f"/api/works/{work}/duplicate", headers=member.headers)
    assert copy.status_code == 201, copy.text
    tags = client.get(f"/api/tags/work/{copy.json()['id']}", headers=member.headers).json()
    assert [(one["label"], one["type_slug"]) for one in tags] == [
        ("고객Z", customers),
        ("EMC", "cc_tag"),
    ]

    promoted = client.post(f"/api/works/{work}/promote/part", json={}, headers=member.headers)
    assert promoted.status_code in (200, 201), promoted.text
    part_id = promoted.json()["part_id"]
    got = client.get(f"/api/tags/part/{part_id}", headers=member.headers).json()
    assert [one["label"] for one in got] == ["고객Z", "EMC"]

    # 글자 목록으로 통째로 바꿔도(옛 길) 이름이 남는 태그는 타입째 산다.
    patched = client.patch(
        f"/api/works/{work}", json={"tags": ["고객Z", "새것"]}, headers=member.headers
    )
    assert patched.status_code == 200 and patched.json()["tags"] == ["고객Z", "새것"]
    after = client.get(f"/api/tags/work/{work}", headers=member.headers).json()
    assert [(one["label"], one["type_slug"]) for one in after] == [
        ("고객Z", customers),
        ("새것", "cc_tag"),
    ]


def test_타입별_거르개는_이름이_같아도_객체로_가린다(
    client: TestClient, member: Signed, admin: Signed, db: Session
) -> None:
    """고객사 「A」 와 프로젝트 「A」 는 다른 태그다 — 이름 거르개(`tag`)는 둘 다, 객체
    거르개(`tag_id`)는 고른 것만 건다."""
    customers = _type(client, admin, "고객사")
    projects = _type(client, admin, "프로젝트")
    for slug in (customers, projects):
        assert _mode(client, admin, slug, "grow").status_code == 200
    word = _uniq("A")
    first = _work(client, member, "고객 판")
    second = _work(client, member, "과제 판")
    tagged = _tag(client, member, "work", first, type_slug=customers, label=word).json()
    _tag(client, member, "work", second, type_slug=projects, label=word)
    customer_a = tagged[0]["object_id"]

    by_name = client.get("/api/works", params={"tag": word}, headers=member.headers).json()
    assert {one["id"] for one in by_name["items"]} == {first, second}
    by_object = client.get(
        "/api/works", params={"tag_id": customer_a}, headers=member.headers
    ).json()
    assert [one["id"] for one in by_object["items"]] == [first]

    # 거르개의 칩 — 쓰인 태그 객체를 타입별로(「일반 태그」 가 먼저, 그다음 타입 이름 순).
    used = client.get("/api/tags/used/work", headers=member.headers)
    assert used.status_code == 200, used.text
    mine = [(one["type_slug"], one["label"], one["uses"]) for one in used.json()]
    assert (customers, word, 1) in mine and (projects, word, 1) in mine
    # 남의 작업 태그는 관리자만.
    assert (
        client.get("/api/tags/used/work", params={"owner": "all"}, headers=member.headers)
    ).status_code == 403
    every = client.get("/api/tags/used/work", params={"owner": "all"}, headers=admin.headers)
    assert every.status_code == 200 and customer_a in {
        one["object_id"] for one in every.json()
    }

    # 부품 · 지그도 같은 거르개 — 공용 카탈로그 전부를 센다.
    part = _part(db, admin, _uniq("공용 판"))
    _tag(client, admin, "part", part.id, object_id=customer_a)
    parts = client.get("/api/parts", params={"tag_id": customer_a}, headers=member.headers)
    assert [one["id"] for one in parts.json()["items"]] == [str(part.id)]
    assert customer_a in {
        one["object_id"]
        for one in client.get("/api/tags/used/part", headers=member.headers).json()
    }

    # DOE — 대상 작업의 태그로.
    study = client.post(
        "/api/doe",
        json={"name": _uniq("고객 판 DOE"), "recipe": BOX, "work_id": first},
        headers=member.headers,
    )
    assert study.status_code == 201, study.text
    studies = client.get(
        "/api/doe", params={"tag_id": customer_a, "scope": "mine"}, headers=member.headers
    ).json()
    assert [one["id"] for one in studies["items"]] == [study.json()["id"]]
    objects = client.get("/api/doe/tag-objects", headers=member.headers).json()
    assert customer_a in {one["object_id"] for one in objects}
