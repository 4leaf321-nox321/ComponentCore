"""공용 공간(부품 · 지그 · 템플릿)의 **폴더** — 내 작업과 같은 경로 한 칸. 다른 점은 여럿이
함께 쓴다는 것: 옮기는 것은 주인 · 관리자, 남의 것이 든 폴더째 옮기기는 관리자만.

카탈로그는 모두의 것이라 앞 시험의 줄이 남아 있다 — 시험마다 제 맨 위 폴더(`root`) 아래만
본다.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.jigs.models import Jig
from app.modules.parts.models import Part
from tests.api.conftest import Signed, _login, make_user

BOX = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 40, "height": 30}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 10},
    ]
}

#: 부품 · 지그는 승격으로만 생긴다 — 폴더 규칙만 볼 때는 줄을 바로 넣는다.
CATALOGS = [("parts", Part), ("jigs", Jig)]


@pytest.fixture
def root() -> str:
    return f"시험{uuid.uuid4().hex[:8]}"


def _owner(db: Session, who: Signed) -> User:
    user = db.scalar(select(User).where(User.email == who.email))
    assert user is not None
    return user


def _item(db: Session, model: Any, who: Signed, name: str, folder: str) -> str:
    row = model(name=name, owner_id=_owner(db, who).id, folder=folder)
    db.add(row)
    db.commit()
    return str(row.id)


def _stranger(client: TestClient, db: Session) -> Signed:
    user = make_user(db, label="stranger", is_system_admin=False)
    return Signed(email=user.email, token=_login(client, user.email))


def _names(client: TestClient, who: Signed, base: str, **params: Any) -> list[str]:
    page = client.get(f"/api/{base}", params={"limit": 100, **params}, headers=who.headers)
    assert page.status_code == 200, page.text
    return sorted(one["name"] for one in page.json()["items"])


def _tree(
    client: TestClient, who: Signed, base: str, root: str, **params: Any
) -> dict[str, int]:
    """`root` 아래의 나무만 — `{하위 경로: 바로 그 폴더의 수}`."""
    got = client.get(f"/api/{base}/folders", params=params, headers=who.headers)
    assert got.status_code == 200, got.text
    return {
        one["path"][len(root) :].lstrip("/"): one["count"]
        for one in got.json()
        if one["path"] == root or one["path"].startswith(root + "/")
    }


def _post(client: TestClient, who: Signed, url: str, body: dict[str, Any]) -> Any:
    return client.post(url, json=body, headers=who.headers)


@pytest.mark.parametrize(("base", "model"), CATALOGS)
def test_카탈로그를_폴더로_거르고_나무를_센다(
    client: TestClient, db: Session, member: Signed, root: str, base: str, model: Any
) -> None:
    _item(db, model, member, "맨위", root)
    _item(db, model, member, "가", f"{root}/고객A")
    _item(db, model, member, "나", f"{root}/고객A/2026")
    _item(db, model, member, "라", f"{root}/고객A_비슷")  # LIKE 의 _ 를 글자로 읽는지
    assert _names(client, member, base, folder=f"{root}/고객A") == ["가", "나"]
    assert _names(client, member, base, folder=f"{root}/고객A", subfolders=False) == ["가"]
    assert _names(client, member, base, folder=root, subfolders=False) == ["맨위"]
    assert _tree(client, member, base, root) == {
        "": 1,
        "고객A": 1,
        "고객A/2026": 1,
        "고객A_비슷": 1,
    }
    # 목록에도 폴더와 주인이 실린다 — 화면이 「옮길 수 있나」 를 미리 가린다.
    page = client.get(
        f"/api/{base}", params={"folder": f"{root}/고객A/2026"}, headers=member.headers
    )
    item = page.json()["items"][0]
    assert item["folder"] == f"{root}/고객A/2026"
    assert item["owner_id"] == str(_owner(db, member).id)


@pytest.mark.parametrize(("base", "model"), CATALOGS)
def test_남의_것은_옮기지_못하고_관리자는_옮긴다(
    client: TestClient,
    db: Session,
    member: Signed,
    admin: Signed,
    root: str,
    base: str,
    model: Any,
) -> None:
    mine = _item(db, model, member, "내것", root)
    theirs = _item(db, model, admin, "남의것", root)
    ok = _post(client, member, f"/api/{base}/move", {"ids": [mine], "folder": f" /{root}/A/ "})
    assert ok.json() == {"moved": 1}
    # 하나라도 남의 것이면 아무것도 옮기지 않는다.
    keep = {"ids": [mine, theirs], "folder": f"{root}/B"}
    assert _post(client, member, f"/api/{base}/move", keep).status_code == 403
    assert _names(client, member, base, folder=f"{root}/A") == ["내것"]
    # 관리자는 남의 것도 — 카탈로그 항목을 고치는 규칙과 같다.
    assert _post(client, admin, f"/api/{base}/move", keep).json() == {"moved": 2}
    assert _names(client, member, base, folder=f"{root}/B") == ["남의것", "내것"]
    # 한 항목은 PATCH 로도 옮긴다.
    one = client.patch(
        f"/api/{base}/{mine}", json={"folder": f" {root}/C "}, headers=member.headers
    )
    assert one.status_code == 200 and one.json()["folder"] == f"{root}/C"


@pytest.mark.parametrize(("base", "model"), CATALOGS)
def test_남의_것이_든_폴더째_옮기기는_관리자만(
    client: TestClient,
    db: Session,
    member: Signed,
    admin: Signed,
    root: str,
    base: str,
    model: Any,
) -> None:
    rename = f"/api/{base}/folders/rename"
    _item(db, model, member, "가", f"{root}/공정/선반")
    _item(db, model, member, "나", f"{root}/공정")
    mine_only = {"path": f"{root}/공정", "to": f"{root}/가공"}
    assert _post(client, member, rename, mine_only).json() == {"moved": 2}

    _item(db, model, admin, "다", f"{root}/가공/선반")
    blocked = _post(client, member, rename, {"path": f"{root}/가공", "to": f"{root}/보관"})
    assert blocked.status_code == 403 and "관리자" in blocked.json()["error"]["message"]
    # 하위 폴더도 마찬가지 — 「가공/선반」 에 남의 것이 있다.
    sub = {"path": f"{root}/가공/선반", "to": f"{root}/선반"}
    assert _post(client, member, rename, sub).status_code == 403
    # 관리자가 위 폴더로 합친다 — 폴더 지우기다. 하위는 따라 올라간다.
    merged = _post(client, admin, rename, {"path": f"{root}/가공", "to": root})
    assert merged.json() == {"moved": 3}
    assert _tree(client, admin, base, root) == {"": 1, "선반": 2}


def test_지운_부품은_폴더_수에_들지_않는다(
    client: TestClient, db: Session, member: Signed, root: str
) -> None:
    gone = _item(db, Part, member, "지울것", f"{root}/고객A")
    assert client.delete(f"/api/parts/{gone}", headers=member.headers).status_code == 204
    assert _tree(client, member, "parts", root) == {}
    assert _post(client, member, "/api/parts/move", {"ids": [gone]}).status_code == 404


def test_승격한_부품은_작업의_폴더에_처음_한_번만_놓인다(
    client: TestClient, member: Signed, root: str
) -> None:
    work = _post(
        client,
        member,
        "/api/works",
        {"name": "브래킷", "kind": "part", "recipe": BOX, "folder": f"{root}/고객A"},
    ).json()
    first = _post(client, member, f"/api/works/{work['id']}/promote/part", {})
    assert first.status_code == 201, first.text
    part_url = f"/api/parts/{first.json()['part_id']}"
    assert client.get(part_url, headers=member.headers).json()["folder"] == f"{root}/고객A"

    # 카탈로그에서 옮긴 뒤 새 버전을 올려도 제자리로 끌고 오지 않는다.
    client.patch(part_url, json={"folder": f"{root}/공용"}, headers=member.headers)
    next_version = _post(
        client,
        member,
        f"/api/works/{work['id']}/versions",
        {"recipe": {**BOX, "params": {"두께": 12}}},
    )
    assert next_version.status_code in (200, 201, 202), next_version.text
    again = _post(client, member, f"/api/works/{work['id']}/promote/part", {})
    assert again.status_code == 201, again.text
    assert client.get(part_url, headers=member.headers).json()["folder"] == f"{root}/공용"


def _template(
    client: TestClient, who: Signed, name: str, folder: str, shared: bool = False
) -> dict[str, Any]:
    made = _post(
        client,
        who,
        "/api/templates",
        {"name": name, "recipe": BOX, "is_shared": shared, "folder": folder},
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def test_템플릿_폴더는_보이는_것만_센다(
    client: TestClient, db: Session, member: Signed, root: str
) -> None:
    stranger = _stranger(client, db)
    _template(client, member, "내것", f"{root}/형상/브래킷")
    _template(client, stranger, "남의_공용", f"{root}/형상", shared=True)
    _template(client, stranger, "남의_비공개", f"{root}/비밀")
    assert _tree(client, member, "templates", root) == {"": 0, "형상": 1, "형상/브래킷": 1}
    mine = _tree(client, member, "templates", root, scope="mine")
    assert mine == {"": 0, "형상": 0, "형상/브래킷": 1}
    assert _names(client, member, "templates", folder=f"{root}/형상") == ["남의_공용", "내것"]

    rename = "/api/templates/folders/rename"
    # 남의 공용 템플릿이 든 폴더는 관리자만 — 하위 폴더에는 내 것뿐이라 된다.
    whole = {"path": f"{root}/형상", "to": f"{root}/모양"}
    assert _post(client, member, rename, whole).status_code == 403
    sub = {"path": f"{root}/형상/브래킷", "to": f"{root}/브래킷"}
    assert _post(client, member, rename, sub).json() == {"moved": 1}
    # 남의 비공개 템플릿은 같은 이름의 폴더에 있어도 내가 옮기지 않는다(보이지도 않는다).
    secret = {"path": f"{root}/비밀", "to": f"{root}/공개"}
    assert _post(client, member, rename, secret).json() == {"moved": 0}
    assert _tree(client, stranger, "templates", root, scope="mine") == {
        "": 0,
        "비밀": 1,
        "형상": 1,
    }


def test_템플릿을_복사하면_폴더와_꼬리표를_가져온다(
    client: TestClient, db: Session, member: Signed, root: str
) -> None:
    stranger = _stranger(client, db)
    made = _post(
        client,
        member,
        "/api/templates",
        {"name": "판", "recipe": BOX, "is_shared": True, "folder": root, "tags": ["얇은"]},
    ).json()
    copied = _post(client, stranger, f"/api/templates/{made['id']}/copy", {}).json()
    assert copied["folder"] == root and copied["tags"] == ["얇은"]
    # 남의 템플릿은 옮기지 못한다 — 복사본은 내 것이니 옮긴다.
    move = "/api/templates/move"
    denied = _post(client, stranger, move, {"ids": [made["id"]], "folder": f"{root}/내판"})
    assert denied.status_code == 403
    ok = _post(client, stranger, move, {"ids": [copied["id"]], "folder": f"{root}/내판"})
    assert ok.json() == {"moved": 1}
    bad = client.patch(
        f"/api/templates/{copied['id']}",
        json={"folder": "/".join("x" * 9)},
        headers=stranger.headers,
    )
    assert bad.status_code == 400
