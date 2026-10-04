"""지그 편집 — 받침을 옮기거나 높이를 바꾸면 **제품과의 간섭을 다시 본다.**

생성된 지그의 레시피에는 제품이 없다(지그만). 그래서 편집기는 지그를 만들 때의 제품을 생성기의
좌표계 규칙으로 옆에 놓고(`jig-product`), 요소(받침_1 · 위치_핀_1 · 클램프_1 …)마다 간섭을
본다(`jig-check`). 이름은 생성 결과의 간섭 보고 · 미리보기 · 레시피 노드 id 가 같다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi.testclient import TestClient

from tests.api.conftest import Signed
from tests.api.test_works import _plate, _work


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201, 202), response.text
    return response.json()


def _generated(client: TestClient, who: Signed) -> tuple[dict[str, Any], dict[str, Any]]:
    part = _work(client, who, _plate(client, who))
    run = _ok(
        client.post(
            "/api/works/jig-from-part",
            json={"source": f"work:{part['id']}", "options": {"support_count": 3}},
            headers=who.headers,
        )
    )
    jig, job = run["work"], run["job"]
    version = _ok(
        client.post(f"/api/works/{jig['id']}/jig-runs/{job['id']}/adopt", headers=who.headers)
    )
    return jig, version


def _hits(report: dict[str, Any]) -> set[frozenset[str]]:
    return {frozenset((one["a"], one["b"])) for one in report["items"] if not one["ok"]}


def test_생성된_지그는_만들_때의_제품을_받침_높이에_놓는다(
    client: TestClient, member: Signed
) -> None:
    jig, version = _generated(client, member)
    found = _ok(client.get(f"/api/works/{jig['id']}/jig-product", headers=member.headers))
    assert found["available"] is True and found["lift_param"] == "받침_높이"
    node = found["node"]
    assert node["id"] == "제품" and node["op"] == "component"
    assert node["source"].startswith("work:") and node["source"].endswith("@1")
    assert isinstance(node["translate"][2], str) and node["translate"][2].startswith(
        "=받침_높이"
    )

    # 생성기가 놓은 그대로면 겹침이 없다 — 요소마다, 이름은 레시피 노드 id 그대로.
    report = _ok(
        client.post(f"/api/works/{jig['id']}/jig-check", json={}, headers=member.headers)
    )
    assert report["available"] is True and report["ok"] is True, report["items"]
    assert {"바닥판", "받침_1", "받침_2", "받침_3", "제품"} <= set(report["parts"])
    group = next(one for one in version["recipe"]["nodes"] if one["id"] == "지그")
    assert set(report["parts"]) == {*group["targets"], "제품"}


def test_받침을_제품_안으로_올리면_그_받침이_걸리고_받침_높이를_올리면_제품도_따라_오른다(
    client: TestClient, member: Signed
) -> None:
    jig, version = _generated(client, member)
    recipe = deepcopy(version["recipe"])
    support = next(one for one in recipe["nodes"] if one["id"] == "받침_1")
    support["height"] = "=받침_높이 + 4"  # 제품 바닥을 4 mm 뚫고 들어간다
    report = _ok(
        client.post(
            f"/api/works/{jig['id']}/jig-check",
            json={"recipe": recipe},
            headers=member.headers,
        )
    )
    assert report["ok"] is False
    assert frozenset(("받침_1", "제품")) in _hits(report)

    # 받침 높이 변수를 올리면 받침과 제품이 같이 오른다 — 겹침이 그대로 생기지 않는다.
    raised = deepcopy(version["recipe"])
    raised["params"]["받침_높이"] = raised["params"]["받침_높이"] + 10
    again = _ok(
        client.post(
            f"/api/works/{jig['id']}/jig-check",
            json={"recipe": raised},
            headers=member.headers,
        )
    )
    assert frozenset(("받침_1", "제품")) not in _hits(again)
    # 저장한 도면은 그대로 — 검사는 아무것도 저장하지 않는다.
    current = _ok(client.get(f"/api/works/{jig['id']}", headers=member.headers))
    assert current["current_version"] == version["number"]


def test_제품의_자리를_모르면_까닭을_말한다(client: TestClient, member: Signed) -> None:
    part = _work(client, member, _plate(client, member))
    assert (
        _ok(client.get(f"/api/works/{part['id']}/jig-product", headers=member.headers))[
            "reason"
        ]
        == "지그 작업이 아닙니다."
    )
    drawn = _ok(
        client.post(
            "/api/works",
            json={"name": "손 지그", "kind": "jig", "recipe": _plate(client, member)},
            headers=member.headers,
        )
    )
    found = _ok(
        client.post(f"/api/works/{drawn['id']}/jig-check", json={}, headers=member.headers)
    )
    assert found["available"] is False and "제품의 자리를 모릅니다" in found["reason"]
