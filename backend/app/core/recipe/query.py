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
#: 「같은 방향」 의 문턱 — 법선 · 축이 이만큼 나란하면 같다(약 2.6°). 반올림한 값끼리
#: 견줘도 된다.
_SAME_DIRECTION = 0.999
_AXIS_VECTORS = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _unit(v: Any) -> tuple[float, float, float] | None:
    """「x」 · 「y」 · 「z」 또는 [x, y, z] → 단위 벡터. 못 알아들으면 None."""
    if isinstance(v, str):
        return _AXIS_VECTORS.get(v.lower())
    if isinstance(v, (list, tuple)) and len(v) == 3:
        size = sum(float(one) ** 2 for one in v) ** 0.5
        if size > 0:
            return (float(v[0]) / size, float(v[1]) / size, float(v[2]) / size)
    return None


def _dot(a: Any, b: tuple[float, float, float]) -> float:
    unit = _unit(a)
    return sum(x * y for x, y in zip(unit, b, strict=True)) if unit else 0.0


_LIMIT = 60
#: 선택 그룹은 맞는 것을 **전부** 집는다 — 목록 상한(60)에 말없이 잘리면 구멍 백 개 중 예순만
#: 하중을 받는다.
_EVERYTHING = 100_000
#: 바디 이름 대신 쓰는 말 — 모든 바디. `topology.bodies` 가 단품을 이 이름 하나로 부른다.
_ALL_BODIES = "전체"
#: 찍은 자리와 면 · 엣지의 대표 점이 「같은 자리」 인 거리(mm) — 화면은 4 자리, 여기는 3 자리로
#: 반올림한다.
_SAME_PLACE = 0.01


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
      of_face     면 질의 — 그 면들의 **테두리** 엣지만(점이면 그 면들의 꼭짓점). 예
                  `{"body": "블록", "normal": [0, 0, 1]}` → 블록 윗면 둘레
      axis        x | y | z (직선 엣지의 방향) — 면이면 원통 · 원뿔의 축(`[x, y, z]` 도 된다)
      normal      [x, y, z] 또는 x | y | z — 이 방향을 보는 평면만(면)
      radius      이 반지름(±0.05)의 원 · 원통만
      min_length / max_length
      tag         `divide_face` 가 붙인 이름 — 그 패치의 면만. `tags` 를 줘야 듣는다
      edges       이 점에 모이는 엣지 수(점) — 꼭짓점 3 · 구멍 테두리 2
      body        이 바디의 것만 — 조립의 구성품 이름표(`topology.bodies` 의 이름), 단품은
                  「전체」. 좌표 없이 「블록의 아랫면」 을 말할 수 있다
      near        [x, y, z] — **이 점에서 가장 가까운 것 하나.** 여럿을 가까운 순으로 보려면
                  `limit` 을 함께 준다
      limit       near 가 있으면 1, 없으면 60
    답의 `midpoint`(엣지) · `center`(면) · `point`(점)를 그대로 `near` 나 `plane` 에 쓴다.

    **`near` 가 순서만 정하면 안 된다** — 2026-10-02 까지는 그랬고, 「+Z 평면 중
    (40, 25, 5) 의 면」 이 판 윗면과 블록 윗면을 **둘 다** 집었다(SimEngBay 가 받은 픽스처).
    사람이 near 를 쓰는 뜻은 「이 자리의 것」 이고, 3D 에서 고른 규칙도 늘 `limit: 1` 을 붙여
    왔다. 그래서 near 는 하나다 — 찾기 · 선택 그룹 · 면 나누기가 같은 말을 같은 뜻으로 읽는다.
    """
    what = query.get("what", "edges")
    box = shape.bounding_box()
    z_lo, z_hi = float(box.min.Z), float(box.max.Z)
    near = query.get("near")
    limit = int(query.get("limit") or (1 if near else _LIMIT))

    if what == "vertices":
        rows = [_vertex_row(i, v, shape) for i, v in enumerate(shape.vertices())]
        if isinstance(query.get("of_face"), dict):
            corners = _rim(shape, query["of_face"], tags, "vertices")
            vertices = shape.vertices()
            rows = [r for r in rows if vertices[r["index"]] in corners]
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
        # **방향으로 거른다** — 평면은 법선, 원통 · 원뿔은 축. 치수가 바뀌어도 방향은 대개
        # 그대로라 「이 방향의 면들 중 가장 가까운 것」 은 좌표만으로 고르는 것보다 훨씬 덜
        # 헛집는다.
        if query.get("normal") is not None and (want := _unit(query["normal"])):
            rows = [
                r
                for r in rows
                if r.get("normal") and _dot(r["normal"], want) > _SAME_DIRECTION
            ]
        if query.get("axis") is not None and (want := _unit(query["axis"])):
            rows = [
                r
                for r in rows
                if isinstance(r.get("axis"), dict)
                and abs(_dot(r["axis"]["direction"], want)) > _SAME_DIRECTION
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
        if isinstance(query.get("of_face"), dict):
            around = _rim(shape, query["of_face"], tags, "edges")
            edges = [(i, e) for i, e in edges if e in around]
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

    known_bodies: list[str] | None = None
    if query.get("body") is not None:
        rows, known_bodies = _in_body(shape, what, rows, str(query["body"]))

    if near:
        point = [float(v) for v in near]
        for r in rows:
            r["distance_from_near"] = round(_dist(r[key], point), 3)
        rows.sort(key=lambda r: r["distance_from_near"])
    out: dict[str, Any] = {"what": what, "total": len(rows), "items": rows[:limit]}
    if known_bodies is not None:
        # 없는 바디 이름 — 0 개라고만 하면 오타인지 알 길이 없다. 있는 이름을 알려 준다.
        out["bodies"] = known_bodies
    return out


def _rim(
    shape: Shape, face_query: dict[str, Any], tags: dict[str, list[int]] | None, what: str
) -> set[Any]:
    """면 질의에 맞는 면들의 테두리 엣지(또는 꼭짓점) — `of_face` 가 쓴다."""
    faces = shape.faces()
    found = select_features(shape, {**face_query, "what": "faces"}, tags)["items"]
    out: set[Any] = set()
    for row in found:
        face = faces[row["index"]]
        out |= set(face.edges() if what == "edges" else face.vertices())
    return out


def body_parts(shape: Shape) -> dict[str, Shape]:
    """바디 이름 → 그 덩어리. 이름표가 **모두** 붙은 조립이면 구성품마다, 아니면 빈 것(단품 —
    「전체」 하나). `topology.bodies` 가 내는 이름과 같다."""
    children = list(getattr(shape, "children", ()) or ())
    if children and all(getattr(child, "label", "") for child in children):
        return {str(child.label): child for child in children}
    return {}


def _in_body(
    shape: Shape, what: str, rows: list[dict[str, Any]], name: str
) -> tuple[list[dict[str, Any]], list[str] | None]:
    """그 바디에 속한 줄만. 모르는 이름이면 (빈 목록, 있는 이름들)."""
    if name == _ALL_BODIES:
        return rows, None
    parts = body_parts(shape)
    part = parts.get(name)
    if part is None:
        return [], sorted(parts) or [_ALL_BODIES]
    if what == "faces":
        mine, every = set(part.faces()), shape.faces()
    elif what == "vertices":
        mine, every = set(part.vertices()), shape.vertices()
    else:
        mine, every = set(part.edges()), shape.edges()
    keep = {index for index, one in enumerate(every) if one in mine}
    return [row for row in rows if row["index"] in keep], None


def select_features(
    shape: Shape, select: dict[str, Any], tags: dict[str, list[int]] | None = None
) -> dict[str, Any]:
    """선택 그룹의 셀렉터를 푼다 — 하나면 `find_features` 그대로, `{"any": [...]}` 면 **합**.

    3D 에서 면을 하나씩 골라(Ctrl · Shift) 한 그룹으로 묶으면, 규칙 하나로는 그 모음을 말할 수
    없다(「윗면과 왼쪽 구멍 하나」). 그래서 고른 것마다 제 규칙을 두고 그 합을 그룹으로 한다 —
    규칙마다 설계점에서 다시 풀리므로 치수를 바꿔도 같은 것들을 가리킨다.

    두 규칙이 같은 것을 집으면 **한 번만** 센다(번호로 가른다) — 안 그러면 받는 쪽이 같은 면에
    하중을 두 번 건다.

    `near` 없는 규칙은 맞는 것을 **전부** 집는다 — 목록 상한(60)에 잘리지 않는다.
    """
    members = select.get("any")
    if not isinstance(members, list):
        return find_features(shape, _whole(select), tags)
    what = next(
        (one.get("what") for one in members if isinstance(one, dict) and one.get("what")),
        "faces",
    )
    seen: set[int] = set()
    items: list[dict[str, Any]] = []
    for member in members:
        for row in find_features(shape, _whole(member), tags)["items"]:
            if row["index"] in seen:
                continue
            seen.add(row["index"])
            items.append(row)
    return {"what": what, "total": len(items), "items": items}


def _whole(rule: dict[str, Any]) -> dict[str, Any]:
    """그룹의 규칙 — 상한을 안 적었고 `near` 도 없으면 맞는 것 전부."""
    if rule.get("limit") or rule.get("near"):
        return rule
    return {**rule, "limit": _EVERYTHING}


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


def _direction_label(v: Any, *, signed: bool) -> str:
    """사람이 읽을 방향 — 축과 나란하면 「+X」 · 「Z」, 아니면 벡터 그대로."""
    unit = _unit(v)
    if unit is None:
        return "?"
    for name, axis in _AXIS_VECTORS.items():
        dot = sum(x * y for x, y in zip(unit, axis, strict=True))
        if abs(dot) > _SAME_DIRECTION:
            return f"{'+' if dot > 0 else '-'}{name.upper()}" if signed else name.upper()
    return "(" + ", ".join(f"{one:.2f}" for one in unit) + ")"


def _rounded(v: Any) -> list[float]:
    return [round(float(one), 4) for one in v]


#: 후보 하나 — (말, 셀렉터, **치수가 바뀌어도 같은 것을 가리키나**).
Candidate = tuple[str, dict[str, Any], bool]

_KIND_LABEL = {"cylinder": "원통면", "cone": "원뿔면", "sphere": "구면", "torus": "토러스면"}


def _face_candidates(
    row: dict[str, Any], point: list[float], body: str | None = None
) -> list[Candidate]:
    """면 하나를 부를 말들 — **좌표에 기대지 않는 것부터.**

    「이 좌표에 가장 가까운 면」 은 치수가 바뀌면 **말없이 다른 면을 집는다** — 못 찾는 게
    아니라 가장 가까운 딴 면을 준다(실측 2026-09-24: 판 길이를 80 → 130 으로 늘리면 +X
    옆면 대신 구멍 원통면이 잡혔다). 그래서 한 면을 고르는 기본은 **같은 종류 · 같은 방향
    중 가장 가까운 것**이다 — 방향은 치수가 바뀌어도 대개 그대로라, 헛집으려면 같은 방향의
    딴 면이 더 가까워야 한다. 좌표만 쓰는 후보는 맨 끝에 두고 `stable=False` 로 알린다.

    조립이면 **「그 바디의 이 방향 면」** 을 맨 먼저 낸다(`body`) — 좌표가 아예 없어 치수가
    바뀌어도 헛집을 수 없다. 판 위에 블록이 앉으면 「+Z 평면 중 이 면」 은 둘 중 가까운
    것이지만 「받침판의 +Z 평면」 은 하나다.
    """
    out: list[Candidate] = []
    if body is not None and row["kind"] == "plane" and row.get("normal"):
        direction = _direction_label(row["normal"], signed=True)
        out.append(
            (
                f"「{body}」 의 {direction} 방향 평면",
                {
                    "what": "faces",
                    "body": body,
                    "kind": "plane",
                    "normal": _rounded(row["normal"]),
                },
                True,
            )
        )
    elif body is not None and isinstance(row.get("axis"), dict):
        direction = _direction_label(row["axis"]["direction"], signed=False)
        kind = _KIND_LABEL.get(row["kind"], f"{row['kind']} 면")
        out.append(
            (
                f"「{body}」 의 {direction}축 {kind}",
                {
                    "what": "faces",
                    "body": body,
                    "kind": row["kind"],
                    "axis": _rounded(row["axis"]["direction"]),
                },
                True,
            )
        )
    role = row.get("role")
    if role:
        out.append((f"{role} 면", {"what": "faces", "role": role}, True))
    if row.get("radius") is not None:
        out.append(
            (
                f"반지름 {row['radius']} 원통면",
                {"what": "faces", "kind": row["kind"], "radius": row["radius"]},
                True,
            )
        )
    if row["kind"] == "plane" and row.get("normal"):
        out.append(
            (
                f"{_direction_label(row['normal'], signed=True)} 방향 평면 중 이 면",
                {
                    "what": "faces",
                    "kind": "plane",
                    "normal": _rounded(row["normal"]),
                    "near": point,
                    "limit": 1,
                },
                True,
            )
        )
    elif isinstance(row.get("axis"), dict):
        direction = row["axis"]["direction"]
        kind = _KIND_LABEL.get(row["kind"], f"{row['kind']} 면")
        out.append(
            (
                f"{_direction_label(direction, signed=False)}축 {kind} 중 이 면",
                {
                    "what": "faces",
                    "kind": row["kind"],
                    "axis": _rounded(direction),
                    "near": point,
                    "limit": 1,
                },
                True,
            )
        )
    # **찍은 자리를 그대로 쓴다.** 원통면의 `center` 는 축이 아니라 표면 위의 점이라
    # (topology.py 머리말) 사람이 읽으면 엉뚱한 좌표로 보인다.
    out.append(("좌표에 가장 가까운 면", {"what": "faces", "near": point, "limit": 1}, False))
    return out


def _edge_candidates(row: dict[str, Any], point: list[float]) -> list[Candidate]:
    out: list[Candidate] = []
    if row.get("radius") is not None:
        out.append(
            (
                f"반지름 {row['radius']} 원",
                {"what": "edges", "kind": row["kind"], "radius": row["radius"]},
                True,
            )
        )
    if row.get("axis"):
        out.append(
            (
                f"{row['axis']} 방향 직선 엣지",
                {"what": "edges", "kind": row["kind"], "axis": row["axis"]},
                True,
            )
        )
        # 같은 방향의 직선 중 가장 가까운 것 — 면과 같은 까닭으로 좌표만 쓰는 것보다 낫다.
        out.append(
            (
                f"{row['axis']} 방향 직선 엣지 중 이 엣지",
                {
                    "what": "edges",
                    "kind": row["kind"],
                    "axis": row["axis"],
                    "near": point,
                    "limit": 1,
                },
                True,
            )
        )
    elif row["kind"] in ("circle", "ellipse"):
        # 반지름은 실험계획이 훑는 치수일 수 있다 — 종류로만 거르고 가장 가까운 것.
        out.append(
            (
                "원 엣지 중 이 엣지",
                {"what": "edges", "kind": row["kind"], "near": point, "limit": 1},
                True,
            )
        )
    out.append(
        ("좌표에 가장 가까운 엣지", {"what": "edges", "near": point, "limit": 1}, False)
    )
    return out


def _vertex_candidates(row: dict[str, Any], point: list[float]) -> list[Candidate]:
    return [
        (
            f"엣지 {row['edges']}개가 모이는 점",
            {"what": "vertices", "edges": row["edges"]},
            True,
        ),
        (
            f"엣지 {row['edges']}개가 모이는 점 중 이 점",
            {"what": "vertices", "edges": row["edges"], "near": point, "limit": 1},
            True,
        ),
        ("좌표에 가장 가까운 점", {"what": "vertices", "near": point, "limit": 1}, False),
    ]


def _body_of(shape: Shape, index: int) -> str | None:
    """조립이면 그 면이 속한 바디의 이름. 단품이면 None — 「전체」 로 거르는 것은 뜻이 없다."""
    face = shape.faces()[index]
    for name, part in body_parts(shape).items():
        if face in set(part.faces()):
            return name
    return None


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

    found = find_features(shape, {"what": what, "near": point, "limit": _EVERYTHING})["items"]
    if not found:
        return {"picked": None, "candidates": []}
    row = found[0]
    # **번호가 있으면 그것을 믿는다** — 판 윗면과 그 위에 앉은 블록의 아랫면은 중심이 같아
    # (0, 0, 5) 가장 가까운 것이 둘이고, 어느 쪽이 먼저인지는 면 순서가 정한다. 화면은 누른
    # 면의 번호를 안다. 자리가 맞을 때만 쓴다 — 도면이 그새 바뀌었으면 번호가 딴 것을 가리킨다.
    index = pick.get("index")
    if isinstance(index, int):
        exact = next(
            (
                one
                for one in found
                if one["index"] == index and one["distance_from_near"] <= _SAME_PLACE
            ),
            None,
        )
        row = exact or row

    if what == "faces":
        pairs = _face_candidates(row, point, _body_of(shape, row["index"]))
    elif what == "vertices":
        pairs = _vertex_candidates(row, point)
    else:
        pairs = _edge_candidates(row, point)

    candidates = []
    for label, select, stable in pairs:
        matched = find_features(shape, select)
        # **몇 개에 맞나.** 1 이면 이것 하나, 여럿이면 그 부류 전부다 — 둘 다 쓸모가 있어서
        # 고르게 한다(볼트 구멍은 넷을 한꺼번에 잡고 싶다).
        #
        # 셀렉터가 `limit` 을 들고 있으면 그것이 곧 집는 수다. `total`(거른 뒤 전체)을 세면
        # 「좌표에 가장 가까운 면」 이 10 개에 맞는다고 말하게 된다 — 사람은 그 수를 보고
        # 고른다.
        matches = len(matched["items"]) if "limit" in select else matched["total"]
        # `stable` — 치수가 바뀌어도 같은 것을 가리키나. 좌표만 쓰는 후보는 거짓이다: 못
        # 찾는 게 아니라 가장 가까운 **딴 것**을 말없이 집는다. 화면은 이것을 기본으로 고르지
        # 않는다.
        candidates.append(
            {"label": label, "select": select, "matches": matches, "stable": stable}
        )
    return {"picked": row, "candidates": candidates}
