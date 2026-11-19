"""코어 구독 — **SP 허브의 코어를 통째로**, 토큰은 한 번만(SP ADR 0085 를 들인다, 2026-11-19).

가짜 허브를 httpx 에 끼워 소켓 없이 본다. 허브는 SP 의 응답 모양을 그대로 흉내 낸다 — 카탈로그
(`/core`), 공개 타입의 정의(`/core/sp-definitions` — 지문 `mark` · `known` · 칸이 생긴 때
`added`), 행(`/core/<타입>`), 선(`/core/<타입>/relations`). 허브의 정의에는 **SP 에만 있는 칸**
(개정 칸 · 자료 범위 · 관계의 유효 기간 · 수량 칸 · 계보)이 실제처럼 실린다 — CompCore 의
가져오기는 그것을 모르는 항목으로 거절하므로 구독이 낮춰 세워야 한다.

지키는 것:

- 구독 하나가 정의를 세우고, 공개 타입마다 소스를 만들고, 행 · 선을 끝까지 받는다(정의 묶음
  파일을 따로 받지 않는다). SP 에만 있는 칸은 빼고 세운다 — 값이 있던 것은 알린다.
- 허브에 공개 타입 · 칸이 늘면 **다음 확인이** 정의를 세우고 소스 · 칸 대응을 맞추고 새 칸의
  값을 받는다 — 토큰을 다시 넣지 않는다.
- 저장값을 잃을 수 있는 변경(고를 값 빼기)은 정의 검토 대기로 남기고, 같은 때의 안전한
  변경(새 칸)은 들어간다. 검토한 지문으로 적용하면 들어간다.
- 공개를 해제한 타입은 수신만 멈추고 받은 자료는 남는다 — 다시 공개되면 이어 받는다.
- 이 설치가 만든 같은 이름의 타입은 건드리지 않는다.
- 토큰은 구독 한 곳에서 바뀐다. 구독의 소스는 소스 따로의 차례로 돌지 않는다.
- 정의 창구가 없는 허브(SP 0.4.90 까지)에서는 이 설치에 정의가 있는 타입만 받는다.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.modules.datasources import services, subscriptions
from app.modules.datasources.models import CoreSubscription, DataSource
from app.modules.objects.models import ObjectInstance, ObjectRelation
from app.modules.ontology import managed
from app.modules.ontology.models import ObjectType, PropertyDef
from app.modules.tasks import services as job_services
from tests.platform.conftest import Signed, bundle_import, finish_job, maintenance_counts

AT = "2026-11-19T00:00:00.000000Z"
LATER = "2026-11-19T06:00:00.000000Z"
EARLIER = "2026-01-01T00:00:00.000000Z"


class FakeHub:
    """SP 허브의 코어 창구 흉내 — 공개 여부 · 정의 · 행 · 선을 시험이 바꾼다."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.base = f"http://hub-{tag}.local/api"
        self.token = "Bearer hub-token"
        self.system = "허브 SP"
        #: 참이면 SP 0.4.90 까지처럼 정의 창구가 없다(그 주소를 타입으로 읽어 404).
        self.no_definitions = False
        #: slug → {def: 정의, published: bool, items: [행], added: {칸: 생긴 때}, edges: [선]}
        self.types: dict[str, dict[str, Any]] = {}
        self.kinds: list[dict[str, Any]] = []
        self.as_of = AT
        self.requests: list[httpx.Request] = []

    # --- 시험이 허브를 꾸민다 ---------------------------------------------------

    def slug(self, name: str) -> str:
        return f"sp{self.tag}_{name}"

    def add_type(
        self,
        name: str,
        label: str,
        properties: list[dict[str, Any]],
        *,
        extra: dict[str, Any] | None = None,
        added: str = EARLIER,
    ) -> str:
        slug = self.slug(name)
        definition = {
            "slug": slug,
            "label": label,
            "key_policy": "required",
            "core": True,
            "properties": properties,
            # **SP 의 `importer.capture` 는 이 칸들을 늘 싣는다** — 비어 있어도.
            "revision_key": "",
            "scope": "",
            **(extra or {}),
        }
        self.types[slug] = {
            "def": definition,
            "published": True,
            "items": [],
            "added": {str(one["key"]): added for one in properties},
            "edges": [],
        }
        return slug

    def add_property(self, slug: str, prop: dict[str, Any], *, added: str) -> None:
        self.types[slug]["def"]["properties"].append(prop)
        self.types[slug]["added"][str(prop["key"])] = added

    def add_kind(self, name: str, src: str, dst: str, **extra: Any) -> str:
        slug = self.slug(name)
        self.kinds.append(
            {
                "slug": slug,
                "label": "사용",
                "src_type_slugs": [src],
                "dst_type_slugs": [dst],
                "directed": True,
                "cardinality": "many_to_many",
                "effectivity": False,
                "quantity_key": "",
                "lineage_source": "",
                **extra,
            }
        )
        return slug

    def item(self, slug: str, key: str, label: str, at: str = AT, **props: Any) -> None:
        rows = self.types[slug]["items"]
        rows[:] = [one for one in rows if one["key"] != key]
        rows.append(
            {
                "key": key,
                "label": label,
                "status": "active",
                "updated_at": at,
                "deleted": False,
                "properties": props,
            }
        )

    def edge(self, src_type: str, src: str, kind: str, dst_type: str, dst: str) -> None:
        self.types[src_type]["edges"].append(
            {
                "src": src,
                "relation": kind,
                "dst": dst,
                "dst_type": dst_type,
                "updated_at": AT,
                "deleted": False,
            }
        )

    # --- 창구 ------------------------------------------------------------------

    def _published(self) -> dict[str, dict[str, Any]]:
        return {slug: one for slug, one in self.types.items() if one["published"]}

    def _ontology(self) -> dict[str, Any]:
        published = self._published()
        return {
            "groups": [],
            "interfaces": [],
            "types": [copy.deepcopy(one["def"]) for one in published.values()],
            "relation_types": [
                copy.deepcopy(kind)
                for kind in self.kinds
                if set(kind["src_type_slugs"]) | set(kind["dst_type_slugs"]) <= set(published)
            ],
        }

    def mark(self) -> str:
        text = json.dumps(self._ontology(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("Authorization") != self.token:
            return httpx.Response(401, json={"error": {"message": "범위가 없습니다"}})
        path = request.url.path
        query = parse_qs(request.url.query.decode())
        if path.endswith("/core"):
            return httpx.Response(200, json=self._catalog())
        if path.endswith("/core/sp-definitions"):
            if self.no_definitions:
                return httpx.Response(
                    404,
                    json={
                        "error": {
                            "code": "APP-CORE-0001",
                            "message": "열려 있는 코어 타입이 아닙니다",
                        }
                    },
                )
            mark = self.mark()
            changed = query.get("known", [""])[0] != mark
            added = {
                f"{slug}.{key}": when
                for slug, one in self._published().items()
                for key, when in one["added"].items()
            }
            return httpx.Response(
                200,
                json={
                    "system": self.system,
                    "mark": mark,
                    "changed": changed,
                    "ontology": self._ontology() if changed else None,
                    "added": added,
                    "outside": [],
                    "groups": [],
                },
            )
        for slug, one in self._published().items():
            if path.endswith(f"/core/{slug}/relations"):
                return self._page(slug, one["edges"], query)
            if path.endswith(f"/core/{slug}"):
                return self._page(slug, one["items"], query)
        return httpx.Response(
            404, json={"error": {"code": "APP-CORE-0001", "message": "안 연 타입"}}
        )

    def _catalog(self) -> dict[str, Any]:
        types = []
        for slug, one in self._published().items():
            kinds = [k["slug"] for k in self.kinds if slug in k["src_type_slugs"]]
            types.append(
                {
                    "slug": slug,
                    "label": one["def"]["label"],
                    "count": len(one["items"]),
                    "updated_at": self.as_of,
                    "endpoint": f"{self.base}/core/{slug}",
                    "relations_endpoint": f"{self.base}/core/{slug}/relations"
                    if kinds
                    else None,
                    "relations": kinds,
                    "properties": [
                        {
                            "key": p["key"],
                            "label": p["label"],
                            "data_type": p["data_type"],
                            "enum_options": p.get("enum_options") or [],
                        }
                        for p in one["def"]["properties"]
                        if p["data_type"] not in ("file", "document")
                    ],
                }
            )
        return {
            "system": self.system,
            "revision": "3-0000000001",
            "as_of": self.as_of,
            "types": types,
        }

    def _page(
        self, slug: str, rows: list[dict[str, Any]], query: dict[str, list[str]]
    ) -> httpx.Response:
        since = query.get("since", [""])[0]
        picked = [one for one in rows if not since or one["updated_at"] > since]
        if not since:
            picked = [one for one in picked if not one.get("deleted")]
        limit = int(query.get("limit", ["500"])[0])
        start = int(query.get("cursor", ["0"])[0] or 0)
        more = start + limit < len(picked)
        return httpx.Response(
            200,
            json={
                "type_slug": slug,
                "since": since or None,
                "as_of": None if more else self.as_of,
                "next": str(start + limit) if more else None,
                "items": picked[start : start + limit],
            },
        )


@pytest.fixture
def hub() -> Iterator[FakeHub]:
    fake = FakeHub(uuid.uuid4().hex[:6])
    services.transport = httpx.MockTransport(fake)
    try:
        yield fake
    finally:
        services.transport = None


def _world(hub: FakeHub) -> tuple[str, str, str]:
    """부품 · 공급사 두 타입과 「부품 → 공급사」 관계 — 행 둘, 선 하나."""
    vendor = hub.add_type(
        "vendor", "공급사", [{"key": "country", "label": "국가", "data_type": "text"}]
    )
    part = hub.add_type(
        "part",
        "부품",
        [
            {"key": "material", "label": "재질", "data_type": "text"},
            {
                "key": "grade",
                "label": "등급",
                "data_type": "enum",
                "enum_options": ["A", "B", "C"],
            },
        ],
    )
    kind = hub.add_kind("supplied", part, vendor)
    hub.item(vendor, "V-1", "한빛정밀", country="한국")
    hub.item(part, "P-1", "브래킷", material="SUS304", grade="A")
    hub.item(part, "P-2", "커버", material="AL6061", grade="B")
    hub.edge(part, "P-1", kind, vendor, "V-1")
    return part, vendor, kind


def _create(
    client: TestClient, admin: Signed, hub: FakeHub, *, apply: bool, secret: str = "hub-token"
) -> Any:
    return client.post(
        "/api/datasources/core-subscriptions",
        json={
            "base_url": hub.base,
            "auth_kind": "bearer",
            "auth_secret": secret,
            "source_name": f"hub{hub.tag}",
            "interval_minutes": 60,
            "apply": apply,
        },
        headers=admin.headers,
    )


def _subscribe(client: TestClient, admin: Signed, hub: FakeHub) -> tuple[str, dict[str, Any]]:
    """만들고 첫 동기화 작업을 끝까지 — (구독 id, 작업 결과)."""
    made = _create(client, admin, hub, apply=True)
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["applied"] is True and body["job_id"], body
    done = finish_job(client, admin, {"id": body["job_id"]})
    assert done["status"] == "done", done
    return str(body["subscription"]["id"]), dict(done["result"])


def _check(client: TestClient, admin: Signed, sub_id: str) -> dict[str, Any]:
    started = client.post(
        f"/api/datasources/core-subscriptions/{sub_id}/sync", headers=admin.headers
    )
    assert started.status_code == 202, started.text
    done = finish_job(client, admin, started.json())
    assert done["status"] == "done", done
    return dict(done["result"])


def _row(client: TestClient, admin: Signed, sub_id: str) -> dict[str, Any]:
    got = client.get("/api/datasources/core-subscriptions", headers=admin.headers)
    assert got.status_code == 200, got.text
    return next(one for one in got.json() if one["id"] == sub_id)


def _objects(slug: str) -> dict[str, dict[str, Any]]:
    with SessionLocal() as db:
        type_id = db.scalar(select(ObjectType.id).where(ObjectType.slug == slug))
        return {
            str(one.key): {"label": one.label, **(one.properties or {}), "_status": one.status}
            for one in db.scalars(
                select(ObjectInstance).where(
                    ObjectInstance.type_id == type_id, ObjectInstance.deleted_at.is_(None)
                )
            )
        }


def _edges(kind: str) -> int:
    with SessionLocal() as db:
        return int(
            db.scalar(
                select(func.count())
                .select_from(ObjectRelation)
                .where(ObjectRelation.relation == kind)
            )
            or 0
        )


def _props(slug: str) -> dict[str, PropertyDef]:
    from app.modules.objects.services import properties_of

    with SessionLocal() as db:
        type_id = db.scalar(select(ObjectType.id).where(ObjectType.slug == slug))
        assert type_id is not None, f"{slug} 정의가 없다"
        return {one.key: one for one in properties_of(db, type_id)}


def _source_of(slug: str) -> DataSource:
    with SessionLocal() as db:
        found = db.scalar(
            select(DataSource).where(
                DataSource.kind == "sp_core", DataSource.entity_set == slug
            )
        )
        assert found is not None, slug
        db.expunge(found)
        return found


def test_구독은_정의를_세우고_공개_타입마다_소스를_만들어_행과_선을_받는다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    part, vendor, kind = _world(hub)
    preview = _create(client, admin, hub, apply=False)
    assert preview.status_code == 200, preview.text
    plan = preview.json()
    assert plan["applied"] is False and plan["definitions"] is True
    assert {one["type_slug"]: one["action"] for one in plan["types"]} == {
        vendor: "define",
        part: "define",
    }
    assert plan["held"] == []
    with SessionLocal() as db:
        assert db.scalar(select(ObjectType).where(ObjectType.slug == part)) is None, (
            "미리 보기는 아무것도 남기지 않는다"
        )

    sub_id, result = _subscribe(client, admin, hub)
    assert result["definitions_applied"] > 0 and sorted(result["created"]) == sorted(
        [f"{part}_core"[:32], f"{vendor}_core"[:32]]
    )
    assert result["failed"] == 0, result
    # 정의 — 허브의 관리 이름으로, 칸 · 고를 값 그대로.
    with SessionLocal() as db:
        made = db.scalar(select(ObjectType).where(ObjectType.slug == part))
        assert made is not None and managed.owner_of(made) == f"hub{hub.tag}"
    assert _props(part)["grade"].enum_options == ["A", "B", "C"]
    # 행 · 선.
    assert _objects(part)["P-1"]["material"] == "SUS304"
    assert sorted(_objects(part)) == ["P-1", "P-2"]
    assert _objects(vendor)["V-1"]["country"] == "한국"
    assert _edges(kind) == 1
    row = _row(client, admin, sub_id)
    assert row["last_status"] == "ok" and row["has_secret"] is True
    assert {one["type_slug"] for one in row["sources"]} == {part, vendor}
    assert all(one["last_success_at"] for one in row["sources"])
    # 소스 목록에도 구독이 보인다 — 토큰 · 간격 · 칸 대응을 구독이 맞춘다.
    listed = client.get("/api/datasources", headers=admin.headers).json()
    mine = [one for one in listed if one["entity_set"] in (part, vendor)]
    assert len(mine) == 2 and all(one["subscription_id"] == sub_id for one in mine)
    # 같은 허브를 또 구독하지 않는다.
    again = _create(client, admin, hub, apply=False)
    assert again.status_code == 409, again.text


def test_SP_에만_있는_칸은_빼고_세우고_값이_있던_것은_알린다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    """CompCore 의 가져오기는 모르는 칸이 하나라도 있으면 정의 전체를 거절한다 — 낮추지 않으면
    첫 확인에서 아무것도 못 받는다."""
    part = hub.add_type(
        "doc",
        "도면",
        [
            {"key": "rev", "label": "판", "data_type": "text"},
            {"key": "manual", "label": "설명서", "data_type": "document"},
        ],
        extra={"revision_key": "rev", "scope": "국내", "label_prefix": "properties.rev"},
    )
    kind = hub.add_kind(
        "derived", part, part, effectivity=True, lineage_source="src", quantity_key=""
    )
    hub.item(part, "D-1", "브래킷 도면", rev="C")
    hub.item(part, "D-2", "커버 도면", rev="A")
    hub.edge(part, "D-2", kind, part, "D-1")

    sub_id, result = _subscribe(client, admin, hub)
    assert result["failed"] == 0, result
    assert _objects(part)["D-1"]["rev"] == "C", "값은 그대로 받는다"
    assert set(_props(part)) == {"rev"}, "모르는 자료형(document)의 칸은 세우지 않는다"
    assert _edges(kind) == 1, "유효 기간이 있는 관계도 오늘 유효한 선은 받는다"
    notes = " ".join(_row(client, admin, sub_id)["notes"])
    assert "revision_key='rev'" in notes and "scope='국내'" in notes
    assert "effectivity=True" in notes and "lineage_source='src'" in notes
    assert "document" in notes
    assert "quantity_key" not in notes, "비어 있던 칸은 말없이 뺀다"


def test_허브에_공개_타입과_칸이_늘면_다음_확인이_정의와_소스와_값을_맞춘다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    part, _, _ = _world(hub)
    sub_id, _ = _subscribe(client, admin, hub)
    asked = len(hub.requests)

    # 허브 — 칸 하나(받은 뒤에 생겼다), 공개 타입 하나.
    hub.add_property(
        part, {"key": "weight", "label": "무게", "data_type": "number"}, added=LATER
    )
    hub.item(part, "P-1", "브래킷", LATER, material="SUS304", grade="A", weight=12.5)
    plant = hub.add_type(
        "plant", "공장", [{"key": "city", "label": "도시", "data_type": "text"}]
    )
    hub.item(plant, "F-1", "창원 공장", LATER, city="창원")
    hub.as_of = LATER

    result = _check(client, admin, sub_id)
    assert result["failed"] == 0, result
    assert result["created"] == [f"{plant}_core"[:32]]
    assert result["restarted"] == [], "칸이 받은 뒤에 생겼으면 처음부터 다시 받지 않는다"
    assert "weight" in _props(part)
    assert _objects(part)["P-1"]["weight"] == 12.5, "새 칸의 값이 빠지지 않는다"
    assert _objects(plant)["F-1"]["city"] == "창원"
    mapping = _source_of(part).mapping or {}
    assert {"source": "weight", "target": "properties.weight"} in mapping["columns"]
    # 토큰을 다시 넣지 않았다 — 같은 토큰으로 물었다.
    assert all(
        one.headers["Authorization"] == "Bearer hub-token" for one in hub.requests[asked:]
    )


def test_예전부터_있던_칸을_새로_이으면_처음부터_다시_받는다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    """정의 검토 대기를 늦게 적용했거나, 허브 칸이 늦게 이어지면 이미 받은 행에도 그 칸의 값이
    있다 — 증분으로는 안 온다(SP ADR 0085 의 5절)."""
    part, _, _ = _world(hub)
    sub_id, _ = _subscribe(client, admin, hub)
    hub.add_property(
        part, {"key": "maker", "label": "제조사", "data_type": "text"}, added=EARLIER
    )
    hub.item(part, "P-2", "커버", AT, material="AL6061", grade="B", maker="한빛")

    result = _check(client, admin, sub_id)
    assert result["restarted"] == [_source_of(part).slug], result
    assert _objects(part)["P-2"]["maker"] == "한빛"


def test_값을_잃을_수_있는_변경은_정의_검토_대기로_남기고_적용하면_들어간다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    part, _, _ = _world(hub)
    sub_id, _ = _subscribe(client, admin, hub)
    before = maintenance_counts(client, admin).get("core_subscription_held", 0)

    # 허브 — 고를 값 C 를 빼고(잃을 수 있다), 칸 하나를 더한다(안전하다).
    for prop in hub.types[part]["def"]["properties"]:
        if prop["key"] == "grade":
            prop["enum_options"] = ["A", "B"]
    hub.add_property(part, {"key": "color", "label": "색", "data_type": "text"}, added=LATER)

    result = _check(client, admin, sub_id)
    assert result["held"] == 1 and result["definitions_applied"] > 0, result
    assert "color" in _props(part), "같은 때의 안전한 변경은 들어간다"
    assert _props(part)["grade"].enum_options == ["A", "B", "C"], "고를 값은 이쪽 그대로"
    row = _row(client, admin, sub_id)
    assert row["last_status"] == "held" and row["held"] is not None
    assert any("고를 값에서 C" in one for one in row["held"]["lines"]), row["held"]
    assert maintenance_counts(client, admin)["core_subscription_held"] == before + 1

    # 다른 지문으로는 적용하지 않는다.
    wrong = client.post(
        f"/api/datasources/core-subscriptions/{sub_id}/held/apply",
        json={"mark": "다른지문"},
        headers=admin.headers,
    )
    assert wrong.status_code == 409, wrong.text
    started = client.post(
        f"/api/datasources/core-subscriptions/{sub_id}/held/apply",
        json={"mark": row["held"]["mark"]},
        headers=admin.headers,
    )
    assert started.status_code == 202, started.text
    done = finish_job(client, admin, started.json())
    assert done["status"] == "done", done
    assert _props(part)["grade"].enum_options == ["A", "B"]
    after = _row(client, admin, sub_id)
    assert after["last_status"] == "ok" and after["held"] is None


def test_공개를_해제한_타입은_수신만_멈추고_받은_자료는_남는다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    part, vendor, _ = _world(hub)
    sub_id, _ = _subscribe(client, admin, hub)
    hub.types[vendor]["published"] = False

    result = _check(client, admin, sub_id)
    source = _source_of(vendor)
    assert result["paused"] == [source.slug] and source.is_active is False
    assert sorted(_objects(vendor)) == ["V-1"], "받은 자료는 남는다"
    row = _row(client, admin, sub_id)
    assert [one["paused"] for one in row["sources"] if one["slug"] == source.slug] == [True]

    # 사람이 끈 소스는 다시 공개돼도 안 켠다 — 구독이 멈춘 것만 되살린다.
    other = _source_of(part)
    turned = client.patch(
        f"/api/datasources/{other.slug}", json={"is_active": False}, headers=admin.headers
    )
    assert turned.status_code == 200, turned.text
    hub.types[vendor]["published"] = True
    again = _check(client, admin, sub_id)
    assert again["resumed"] == [source.slug]
    assert _source_of(vendor).is_active is True
    assert _source_of(part).is_active is False


def test_이_설치가_만든_같은_이름의_타입은_건드리지_않는다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    part, vendor, _ = _world(hub)
    made = client.post(
        "/api/ontology/import",
        json={"types": [{"slug": vendor, "label": "우리 공급사", "key_policy": "optional"}]},
        params={"dry_run": "false"},
        headers=admin.headers,
    )
    assert made.status_code == 200, made.text
    plan = _create(client, admin, hub, apply=False).json()
    actions = {one["type_slug"]: one for one in plan["types"]}
    assert actions[vendor]["action"] == "skip" and "같은 이름" in actions[vendor]["reason"]
    assert actions[part]["action"] == "define"

    sub_id, result = _subscribe(client, admin, hub)
    with SessionLocal() as db:
        mine = db.scalar(select(ObjectType).where(ObjectType.slug == vendor))
        assert mine is not None and mine.label == "우리 공급사" and not managed.owner_of(mine)
    assert _objects(vendor) == {}, "남의 타입에 허브의 행을 넣지 않는다"
    assert sorted(_objects(part)) == ["P-1", "P-2"]
    assert any(vendor in one for one in _row(client, admin, sub_id)["notes"])
    assert result["failed"] == 0, result["sources"]


def test_토큰은_구독_한_곳에서_바꾸고_구독의_소스는_따로_차례가_되지_않는다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    part, vendor, _ = _world(hub)
    sub_id, _ = _subscribe(client, admin, hub)
    hub.token = "Bearer new-token"
    changed = client.patch(
        f"/api/datasources/core-subscriptions/{sub_id}",
        json={"auth_secret": "new-token", "interval_minutes": 30},
        headers=admin.headers,
    )
    assert changed.status_code == 200, changed.text
    for slug in (part, vendor):
        source = _source_of(slug)
        assert (source.auth or {}).get(
            "secret"
        ) == "new-token" and source.interval_minutes == 30
    assert _check(client, admin, sub_id)["failed"] == 0

    with SessionLocal() as db:
        due = {one.slug for one in services.due(db)}
        assert not due & {_source_of(part).slug, _source_of(vendor).slug}, (
            "구독의 소스는 구독과 같은 차례에 돈다"
        )
        row = db.get(CoreSubscription, uuid.UUID(sub_id))
        assert row is not None
        row.checked_at = None
        db.commit()
        assert sub_id in {str(one.id) for one in subscriptions.due(db)}
        # 타이머의 차례 — 구독을 먼저 확인하고 그 구독의 소스를 함께 돈다.
        job = job_services.enqueue(
            db,
            kind="datasource_sync_round",
            params={"slugs": [], "apply": True, "subscriptions": [sub_id]},
            user=None,
            workspace_id=None,
        )
        db.commit()
        job_id = str(job.id)
    done = finish_job(client, admin, {"id": job_id})
    assert done["status"] == "done", done
    ran = {one["slug"] for one in done["result"]["sources"]}
    assert ran == {_source_of(part).slug, _source_of(vendor).slug}
    assert [one["status"] for one in done["result"]["subscriptions"]] == ["ok"]


def test_구독을_지워도_소스와_자료는_남는다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    part, _, _ = _world(hub)
    sub_id, _ = _subscribe(client, admin, hub)
    removed = client.delete(
        f"/api/datasources/core-subscriptions/{sub_id}", headers=admin.headers
    )
    assert removed.status_code == 204, removed.text
    source = _source_of(part)
    assert source.subscription_id is None and source.is_active is True
    assert sorted(_objects(part)) == ["P-1", "P-2"]


def test_정의_창구가_없는_허브는_이_설치에_정의가_있는_타입만_받는다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    part, vendor, _ = _world(hub)
    hub.no_definitions = True
    name = f"hub{hub.tag}"
    # 부품만 정의 묶음으로 받아 둔 설치 — 관리 이름이 구독과 같다.
    defined = bundle_import(
        client,
        admin,
        {
            "ontology": downlevel_only(hub.types[part]["def"]),
            "source": name,
            "apply": True,
        },
    )
    assert defined["applied"] is True, defined
    plan = _create(client, admin, hub, apply=False).json()
    assert plan["definitions"] is False
    assert {one["type_slug"]: one["action"] for one in plan["types"]} == {
        part: "create",
        vendor: "skip",
    }


def downlevel_only(definition: dict[str, Any]) -> dict[str, Any]:
    """정의 묶음 하나(타입 하나) — 이 설치가 아는 칸만."""
    lowered, _ = subscriptions.downlevel({"types": [copy.deepcopy(definition)]})
    return lowered


def test_알림은_넘치면_외_N건으로_끝을_표시한다() -> None:
    lines = [f"줄 {n}" for n in range(205)]
    assert subscriptions.capped(lines)[-1] == "… 외 5건"
    assert len(subscriptions.capped(lines)) == subscriptions.NOTES_MAX + 1
    assert subscriptions.capped(lines[:3]) == lines[:3]


def test_낮추기는_허용_목록과_견준다() -> None:
    """SP 가 칸을 더 늘려도 구독이 막히지 않게 — 특정 칸 이름에 기대지 않는다."""
    lowered, notes = subscriptions.downlevel(
        {
            "types": [
                {
                    "slug": "t",
                    "label": "T",
                    "future_flag": True,
                    "properties": [{"key": "a", "label": "A", "data_type": "text", "x": 1}],
                }
            ],
            "future_top": [1],
        }
    )
    assert "future_top" not in lowered
    assert "future_flag" not in lowered["types"][0]
    assert lowered["types"][0]["properties"] == [
        {"key": "a", "label": "A", "data_type": "text"}
    ]
    assert any("future_flag=True" in one for one in notes)
    assert any("x" in one for one in notes)


def test_같은_허브의_손으로_만든_소스는_구독이_맡고_다른_주소의_소스가_받는_타입은_건너뛴다(
    client: TestClient, admin: Signed, hub: FakeHub
) -> None:
    """CompCore 는 구독 전에 형제 코어 소스를 손으로 만들어 받았다(2026-10-13) — 구독이 그
    소스를 다시 만들면 그 소스가 남긴 외부 식별자를 잃어 같은 것이 둘이 된다."""
    part, vendor, _ = _world(hub)
    name = f"hub{hub.tag}"
    for slug in (part, vendor):
        defined = bundle_import(
            client,
            admin,
            {
                "ontology": downlevel_only(hub.types[slug]["def"]),
                "source": name,
                "apply": True,
            },
        )
        assert defined["applied"] is True, defined
    with SessionLocal() as db:
        types = {one.slug: one.id for one in db.scalars(select(ObjectType))}
        old = DataSource(
            slug=f"old{hub.tag}",
            name="손으로 만든 부품 소스",
            kind="sp_core",
            base_url=hub.base,
            entity_set=part,
            options={},
            filter="",
            select="",
            auth={"kind": "bearer", "user": "", "secret": "old-token"},
            page_size=500,
            type_id=types[part],
            mapping={"external_key": "key", "columns": [{"source": "key", "target": "key"}]},
            source_name=name,
            deprecate_missing=False,
            interval_minutes=0,
            is_active=True,
        )
        # 같은 허브를 다른 주소(IP)로 적은 소스 — 넘겨받지 못한다.
        rival = DataSource(
            slug=f"ip{hub.tag}",
            name="IP 로 적은 공급사 소스",
            kind="sp_core",
            base_url="http://10.0.0.9/api",
            entity_set=vendor,
            options={},
            filter="",
            select="",
            auth={},
            page_size=500,
            type_id=types[vendor],
            mapping={"external_key": "key", "columns": []},
            source_name=name,
            deprecate_missing=False,
            interval_minutes=0,
            is_active=False,
        )
        db.add_all([old, rival])
        db.commit()

    plan = _create(client, admin, hub, apply=False).json()
    actions = {one["type_slug"]: one for one in plan["types"]}
    assert (
        actions[part]["action"] == "adopt" and actions[part]["source_slug"] == f"old{hub.tag}"
    )
    assert actions[vendor]["action"] == "skip" and "다른 주소" in actions[vendor]["reason"]

    sub_id, result = _subscribe(client, admin, hub)
    assert result["adopted"] == [f"old{hub.tag}"] and result["created"] == [], result
    taken = _source_of(part)
    assert taken.slug == f"old{hub.tag}" and str(taken.subscription_id) == sub_id
    assert (taken.auth or {}).get("secret") == "hub-token", "토큰은 구독의 것으로"
    mapping = taken.mapping or {}
    assert {"source": "material", "target": "properties.material"} in mapping["columns"], (
        "칸 대응에 허브의 칸을 더한다"
    )
    assert sorted(_objects(part)) == ["P-1", "P-2"]
