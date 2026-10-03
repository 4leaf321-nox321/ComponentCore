"""DOE 계획 — 제약식 · 미리 만들어 보기 · 형상 점검 · 표 넣기 · 점 더하기 · 측정값 · 표본 방식.

모두 「보내기 전에 나쁜 점을 거른다」 와 「해석 쪽이 고른 점을 그대로 만든다」 를 위한 것이다.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed
from tests.api.test_doe import JIG

#: 다른 치수에서 나온 값(`보_비율`)도 제약식이 부른다.
DERIVED: dict[str, Any] = {**JIG, "params": {**JIG["params"], "보_비율": "=길이 / 두께"}}

FACTORS = [
    {"name": "두께", "mode": "list", "values": [4, 8, 12]},
    {"name": "길이", "mode": "list", "values": [80, 100]},
]


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _manifest(client: TestClient, who: Signed, study_id: str) -> list[dict[str, str]]:
    got = client.get(f"/api/doe/{study_id}/manifest.csv", headers=who.headers)
    assert got.status_code == 200, got.text
    return list(csv.DictReader(got.text.lstrip("﻿").splitlines()))


def test_제약식은_만들기_전에_어긴_조합을_거른다(client: TestClient, member: Signed) -> None:
    body = {"factors": FACTORS, "recipe": DERIVED, "constraints": ["보_비율 >= 10"]}
    preview = client.post("/api/doe/preview", json=body, headers=member.headers)
    assert preview.status_code == 200, preview.text
    got = preview.json()
    assert got["requested"] == 6 and got["count"] == 4 and got["rejected"] == 2
    assert got["hits"] == [2]
    assert {(p["두께"], p["길이"]) for p in got["rejected_points"]} == {
        (12.0, 80.0),
        (12.0, 100.0),
    }

    made = client.post(
        "/api/doe",
        json={"name": "제약", "recipe": DERIVED, **body},
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    study = made.json()
    assert study["point_count"] == 4 and study["constraints"] == ["보_비율 >= 10"]
    assert all(float(p["params"]["두께"]) < 12 for p in study["points"])


def test_제약식이_틀리면_이름을_짚어_말한다(client: TestClient, member: Signed) -> None:
    def ask(constraints: list[Any]) -> str:
        got = client.post(
            "/api/doe/preview",
            json={"factors": FACTORS, "recipe": DERIVED, "constraints": constraints},
            headers=member.headers,
        )
        assert got.status_code == 400, got.text
        return str(got.json()["error"]["message"])

    assert "모르는 이름 높이" in ask(["높이 > 3"])
    assert "비교" in ask(["두께 * 2"])
    # 아무것도 못 지키면 만들지 않는다.
    none = client.post(
        "/api/doe",
        json={
            "name": "없음",
            "recipe": DERIVED,
            "factors": FACTORS,
            "constraints": ["두께 > 100"],
        },
        headers=member.headers,
    )
    assert none.status_code == 400 and "하나도 없습니다" in none.json()["error"]["message"]


def test_미리_만들어_보기는_끝_점을_만들고_어긴_점과_깨진_점을_말한다(
    client: TestClient, member: Signed
) -> None:
    got = client.post(
        "/api/doe/probe",
        json={
            "recipe": JIG,
            "factors": [
                {"name": "두께", "mode": "range", "start": 0, "end": 12, "steps": 4},
                {"name": "길이", "mode": "list", "values": [80, 90, 100]},
            ],
            "constraints": ["길이 >= 9 * 두께"],
            "conditions": {},
        },
        headers=member.headers,
    )
    assert got.status_code == 200, got.text
    rows = {one["label"]: one for one in got.json()["points"]}
    assert next(iter(rows)) == "가운데" and rows["가운데"]["status"] == "ok"
    assert rows["가운데"]["params"] == {"두께": 6.0, "길이": 90.0}
    assert rows["가운데"]["ms"] >= 0 and rows["가운데"]["solids"] == 1
    # 두께 12 · 길이 90 은 제약(길이 >= 9 * 두께)을 어긴다 — 만들지 않고 까닭을 말한다.
    assert rows["두께 최대"]["status"] == "skipped" and "제약 1" in rows["두께 최대"]["error"]
    # 두께 0 은 형상이 깨진다 — 미리 안다.
    assert rows["두께 최소"]["status"] == "failed" and rows["두께 최소"]["error"]
    assert got.json()["mean_ms"] is not None


#: 구멍을 옆으로 밀면 가장자리 벽이 얇아진다 — 형상은 멀쩡히 만들어지지만 메시가 막힌다.
HOLE_PLATE: dict[str, Any] = {
    "params": {"구멍_x": 0.0},
    "nodes": [
        {"id": "판", "op": "box", "length": 50, "width": 50, "height": 10},
        {"id": "구멍", "op": "hole", "target": "판", "at": [["=구멍_x", 0]], "diameter": 9.6},
    ],
}


def test_형상_점검은_얇은_벽을_표와_점에_적는다(client: TestClient, member: Signed) -> None:
    made = client.post(
        "/api/doe",
        json={
            "name": "구멍 밀기",
            "recipe": HOLE_PLATE,
            "factors": [{"name": "구멍_x", "mode": "list", "values": [0, 20]}],
            "conditions": {},
            "checks": {"min_wall": 1.0},
        },
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    study = client.get(f"/api/doe/{made.json()['id']}", headers=member.headers).json()
    assert study["checks"] == {"min_wall": 1.0}
    first, second = study["points"]
    assert first["quality"]["warnings"] == [] and first["quality"]["min_wall"] > 5
    assert second["quality"]["min_wall"] == pytest.approx(0.2, abs=1e-3)
    assert second["quality"]["warnings"][0].startswith("벽 두께 0.2 mm (기준 1)")
    rows = _manifest(client, member, study["id"])
    assert rows[0]["warnings"] == "" and rows[1]["warnings"].startswith("벽 두께 0.2 mm")

    # 기준이 틀리면 만들기 전에 말한다.
    bad = client.post(
        "/api/doe",
        json={
            "name": "틀린 기준",
            "recipe": HOLE_PLATE,
            "factors": [{"name": "구멍_x", "mode": "list", "values": [0, 20]}],
            "checks": {"wall": 1},
        },
        headers=member.headers,
    )
    assert bad.status_code == 400 and "모르는 점검 기준" in bad.json()["error"]["message"]


def test_미리_만들어_보기도_형상을_점검한다(client: TestClient, member: Signed) -> None:
    got = client.post(
        "/api/doe/probe",
        json={
            "recipe": HOLE_PLATE,
            "factors": [
                {"name": "구멍_x", "mode": "range", "start": 0, "end": 20, "steps": 3}
            ],
            "conditions": {},
        },
        headers=member.headers,
    )
    assert got.status_code == 200, got.text
    rows = {one["label"]: one for one in got.json()["points"]}
    far = next(one for label, one in rows.items() if "최대" in label)
    assert far["quality"]["warnings"] and far["quality"]["min_wall"] == pytest.approx(
        0.2, abs=1e-3
    )
    assert rows["가운데"]["quality"]["warnings"] == []


def test_표를_직접_주면_값_그대로_줄_순서대로_만든다(
    client: TestClient, member: Signed
) -> None:
    # CSV 에서 온 것처럼 글자로 — 가공 단위로 맞추지 않고, 겹친 줄도 그대로 둔다.
    table = [
        {"두께": "6.333", "길이": "90"},
        {"두께": "4", "길이": "80"},
        {"두께": "4", "길이": "80"},
    ]
    body = {
        "name": "최적화기가 고른 점",
        "recipe": JIG,
        "method": "table",
        "table": table,
        "factors": [{"name": "두께", "mode": "fixed", "value": 6}],
        "conditions": {},
        "idempotency_key": "table-1",
    }
    preview = client.post("/api/doe/preview", json=body, headers=member.headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()["count"] == 3 and preview.json()["varying"] == ["두께", "길이"]

    made = client.post("/api/doe", json=body, headers=member.headers)
    assert made.status_code == 201, made.text
    study = made.json()
    assert study["method"] == "table" and study["point_count"] == 3
    assert [p["params"] for p in study["points"]] == [
        {"두께": 6.333, "길이": 90.0},
        {"두께": 4.0, "길이": 80.0},
        {"두께": 4.0, "길이": 80.0},
    ]
    # 표에만 있던 `길이` 는 인자로 더해지고, 정의는 표의 값 목록이다.
    by_name = {one["name"]: one for one in study["factors"]}
    assert by_name["두께"]["mode"] == "list" and by_name["길이"]["values"] == [80.0, 90.0]
    assert all(p["status"] == "ok" for p in study["points"])
    # 같은 열쇠로 다시 부르면 같은 스터디 — 표를 설계점에서 되짚어 견준다.
    again = client.post("/api/doe", json=body, headers=member.headers)
    assert again.status_code == 200 and again.json()["id"] == study["id"]


def test_표가_틀리거나_제약을_어기면_만들지_않는다(client: TestClient, member: Signed) -> None:
    def make(table: list[dict[str, Any]], **extra: Any) -> str:
        got = client.post(
            "/api/doe",
            json={"name": "표", "recipe": JIG, "method": "table", "table": table, **extra},
            headers=member.headers,
        )
        assert got.status_code == 400, got.text
        return str(got.json()["error"]["message"])

    assert "숫자가 아닙니다" in make([{"두께": "얇게"}])
    assert "값이 없습니다" in make([{"두께": 4, "길이": 80}, {"두께": 5}])
    assert "표가 비었습니다" in make([])
    assert "레시피에 없는 치수" in make([{"높이": 3}])
    assert "1 줄이 제약을 어깁니다" in make(
        [{"두께": 4, "길이": 80}, {"두께": 12, "길이": 80}], constraints=["길이 >= 10 * 두께"]
    )


def test_점을_더하면_번호를_잇고_같은_값은_빼고_묶음을_남긴다(
    client: TestClient, member: Signed
) -> None:
    made = client.post(
        "/api/doe",
        json={
            "name": "두께 훑기",
            "recipe": JIG,
            "factors": [{"name": "두께", "mode": "list", "values": [4, 8]}],
            "conditions": {},
        },
        headers=member.headers,
    ).json()
    sent = client.post(f"/api/doe/{made['id']}/export", headers=member.headers)
    assert sent.status_code == 200 and sent.json()["export_stale"] is False

    narrower = {
        "method": "factorial",
        "factors": [{"name": "두께", "mode": "list", "values": [8, 10]}],
        "idempotency_key": "batch-2",
    }
    dry = client.post(
        f"/api/doe/{made['id']}/extend?dry_run=true", json=narrower, headers=member.headers
    )
    assert dry.status_code == 200, dry.text
    assert dry.json()["batch"]["added"] == 1 and dry.json()["batch"]["skipped"] == 1
    assert dry.json()["study"]["point_count"] == 2  # 세기만 했다

    got = client.post(f"/api/doe/{made['id']}/extend", json=narrower, headers=member.headers)
    assert got.status_code == 200, got.text
    batch = got.json()["batch"]
    assert (batch["number"], batch["from"], batch["to"], batch["added"]) == (2, 3, 3, 1)
    study = client.get(f"/api/doe/{made['id']}", headers=member.headers).json()
    assert study["point_count"] == 3 and study["done"] == 3
    assert [p["params"]["두께"] for p in study["points"]] == [4.0, 8.0, 10.0]
    assert study["batches"][0]["seed"] and study["export_stale"] is True
    rows = _manifest(client, member, made["id"])
    assert [row["point"] for row in rows] == ["1", "2", "3"]

    # 같은 열쇠로 다시 부르면 더하지 않는다.
    again = client.post(f"/api/doe/{made['id']}/extend", json=narrower, headers=member.headers)
    assert again.json()["batch"]["reused"] is True
    assert (
        client.get(f"/api/doe/{made['id']}", headers=member.headers).json()["point_count"] == 3
    )

    # 없는 변수는 더할 수 없다 · 새 점이 없으면 말한다.
    new_var = client.post(
        f"/api/doe/{made['id']}/extend",
        json={"method": "table", "table": [{"길이": 100}]},
        headers=member.headers,
    )
    assert (
        new_var.status_code == 400
        and "이 DOE 에 없는 변수" in new_var.json()["error"]["message"]
    )
    nothing = client.post(
        f"/api/doe/{made['id']}/extend",
        json={
            "method": "factorial",
            "factors": [{"name": "두께", "mode": "list", "values": [4]}],
        },
        headers=member.headers,
    )
    assert (
        nothing.status_code == 400
        and "더할 새 점이 없습니다" in nothing.json()["error"]["message"]
    )


BLOCK: dict[str, Any] = {
    "params": {"길이": 50.0},
    "nodes": [{"id": "블록", "op": "box", "length": "=길이", "width": 40, "height": 10}],
}
FACES = {
    "named_selections": [
        {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}},
        {"name": "윗면", "entity": "face", "select": {"what": "faces", "role": "top"}},
    ]
}
MEASURES = [
    {"name": "부피", "kind": "volume"},
    {"name": "높이", "kind": "size", "axis": "z"},
    {"name": "바닥_넓이", "kind": "region_area", "region": "바닥"},
    {"name": "판_사이", "kind": "distance", "a": "바닥", "b": "윗면"},
    {"name": "질량_kg", "kind": "expr", "expr": "부피 * 7.85e-6"},
]


def test_측정값은_점마다_재서_표의_열로_붙는다(client: TestClient, member: Signed) -> None:
    made = client.post(
        "/api/doe",
        json={
            "name": "길이 훑기",
            "recipe": BLOCK,
            "factors": [{"name": "길이", "mode": "list", "values": [50, 100]}],
            "conditions": FACES,
            "measures": MEASURES,
        },
        headers=member.headers,
    )
    assert made.status_code == 201, made.text
    study = client.get(f"/api/doe/{made.json()['id']}", headers=member.headers).json()
    first, second = (one["measures"] for one in study["points"])
    assert first == {
        "부피": pytest.approx(20000),
        "높이": pytest.approx(10),
        "바닥_넓이": pytest.approx(2000),
        "판_사이": pytest.approx(10),
        "질량_kg": pytest.approx(0.157),
    }
    assert second["부피"] == pytest.approx(40000) and second["바닥_넓이"] == pytest.approx(
        4000
    )
    rows = _manifest(client, member, study["id"])
    assert list(rows[0])[:8] == [
        "point",
        "status",
        "길이",
        "부피",
        "높이",
        "바닥_넓이",
        "판_사이",
        "질량_kg",
    ]
    assert float(rows[1]["부피"]) == pytest.approx(40000)


def test_측정값이_틀리면_만들기_전에_말한다(client: TestClient, member: Signed) -> None:
    def make(measures: list[dict[str, Any]]) -> str:
        got = client.post(
            "/api/doe",
            json={
                "name": "틀림",
                "recipe": BLOCK,
                "factors": [{"name": "길이", "mode": "list", "values": [50, 100]}],
                "conditions": FACES,
                "measures": measures,
            },
            headers=member.headers,
        )
        assert got.status_code == 400, got.text
        return str(got.json()["error"]["message"])

    assert "해석 조건에 없는 선택 그룹 옆면" in make(
        [{"name": "a", "kind": "region_area", "region": "옆면"}]
    )
    assert "겹칩니다" in make([{"name": "길이", "kind": "volume"}])
    assert "모르는 이름 밀도" in make([{"name": "m", "kind": "expr", "expr": "부피 * 밀도"}])
    assert "x · y · z" in make([{"name": "s", "kind": "size", "axis": "w"}])


def test_표본_방식_넷과_Sobol_은_더하면_이어_뽑는다(
    client: TestClient, member: Signed
) -> None:
    three = [
        {"name": "두께", "mode": "range", "start": 4, "end": 12, "steps": 3},
        {"name": "길이", "mode": "range", "start": 80, "end": 100, "steps": 3},
    ]
    counts = {}
    for method in ("oat", "ccd"):
        got = client.post(
            "/api/doe/preview",
            json={"factors": three, "method": method},
            headers=member.headers,
        )
        assert got.status_code == 200, got.text
        counts[method] = got.json()["count"]
    assert counts == {"oat": 5, "ccd": 9}
    bbd = client.post(
        "/api/doe/preview", json={"factors": three, "method": "bbd"}, headers=member.headers
    )
    assert bbd.status_code == 400 and "셋 이상" in bbd.json()["error"]["message"]
    unknown = client.post(
        "/api/doe/preview",
        json={"factors": three, "method": "taguchi"},
        headers=member.headers,
    )
    assert unknown.status_code == 400 and "모르는 방식" in unknown.json()["error"]["message"]

    made = client.post(
        "/api/doe",
        json={
            "name": "소볼",
            "recipe": JIG,
            "factors": three,
            "method": "sobol",
            "samples": 4,
            "seed": 3,
            "conditions": {},
        },
        headers=member.headers,
    ).json()
    more = client.post(
        f"/api/doe/{made['id']}/extend",
        json={"method": "sobol", "samples": 4},
        headers=member.headers,
    )
    assert more.status_code == 200, more.text
    assert more.json()["batch"]["seed"] == 3 and more.json()["batch"]["next"] == 8
    # 이어 뽑은 8점은 처음부터 8점을 뽑은 것과 같다.
    whole = client.post(
        "/api/doe/preview",
        json={"factors": three, "method": "sobol", "samples": 8, "seed": 3},
        headers=member.headers,
    ).json()["points"]
    study = client.get(f"/api/doe/{made['id']}", headers=member.headers).json()
    assert [p["params"] for p in study["points"]] == whole


def test_여러_프로세스로_나눠_만들어도_한_프로세스와_같다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """형상 만들기를 일꾼 둘로 나눠도 점 · 표 · 점검 · 측정값이 한 프로세스와 같다.
    조건만 훑는 변수(`압력`)가 있어 형상을 나눠 쓰는 점도 섞는다."""
    recipe = {**BLOCK, "params": {**BLOCK["params"], "압력": 1.0}}
    body = {
        "recipe": recipe,
        "factors": [
            {"name": "길이", "mode": "list", "values": [50, 70, 90]},
            {"name": "압력", "mode": "list", "values": [1, 2]},
        ],
        "conditions": FACES,
        "measures": MEASURES,
    }
    settings = get_settings()
    results = []
    for workers in (1, 2):
        settings.doe_workers = workers
        try:
            made = client.post(
                "/api/doe", json={"name": f"일꾼 {workers}", **body}, headers=member.headers
            )
        finally:
            settings.doe_workers = 1
        assert made.status_code == 201, made.text
        study = client.get(f"/api/doe/{made.json()['id']}", headers=member.headers).json()
        assert study["done"] == 6 and study["failed"] == 0
        results.append(
            (
                [
                    (p["number"], p["params"], p["step_file"], p["measures"])
                    for p in study["points"]
                ],
                [p["quality"]["min_wall"] for p in study["points"]],
                [
                    {k: v for k, v in row.items()}
                    for row in _manifest(client, member, study["id"])
                ],
            )
        )
    assert results[0] == results[1]
    # 압력만 다른 점은 형상을 나눠 쓴다 — `shapes/<지문>.step` 한 벌.
    assert (
        results[1][0][0][2].startswith("shapes/")
        and results[1][0][0][2] == results[1][0][1][2]
    )
