from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import Signed

BOX = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 40, "height": 30}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 10},
    ]
}


def test_스키마와_템플릿을_서버가_준다(client: TestClient, member: Signed) -> None:
    got = client.get("/api/cad/recipe/schema", headers=member.headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert "bracket" in body["templates"]
    assert body["template_labels"]["bracket"] == "L 브래킷"
    assert "$defs" in body["schema"]


def test_검증_미리보기_STEP(client: TestClient, member: Signed) -> None:
    check = client.post("/api/cad/recipe/check", json={"recipe": BOX}, headers=member.headers)
    assert check.json() == {"ok": True, "problems": []}

    bad = client.post(
        "/api/cad/recipe/check",
        json={
            "recipe": {"nodes": [{"id": "b", "op": "extrude", "sketch": "x", "distance": 1}]}
        },
        headers=member.headers,
    )
    assert bad.json()["ok"] is False and "앞에 없는 피처" in bad.json()["problems"][0]

    info = client.post("/api/cad/recipe/info", json={"recipe": BOX}, headers=member.headers)
    assert info.status_code == 200, info.text
    assert info.json()["summary"]["volume"] == 12000

    glb = client.post("/api/cad/recipe/preview", json={"recipe": BOX}, headers=member.headers)
    assert glb.status_code == 200 and glb.content[:4] == b"glTF"
    step = client.post("/api/cad/recipe/step", json={"recipe": BOX}, headers=member.headers)
    assert step.status_code == 200 and step.content.startswith(b"ISO-10303-21")


def test_STL_과_2D_도면으로도_받는다(client: TestClient, member: Signed) -> None:
    stl = client.post("/api/cad/recipe/stl", json={"recipe": BOX}, headers=member.headers)
    assert stl.status_code == 200 and stl.content.startswith(b"STL Exported")  # 바이너리 STL

    # 입체는 높이 절반에서 자른 단면이 2D 가 된다.
    dxf = client.post("/api/cad/recipe/dxf", json={"recipe": BOX}, headers=member.headers)
    assert dxf.status_code == 200 and b"SECTION" in dxf.content[:4000]

    svg = client.post("/api/cad/recipe/svg", json={"recipe": BOX}, headers=member.headers)
    assert svg.status_code == 200 and svg.content.lstrip().startswith(b"<?xml")
    assert b"mm" in svg.content[:400]

    # 스케치만 있어도 2D 는 나온다 — 도면은 원래 2D 다.
    sketch_only = {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rounded_rect", "width": 40, "height": 30, "radius": 5}],
            }
        ]
    }
    flat = client.post(
        "/api/cad/recipe/dxf", json={"recipe": sketch_only}, headers=member.headers
    )
    assert flat.status_code == 200 and len(flat.content) > 1000


def test_만들지_못하는_레시피는_노드를_말한다(client: TestClient, member: Signed) -> None:
    recipe = {
        "nodes": [
            *BOX["nodes"],
            {"id": "f", "op": "fillet", "target": "b", "edges": "all", "radius": 100},
        ]
    }
    got = client.post("/api/cad/recipe/info", json={"recipe": recipe}, headers=member.headers)
    assert got.status_code == 400
    assert got.json()["error"]["code"] == "CCR-CAD-0003"
    assert got.json()["error"]["details"]["node_id"] == "f"


def test_스케치만_있어도_미리보기는_보이고_저장은_거절(
    client: TestClient, member: Signed
) -> None:
    """처음부터 그리면 반드시 「스케치만 있는」 순간을 지난다 — 그때 빨간 오류가 뜨면 안
    된다."""
    sketch_only = {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rect", "width": 40, "height": 30}],
            }
        ]
    }
    info = client.post(
        "/api/cad/recipe/info", json={"recipe": sketch_only}, headers=member.headers
    )
    assert info.status_code == 200, info.text
    summary = info.json()["summary"]
    assert (
        summary["is_sketch"] is True and summary["solid_count"] == 0 and summary["volume"] == 0
    )
    assert summary["warnings"] and "돌출" in summary["warnings"][0]
    mesh = client.post(
        "/api/cad/recipe/mesh", json={"recipe": sketch_only}, headers=member.headers
    )
    assert mesh.status_code == 200 and len(mesh.json()["mesh"]["faces"]) == 1
    # STEP 과 저장은 입체여야 한다.
    step = client.post(
        "/api/cad/recipe/step", json={"recipe": sketch_only}, headers=member.headers
    )
    assert step.status_code == 400 and step.json()["error"]["details"]["node_id"] == "s"
    work = client.post(
        "/api/works", json={"name": "2D", "recipe": sketch_only}, headers=member.headers
    )
    assert work.status_code == 201  # 모양은 맞으니 저장은 되고
    assert (
        work.json()["current"]["job"]["status"] == "failed"
    )  # 평가가 「입체를 만드세요」 로 실패한다


def test_치수를_훑어_고르고_보_공진을_가늠한다(client: TestClient, member: Signed) -> None:
    """지그를 세트의 공진에 맞추는 흐름 — 연결부는 그대로, 튜닝부만 바꿔 가며 고른다."""
    jig = {
        "params": {"튜닝_두께": 6.0},
        "nodes": [
            {
                "id": "연결판",
                "op": "box",
                "length": 60,
                "width": 60,
                "height": 12,
                "align": ["min", "center", "min"],
            },
            {
                "id": "볼트",
                "op": "hole",
                "target": "연결판",
                "at": [[10, -22], [50, 22]],
                "thread": "M6",
            },
            {
                "id": "튜닝보",
                "op": "box",
                "length": 90,
                "width": 40,
                "height": "=튜닝_두께",
                "at": [60, 0, 0],
                "align": ["min", "center", "min"],
            },
            {"id": "지그", "op": "union", "targets": ["볼트", "튜닝보"]},
        ],
    }
    swept = client.post(
        "/api/cad/recipe/sweep",
        json={
            "recipe": jig,
            "param": "튜닝_두께",
            "values": [4, 6, 10],
            "material": "aluminum",
        },
        headers=member.headers,
    )
    assert swept.status_code == 200, swept.text
    rows = swept.json()["results"]
    assert [row["튜닝_두께"] for row in rows] == [4, 6, 10]
    masses = [row["geometry"]["mass"]["mass_g"] for row in rows]
    assert masses[0] < masses[1] < masses[2]  # 두꺼울수록 무겁다
    # 연결부는 어떤 값에서도 그대로다 — 구멍 자리가 같다.
    holes = [sorted(tuple(h["at"]) for h in row["geometry"]["holes"]) for row in rows]
    assert holes[0] == holes[1] == holes[2]

    missing = client.post(
        "/api/cad/recipe/sweep",
        json={"recipe": jig, "param": "없는치수", "values": [1]},
        headers=member.headers,
    )
    assert missing.status_code == 400 and "없습니다" in missing.json()["error"]["message"]

    tuned = client.post(
        "/api/cad/beam-frequency",
        json={"target_hz": 440, "length_mm": 90, "width_mm": 40, "added_mass_g": 120},
        headers=member.headers,
    )
    assert tuned.status_code == 200
    assert 10 < tuned.json()["thickness_mm"] < 11
    assert "가늠값" in tuned.json()["accuracy"]

    too_high = client.post(
        "/api/cad/beam-frequency",
        json={"target_hz": 500000, "length_mm": 200, "width_mm": 20},
        headers=member.headers,
    )
    assert too_high.status_code == 400 and "짧게" in too_high.json()["error"]["message"]


def test_그림_찾기_재기_는_AI_가_좌표를_짐작하지_않게_한다(
    client: TestClient, member: Signed
) -> None:
    """AI 는 3D 를 못 본다 — 그림(PNG)으로 확인하고, 말로 고른 엣지 · 면의 좌표를 받고, 둘
    사이를 서버가 재 준다."""
    recipe = {
        "nodes": [
            {"id": "판", "op": "box", "length": 80, "width": 50, "height": 20},
            {"id": "구멍", "op": "hole", "target": "판", "diameter": 8, "at": [[20, 10]]},
        ]
    }
    views = client.post(
        "/api/cad/recipe/views",
        json={"recipe": recipe, "views": ["iso", "top"], "width": 300},
        headers=member.headers,
    )
    assert views.status_code == 200, views.text
    got = views.json()["views"]
    assert set(got) == {"iso", "top"}
    assert got["top"]["svg"].startswith("<?xml") and len(got["top"]["png_base64"]) > 100
    bad = client.post(
        "/api/cad/recipe/views",
        json={"recipe": recipe, "views": ["back"]},
        headers=member.headers,
    )
    assert bad.status_code == 400 and "back" in bad.json()["error"]["message"]

    # 윗면 테두리의 직선 엣지 — 필렛에 넣을 near 점이 바로 나온다.
    rim = client.post(
        "/api/cad/recipe/find",
        json={
            "recipe": recipe,
            "query": {"what": "edges", "of_face_role": "top", "kind": "line"},
        },
        headers=member.headers,
    ).json()
    assert rim["total"] == 4 and all(
        one["midpoint"][2] == 10 for one in rim["items"]
    )  # 상자는 원점 중심
    # 지름 8 구멍의 원 — 위 · 아래 둘. near 로 가까운 순.
    circles = client.post(
        "/api/cad/recipe/find",
        json={
            "recipe": recipe,
            "query": {"kind": "circle", "radius": 4, "near": [20, 10, 20]},
        },
        headers=member.headers,
    ).json()
    assert circles["total"] == 2 and circles["items"][0]["center"][2] == 10
    faces = client.post(
        "/api/cad/recipe/find",
        json={"recipe": recipe, "query": {"what": "faces", "role": "top"}},
        headers=member.headers,
    ).json()
    assert faces["total"] == 1 and faces["items"][0]["normal"] == [0, 0, 1]

    # 점 — 꼭짓점(엣지 셋)과 구멍 테두리의 점(엣지 둘)이 갈린다.
    corners = client.post(
        "/api/cad/recipe/find",
        json={"recipe": recipe, "query": {"what": "vertices", "edges": 3}},
        headers=member.headers,
    ).json()
    assert corners["total"] == 8, "상자의 꼭짓점 여덟"
    assert all(one["kind"] == "vertex" and len(one["point"]) == 3 for one in corners["items"])

    # **찍은 자리를 말로 되돌려 준다.** 좌표를 조건에 박으면 치수를 바꾸는 순간 그 자리에
    # 아무것도 없다 — 셀렉터로 저장해야 설계점마다 다시 풀린다.
    back = client.post(
        "/api/cad/recipe/selectors",
        json={"recipe": recipe, "pick": {"what": "faces", "point": [0, 0, 10]}},
        headers=member.headers,
    ).json()
    labels = {one["label"]: one for one in back["candidates"]}
    assert "top 면" in labels and labels["top 면"]["select"] == {
        "what": "faces",
        "role": "top",
    }
    assert labels["top 면"]["matches"] == 1
    # 「이 자리의 면」 은 **찍은 자리**를 그대로 쓴다(원통면의 center 는 표면 위의 점이라
    # 사람이 읽으면 엉뚱해 보인다). 그리고 하나만 집는다.
    assert labels["이 자리의 면"]["select"]["near"] == [0, 0, 10]
    assert labels["이 자리의 면"]["matches"] == 1

    # 구멍을 찍으면 **그 부류를 잡는 후보**가 함께 온다(이 레시피엔 구멍이 하나라 1).
    # 여럿일 때 한꺼번에 잡는 것은 `test_core_query.py` 가 못 박는다.
    hole = client.post(
        "/api/cad/recipe/selectors",
        json={"recipe": recipe, "pick": {"what": "faces", "point": [20, 10, 5]}},
        headers=member.headers,
    ).json()
    group = [one for one in hole["candidates"] if one["select"].get("kind") == "cylinder"]
    assert group and group[0]["matches"] == 1

    bad_pick = client.post(
        "/api/cad/recipe/selectors",
        json={"recipe": recipe, "pick": {"what": "faces"}},
        headers=member.headers,
    )
    assert bad_pick.status_code == 400 and "point" in bad_pick.json()["error"]["message"]

    # 재기 — 윗면과 바닥면 사이(두께), 구멍 중심에서 모서리까지.
    got = client.post(
        "/api/cad/recipe/measure",
        json={
            "recipe": recipe,
            "a": {"face_near": [0, 0, 10]},
            "b": {"face_near": [0, 0, -10]},
        },
        headers=member.headers,
    ).json()
    assert got["angle"] == 0 and got["gap"] == 20
    got = client.post(
        "/api/cad/recipe/measure",
        json={
            "recipe": recipe,
            "a": {"hole_near": [20, 10, 10]},
            "b": {"point": [-40, -25, 0]},
        },
        headers=member.headers,
    ).json()
    assert got["a"]["diameter"] == 8 and got["delta"] == [-60, -35, 0]
