"""공용 부품으로 남이 이어서 일한다 — 해석 조건이 따라가고, STEP 으로 시작한 부품도 고친다.

- 부품으로 올릴 때 작업 버전의 해석 조건을 스냅샷으로 싣고(끌 수 있다), 「내 작업으로
  복사」 가 그것을 새 작업으로 옮긴다. 복사한 작업으로 DOE 를 만들면 그 조건이 박힌다.
- STEP 을 올려 시작한 부품을 공용으로 올리면, 복사한 사람도 미리보기 · 저장 · DOE 를 한다
  (2026-10-04 전에는 올린 원본이 「남의 작업물」 이라 막혔다). 올리지 않은 STEP 은 여전히
  막힌다(`test_access_checks`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api.conftest import Signed, _login, make_user

RECIPE = {
    "params": {"두께": 10},
    "nodes": [{"id": "b", "op": "box", "length": 40, "width": 30, "height": "=두께"}],
}
CONDITIONS = {
    "named_selections": [
        {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
    ],
    "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
    "analysis": {"type": "modal", "modes": 6},
}


def _other(client: TestClient, db: Session) -> dict[str, str]:
    someone = make_user(db, label="colleague", is_system_admin=False)
    return {"Authorization": f"Bearer {_login(client, someone.email)}"}


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201, 202), response.text
    return response.json()


def _published(client: TestClient, who: Signed, **promote: Any) -> str:
    work = _ok(
        client.post("/api/works", json={"name": "판", "recipe": RECIPE}, headers=who.headers)
    )
    _ok(
        client.put(
            f"/api/works/{work['id']}/versions/1/conditions",
            json={"conditions": CONDITIONS},
            headers=who.headers,
        )
    )
    made = _ok(
        client.post(f"/api/works/{work['id']}/promote/part", json=promote, headers=who.headers)
    )
    return str(made["part_id"])


def test_해석_조건은_공용_부품을_거쳐_복사한_작업과_DOE_까지_따라간다(
    client: TestClient, member: Signed, db: Session
) -> None:
    part = _published(client, member)
    shown = _ok(client.get(f"/api/parts/{part}", headers=member.headers))
    assert shown["current"]["conditions"]["constraints"][0]["on"] == "바닥"

    colleague = _other(client, db)
    copied = _ok(client.post(f"/api/parts/{part}/copy-to-work", json={}, headers=colleague))
    assert copied["current"]["conditions"]["constraints"][0]["name"] == "고정"

    study = _ok(
        client.post(
            "/api/doe",
            json={
                "name": "두께 훑기",
                "recipe": copied["current"]["recipe"],
                "factors": [
                    {"name": "두께", "mode": "range", "start": 5, "end": 15, "steps": 3}
                ],
                "work_id": copied["id"],
            },
            headers=colleague,
        )
    )
    assert study["point_count"] == 3
    assert study["conditions"]["constraints"][0]["on"] == "바닥"


def test_형상만_공개하거나_형상만_복사할_수_있다(
    client: TestClient, member: Signed, db: Session
) -> None:
    bare = _published(client, member, conditions=False)
    assert (
        _ok(client.get(f"/api/parts/{bare}", headers=member.headers))["current"]["conditions"]
        == {}
    )

    part = _published(client, member)
    copied = _ok(
        client.post(
            f"/api/parts/{part}/copy-to-work",
            json={"conditions": False},
            headers=_other(client, db),
        )
    )
    assert copied["current"]["conditions"] == {}


def test_STEP_으로_시작한_공용_부품도_복사한_사람이_고치고_DOE_를_만든다(
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
    part = _ok(
        client.post(f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers)
    )["part_id"]

    colleague = _other(client, db)
    copied = _ok(client.post(f"/api/parts/{part}/copy-to-work", json={}, headers=colleague))
    recipe = copied["current"]["recipe"]
    assert recipe["nodes"][0]["op"] == "import_step"
    _ok(client.post("/api/cad/recipe/info", json={"recipe": recipe}, headers=colleague))

    # 위에 변수로 구멍을 얹어 새 버전 — 그 변수로 DOE 를 훑는다.
    drilled = {
        "params": {"지름": 3},
        "nodes": [
            *recipe["nodes"],
            {
                "id": "구멍",
                "op": "hole",
                "target": recipe["nodes"][0]["id"],
                "diameter": "=지름",
                "at": [[0, 0]],
            },
        ],
    }
    _ok(
        client.post(
            f"/api/works/{copied['id']}/versions", json={"recipe": drilled}, headers=colleague
        )
    )
    study = _ok(
        client.post(
            "/api/doe",
            json={
                "name": "구멍 훑기",
                "recipe": drilled,
                "factors": [
                    {"name": "지름", "mode": "range", "start": 2, "end": 4, "steps": 2}
                ],
                "work_id": copied["id"],
            },
            headers=colleague,
        )
    )
    assert study["point_count"] == 2
