"""도면에 묻기 — **엣지 · 면 찾기**와 **재기**. AI 가 좌표를 짐작하지 않게.

필렛 · 모따기는 `near` 점으로 엣지를 가리키고, 스케치는 면의 `plane` 을 가리킨다. 사람은 3D 를
눌러 고르지만 AI 는 못 본다 — 그래서 「윗면의 바깥 엣지」 「지름 8 구멍의 위 원」 처럼 **말로
고르면 좌표를 돌려주는** 질의와, 두 것 사이 거리 · 각도를 재는 계산을 서버가 한다.
"""

from __future__ import annotations

import math
from typing import Any

from build123d import Edge, Face, GeomType, Shape, Vector, Vertex

_AXIS_COS = 0.95
_LIMIT = 60


def _xyz(v: Any) -> list[float]:
    return [round(float(v.X), 3), round(float(v.Y), 3), round(float(v.Z), 3)]


def _dist(a: list[float], b: list[float]) -> float:
    return math.dist(a, b)


# --- 엣지 · 면 목록 -------------------------------------------------------------


def _face_role(face: Face, box_min_z: float, box_max_z: float) -> str:
    normal = face.normal_at(face.center())
    z = face.center().Z
    if normal.Z > _AXIS_COS:
        return "top" if abs(z - box_max_z) < 0.5 else "step"
    if normal.Z < -_AXIS_COS:
        return "bottom" if abs(z - box_min_z) < 0.5 else "underside"
    if abs(normal.Z) < 1 - _AXIS_COS:
        return "side"
    return "slanted"


def _edge_row(index: int, edge: Edge) -> dict[str, Any]:
    kind = edge.geom_type.name.lower()
    tangent = edge.tangent_at(0.5)
    row: dict[str, Any] = {
        "index": index,
        "kind": kind,
        "length": round(float(edge.length), 3),
        "midpoint": _xyz(edge.position_at(0.5)),
        "start": _xyz(edge.position_at(0)),
        "end": _xyz(edge.position_at(1)),
        "direction": _xyz(tangent),
    }
    if kind == "line":
        row["axis"] = (
            "z"
            if abs(tangent.Z) > _AXIS_COS
            else "x"
            if abs(tangent.X) > _AXIS_COS
            else "y"
            if abs(tangent.Y) > _AXIS_COS
            else None
        )
    try:
        row["radius"] = round(float(edge.radius), 3)
        row["center"] = _xyz(edge.arc_center)
    except Exception:
        pass
    return row


def _vertex_row(index: int, vertex: Vertex, shape: Shape) -> dict[str, Any]:
    """점 하나 — 좌표와 **거기 모이는 엣지 수**.

    엣지 수가 있어야 「모서리 꼭짓점(3개)」 과 「구멍 테두리 위의 점(2개)」 을 가른다. 좌표만
    보면 같은 점이 여럿이고, 사람은 셋 중 무엇을 고른 것인지 말할 수 없다.
    """
    point = vertex.to_tuple()
    return {
        "index": index,
        "kind": "vertex",
        "point": [round(float(v), 3) for v in point],
        "edges": sum(
            1 for edge in shape.edges() if any(v.to_tuple() == point for v in edge.vertices())
        ),
    }


def _face_row(index: int, face: Face, box_min_z: float, box_max_z: float) -> dict[str, Any]:
    kind = face.geom_type.name.lower()
    row: dict[str, Any] = {
        "index": index,
        "kind": kind,
        "area": round(float(face.area), 2),
        "center": _xyz(face.center()),
    }
    if kind == "plane":
        row["normal"] = _xyz(face.normal_at(face.center()))
        row["role"] = _face_role(face, box_min_z, box_max_z)
    try:
        row["radius"] = round(float(face.radius), 3)
        axis = face.axis_of_rotation
        if axis is not None:
            row["axis"] = {"origin": _xyz(axis.position), "direction": _xyz(axis.direction)}
    except Exception:
        pass
    return row


def find_features(
    shape: Shape, query: dict[str, Any], tags: dict[str, list[int]] | None = None
) -> dict[str, Any]:
    """말로 고른 엣지 · 면의 좌표.

    query:
      what        edges | faces | vertices
      kind        line | circle | arc | plane | cylinder … (엣지 · 면의 기하 종류)
      role        top | bottom | side | step | underside (면)
      of_face_role  이 역할의 **가장 넓은 면**에 속한 엣지만 (예: top → 윗면 테두리)
      axis        x | y | z (직선 엣지의 방향)
      radius      이 반지름(±0.05)의 원 · 원통만
      min_length / max_length
      tag         `divide_face` 가 붙인 이름 — 그 패치의 면만. `tags` 를 줘야 듣는다
      edges       이 점에 모이는 엣지 수(점) — 꼭짓점 3 · 구멍 테두리 2
      near        [x, y, z] — 이 점에서 가까운 순으로
      limit       기본 60
    답의 `midpoint`(엣지) · `center`(면) · `point`(점)를 그대로 `near` 나 `plane` 에 쓴다.
    """
    what = query.get("what", "edges")
    box = shape.bounding_box()
    z_lo, z_hi = float(box.min.Z), float(box.max.Z)
    limit = int(query.get("limit") or _LIMIT)
    near = query.get("near")

    if what == "vertices":
        rows = [_vertex_row(i, v, shape) for i, v in enumerate(shape.vertices())]
        if query.get("edges") is not None:
            rows = [r for r in rows if r["edges"] == int(query["edges"])]
        key = "point"
    elif what == "faces":
        rows = [_face_row(i, f, z_lo, z_hi) for i, f in enumerate(shape.faces())]
        if query.get("tag"):
            # **번호는 이 평가 안에서만 뜻이 있다.** 그래서 저장하지 않고 평가가 찾아 준
            # 것(`Evaluation.tags`)을 받아 쓴다 — 설계점이 바뀌면 그때 다시 찾는다.
            wanted = set((tags or {}).get(str(query["tag"]), []))
            rows = [r for r in rows if r["index"] in wanted]
        if query.get("kind"):
            rows = [r for r in rows if r["kind"] == query["kind"]]
        if query.get("role"):
            rows = [r for r in rows if r.get("role") == query["role"]]
        if query.get("radius") is not None:
            rows = [
                r for r in rows if abs(r.get("radius", -1) - float(query["radius"])) <= 0.05
            ]
        key = "center"
    else:
        edges: list[tuple[int, Edge]] = list(enumerate(shape.edges()))
        if query.get("of_face_role"):
            faces = [
                f
                for f in shape.faces().filter_by(GeomType.PLANE)
                if _face_role(f, z_lo, z_hi) == query["of_face_role"]
            ]
            if faces:
                widest = max(faces, key=lambda f: f.area)
                rim = list(widest.edges())
                edges = [(i, e) for i, e in edges if any(e.is_same(w) for w in rim)]
            else:
                edges = []
        rows = [_edge_row(i, e) for i, e in edges]
        if query.get("kind"):
            rows = [r for r in rows if r["kind"] == query["kind"]]
        if query.get("axis"):
            rows = [r for r in rows if r.get("axis") == query["axis"]]
        if query.get("radius") is not None:
            rows = [
                r for r in rows if abs(r.get("radius", -1) - float(query["radius"])) <= 0.05
            ]
        if query.get("min_length") is not None:
            rows = [r for r in rows if r["length"] >= float(query["min_length"])]
        if query.get("max_length") is not None:
            rows = [r for r in rows if r["length"] <= float(query["max_length"])]
        key = "midpoint"

    if near:
        point = [float(v) for v in near]
        for r in rows:
            r["distance_from_near"] = round(_dist(r[key], point), 3)
        rows.sort(key=lambda r: r["distance_from_near"])
    return {"what": what, "total": len(rows), "items": rows[:limit]}


def select_features(
    shape: Shape, select: dict[str, Any], tags: dict[str, list[int]] | None = None
) -> dict[str, Any]:
    """선택 그룹의 셀렉터를 푼다 — 하나면 `find_features` 그대로, `{"any": [...]}` 면 **합**.

    3D 에서 면을 하나씩 골라(Ctrl · Shift) 한 그룹으로 묶으면, 규칙 하나로는 그 모음을 말할 수
    없다(「윗면과 왼쪽 구멍 하나」). 그래서 고른 것마다 제 규칙을 두고 그 합을 그룹으로 한다 —
    규칙마다 설계점에서 다시 풀리므로 치수를 바꿔도 같은 것들을 가리킨다.

    두 규칙이 같은 것을 집으면 **한 번만** 센다(번호로 가른다) — 안 그러면 받는 쪽이 같은 면에
    하중을 두 번 건다.
    """
    members = select.get("any")
    if not isinstance(members, list):
        return find_features(shape, select, tags)
    what = next(
        (one.get("what") for one in members if isinstance(one, dict) and one.get("what")),
        "faces",
    )
    seen: set[int] = set()
    items: list[dict[str, Any]] = []
    for member in members:
        for row in find_features(shape, member, tags)["items"]:
            if row["index"] in seen:
                continue
            seen.add(row["index"])
            items.append(row)
    return {"what": what, "total": len(items), "items": items}


# --- 재기 -------------------------------------------------------------------------


def _resolve(shape: Shape, selector: dict[str, Any]) -> dict[str, Any]:
    """선택자 하나를 점 · 면 · 구멍으로.

    {point:[…]} | {face_near:[…]} | {hole_near:[…]} | {edge_near:[…]}"""
    if "point" in selector:
        return {"kind": "point", "at": [float(v) for v in selector["point"]]}
    if "hole_near" in selector:
        point = Vector(*selector["hole_near"])
        best = None
        for face in shape.faces().filter_by(GeomType.CYLINDER):
            axis = face.axis_of_rotation
            if axis is None:
                continue
            d = (face.center() - point).length
            if best is None or d < best[0]:
                best = (d, face, axis)
        if best is None:
            raise ValueError("원통(구멍)이 없습니다")
        _d, face, axis = best
        origin = axis.position
        return {
            "kind": "hole",
            "at": _xyz(Vector(origin.X, origin.Y, face.center().Z)),
            "axis": _xyz(axis.direction),
            "diameter": round(float(face.radius) * 2, 3),
        }
    if "face_near" in selector:
        point = Vector(*selector["face_near"])
        face = min(shape.faces(), key=lambda f: (f.center() - point).length)
        row: dict[str, Any] = {"kind": "face", "at": _xyz(face.center())}
        if face.geom_type == GeomType.PLANE:
            row["normal"] = _xyz(face.normal_at(face.center()))
        return row
    if "edge_near" in selector:
        point = Vector(*selector["edge_near"])
        edge = min(shape.edges(), key=lambda e: (e.position_at(0.5) - point).length)
        return {
            "kind": "edge",
            "at": _xyz(edge.position_at(0.5)),
            "length": round(float(edge.length), 3),
        }
    raise ValueError("선택자는 point · hole_near · face_near · edge_near 중 하나입니다")


def measure(shape: Shape, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """둘 사이를 잰다 — 점끼리 거리(축별 차), 평면끼리 각도(평행이면 간격), 점과 평면의 수직
    거리."""
    one, two = _resolve(shape, a), _resolve(shape, b)
    out: dict[str, Any] = {"a": one, "b": two}
    pa, pb = one["at"], two["at"]
    delta = [round(y - x, 3) for x, y in zip(pa, pb, strict=True)]
    out["distance"] = round(_dist(pa, pb), 3)
    out["delta"] = delta
    na, nb = one.get("normal"), two.get("normal")
    if na and nb:
        cos = max(-1.0, min(1.0, sum(x * y for x, y in zip(na, nb, strict=True))))
        angle = math.degrees(math.acos(abs(cos)))
        out["angle"] = round(angle, 3)
        if angle < 0.5:
            out["gap"] = round(abs(sum(d * n for d, n in zip(delta, na, strict=True))), 3)
    elif na or nb:
        normal, point, plane_point = (na, pb, pa) if na else (nb, pa, pb)
        assert normal is not None
        d = [p - q for p, q in zip(point, plane_point, strict=True)]
        out["normal_distance"] = round(
            abs(sum(x * n for x, n in zip(d, normal, strict=True))), 3
        )
    return out


# --- 고른 것을 말로 되돌려 주기 -------------------------------------------------


def _face_candidates(
    row: dict[str, Any], point: list[float]
) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    role = row.get("role")
    if role:
        out.append((f"{role} 면", {"what": "faces", "role": role}))
    if row.get("radius") is not None:
        out.append(
            (
                f"반지름 {row['radius']} 원통면",
                {"what": "faces", "kind": row["kind"], "radius": row["radius"]},
            )
        )
    # **찍은 자리를 그대로 쓴다.** 원통면의 `center` 는 축이 아니라 표면 위의 점이라
    # (topology.py 머리말) 사람이 읽으면 엉뚱한 좌표로 보인다.
    out.append(("이 자리의 면", {"what": "faces", "near": point, "limit": 1}))
    return out


def _edge_candidates(
    row: dict[str, Any], point: list[float]
) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if row.get("radius") is not None:
        out.append(
            (
                f"반지름 {row['radius']} 원",
                {"what": "edges", "kind": row["kind"], "radius": row["radius"]},
            )
        )
    if row.get("axis"):
        out.append(
            (
                f"{row['axis']} 방향 직선 엣지",
                {"what": "edges", "kind": row["kind"], "axis": row["axis"]},
            )
        )
    out.append(("이 자리의 엣지", {"what": "edges", "near": point, "limit": 1}))
    return out


def _vertex_candidates(
    row: dict[str, Any], point: list[float]
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (f"엣지 {row['edges']}개가 모이는 점", {"what": "vertices", "edges": row["edges"]}),
        ("이 자리의 점", {"what": "vertices", "near": point, "limit": 1}),
    ]


def selector_candidates(shape: Shape, pick: dict[str, Any]) -> dict[str, Any]:
    """3D 에서 **고른 것을 말로 되돌려 준다** — 좌표가 아니라 셀렉터로.

    왜 좌표로 저장하지 않나: 실험계획은 치수를 바꿔 형상을 여러 벌 만든다. 「(30, 15, 5) 의
    면」 은 두께를 바꾸는 순간 그 자리에 없다. 「아래쪽 면」 · 「반지름 4.25 원통면」 은
    남는다.

    그래서 후보를 **여럿** 주고 사람이 고르게 한다. 하나만 자동으로 정하면, 「볼트 구멍 넷
    전부」 를 원했는데 「이 구멍 하나」 가 저장되는 날이 온다 — 그 사실은 설계점 스무 개를
    돌린 뒤에야 보인다. 그래서 **지금 몇 개에 맞는지**(`matches`)를 함께 돌려준다.
    """
    what = pick.get("what", "faces")
    point = pick.get("point")
    if not isinstance(point, list) or len(point) != 3:
        raise ValueError("pick.point: [x, y, z] 가 필요합니다")

    found = find_features(shape, {"what": what, "near": point, "limit": 1})
    if not found["items"]:
        return {"picked": None, "candidates": []}
    row = found["items"][0]

    if what == "faces":
        pairs = _face_candidates(row, point)
    elif what == "vertices":
        pairs = _vertex_candidates(row, point)
    else:
        pairs = _edge_candidates(row, point)

    candidates = []
    for label, select in pairs:
        matched = find_features(shape, select)
        # **몇 개에 맞나.** 1 이면 이것 하나, 여럿이면 그 부류 전부다 — 둘 다 쓸모가 있어서
        # 고르게 한다(볼트 구멍은 넷을 한꺼번에 잡고 싶다).
        #
        # 셀렉터가 `limit` 을 들고 있으면 그것이 곧 집는 수다. `total`(거른 뒤 전체)을 세면
        # 「이 자리의 면」 이 10 개에 맞는다고 말하게 된다 — 사람은 그 수를 보고 고른다.
        matches = len(matched["items"]) if "limit" in select else matched["total"]
        candidates.append({"label": label, "select": select, "matches": matches})
    return {"picked": row, "candidates": candidates}
