"""레시피가 **가리키는 것**과 대행 — 2026-10-04 점검에서 드러난 구멍들.

- `component` 의 `work:<id>` 는 남의 비공개 작업을 소유 확인 없이 읽었다 — 작업 id 하나로 그
  작업의 모든 버전을 STEP 으로 받아 갈 수 있었다(읽기 전용 토큰으로도).
- `import_step` 의 작업물 id 도 마찬가지.
- 누구나 제 토큰에 `act_for_others`(대행)를 줄 수 있었다.
- DOE 에 조건을 함께 주면 `work_id` 의 소유를 보지 않았다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api.conftest import Signed, _login, make_user

BOX = {"nodes": [{"id": "b", "op": "box", "length": 40, "width": 30, "height": 10}]}


def _other(client: TestClient, db: Session) -> dict[str, str]:
    stranger = make_user(db, label="stranger", is_system_admin=False)
    return {"Authorization": f"Bearer {_login(client, stranger.email)}"}


def _code(response: object) -> str:
    return str(response.json()["error"]["code"])  # type: ignore[attr-defined]


def test_남의_비공개_작업은_component_로_가져오지_못한다(
    client: TestClient, member: Signed, admin: Signed, db: Session
) -> None:
    made = client.post(
        "/api/works", json={"name": "비공개", "recipe": BOX}, headers=member.headers
    )
    assert made.status_code == 201, made.text
    recipe = {
        "nodes": [{"id": "x", "op": "component", "source": f"work:{made.json()['id']}@1"}]
    }
    stranger = _other(client, db)
    for path in ("/api/cad/recipe/step", "/api/cad/recipe/info"):
        refused = client.post(path, json={"recipe": recipe}, headers=stranger)
        assert refused.status_code == 403 and _code(refused).endswith("CAD-0022"), path
    # 저장 · 닮은 형상 찾기도 같은 문으로 들어온다.
    saved = client.post(
        "/api/works", json={"name": "훔침", "recipe": recipe}, headers=stranger
    )
    assert saved.status_code == 403
    similar = client.post("/api/search/similar", json={"recipe": recipe}, headers=stranger)
    assert similar.status_code == 403
    # 주인과 관리자는 된다.
    for headers in (member.headers, admin.headers):
        ok = client.post("/api/cad/recipe/info", json={"recipe": recipe}, headers=headers)
        assert ok.status_code == 200, ok.text


def test_남의_STEP_작업물은_import_step_으로_가져오지_못한다(
    client: TestClient, member: Signed, db: Session, tmp_path: Path
) -> None:
    from build123d import Box, export_step

    step = tmp_path / "block.step"
    export_step(Box(20, 10, 5), str(step))
    with step.open("rb") as handle:
        made = client.post(
            "/api/works/from-step",
            data={"name": "올린 STEP"},
            files={"file": ("block.step", handle, "application/step")},
            headers=member.headers,
        )
    assert made.status_code == 201, made.text
    recipe = made.json()["current"]["recipe"]
    assert recipe["nodes"][0]["op"] == "import_step"
    refused = client.post(
        "/api/cad/recipe/info", json={"recipe": recipe}, headers=_other(client, db)
    )
    assert refused.status_code == 403 and _code(refused).endswith("JOBS-0005")
    mine = client.post("/api/cad/recipe/info", json={"recipe": recipe}, headers=member.headers)
    assert mine.status_code == 200, mine.text


def test_대행_범위는_관리자만_토큰에_준다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    asked = {"name": "기계", "scopes": ["read", "write", "act_for_others"]}
    refused = client.post("/api/auth/tokens", json=asked, headers=member.headers)
    assert refused.status_code == 403 and _code(refused).endswith("AUTH-0108")
    granted = client.post("/api/auth/tokens", json=asked, headers=admin.headers)
    assert granted.status_code == 201, granted.text


def test_DOE_는_남의_작업에_붙지_못한다_조건을_함께_줘도(
    client: TestClient, member: Signed, db: Session
) -> None:
    made = client.post(
        "/api/works",
        json={"name": "남의 대상", "recipe": {**BOX, "params": {"두께": 10}}},
        headers=member.headers,
    )
    refused = client.post(
        "/api/doe",
        json={
            "name": "몰래",
            "recipe": {"params": {"두께": 10}, "nodes": BOX["nodes"]},
            "work_id": made.json()["id"],
            "conditions": {},
            "factors": [{"name": "두께", "mode": "list", "values": [10]}],
        },
        headers=_other(client, db),
    )
    assert refused.status_code == 403 and _code(refused).endswith("WORKS-0002")
