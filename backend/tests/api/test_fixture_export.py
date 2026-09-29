"""SimEngBay 에 건넬 **조건 픽스처** — 우리 내보내기 코드가 실제로 쓰는 폴더.

받는 쪽은 시험을 **양쪽이 실제로 낸 파일**로 돌린다(SimEngBay `docs/해석-연동-계획.md`). 손으로
짠 JSON 은 우리 코드가 바뀌어도 그대로라, 어긋난 줄을 아무도 모른다. 그래서 픽스처는 이 시험이
만든다 — 평소에는 내용이 맞는지 보기만 하고, `COMPCORE_FIXTURE_OUT` 을 주면 그 자리에 폴더를
복사한다::

    COMPCORE_FIXTURE_OUT=../fixtures/simengbay \
        .venv/bin/pytest tests/api/test_fixture_export.py

물성은 MatNexus 의 **실제 줄**(`tests/fixtures/matnexus/*.json`, 2026-09-28 스냅샷)을 화면이
싣는 모양 그대로 싣는다 — 시험 환경은 MatNexus 에 닿지 않는다.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from tests.api.conftest import Signed

MATNEXUS = Path(__file__).parents[1] / "fixtures" / "matnexus"


@pytest.fixture(autouse=True)
def property_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """MatNexus 물성 사전(2026-09-29 스냅샷). 시험은 MatNexus 에 닿지 않는데, 사전이 없으면
    물성 줄에 표준 열쇠(`mechanical.youngs_modulus`)가 안 붙어 픽스처가 「탄성계수가 없다」 고
    말했다."""
    from app.shared.clients import matnexus

    table = json.loads((MATNEXUS / "property_keys.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(matnexus, "property_keys", lambda: table)


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    """공유 폴더는 임시 폴더로 — 진짜 F: 드라이브에 쓰지 않는다."""
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _material(code: str, bodies: list[str]) -> dict[str, Any]:
    """화면(`ConditionsPanel` 의 물성 담기)이 싣는 모양 그대로 — payload 통째로."""
    row = json.loads((MATNEXUS / f"{code}.json").read_text(encoding="utf-8"))
    return {
        "apply_to": bodies,
        "ref": {
            "source": "matnexus",
            "material_id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "fetched_at": "2026-09-28T00:00:00Z",
        },
        "payload": row["payload"],
    }


def _face(name: str, select: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "entity": "face", "select": {"what": "faces", **select}}


#: ① **바디 둘 · 재료 둘** — 강판(SECC) 위에 알루미늄 블록(Al5052)을 본딩. 판 두께를 훑는다.
#: 받는 쪽이 「어느 Mechanical 바디가 어느 파트인가」 를 부피 · 무게중심으로 짝지을 자리.
TWO_BODIES: dict[str, Any] = {
    "name": "조건_두바디_두재료",
    "recipe": {
        "params": {"두께": 5.0},
        "nodes": [
            {
                "id": "받침판",
                "op": "box",
                "length": 100,
                "width": 60,
                "height": "=두께",
                "align": ["center", "center", "min"],
            },
            {
                "id": "블록",
                "op": "box",
                "length": 40,
                "width": 40,
                "height": 20,
                "at": [0, 0, "=두께"],
                "align": ["center", "center", "min"],
            },
            {"id": "조립", "op": "group", "targets": ["받침판", "블록"]},
        ],
    },
    "factors": [{"name": "두께", "mode": "list", "values": [5, 8]}],
    "conditions": {
        "units": {"system": "mm_n_tonne"},
        "named_selections": [
            _face("바닥", {"role": "bottom"}),
            _face("블록 윗면", {"role": "top", "near": [0, 0, 25]}),
            _face("판 윗면", {"kind": "plane", "normal": [0, 0, 1], "near": [40, 25, 5]}),
            _face("블록 아랫면", {"kind": "plane", "normal": [0, 0, -1], "near": [0, 0, 5]}),
        ],
        "materials": [
            _material("M-000138", ["받침판"]),
            _material("M-000158", ["블록"]),
        ],
        "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
        "loads": [
            {
                "name": "누름",
                "type": "pressure",
                "on": "블록 윗면",
                "magnitude": 1.5,
                "direction": "normal",
            }
        ],
        "contacts": [
            {
                "name": "블록-판",
                "type": "bonded",
                "source": "블록 아랫면",
                "target": "판 윗면",
            }
        ],
        "mesh_hints": [{"on": "전체", "element_size": 4, "order": "quadratic"}],
        "analysis": {"type": "static"},
    },
}

#: ② **SI 로 내보내기 · 원통면** — 구멍에 원통 지지(접선은 풀어 돈다) · 베어링 하중, 모달.
#: 값은 mm · N · t 로 적었고 점 파일에는 SI 로 옮겨져 나간다.
HOLE_SI: dict[str, Any] = {
    "name": "조건_원통_SI",
    "recipe": {
        "params": {"지름": 12.0},
        "nodes": [
            {
                "id": "판",
                "op": "box",
                "length": 80,
                "width": 50,
                "height": 10,
                "align": ["min", "center", "min"],
            },
            {"id": "구멍", "op": "hole", "target": "판", "at": [[20, 0]], "diameter": "=지름"},
        ],
    },
    "factors": [{"name": "지름", "mode": "list", "values": [10, 12]}],
    "conditions": {
        "units": {"system": "si"},
        "named_selections": [
            _face("구멍면", {"kind": "cylinder", "near": [20, 0, 5]}),
            _face("끝면", {"kind": "plane", "normal": [1, 0, 0], "near": [80, 0, 5]}),
        ],
        "materials": [_material("M-000158", ["전체"])],
        "constraints": [
            {
                "name": "핀",
                "type": "cylindrical",
                "on": "구멍면",
                "tangential": "free",
            }
        ],
        "loads": [
            {
                "name": "끝 누름",
                "type": "force",
                "on": "끝면",
                "magnitude": 200,
                "direction": [0, 0, -1],
            },
            {
                "name": "핀 하중",
                "type": "bearing",
                "on": "구멍면",
                "magnitude": 500,
                "direction": [1, 0, 0],
            },
        ],
        # 계가 바뀌면 숫자가 바뀌는 값 — 2 mm 가 점 파일에는 0.002 m 로 나간다.
        "mesh_hints": [{"on": "구멍면", "element_size": 2}],
        "analysis": {"type": "modal", "modes": 8, "frequency_range": [0, 5000]},
    },
}


#: ③ **재료 훑기** — 형상은 그대로, 블록의 재료만 Al5052 ↔ SECC 로 바꿔 끼운다. 두 점이 한
#: 형상(`shapes/<지문>.step`)을 나눠 쓰고, 점 파일의 `conditions.materials` 만 다르다.
MATERIAL_SWEEP: dict[str, Any] = {
    "name": "조건_재료훑기",
    "recipe": TWO_BODIES["recipe"],
    "factors": [
        {
            "name": "블록 재료",
            "mode": "material",
            "bodies": ["블록"],
            "values": ["AL5052H32DEMO_-_-", "SECC-EXAD87-DP_선언물성_0.8"],
        }
    ],
    "conditions": TWO_BODIES["conditions"],
}


#: ④ **조건을 훑는다** — 접촉 종류(본딩 ↔ 마찰)와 블록 탄성계수 배율(0.9 · 1.1)의 조합. 하중은
#: 인자가 아닌 도면 변수(`=압력`)를, 모드 수는 정수 칸의 식(`=모드수`)을 부른다.
CONDITION_SWEEP: dict[str, Any] = {
    "name": "조건_조건훑기",
    "recipe": {
        **TWO_BODIES["recipe"],
        "params": {**TWO_BODIES["recipe"]["params"], "압력": 1.5, "모드수": 10},
    },
    "factors": [
        {
            "name": "접촉 종류",
            "mode": "choice",
            "target": {"group": "contacts", "item": "블록-판", "field": "type"},
            "values": ["bonded", "frictional"],
        },
        {
            "name": "블록 탄성계수 배율",
            "mode": "scale",
            "bodies": ["블록"],
            "property": "탄성계수",
            "values": [0.9, 1.1],
        },
    ],
    "conditions": {
        **TWO_BODIES["conditions"],
        "loads": [{**TWO_BODIES["conditions"]["loads"][0], "magnitude": "=압력"}],
        # 마찰로 바꿔 볼 것이므로 마찰계수를 미리 적어 둔다(본딩에서는 쓰이지 않는다).
        "contacts": [{**TWO_BODIES["conditions"]["contacts"][0], "friction": 0.2}],
        "analysis": {"type": "modal", "modes": "=모드수"},
    },
}


def _export(client: TestClient, member: Signed, root: Path, study: dict[str, Any]) -> Path:
    made = client.post("/api/doe", json=study, headers=member.headers)
    assert made.status_code == 201, made.text
    done = client.post(f"/api/doe/{made.json()['id']}/export", headers=member.headers)
    assert done.status_code in (200, 201, 202), done.text
    prefix = study["name"].replace(" ", "_")
    return next(one for one in root.iterdir() if one.name.startswith(prefix))


def _points(folder: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((folder / "points").glob("p*.json"))
    ]


def test_조건_픽스처를_실제_내보내기로_만든다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    two = _export(client, member, export_root, TWO_BODIES)
    hole = _export(client, member, export_root, HOLE_SI)
    sweep = _export(client, member, export_root, MATERIAL_SWEEP)
    combo = _export(client, member, export_root, CONDITION_SWEEP)

    # ① 바디마다 재료가 따로 — 받는 쪽이 부피 · 무게중심으로 짝지을 수 있게 둘 다 실린다.
    for point in _points(two):
        bodies = {one["name"]: one for one in point["bodies"]}
        assert set(bodies) == {"받침판", "블록"}
        for one in bodies.values():
            assert one["volume"] > 0 and len(one["centroid"]) == 3
        materials = point["conditions"]["materials"]
        assert [one["apply_to"] for one in materials] == [["받침판"], ["블록"]]
        assert materials[0]["ref"]["code"] == "M-000138"
        assert materials[1]["ref"]["code"] == "M-000158"
        # 접촉 · 구속 · 하중의 선택 그룹이 이 점에서 풀렸다.
        assert point["unresolved"] == []
        assert point["conditions"]["analysis"]["type"] == "static"
    thick = [
        {one["name"]: one["volume"] for one in point["bodies"]}["받침판"]
        for point in _points(two)
    ]
    assert thick == [pytest.approx(30000), pytest.approx(48000)]

    # ② SI 로 옮겨져 나간다 — 베어링 500 N 은 그대로, 모달의 칸만.
    for point in _points(hole):
        conditions = point["conditions"]
        assert conditions["units"]["system"] == "si"
        assert point["unresolved"] == []
        bearing = next(one for one in conditions["loads"] if one["type"] == "bearing")
        assert bearing["magnitude"] == 500 and bearing["unit"] == "N"
        assert conditions["constraints"][0]["tangential"] == "free"
        assert conditions["mesh_hints"][0]["element_size"] == pytest.approx(0.002)
        assert set(conditions["analysis"]) == {
            "type",
            "modes",
            "frequency_range",
            "prestressed",
            "solver",
        }

    # ③ 재료만 바뀐다 — 형상 하나를 나눠 쓰고, 블록에 붙은 재료가 점마다 다르다.
    swept = _points(sweep)
    assert [one["point"]["params"]["블록 재료"] for one in swept] == [
        "AL5052H32DEMO_-_-",
        "SECC-EXAD87-DP_선언물성_0.8",
    ]
    assert swept[0]["point"]["step_file"] == swept[1]["point"]["step_file"]
    assert swept[0]["point"]["step_file"].startswith("shapes/")
    on_block = [
        [
            one["ref"]["code"]
            for one in point["conditions"]["materials"]
            if "블록" in one["apply_to"]
        ]
        for point in swept
    ]
    assert on_block == [["M-000158"], ["M-000138"]]
    # 받침판은 그대로 SECC — 한 바디에 재료 하나.
    for point in swept:
        plate = [
            one for one in point["conditions"]["materials"] if "받침판" in one["apply_to"]
        ]
        assert [one["ref"]["code"] for one in plate] == ["M-000138"]
    manifest = (sweep / "manifest.csv").read_text(encoding="utf-8-sig")
    assert "블록 재료" in manifest.splitlines()[0] and "AL5052H32DEMO_-_-" in manifest

    # ④ 조건 훑기 — 네 점이 한 형상을 나눠 쓰고, 접촉 종류 · 블록 탄성계수만 다르다.
    combos = _points(combo)
    assert len(combos) == 4 and len({one["point"]["step_file"] for one in combos}) == 1
    for point in combos:
        params = point["point"]["params"]
        conditions = point["conditions"]
        assert conditions["contacts"][0]["type"] == params["접촉 종류"]
        # 인자가 아닌 도면 변수(압력)와 정수 칸의 식(모드 수)도 풀린다.
        assert conditions["loads"][0]["magnitude"] == pytest.approx(1.5)
        assert conditions["analysis"]["modes"] == 10
        block = next(m for m in conditions["materials"] if "블록" in m["apply_to"])
        support = next(m for m in conditions["materials"] if "받침판" in m["apply_to"])
        youngs = next(
            r
            for r in block["converted"]["properties"]
            if r["key"] == "mechanical.youngs_modulus"
        )
        original = next(
            one for one in block["payload"]["declared_properties"] if one["item"] == "탄성계수"
        )["points"][0]["value_si"]
        # mm · N · t 로 옮긴 값(MPa)에 배율 — 원본(payload, Pa)은 그대로.
        assert youngs["points"][0]["value"] == pytest.approx(
            original / 1e6 * params["블록 탄성계수 배율"]
        )
        assert block["converted"]["scaled"] == {"탄성계수": params["블록 탄성계수 배율"]}
        assert "scaled" not in support["converted"]
        # 물성 사전이 있어 표준 열쇠가 붙고, 탄성계수를 「없다」 고 하지 않는다.
        assert "missing_structural" not in block["converted"]

    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out)
        target.mkdir(parents=True, exist_ok=True)
        for folder in (two, hole, sweep, combo):
            # 폴더 이름의 끝(스터디 id 여덟 자리)은 돌릴 때마다 달라진다 — 이름만 남긴다.
            name = folder.name.rsplit("-", 1)[0]
            shutil.rmtree(target / name, ignore_errors=True)
            shutil.copytree(folder, target / name)


def test_DOE_는_조건을_안_주면_작업의_현재_조건을_싣는다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """화면 · MCP 가 조건을 따로 실어 보내지 않아 DOE 폴더에 조건이 빠지고 있었다."""
    work = client.post(
        "/api/works",
        json={"name": "조건 따라가기", "recipe": TWO_BODIES["recipe"]},
        headers=member.headers,
    ).json()
    saved = client.put(
        f"/api/works/{work['id']}/versions/1/conditions",
        json={"conditions": TWO_BODIES["conditions"]},
        headers=member.headers,
    )
    assert saved.status_code == 200, saved.text
    study = {
        "name": "조건 따라가기",
        "recipe": TWO_BODIES["recipe"],
        "factors": TWO_BODIES["factors"],
        "work_id": work["id"],
    }
    made = client.post("/api/doe", json=study, headers=member.headers)
    assert made.status_code == 201, made.text
    assert made.json()["conditions"]["contacts"][0]["name"] == "블록-판"
    # 재료 인자도 작업의 조건에서 후보를 찾는다.
    swept = client.post(
        "/api/doe",
        json={**study, "name": "작업 재료 훑기", "factors": MATERIAL_SWEEP["factors"]},
        headers=member.headers,
    )
    assert swept.status_code == 201, swept.text
    # 빈 한 벌을 주면 형상만 훑는다.
    bare = client.post(
        "/api/doe", json={**study, "name": "형상만", "conditions": {}}, headers=member.headers
    )
    assert bare.status_code == 201 and bare.json()["conditions"] == {}


def test_재료_인자는_조건에_담긴_재료와_도면의_바디만_받는다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    def create(factor: dict[str, Any], conditions: dict[str, Any] | None = None) -> Any:
        body = {
            **MATERIAL_SWEEP,
            "factors": [factor],
            "conditions": TWO_BODIES["conditions"] if conditions is None else conditions,
        }
        return client.post("/api/doe", json=body, headers=member.headers)

    base = MATERIAL_SWEEP["factors"][0]
    bad = create({**base, "values": ["없는재료"]})
    assert bad.status_code >= 400 and "조건에 없습니다" in bad.text
    bad = create({**base, "bodies": ["다리"]})
    assert bad.status_code >= 400 and "도면에 없는 바디" in bad.text
    bad = create(base, conditions={})
    assert bad.status_code >= 400 and "조건에 재료가 없습니다" in bad.text


def test_남의_작업의_조건은_DOE_로_가져오지_못한다(
    client: TestClient, member: Signed, db: Session, export_root: Path
) -> None:
    """조건에는 그 사람의 물성 · 하중이 들어 있다 — 작업 id 만 알면 가져가게 두지 않는다."""
    from tests.api.conftest import _login, make_user

    work = client.post(
        "/api/works",
        json={"name": "내 것", "recipe": TWO_BODIES["recipe"]},
        headers=member.headers,
    ).json()
    other = make_user(db, label="other", is_system_admin=False)
    headers = {"Authorization": f"Bearer {_login(client, other.email)}"}
    got = client.post(
        "/api/doe",
        json={
            "name": "남의 조건",
            "recipe": TWO_BODIES["recipe"],
            "factors": TWO_BODIES["factors"],
            "work_id": work["id"],
        },
        headers=headers,
    )
    assert got.status_code == 403, got.text


def test_고르기_배율_인자가_틀리면_만들기_전에_말한다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    def create(factor: dict[str, Any]) -> Any:
        body = {**CONDITION_SWEEP, "name": "틀린 인자", "factors": [factor]}
        return client.post("/api/doe", json=body, headers=member.headers)

    choice = CONDITION_SWEEP["factors"][0]
    bad = create({**choice, "target": {**choice["target"], "item": "없는접촉"}})
    assert bad.status_code >= 400 and "없는접촉" in bad.text
    bad = create({**choice, "values": ["bonded", "sticky"]})
    assert bad.status_code >= 400 and "sticky" in bad.text
    scale = CONDITION_SWEEP["factors"][1]
    bad = create({**scale, "property": "없는물성"})
    assert bad.status_code >= 400 and "없는물성" in bad.text
    # 조건의 식이 도면에 없는 이름을 부르면 설계점을 만들기 전에 말한다.
    broken = {
        **CONDITION_SWEEP,
        "name": "모르는 이름",
        "conditions": {
            **CONDITION_SWEEP["conditions"],
            "loads": [{**CONDITION_SWEEP["conditions"]["loads"][0], "magnitude": "=없는것"}],
        },
    }
    bad = client.post("/api/doe", json=broken, headers=member.headers)
    assert bad.status_code >= 400 and "없는것" in bad.text


def test_재료를_훑는_바디의_배율은_후보마다_그_물성이_있어야_한다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """SECC(선언 물성)에는 항복강도가 없다 — 그 후보에서 배율이 조용히 빠지지 않게 막는다."""
    body = {
        **MATERIAL_SWEEP,
        "name": "항복강도 배율",
        "factors": [
            *MATERIAL_SWEEP["factors"],
            {
                "name": "항복강도 배율",
                "mode": "scale",
                "bodies": ["블록"],
                "property": "항복강도",
                "values": [0.9, 1.1],
            },
        ],
    }
    got = client.post("/api/doe", json=body, headers=member.headers)
    assert got.status_code >= 400, got.text
    assert "SECC" in got.text and "항복강도" in got.text
    # 둘 다 가진 물성(탄성계수)이면 된다.
    body["factors"][1] = {**body["factors"][1], "property": "탄성계수"}
    assert client.post("/api/doe", json=body, headers=member.headers).status_code == 201
