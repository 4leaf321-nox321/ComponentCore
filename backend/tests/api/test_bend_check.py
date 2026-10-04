"""판금 굽힘 점검 — 2026-10-04 의 고침(굽힘 반지름은 늘 안쪽 반지름)으로 모양이 바뀌거나 이제
만들어지지 않는 판금을 서버 화면이 찾는다."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.api.conftest import Signed


def _sheet(side: str, path: list[list[int]]) -> dict[str, object]:
    return {
        "params": {"두께": 3.0},
        "nodes": [
            {"id": "판", "op": "sheet_metal", "thickness": "=두께", "width": 30,
             "path": path, "bend_radius": 4, "side": side}
        ],
    }  # fmt: skip


def test_안쪽에_두께가_붙은_굽힘을_찾고_이제_실패하는_것을_가른다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    t = uuid.uuid4().hex[:6]
    made = {}
    for name, side, path in (
        # 안쪽(right) — 모양이 바뀐다(안쪽 r - t → r).
        (f"안쪽{t}", "right", [[0, 0], [40, 0], [40, 40]]),
        # 바깥(left) — 그대로라 목록에 없다.
        (f"바깥{t}", "left", [[0, 0], [40, 0], [40, 40]]),
        # 짧은 가운데 구간(10)의 Z — 굽힘 둘에 r + t(7)와 r(4)가 안 들어가 이제 실패한다.
        (f"짧은{t}", "right", [[0, 0], [30, 0], [30, 10], [60, 10]]),
    ):
        got = client.post(
            "/api/works",
            json={"name": name, "recipe": _sheet(side, path)},
            headers=member.headers,
        )
        assert got.status_code == 201, got.text
        made[name] = got.json()["id"]

    assert client.get("/api/server/bend-check", headers=member.headers).status_code == 403
    report = client.get("/api/server/bend-check", headers=admin.headers)
    assert report.status_code == 200, report.text
    mine = [one for one in report.json()["items"] if t in one["name"]]
    assert [(one["name"], one["status"], one["bends"]) for one in mine] == [
        (f"안쪽{t}", "changed", 1),
        (f"짧은{t}", "failing", 1),
    ]
    assert "판을 굽히지 못했습니다" in mine[1]["error"]
    assert mine[0]["kind"] == "work" and mine[0]["id"] == made[f"안쪽{t}"]
    assert mine[0]["owner"] == "member" and mine[0]["node"] == "판"
