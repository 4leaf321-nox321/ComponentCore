"""도면 — 3각법 세 뷰(정면 · 평면 · 우측면)에 치수 · 구멍표 · 표제란.

가공을 맡길 때 오가는 것은 아직 2D 도면이다. 3D 를 은선 투영해 세 뷰를 놓고(보이는 선 실선 ·
숨은 선 점선), 전체 치수를 넣고, 구멍은 **기호와 구멍표**로 적는다 — 구멍마다 치수선을 그으면
도면이 치수선으로 덮인다. 구멍 위치는 그 구멍이 원으로 보이는 뷰의 **왼쪽 아래 모서리**에서 잰
가로 · 세로다.

한 벌의 그림(종이 위 mm)을 세 가지로 쓴다:

- **DXF** — 치수는 진짜 치수 객체(CAD 에서 고칠 수 있다). 층: VISIBLE · HIDDEN · CENTER · DIM ·
  TEXT · BORDER · TABLE.
- **SVG** — 화면에서 보고 문서에 붙인다(글씨는 보는 쪽 글꼴).
- **PDF** — SVG 를 그대로(서버 글꼴 — 한글은 나눔글꼴이 깔려 있어야 한다).

축척은 표준 축척(5:1 … 1:100) 중 세 뷰가 용지에 들어가는 가장 큰 것을 고른다. 도면 위의 치수는
**실제 크기**다(축척을 되돌려 적는다).
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from build123d import GeomType, Shape, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepTools import BRepTools
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_OUT, TopAbs_REVERSED

#: 용지(가로 놓기, mm).
SHEETS: dict[str, tuple[float, float]] = {"A3": (420.0, 297.0), "A4": (297.0, 210.0)}
#: 표준 축척 — 큰 것부터. 5 는 5:1(확대), 0.5 는 1:2.
SCALES = (5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01)
#: 글꼴 — 한글이 나와야 한다. SVG 는 보는 쪽에서 앞에서부터 고른다.
FONT_FAMILY = (
    "NanumGothic, 'Noto Sans CJK KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif"
)
DXF_FONT = "NanumGothic.ttf"

#: 테두리 여백 — 왼쪽은 철하는 자리라 넓게(KS).
_MARGIN = {"left": 20.0, "right": 10.0, "top": 10.0, "bottom": 10.0}
_TITLE = (170.0, 32.0)
_GAP = 22.0


@dataclass
class Line:
    a: tuple[float, float]
    b: tuple[float, float]
    layer: str


@dataclass
class Circle:
    center: tuple[float, float]
    radius: float
    layer: str


@dataclass
class Arc:
    center: tuple[float, float]
    radius: float
    start: float
    """도, 반시계."""
    end: float
    layer: str


@dataclass
class Poly:
    points: list[tuple[float, float]]
    layer: str


@dataclass
class Text:
    at: tuple[float, float]
    text: str
    height: float
    align: str = "left"
    """left · center · right — 세로는 글자 아래선."""
    angle: float = 0.0
    layer: str = "TEXT"


@dataclass
class Dim:
    """선형 치수 — `p1` · `p2` 사이를 `horizontal` 이면 가로로, 아니면 세로로 잰다. 치수선은
    `offset` 만큼 비켜 놓는다(가로면 y 로, 세로면 x 로). `value` 는 실제 크기(mm)."""

    p1: tuple[float, float]
    p2: tuple[float, float]
    horizontal: bool
    offset: float
    value: float
    layer: str = "DIM"


Item = Line | Circle | Arc | Poly | Text | Dim


@dataclass
class Sheet:
    """종이 한 장 — 모든 좌표는 종이 위 mm(왼쪽 아래가 원점)."""

    name: str
    width: float
    height: float
    scale: float
    items: list[Item] = field(default_factory=list)
    holes: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def scale_text(self) -> str:
        return _scale_text(self.scale)

    def summary(self) -> dict[str, Any]:
        return {
            "sheet": self.name,
            "scale": self.scale_text,
            "holes": self.holes,
            "dimensions": [
                {
                    "value": round(one.value, 3),
                    "direction": "가로" if one.horizontal else "세로",
                }
                for one in self.items
                if isinstance(one, Dim)
            ],
            "notes": list(self.notes),
        }


def _scale_text(scale: float) -> str:
    if scale >= 1:
        return f"{scale:g}:1"
    return f"1:{1 / scale:g}"


def _number(value: float) -> str:
    """치수 글씨 — 소수 둘째 자리까지, 뒤의 0 은 뗀다."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


# --- 구멍 -------------------------------------------------------------------------


def _cylinder(face: Any) -> tuple[Vector, Vector, float]:
    surface = BRepAdaptor_Surface(face.wrapped).Cylinder()
    axis = surface.Axis()
    location, direction = axis.Location(), axis.Direction()
    return (
        Vector(location.X(), location.Y(), location.Z()),
        Vector(direction.X(), direction.Y(), direction.Z()),
        float(surface.Radius()),
    )


def _concave(face: Any, axis_point: Vector, axis: Vector) -> bool:
    """구멍 벽인가 — 바깥 법선이 축을 본다(기둥 · 보스는 축에서 멀어진다)."""
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face.wrapped)
    surface = BRepAdaptor_Surface(face.wrapped)
    u, v = (umin + umax) / 2, (vmin + vmax) / 2
    point, d1u, d1v = gp_Pnt(), Vector(), Vector()
    del d1u, d1v
    point = surface.Value(u, v)
    from OCP.BRepLProp import BRepLProp_SLProps

    props = BRepLProp_SLProps(surface, u, v, 1, 1e-7)
    normal = props.Normal()
    if face.wrapped.Orientation() == TopAbs_REVERSED:
        normal.Reverse()
    p = Vector(point.X(), point.Y(), point.Z())
    radial = (p - axis_point) - axis * (p - axis_point).dot(axis)
    return Vector(normal.X(), normal.Y(), normal.Z()).dot(radial) < 0


class _Inside:
    """점이 솔리드 밖인가 — 분류기를 **한 번 만들어** 되쓴다. 점마다 새로 만들면 면이 많은
    솔리드(필렛 · 구멍 수십)에서 구멍 찾기가 형상 만들기만큼 걸렸다(실측: 구멍 110 개
    1.4 초 → 0.24 초)."""

    def __init__(self, solid: Any) -> None:
        self._classifier = BRepClass3d_SolidClassifier(solid.wrapped)

    def outside(self, p: Vector) -> bool:
        self._classifier.Perform(gp_Pnt(p.X, p.Y, p.Z), 1e-7)
        return bool(self._classifier.State() == TopAbs_OUT)


def holes(shape: Shape) -> list[dict[str, Any]]:
    """구멍 — 오목한 원통면을 축 · 반지름으로 묶어 **한 바퀴 다 도는 것**만(안쪽 필렛도 오목한
    원통이지만 한 바퀴가 아니다). 양쪽 끝 너머가 다 비었으면 관통, 아니면 깊이."""
    groups: list[dict[str, Any]] = []
    for face in shape.faces():
        if face.geom_type != GeomType.CYLINDER:
            continue
        axis_point, axis, radius = _cylinder(face)
        if not _concave(face, axis_point, axis):
            continue
        umin, umax, _, _ = BRepTools.UVBounds_s(face.wrapped)
        heights = [(Vector(*tuple(one)) - axis_point).dot(axis) for one in face.vertices()]
        box = face.bounding_box()
        for corner in (box.min, box.max):
            heights.append((corner - axis_point).dot(axis))
        group = next(
            (
                one
                for one in groups
                if abs(one["radius"] - radius) < 1e-6
                and abs(abs(one["axis"].dot(axis)) - 1) < 1e-6
                and (one["point"] - axis_point).cross(one["axis"]).length < 1e-6
            ),
            None,
        )
        if group is None:
            group = {"radius": radius, "axis": axis, "point": axis_point, "span": 0.0, "h": []}
            groups.append(group)
        sign = 1.0 if group["axis"].dot(axis) > 0 else -1.0
        group["span"] += umax - umin
        group["h"].extend(h * sign for h in heights)
    solid = _Inside(shape.solids()[0] if shape.solids() else shape)
    out: list[dict[str, Any]] = []
    for group in groups:
        if group["span"] < 2 * math.pi * 0.97:
            continue
        axis, point = group["axis"], group["point"]
        # 축 방향은 양(+)으로 — 뷰를 고르기 쉽게.
        dominant = max(range(3), key=lambda i: abs(tuple(axis)[i]))
        if tuple(axis)[dominant] < 0:
            axis = -axis
            group["h"] = [-h for h in group["h"]]
        h0, h1 = min(group["h"]), max(group["h"])
        eps = max(1e-3, (h1 - h0) * 1e-3)
        # 끝 너머를 축에서 비켜 본다(반지름의 0.9) — 축 위는 더 작은 구멍(카운터보어의 속)이라
        # 비어 있을 수 있다. 네 군데가 다 비어야 그 끝이 열렸다.
        side = Vector(1, 0, 0) if abs(axis.X) < 0.9 else Vector(0, 1, 0)
        first = (side - axis * side.dot(axis)).normalized()
        second = axis.cross(first)
        reach = group["radius"] * 0.9
        through = all(
            solid.outside(point + axis * height + direction * reach)
            for height in (h0 - eps, h1 + eps)
            for direction in (first, -first, second, -second)
        )
        out.append(
            {
                "diameter": round(2 * group["radius"], 4),
                "axis": axis,
                "center": point + axis * ((h0 + h1) / 2),
                "depth": None if through else round(h1 - h0, 4),
                "top": point + axis * h1,
            }
        )
    return out


# --- 뷰 ---------------------------------------------------------------------------


#: 뷰 — 시선(형상에서 물러나는 쪽) · 위 · 세계 좌표를 뷰 좌표로(가로, 세로).
VIEWS: dict[str, dict[str, Any]] = {
    "front": {
        "label": "정면도",
        "direction": (0.0, -1.0, 0.0),
        "up": (0.0, 0.0, 1.0),
        "uv": lambda p: (p.X, p.Z),
        "axis": 1,
    },
    "top": {
        "label": "평면도",
        "direction": (0.0, 0.0, 1.0),
        "up": (0.0, 1.0, 0.0),
        "uv": lambda p: (p.X, p.Y),
        "axis": 2,
    },
    "right": {
        "label": "우측면도",
        "direction": (1.0, 0.0, 0.0),
        "up": (0.0, 0.0, 1.0),
        "uv": lambda p: (p.Y, p.Z),
        "axis": 0,
    },
}


def _projected(shape: Shape, name: str) -> tuple[list[Any], list[Any]]:
    view = VIEWS[name]
    box = shape.bounding_box()
    center = box.center()
    span = max(box.size.X, box.size.Y, box.size.Z, 1.0)
    d = view["direction"]
    origin = (
        center.X + d[0] * span * 3,
        center.Y + d[1] * span * 3,
        center.Z + d[2] * span * 3,
    )
    visible, hidden = shape.project_to_viewport(
        origin, viewport_up=view["up"], look_at=(center.X, center.Y, center.Z)
    )
    return list(visible), list(hidden)


def _edge_items(
    edges: list[Any],
    layer: str,
    place: Callable[[float, float], tuple[float, float]],
    scale: float,
) -> list[Item]:
    """투영된 엣지를 종이 위 그림으로 — 직선 · 원 · 호는 그대로, 그 밖은 점으로."""
    out: list[Item] = []
    for edge in edges:
        kind = edge.geom_type
        start, end = edge.start_point(), edge.end_point()
        if kind == GeomType.LINE:
            out.append(Line(place(start.X, start.Y), place(end.X, end.Y), layer))
            continue
        if kind == GeomType.CIRCLE:
            center = edge.arc_center
            radius = float(edge.radius) * scale
            c = place(center.X, center.Y)
            if (start - end).length < 1e-7:
                out.append(Circle(c, radius, layer))
                continue
            a0 = math.degrees(math.atan2(start.Y - center.Y, start.X - center.X))
            a1 = math.degrees(math.atan2(end.Y - center.Y, end.X - center.X))
            middle = edge.position_at(0.5)
            am = math.degrees(math.atan2(middle.Y - center.Y, middle.X - center.X))
            # 반시계로 a0 → a1 이 가운데를 지나야 한다 — 아니면 거꾸로 돈 호다.
            if (am - a0) % 360 > (a1 - a0) % 360:
                a0, a1 = a1, a0
            out.append(Arc(c, radius, a0, a1, layer))
            continue
        count = max(12, int(float(edge.length) * scale / 1.0))
        points = [edge.position_at(i / count) for i in range(count + 1)]
        out.append(Poly([place(p.X, p.Y) for p in points], layer))
    return out


#: 정면도 · 우측면도 아래(치수 + 뷰 이름) · 정면도 왼쪽(높이 치수)에 비워 둘 자리.
_BELOW = 24.0
_LEFT = 14.0
#: 구멍표의 폭과 한 줄 높이.
_TABLE_W = 128.0
_ROW = 5.5


def _layout(
    sizes: dict[str, tuple[float, float]], scale: float, origin: tuple[float, float]
) -> dict[str, dict[str, float]]:
    """3각법 — 평면도는 정면도 위, 우측면도는 정면도 오른쪽. 뷰마다 종이 위 사각형."""
    x_size, z_size = sizes["front"]
    y_size = sizes["top"][1]
    left = origin[0] + _LEFT
    bottom = origin[1] + _BELOW
    rects = {
        "front": (left, bottom, scale * x_size, scale * z_size),
        "top": (left, bottom + scale * z_size + _GAP, scale * x_size, scale * y_size),
        "right": (left + scale * x_size + _GAP, bottom, scale * y_size, scale * z_size),
    }
    return {
        name: {"left": x, "bottom": y, "right": x + w, "top": y + h}
        for name, (x, y, w, h) in rects.items()
    }


def _overlaps(a: dict[str, float], b: dict[str, float], margin: float = 4.0) -> bool:
    return not (
        a["right"] + margin <= b["left"]
        or b["right"] + margin <= a["left"]
        or a["top"] + margin <= b["bottom"]
        or b["top"] + margin <= a["bottom"]
    )


def make_sheet(
    shape: Shape,
    *,
    title: str = "",
    sheet: str = "A3",
    material: str = "",
    drawn_by: str = "CompCore",
    note: str = "",
) -> Sheet:
    """형상 → 도면 한 장. 세 뷰와 구멍표가 겹치지 않고 들어가는 가장 큰 표준 축척으로."""
    if sheet not in SHEETS:
        raise ValueError(f"용지는 {', '.join(SHEETS)} 중 하나여야 합니다.")
    paper_w, paper_h = SHEETS[sheet]
    box = shape.bounding_box()
    sizes = {
        "front": (box.size.X, box.size.Z),
        "top": (box.size.X, box.size.Y),
        "right": (box.size.Y, box.size.Z),
    }
    found = holes(shape)
    # 그릴 자리 — 테두리 안, 표제란 위. 구멍표는 오른쪽 위(3각법에서 비는 자리).
    origin = (_MARGIN["left"] + 3, _MARGIN["bottom"] + _TITLE[1] + 3)
    area = {"right": paper_w - _MARGIN["right"] - 3, "top": paper_h - _MARGIN["top"] - 3}
    table = {
        "left": area["right"] - _TABLE_W,
        "bottom": area["top"] - _ROW * (len(found) + 1) - 10,
        "right": area["right"],
        "top": area["top"],
    }
    scale = SCALES[-1]
    views = _layout(sizes, scale, origin)
    for candidate in SCALES:
        placed = _layout(sizes, candidate, origin)
        inside = all(
            one["right"] <= area["right"] and one["top"] <= area["top"] - 4
            for one in placed.values()
        )
        clear = not found or not any(_overlaps(one, table) for one in placed.values())
        if inside and clear:
            scale, views = candidate, placed
            break
    out = Sheet(name=sheet, width=paper_w, height=paper_h, scale=scale)
    for name, view in VIEWS.items():
        rect = views[name]
        cx = (rect["left"] + rect["right"]) / 2
        cy = (rect["bottom"] + rect["top"]) / 2

        def place(x: float, y: float, cx: float = cx, cy: float = cy) -> tuple[float, float]:
            return (cx + scale * x, cy + scale * y)

        visible, hidden = _projected(shape, name)
        out.items.extend(_edge_items(visible, "VISIBLE", place, scale))
        out.items.extend(_edge_items(hidden, "HIDDEN", place, scale))
        # 뷰 이름 — 정면도 · 우측면도는 치수 아래, 평면도는 정면도와의 사이.
        below = 7.0 if name == "top" else _BELOW - 4
        out.items.append(
            Text((cx, rect["bottom"] - below), view["label"], 3.5, align="center")
        )

    # 전체 치수 — 가로 · 높이는 정면도, 깊이는 우측면도(한 치수는 한 번만).
    x_size, z_size = sizes["front"]
    y_size = sizes["top"][1]
    f, r = views["front"], views["right"]
    out.items.append(
        Dim((f["left"], f["bottom"]), (f["right"], f["bottom"]), True, -8, x_size)
    )
    out.items.append(Dim((f["left"], f["bottom"]), (f["left"], f["top"]), False, -8, z_size))
    out.items.append(
        Dim((r["left"], r["bottom"]), (r["right"], r["bottom"]), True, -8, y_size)
    )

    _hole_marks(found, out, views, box, scale)
    _hole_table(out, paper_w, paper_h)
    _frame(out, paper_w, paper_h, title=title, material=material, drawn_by=drawn_by, note=note)
    return out


def _hole_marks(
    found: list[dict[str, Any]],
    out: Sheet,
    views: dict[str, dict[str, float]],
    box: Any,
    scale: float,
) -> None:
    """구멍이 **원으로 보이는 뷰**에 중심선과 기호(A1 …)를 — 위치는 구멍표가 적는다."""
    by_view: dict[str, list[dict[str, Any]]] = {}
    for hole in found:
        axis = tuple(hole["axis"])
        name = next(
            (n for n, v in VIEWS.items() if abs(abs(axis[v["axis"]]) - 1) < 1e-6), None
        )
        if name is None:
            out.notes.append(
                f"기울어진 구멍 Ø{_number(hole['diameter'])}은(는) 구멍표에서 제외했습니다."
            )
            continue
        u, v = VIEWS[name]["uv"](hole["center"])
        u0, v0 = VIEWS[name]["uv"](box.min)
        hole["view"] = name
        hole["uv"] = (u - u0, v - v0)
        by_view.setdefault(name, []).append(hole)
    # 같은 자리의 구멍 둘(카운터보어)은 하나로 — 작은 것이 구멍, 큰 것이 자리파기.
    entries: list[dict[str, Any]] = []
    for name, rows in by_view.items():
        rows.sort(key=lambda one: one["diameter"])
        for hole in rows:
            twin = next(
                (
                    one
                    for one in entries
                    if one["view"] == name and math.dist(one["uv"], hole["uv"]) < 1e-4
                ),
                None,
            )
            if twin is None:
                entries.append({**hole, "counterbore": None})
            elif twin["counterbore"] is None:
                twin["counterbore"] = hole
    specs = sorted({_spec(one) for one in entries}, key=lambda s: (-_spec_size(s, entries), s))
    letters = {spec: chr(ord("A") + i) if i < 26 else f"Z{i}" for i, spec in enumerate(specs)}
    counters: dict[str, int] = {}
    entries.sort(key=lambda one: (letters[_spec(one)], -one["uv"][1], one["uv"][0]))
    for entry in entries:
        letter = letters[_spec(entry)]
        counters[letter] = counters.get(letter, 0) + 1
        label = f"{letter}{counters[letter]}"
        view = views[entry["view"]]
        cx = view["left"] + scale * entry["uv"][0]
        cy = view["bottom"] + scale * entry["uv"][1]
        radius = scale * entry["diameter"] / 2
        reach = radius + 1.5
        out.items.append(Line((cx - reach, cy), (cx + reach, cy), "CENTER"))
        out.items.append(Line((cx, cy - reach), (cx, cy + reach), "CENTER"))
        out.items.append(
            Text((cx + radius * 0.75 + 0.8, cy + radius * 0.75 + 0.8), label, 2.5)
        )
        out.holes.append(
            {
                "label": label,
                "spec": _spec(entry),
                "view": VIEWS[entry["view"]]["label"],
                "x": round(entry["uv"][0], 3),
                "y": round(entry["uv"][1], 3),
            }
        )
    for name in by_view:
        view = views[name]
        out.items.append(Circle((view["left"], view["bottom"]), 0.8, "DIM"))


def _spec(entry: dict[str, Any]) -> str:
    depth = "관통" if entry["depth"] is None else f"깊이 {_number(entry['depth'])}"
    text = f"Ø{_number(entry['diameter'])} {depth}"
    bore = entry.get("counterbore")
    if bore:
        bore_depth = "관통" if bore["depth"] is None else f"깊이 {_number(bore['depth'])}"
        text += f" / 자리파기 Ø{_number(bore['diameter'])} {bore_depth}"
    return text


def _spec_size(spec: str, entries: list[dict[str, Any]]) -> float:
    return max(one["diameter"] for one in entries if _spec(one) == spec)


def _hole_table(out: Sheet, paper_w: float, paper_h: float) -> None:
    """구멍표 — 오른쪽 위(3각법에서 비는 자리). 많으면 자르고 몇 개 남았는지 적는다."""
    if not out.holes:
        return
    columns = (("기호", 12.0), ("구멍", 62.0), ("뷰", 18.0), ("가로", 18.0), ("세로", 18.0))
    width = sum(w for _, w in columns)
    row = _ROW
    x0 = paper_w - _MARGIN["right"] - width - 3
    top = paper_h - _MARGIN["top"] - 3
    room = int((top - (_MARGIN["bottom"] + _TITLE[1] + 60)) / row) - 2
    shown = out.holes[: max(1, room)]
    rows = [[name for name, _ in columns]] + [
        [one["label"], one["spec"], one["view"], _number(one["x"]), _number(one["y"])]
        for one in shown
    ]
    for index, cells in enumerate(rows):
        y = top - row * (index + 1)
        out.items.append(Line((x0, y), (x0 + width, y), "TABLE"))
        x = x0
        for (_, w), cell in zip(columns, cells, strict=True):
            out.items.append(
                Text((x + 1.5, y + 1.6), str(cell), 2.6 if index else 2.8, layer="TABLE")
            )
            x += w
    bottom = top - row * len(rows)
    out.items.append(Line((x0, top), (x0 + width, top), "TABLE"))
    x = x0
    for _, w in columns:
        out.items.append(Line((x, top), (x, bottom), "TABLE"))
        x += w
    out.items.append(Line((x, top), (x, bottom), "TABLE"))
    note = "가로·세로: 구멍이 원으로 보이는 뷰의 왼쪽 아래 모서리(점) 기준, 실제 크기(mm)"
    out.items.append(Text((x0, bottom - 4), note, 2.2, layer="TABLE"))
    if len(shown) < len(out.holes):
        out.items.append(
            Text(
                (x0, bottom - 8),
                f"외 {len(out.holes) - len(shown)}개(DXF 요약 참조)",
                2.2,
                layer="TABLE",
            )
        )


def _frame(
    out: Sheet,
    paper_w: float,
    paper_h: float,
    *,
    title: str,
    material: str,
    drawn_by: str,
    note: str,
) -> None:
    """테두리와 표제란(오른쪽 아래)."""
    left, right = _MARGIN["left"], paper_w - _MARGIN["right"]
    bottom, top = _MARGIN["bottom"], paper_h - _MARGIN["top"]
    out.items.extend(
        [
            Line((left, bottom), (right, bottom), "BORDER"),
            Line((right, bottom), (right, top), "BORDER"),
            Line((right, top), (left, top), "BORDER"),
            Line((left, top), (left, bottom), "BORDER"),
        ]
    )
    w, h = _TITLE
    x0, y0 = right - w, bottom
    out.items.extend(
        [
            Line((x0, y0), (x0, y0 + h), "BORDER"),
            Line((x0, y0 + h), (right, y0 + h), "BORDER"),
            Line((x0, y0 + h / 2), (right, y0 + h / 2), "BORDER"),
            Line((x0 + w * 0.6, y0), (x0 + w * 0.6, y0 + h / 2), "BORDER"),
        ]
    )
    out.items.append(Text((x0 + 3, y0 + h * 0.62), title or "(이름 없음)", 5.0))
    lines = [
        f"축척 {out.scale_text}   단위 mm   제3각법",
        f"재료 {material or '—'}",
    ]
    out.items.append(Text((x0 + 3, y0 + h * 0.28), lines[0], 2.8))
    out.items.append(Text((x0 + 3, y0 + h * 0.08), lines[1], 2.8))
    out.items.append(Text((x0 + w * 0.6 + 3, y0 + h * 0.28), f"작성자 {drawn_by}", 2.6))
    out.items.append(Text((x0 + w * 0.6 + 3, y0 + h * 0.08), date.today().isoformat(), 2.6))
    if note:
        out.items.append(Text((left + 4, bottom + 4), note, 2.6))
    if out.scale != 1:
        out.notes.append(f"축척 {out.scale_text}: 도면의 치수 값은 실제 크기입니다.")


# --- 쓰기 ---------------------------------------------------------------------------


_LAYER_STYLE: dict[str, dict[str, Any]] = {
    "VISIBLE": {"width": 0.5, "dash": None},
    "HIDDEN": {"width": 0.25, "dash": "2.5 1.2"},
    "CENTER": {"width": 0.18, "dash": "6 1.2 1 1.2"},
    "DIM": {"width": 0.18, "dash": None},
    "TEXT": {"width": 0.18, "dash": None},
    "TABLE": {"width": 0.25, "dash": None},
    "BORDER": {"width": 0.5, "dash": None},
}


def write_dxf(sheet: Sheet, stream: io.StringIO | None = None) -> str:
    """DXF(R2018) — 종이 위 mm. 치수는 진짜 치수 객체(값은 실제 크기 — `dimlfac`)."""
    from ezdxf import units
    from ezdxf.document import Drawing
    from ezdxf.enums import TextEntityAlignment

    doc = Drawing.new("R2018")
    from ezdxf.tools.standards import setup_drawing

    setup_drawing(doc, topics="all")
    doc.units = units.MM
    doc.styles.new("KO", dxfattribs={"font": DXF_FONT})
    layers: dict[str, dict[str, Any]] = {
        "VISIBLE": {"lineweight": 50},
        "HIDDEN": {"lineweight": 25, "linetype": "DASHED"},
        "CENTER": {"lineweight": 18, "linetype": "CENTER"},
        "DIM": {"lineweight": 18, "color": 3},
        "TEXT": {"lineweight": 18},
        "TABLE": {"lineweight": 25},
        "BORDER": {"lineweight": 50},
    }
    for name, attribs in layers.items():
        doc.layers.add(name, **attribs)
    msp = doc.modelspace()
    align = {
        "left": TextEntityAlignment.LEFT,
        "center": TextEntityAlignment.CENTER,
        "right": TextEntityAlignment.RIGHT,
    }
    for item in sheet.items:
        if isinstance(item, Line):
            msp.add_line(item.a, item.b, dxfattribs={"layer": item.layer})
        elif isinstance(item, Circle):
            msp.add_circle(item.center, item.radius, dxfattribs={"layer": item.layer})
        elif isinstance(item, Arc):
            msp.add_arc(
                item.center,
                item.radius,
                item.start,
                item.end,
                dxfattribs={"layer": item.layer},
            )
        elif isinstance(item, Poly):
            msp.add_lwpolyline(item.points, dxfattribs={"layer": item.layer})
        elif isinstance(item, Text):
            text = msp.add_text(
                item.text,
                height=item.height,
                rotation=item.angle,
                dxfattribs={"layer": item.layer, "style": "KO"},
            )
            text.set_placement(item.at, align=align[item.align])
        elif isinstance(item, Dim):
            base = (
                (item.p1[0], item.p1[1] + item.offset)
                if item.horizontal
                else (item.p1[0] + item.offset, item.p1[1])
            )
            dim = msp.add_linear_dim(
                base=base,
                p1=item.p1,
                p2=item.p2,
                angle=0 if item.horizontal else 90,
                dimstyle="EZDXF",
                override={
                    "dimlfac": 1 / sheet.scale,
                    "dimtxt": 3.0,
                    "dimasz": 2.5,
                    "dimexo": 1.0,
                    "dimexe": 1.5,
                    "dimdec": 2,
                    "dimzin": 8,
                    "dimtxsty": "KO",
                },
                dxfattribs={"layer": item.layer},
            )
            dim.render()
    buffer = stream or io.StringIO()
    doc.write(buffer)
    return buffer.getvalue()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_svg(sheet: Sheet) -> str:
    """SVG — 종이 크기 그대로(mm). 위아래를 뒤집어(SVG 는 y 가 아래로) 그린다."""
    h = sheet.height

    def pt(p: tuple[float, float]) -> str:
        return f"{p[0]:.3f},{h - p[1]:.3f}"

    def stroke(layer: str) -> str:
        style = _LAYER_STYLE.get(layer, _LAYER_STYLE["VISIBLE"])
        dash = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        color = "#2563eb" if layer == "DIM" else "#111"
        return f'fill="none" stroke="{color}" stroke-width="{style["width"]}"{dash}'

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{sheet.width:g}mm" height="{h:g}mm" '
        f'viewBox="0 0 {sheet.width:g} {h:g}">',
        f'<rect width="{sheet.width:g}" height="{h:g}" fill="#fff"/>',
    ]
    anchor = {"left": "start", "center": "middle", "right": "end"}
    for item in sheet.items:
        if isinstance(item, Line):
            parts.append(
                f'<line x1="{item.a[0]:.3f}" y1="{h - item.a[1]:.3f}" x2="{item.b[0]:.3f}" '
                f'y2="{h - item.b[1]:.3f}" {stroke(item.layer)}/>'
            )
        elif isinstance(item, Circle):
            parts.append(
                f'<circle cx="{item.center[0]:.3f}" cy="{h - item.center[1]:.3f}" '
                f'r="{item.radius:.3f}" {stroke(item.layer)}/>'
            )
        elif isinstance(item, Arc):
            a0, a1 = math.radians(item.start), math.radians(item.end)
            start = (
                item.center[0] + item.radius * math.cos(a0),
                item.center[1] + item.radius * math.sin(a0),
            )
            end = (
                item.center[0] + item.radius * math.cos(a1),
                item.center[1] + item.radius * math.sin(a1),
            )
            sweep = (item.end - item.start) % 360
            large = 1 if sweep > 180 else 0
            # 반시계(수학) = SVG 에서는 y 를 뒤집어 시계 — sweep-flag 0.
            parts.append(
                f'<path d="M {pt(start)} A {item.radius:.3f} {item.radius:.3f} 0 {large} 0 '
                f'{pt(end)}" {stroke(item.layer)}/>'
            )
        elif isinstance(item, Poly):
            points = " ".join(pt(p) for p in item.points)
            parts.append(f'<polyline points="{points}" {stroke(item.layer)}/>')
        elif isinstance(item, Text):
            rotate = (
                f' transform="rotate({-item.angle:.3f} {item.at[0]:.3f} {h - item.at[1]:.3f})"'
                if item.angle
                else ""
            )
            x, y = item.at[0], h - item.at[1]
            parts.append(
                f'<text x="{x:.3f}" y="{y:.3f}" font-size="{item.height:.3f}" '
                f'font-family="{FONT_FAMILY}" text-anchor="{anchor[item.align]}" '
                f'fill="#111"{rotate}>{_escape(item.text)}</text>'
            )
        elif isinstance(item, Dim):
            parts.extend(_svg_dim(item, h))
    parts.append("</svg>")
    return "\n".join(parts)


def _svg_dim(item: Dim, h: float) -> list[str]:
    """치수 — 보조선 · 치수선 · 화살표 · 글씨(실제 크기)."""
    color = "#2563eb"

    def line(a: tuple[float, float], b: tuple[float, float]) -> str:
        return (
            f'<line x1="{a[0]:.3f}" y1="{h - a[1]:.3f}" x2="{b[0]:.3f}" y2="{h - b[1]:.3f}" '
            f'stroke="{color}" stroke-width="0.18"/>'
        )

    toward = 1.0 if item.offset > 0 else -1.0
    out: list[str] = []
    if item.horizontal:
        y = item.p1[1] + item.offset
        a, b = (item.p1[0], y), (item.p2[0], y)
        for p in (item.p1, item.p2):
            # 보조선 — 형상에서 1 띄우고 치수선 너머 1.5 까지.
            out.append(line((p[0], p[1] + toward * 1.0), (p[0], y + toward * 1.5)))
    else:
        x = item.p1[0] + item.offset
        a, b = (x, item.p1[1]), (x, item.p2[1])
        for p in (item.p1, item.p2):
            out.append(line((p[0] + toward * 1.0, p[1]), (x + toward * 1.5, p[1])))
    out.append(line(a, b))
    for tip, other in ((a, b), (b, a)):
        dx, dy = other[0] - tip[0], other[1] - tip[1]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        base = (tip[0] + ux * 2.5, tip[1] + uy * 2.5)
        left = (base[0] - uy * 0.6, base[1] + ux * 0.6)
        right = (base[0] + uy * 0.6, base[1] - ux * 0.6)
        points = " ".join(f"{p[0]:.3f},{h - p[1]:.3f}" for p in (tip, left, right))
        out.append(f'<polygon points="{points}" fill="{color}"/>')
    middle = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    label = _escape(_number(item.value))
    font = f'font-size="3" font-family="{FONT_FAMILY}" text-anchor="middle" fill="{color}"'
    if item.horizontal:
        out.append(
            f'<text x="{middle[0]:.3f}" y="{h - middle[1] - 0.8:.3f}" {font}>{label}</text>'
        )
    else:
        cx, cy = middle[0] - 0.8, h - middle[1]
        out.append(
            f'<text x="{cx:.3f}" y="{cy:.3f}" {font} '
            f'transform="rotate(-90 {cx:.3f} {cy:.3f})">{label}</text>'
        )
    return out


def write_pdf(sheet: Sheet) -> bytes:
    """PDF — SVG 를 그대로. 한글은 서버의 글꼴(나눔고딕)로 그린다."""
    import cairosvg

    return bytes(cairosvg.svg2pdf(bytestring=write_svg(sheet).encode("utf-8")))


def write_png(sheet: Sheet, width: int = 1400) -> bytes:
    """PNG — AI 가 눈으로 본다."""
    import cairosvg

    return bytes(
        cairosvg.svg2png(bytestring=write_svg(sheet).encode("utf-8"), output_width=width)
    )
