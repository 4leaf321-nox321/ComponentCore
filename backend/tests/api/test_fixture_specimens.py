"""시험 규격 픽스처 — **종류마다 하나씩** 실제 내보내기 코드로 「설계 하나」 폴더를 만든다.

v0.11.0 에 시험 16종이 들어왔다. 화면 · 조건까지는 시험이 지키지만(`test_specimens.py`),
해석 쪽이 그 조건을 실제로 거는지는 받는 쪽에서 풀어 봐야 안다. 그래서 종류마다 대표 프리셋
하나로 작업을 만들고(시편은 규격 그대로, 제품 시험은 구멍 판에 건다) 물성을 담아 내보낸다.
평소에는 폴더가 온전한지 — 영역을 다 찾았나, 해석 종류가 적혔나 — 만 보고,
`COMPCORE_FIXTURE_OUT` 을 주면 복사한다::

    COMPCORE_FIXTURE_OUT=../fixtures/simengbay/시험규격 \\
        .venv/bin/pytest tests/api/test_fixture_specimens.py
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core import conditions as condition_model
from tests.api.conftest import Signed
from tests.api.test_fixture_export import _material, export_root, property_keys  # noqa: F401

#: (폴더 이름, 프리셋, 시편이면 None · 제품 시험이면 더 줄 칸). 제품 시험의 면은
#: 「윗면」 · 「옆면」 이름으로 적고 제품 메시에서 골라 넣는다.
CASES: list[tuple[str, str, dict[str, Any] | None]] = [
    # 시편
    ("시험_인장_E8", "astm-e8-sheet", None),
    ("시험_오픈홀인장_D5766", "astm-d5766", None),
    ("시험_압축_D695", "astm-d695-prism", None),
    ("시험_오픈홀압축_D6484", "astm-d6484", None),
    ("시험_핀베어링_D5961", "astm-d5961-a", None),
    ("시험_뽑힘_D7332", "astm-d7332-example", None),
    ("시험_겹치기이음_D1002", "astm-d1002", None),
    ("시험_V노치전단_D5379", "astm-d5379", None),
    ("시험_숏빔전단_D2344", "astm-d2344", None),
    ("시험_보드굽힘_JESD22", "jesd22-b113", None),
    # 제품에 거는 시험
    ("시험_정하중_T2", "iec-62368-1-t2", {}),
    ("시험_진동_150Hz", "iec-60068-2-6-150-1g", {}),
    ("시험_랜덤진동", "iec-60068-2-64-example-6g", {}),
    ("시험_고유진동수", "iec-60068-2-6-vri-150", {}),
    ("시험_적층압축", "ista-stack-5x3", {"mass": 1.5}),
    ("시험_비틀림", "twist-example-6deg", {}),
    ("시험_손잡이", "iec-62368-1-8.8-handle", {"faces": {"support": "윗면"}}),
    ("시험_압착", "iec-62133-2-crush", {"faces": {"load": "옆면"}}),
    ("시험_수압_IPX7", "iec-60529-ipx7", {}),
    ("시험_가속도_15g", "iec-60068-2-27-15g-11ms", {}),
    (
        "시험_방향하중",
        "iec-60335-1-cord-1kg",
        {"faces": {"load": "옆면"}, "direction": [0, 0, 1]},
    ),
]

FACE_NORMALS = {"윗면": [0, 0, 1], "옆면": [1, 0, 0]}


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201, 202), response.text
    return response.json()


def _product(client: TestClient, member: Signed) -> str:
    """구멍 판(80 x 50 x 10, 알루미늄) — 제품 시험을 거는 자리."""
    from tests.api.test_works import _plate, _work

    product = _work(client, member, _plate(client, member))
    _ok(
        client.put(
            f"/api/works/{product['id']}/versions/1/conditions",
            json={"conditions": {"materials": [_material("M-000158", ["전체"])]}},
            headers=member.headers,
        )
    )
    return f"work:{product['id']}"


def _picked(
    client: TestClient, member: Signed, source: str, extra: dict[str, Any]
) -> dict[str, Any]:
    """「윗면」 · 「옆면」 을 제품 메시에서 골라 화면이 보내는 모양으로 바꾼다."""
    faces = extra.get("faces")
    if not faces:
        return extra
    mesh = _ok(
        client.post(
            "/api/specimens/product-mesh", json={"source": source}, headers=member.headers
        )
    )["mesh"]["faces"]
    picks = {}
    for role, which in faces.items():
        face = next(one for one in mesh if one["normal"] == FACE_NORMALS[which])
        picks[role] = [
            {"point": face["center"], "normal": face["normal"], "kind": face["kind"]}
        ]
    return {**extra, "faces": picks}


@pytest.mark.parametrize(("name", "preset", "extra"), CASES, ids=[one[0] for one in CASES])
def test_시험_규격마다_설계_하나_폴더가_온전히_나간다(
    client: TestClient,
    member: Signed,
    export_root: Path,  # noqa: F811
    name: str,
    preset: str,
    extra: dict[str, Any] | None,
) -> None:
    if extra is None:
        work = _ok(
            client.post(
                "/api/specimens/works", json={"preset_id": preset}, headers=member.headers
            )
        )
    else:
        source = _product(client, member)
        body = {
            "preset_id": preset,
            "source": source,
            **_picked(client, member, source, extra),
        }
        work = _ok(
            client.post("/api/specimens/product-tests", json=body, headers=member.headers)
        )
    first = _ok(client.get(f"/api/works/{work['id']}/versions/1", headers=member.headers))
    assert first["job"]["status"] == "done", first["job"]
    conditions = dict(first["conditions"])
    # 시편의 물성은 비어 있다 — 비어 있는 파트에만 담는다. 강체 지그에는 생성기가 붙인 기본
    # 강재가 이미 있다(2026-10-23, 해석은 지그도 재료가 있어야 건다).
    names = [
        one["name"]
        for one in _ok(
            client.post(
                "/api/cad/recipe/bodies",
                json={"recipe": first["recipe"]},
                headers=member.headers,
            )
        )["items"]
    ]
    bare = condition_model.unmaterialed(conditions, names)
    if bare:
        whole = not conditions.get("materials")
        conditions["materials"] = [
            *(conditions.get("materials") or []),
            _material("M-000138", ["전체"] if whole else bare),
        ]

    study = _ok(
        client.post(
            "/api/doe",
            json={
                "name": name,
                "recipe": first["recipe"],
                "conditions": conditions,
                "factors": [],
            },
            headers=member.headers,
        )
    )
    _ok(client.post(f"/api/doe/{study['id']}/export", headers=member.headers))
    folder = next(one for one in export_root.iterdir() if one.name.startswith(name))

    point = json.loads((folder / "points" / "p0001.json").read_text(encoding="utf-8"))
    assert point["unresolved"] == [], f"{name}: 영역을 못 찾았다 {point['unresolved']}"
    assert point["conditions"]["analysis"]["type"] in ("static", "modal", "harmonic", "random")
    assert point["conditions"]["materials"], f"{name}: 물성이 없다"
    bodies = [one["name"] for one in point["bodies"]]
    assert condition_model.unmaterialed(point["conditions"], bodies) == [], (
        f"{name}: 재료가 빈 파트 — 해석 쪽이 걸지 않는다"
    )
    for region, found in point["regions"].items():
        assert found, f"{name}: 선택 그룹 ‘{region}’ 이 비었다"

    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out) / name
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(folder, target)


def test_랜덤_진동의_축을_설계점마다_나눈_폴더(
    client: TestClient,
    member: Signed,
    export_root: Path,  # noqa: F811
) -> None:
    """IEC 처럼 X · Y · Z 를 한 축씩 거는 시험 — 한 조건의 가진은 동시라(PSD 여럿은 합산) 축은
    설계점으로 나눈다. 고르기 인자가 하중 방향에 축 이름을 주고, 점 파일에는 성분으로 나간다
    (2026-11-17, SimEngBay 가 「축을 어떻게 나타내는지」 물었다)."""
    source = _product(client, member)
    work = _ok(
        client.post(
            "/api/specimens/product-tests",
            json={"preset_id": "iec-60068-2-64-example-6g", "source": source},
            headers=member.headers,
        )
    )
    first = _ok(client.get(f"/api/works/{work['id']}/versions/1", headers=member.headers))
    (load,) = first["conditions"]["loads"]
    axis = {"group": "loads", "item": load["name"], "field": "direction"}
    factor = {"name": "가진 축", "mode": "choice", "target": axis, "values": ["x", "y", "z"]}
    body = {
        "name": "시험_랜덤진동_축셋",
        "recipe": first["recipe"],
        "conditions": first["conditions"],
        "factors": [factor],
    }
    wrong = client.post(
        "/api/doe",
        json={**body, "factors": [{**factor, "values": ["x", "w"]}]},
        headers=member.headers,
    )
    assert wrong.status_code == 400
    assert "받을 수 없는 값: w" in wrong.json()["error"]["message"]
    study = _ok(client.post("/api/doe", json=body, headers=member.headers))
    _ok(client.post(f"/api/doe/{study['id']}/export", headers=member.headers))
    folder = next(one for one in export_root.iterdir() if one.name.startswith(body["name"]))

    points = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((folder / "points").glob("p*.json"))
    ]
    directions = [one["conditions"]["loads"][0]["direction"] for one in points]
    assert directions == [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "한 점에 한 축 — 성분으로"
    assert all(len(one["conditions"]["loads"]) == 1 for one in points)
    assert all(one["unresolved"] == [] for one in points)
    manifest = (folder / "manifest.csv").read_text(encoding="utf-8-sig").splitlines()
    assert [line.split(",")[2] for line in manifest[1:]] == ["x", "y", "z"]
    assert len({line.split(",")[3] for line in manifest[1:]}) == 1, "형상은 하나를 나눠 쓴다"

    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out) / body["name"]
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(folder, target)
