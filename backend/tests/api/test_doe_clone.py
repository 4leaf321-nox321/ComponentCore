"""DOE 「내 것으로 복제」 — 공개된 DOE 를 다른 사람이 이어서 한다.

원본은 보기만 되고(보내기 · 점 더하기는 소유자만), 이어 하려는 사람은 같은 설계점 · 조건으로
자기 소유의 DOE 를 갖는다. 점은 다시 뽑지 않고 값을 옮긴다 — 더한 묶음까지 번호와 값이 같다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from tests.api.conftest import Signed, _login, make_user

PLATE = {
    "params": {"두께": 6.0, "길이": 80.0},
    "nodes": [{"id": "판", "op": "box", "length": "=길이", "width": 40, "height": "=두께"}],
}
CONDITIONS = {
    "named_selections": [
        {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
    ],
    "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
    "analysis": {"type": "modal", "modes": 6},
}


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201, 202), response.text
    return response.json()


def _colleague(client: TestClient, db: Session) -> dict[str, str]:
    someone = make_user(db, label="colleague", is_system_admin=False)
    return {"Authorization": f"Bearer {_login(client, someone.email)}"}


def _study(client: TestClient, who: Signed, **extra: Any) -> dict[str, Any]:
    work = _ok(
        client.post("/api/works", json={"name": "판", "recipe": PLATE}, headers=who.headers)
    )
    study: dict[str, Any] = _ok(
        client.post(
            "/api/doe",
            json={
                "name": "두께 훑기",
                "recipe": PLATE,
                "work_id": work["id"],
                "conditions": CONDITIONS,
                "factors": [
                    {"name": "두께", "mode": "range", "start": 4, "end": 8, "steps": 3}
                ],
                **extra,
            },
            headers=who.headers,
        )
    )
    return study


def _values(study: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [(one["number"], one["params"]) for one in study["points"]]


def test_남의_공개_DOE_를_같은_점_같은_조건으로_내_것으로_복제한다(
    client: TestClient, member: Signed, db: Session
) -> None:
    source = _study(client, member)
    # 첫 결과를 보고 점을 더한 DOE — 더한 묶음까지 따라와야 한다.
    _ok(
        client.post(
            f"/api/doe/{source['id']}/extend",
            json={
                "method": "lhs",
                "samples": 2,
                "factors": [{"name": "두께", "mode": "range", "start": 5, "end": 7}],
            },
            headers=member.headers,
        )
    )
    source = _ok(client.get(f"/api/doe/{source['id']}", headers=member.headers))
    assert source["point_count"] == 5

    colleague = _colleague(client, db)
    # 남의 것은 보기만 된다.
    refused = client.post(f"/api/doe/{source['id']}/export", headers=colleague)
    assert refused.status_code == 403

    clone = _ok(client.post(f"/api/doe/{source['id']}/clone", json={}, headers=colleague))
    assert clone["name"] == "두께 훑기 (복제)"
    assert clone["owner_id"] != source["owner_id"]
    assert clone["cloned_from_id"] == source["id"]
    assert clone["cloned_from_name"] == "두께 훑기"
    assert clone["work_id"] is None  # 남의 작업에는 붙이지 않는다 — 스냅샷만
    assert _values(clone) == _values(source)
    assert clone["batches"] == source["batches"]
    assert clone["conditions"]["constraints"][0]["on"] == "바닥"
    assert clone["factors"] == source["factors"]

    # 내 것이니 보내고 이어서 점을 더한다. 원본은 그대로다.
    _ok(client.post(f"/api/doe/{clone['id']}/export", headers=colleague))
    _ok(
        client.post(
            f"/api/doe/{clone['id']}/extend",
            json={"method": "lhs", "samples": 1},
            headers=colleague,
        )
    )
    after = _ok(client.get(f"/api/doe/{source['id']}", headers=member.headers))
    assert after["point_count"] == 5


def test_비공개_DOE_는_복제하지_못한다(
    client: TestClient, member: Signed, db: Session
) -> None:
    source = _study(client, member)
    _ok(
        client.post(
            f"/api/doe/{source['id']}/visibility?value=private", headers=member.headers
        )
    )
    refused = client.post(
        f"/api/doe/{source['id']}/clone", json={}, headers=_colleague(client, db)
    )
    assert refused.status_code == 403


def test_내_DOE_를_복제하면_대상_작업이_이어지고_이름을_정할_수_있다(
    client: TestClient, member: Signed
) -> None:
    source = _study(client, member)
    clone = _ok(
        client.post(
            f"/api/doe/{source['id']}/clone",
            json={"name": "두께 훑기 2차"},
            headers=member.headers,
        )
    )
    assert clone["name"] == "두께 훑기 2차"
    assert clone["work_id"] == source["work_id"]


def test_STEP_으로_만든_공개_DOE_도_복제한다(
    client: TestClient, member: Signed, db: Session, tmp_path: Path
) -> None:
    from build123d import Box, export_step

    step = tmp_path / "block.step"
    export_step(Box(20, 10, 5), str(step))
    with step.open("rb") as handle:
        work = _ok(
            client.post(
                "/api/works/from-step",
                data={"name": "올린 STEP"},
                files={"file": ("block.step", handle, "application/step")},
                headers=member.headers,
            )
        )
    recipe = work["current"]["recipe"]
    source = _ok(
        client.post(
            "/api/doe",
            json={"name": "해석 하나", "recipe": recipe, "factors": [], "work_id": work["id"]},
            headers=member.headers,
        )
    )
    clone = _ok(
        client.post(f"/api/doe/{source['id']}/clone", json={}, headers=_colleague(client, db))
    )
    assert clone["point_count"] == 1 and clone["recipe"] == recipe


def test_복제한_DOE_의_폴더는_원본을_가리킨다(
    client: TestClient, member: Signed, db: Session, export_root: Path
) -> None:
    import json

    source = _study(client, member)
    clone = _ok(
        client.post(f"/api/doe/{source['id']}/clone", json={}, headers=_colleague(client, db))
    )
    _ok(client.post(f"/api/doe/{source['id']}/export", headers=member.headers))
    owner = {"Authorization": f"Bearer {_login(client, _email_of(db, clone['owner_id']))}"}
    _ok(client.post(f"/api/doe/{clone['id']}/export", headers=owner))

    def spec(study: dict[str, Any]) -> dict[str, Any]:
        folder = next(
            one for one in export_root.iterdir() if one.name.endswith(study["id"][:8])
        )
        readme = (folder / "README.txt").read_text(encoding="utf-8")
        return {
            **json.loads((folder / "study.json").read_text(encoding="utf-8")),
            "_readme": readme,
        }

    copied = spec(clone)
    assert copied["cloned_from"]["id"] == source["id"]
    assert copied["cloned_from"]["name"] == "두께 훑기"
    assert copied["cloned_from"]["owner"]["email"] == member.email
    assert "복제 원본: ‘두께 훑기’" in copied["_readme"]
    original = spec(source)
    assert original["cloned_from"] is None and "복제 원본" not in original["_readme"]


def _email_of(db: Session, user_id: str) -> str:
    from app.modules.accounts.models import User

    user = db.get(User, user_id)
    assert user is not None
    return user.email
