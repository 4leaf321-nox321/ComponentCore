"""중간면 — 두께가 한결같은 얇은 판의 **가운데 면**.

얇은 판을 셸 요소로 해석할 때 해석 쪽이 받는 것은 입체가 아니라 두께 가운데의 면과 두께다.
판금 · 굽힌 판 · 쉘로 속을 판 상자 · 가져온 판금 STEP 이 그 대상이다.

1. 두께 `t` — 기준면(가장 넓은 평면)에서 재료 안쪽으로 광선을 쏴 반대 면까지(전개도와 같다).
2. **겉면 한쪽**을 모은다 — 기준면에서 엣지로 이어진 면 중 「안쪽으로 t 를 가면 반대 겉면이
   있는」 면만. 옆벽 · 끝면 · 구멍 벽은 그 거리가 t 가 아니라 빠지고, 그래서 반대쪽 겉면으로
   건너가지 않는다.
3. 그 겉면들을 꿰맨 셸을 안쪽으로 `t/2` 띄운다 — 굽힘(원통)은 반지름이 바뀌고, 각진 모서리는
   이웃 면과 만나는 자리에서 자른다(OCC 오프셋, 교차 이음).

잣대: 굽힌 판의 중간면 넓이 = 펼친 판(구멍 빼고), 쉘 상자 = 바닥(안팎 가운데) + 네 벽. 두께가
곳곳에 다르면(리브 · 보스) 그 자리는 겉면 모으기에서 빠진다 — `부피 / t` 와 중간면 넓이가
어긋나면 알린다.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from build123d import Compound, Face, GeomType, Shape, Shell, Vector
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex, BRepBuilderAPI_Sewing
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.BRepOffset import BRepOffset_Skin
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cylinder, GeomAbs_Intersection, GeomAbs_Plane
from OCP.gp import gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape

from app.core.recipe.unfold import _depth, _inside_point

#: 중간면 넓이 x t 와 부피가 이만큼 넘게 어긋나면 두께가 곳곳에 다르다고 본다.
_COVER_TOL = 0.02


class MidSurfaceError(ValueError):
    """사람이 읽고 고칠 수 있는 실패."""


@dataclass
class MidBody:
    """판 하나의 중간면 — 무게중심 · 경계상자는 **중간면 셸의 것**이다(받는 쪽이 `_mid.step` 의
    셸과 짝짓는다. 셸에는 이름이 없다 — 한글 이름은 STEP 에서 깨진다)."""

    name: str
    thickness: float
    area: float
    faces: int
    centroid: list[float] = field(default_factory=list)
    bbox: list[list[float]] = field(default_factory=list)
    step_product: str = ""
    """`_mid.step` 의 셸 이름 — 그 파트의 `topology.bodies[].step_product` 와 같은 ASCII
    글자."""


@dataclass
class MidSurface:
    shape: Shape
    """중간면들 — 판마다 셸 하나(면 여럿). **`bodies` 와 같은 순서**다."""
    bodies: list[MidBody]
    notes: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    """중간면을 못 만든 파트와 까닭 — `strict=False` 일 때만 찬다."""
    solids: list[Any] = field(default_factory=list)
    """`bodies` 와 같은 순서의 원래 솔리드 — 영역을 중간면으로 옮길 때(`attach`) 쓴다."""
    shells: list[Any] = field(default_factory=list)
    """`bodies` 와 같은 순서의 중간면 셸(OCP)."""

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "bodies": [
                {
                    "name": one.name,
                    "thickness": round(one.thickness, 4),
                    "area": round(one.area, 2),
                    "faces": one.faces,
                    "centroid": one.centroid,
                    "bbox": one.bbox,
                    "step_product": one.step_product,
                }
                for one in self.bodies
            ],
            "area": round(sum(one.area for one in self.bodies), 2),
            "notes": list(self.notes),
        }
        if self.failed:
            out["failed"] = [{"name": name, "error": error} for name, error in self.failed]
        return out


def _area(shape: Any) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return float(props.Mass())


def labeled(surface: MidSurface) -> Compound:
    """`_mid.step` 로 쓸 모양 — 셸마다 그 파트의 ASCII 이름(`step_product`)을 붙인 조립.
    이름 없이 셸만 담으면 받는 쪽이 순서 · 무게중심으로만 짝지어야 했다."""
    shells: list[Shape] = []
    for body, shell in zip(surface.bodies, surface.shells, strict=True):
        kind = shell.ShapeType()
        one: Shape
        if kind == TopAbs_SHELL:
            one = Shell(TopoDS.Shell_s(shell))
        elif kind == TopAbs_FACE:
            one = Face(TopoDS.Face_s(shell))
        else:
            one = Compound(TopoDS.Compound_s(shell))
        one.label = body.step_product or body.name
        shells.append(one)
    whole = Compound(children=shells)
    whole.label = "midsurface"
    return whole


def _box(shape: Any) -> tuple[list[float], list[list[float]]]:
    """셸의 넓이 무게중심과 경계상자(mm, 소수 셋째 자리)."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    center = props.CentreOfMass()
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    x0, y0, z0, x1, y1, z1 = box.Get()
    rounded = [round(float(v), 3) for v in (center.X(), center.Y(), center.Z())]
    return rounded, [
        [round(x0, 3), round(y0, 3), round(z0, 3)],
        [round(x1, 3), round(y1, 3), round(z1, 3)],
    ]


def midsurface(
    shape: Shape,
    only: Collection[str] | None = None,
    *,
    strict: bool = True,
    single_name: str = "판",
) -> MidSurface:
    """판(솔리드)마다 중간면 — 조립이면 구성품 이름을 붙인다.

    `only` 를 주면 그 이름의 파트만 — 쉘로 푸는 파트(`body_settings`)만 만들면 판이 아닌
    파트(강체 지그 블록)가 있어도 상관없다. `strict=False` 면 실패한 파트는 `failed` 에 까닭을
    남기고 나머지는 그대로 만든다 — 예전에는 판이 아닌 파트 하나가 점 전체를 오류로 만들어 쉘
    브래킷의 중간면도 나오지 않았다(SimEngBay, 2026-10-04). 단품의 이름은 `single_name`(DOE 는
    토폴로지와 같게 「전체」)."""
    from app.core.recipe.evaluate import _labeled_children
    from app.core.recipe.topology import slug

    children = _labeled_children(shape)
    named = (
        [(str(child.label), solid) for child in children for solid in child.solids()]
        if children
        else [(f"판 {index}", solid) for index, solid in enumerate(shape.solids(), start=1)]
    )
    # 셸 이름 — 토폴로지와 같은 규칙(조립이면 구성품의 순번 · 이름, 단품은 body_1).
    products = {
        str(child.label): slug(str(child.label), fallback=f"body_{index}")
        for index, child in enumerate(children, start=1)
    }
    if not named:
        raise MidSurfaceError(
            "솔리드가 없습니다. 중간면은 판(두께가 균일한 솔리드)에서만 추출할 수 있습니다."
        )
    if len(named) == 1 and not children:
        named = [(single_name, named[0][1])]
    if only is not None:
        wanted = set(only)
        missing = sorted(wanted - {name for name, _ in named})
        named = [(name, solid) for name, solid in named if name in wanted]
        if not named:
            raise MidSurfaceError(
                f"쉘로 지정한 파트가 형상에 없습니다: {', '.join(missing) or '없음'}."
            )
    shells: list[Any] = []
    bodies: list[MidBody] = []
    notes: list[str] = []
    failed: list[tuple[str, str]] = []
    solids: list[Any] = []
    for name, solid in named:
        try:
            mid, thickness, count = _one(solid)
        except MidSurfaceError as failure:
            if not strict:
                failed.append((name, str(failure)))
                continue
            if len(named) == 1:
                raise
            raise MidSurfaceError(f"{name}: {failure}") from failure
        area = _area(mid)
        shells.append(mid)
        solids.append(solid)
        centroid, bbox = _box(mid)
        bodies.append(
            MidBody(
                name=name,
                thickness=thickness,
                area=area,
                faces=count,
                centroid=centroid,
                bbox=bbox,
                step_product=products.get(name, "body_1" if not children else name),
            )
        )
        covered = area * thickness
        volume = float(solid.volume)
        if volume > 0 and abs(covered - volume) / volume > _COVER_TOL:
            notes.append(
                f"{name}: 두께가 위치마다 다릅니다. 중간면 면적 x 두께({covered:.0f} mm³)가 "
                f"부피({volume:.0f} mm³)와 {abs(covered - volume) / volume:.0%} 차이가 "
                "납니다. 두께가 다른 부분(리브, 보스)은 누락되었을 수 있습니다."
            )
    builder, together = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(together)
    for one in shells:
        builder.Add(together, one)
    return MidSurface(
        shape=Compound(together),
        bodies=bodies,
        notes=notes,
        failed=failed,
        solids=solids,
        shells=shells,
    )


# ── 영역을 중간면으로 ─────────────────────────────────────────────────────────


def _r3(point: Any) -> list[float]:
    return [round(float(point.X()), 3), round(float(point.Y()), 3), round(float(point.Z()), 3)]


def _distance(one: Any, other: Any) -> float:
    found = BRepExtrema_DistShapeShape(one, other)
    found.Perform()
    return float(found.Value()) if found.IsDone() else float("inf")


def _vertex(point: Any) -> Any:
    return BRepBuilderAPI_MakeVertex(gp_Pnt(point.X, point.Y, point.Z)).Vertex()


def _subshapes(shape: Any, kind: Any) -> list[Any]:
    found = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, found)
    return [found.FindKey(i) for i in range(1, found.Extent() + 1)]


def _mid_face(face: Any, normal: Vector) -> dict[str, Any]:
    """중간면의 면 한 장 — `normal` 은 **원래 겉면의 바깥 법선**(어느 쪽에서 눌렀는지)."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    surface = BRepAdaptor_Surface(TopoDS.Face_s(face))
    out: dict[str, Any] = {"area": round(float(props.Mass()), 3)}
    if surface.GetType() == GeomAbs_Plane:
        out["centroid"] = _r3(props.CentreOfMass())
        # `+ 0.0` — 반올림한 -0.0 을 0.0 으로(받는 쪽이 글자로 견줄 때 헷갈리지 않게).
        out["normal"] = [round(float(v), 4) + 0.0 for v in (normal.X, normal.Y, normal.Z)]
    else:
        box = Bnd_Box()
        BRepBndLib.Add_s(face, box)
        x0, y0, z0, x1, y1, z1 = box.Get()
        out["centroid"] = [
            round((x0 + x1) / 2, 3),
            round((y0 + y1) / 2, 3),
            round((z0 + z1) / 2, 3),
        ]
        if surface.GetType() == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            axis = cylinder.Axis()
            out["radius"] = round(float(cylinder.Radius()), 4)
            out["axis"] = {
                "point": _r3(axis.Location()),
                "direction": _r3(axis.Direction()),
            }
    return out


def _mid_edge(edge: Any) -> dict[str, Any]:
    curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge))
    middle = curve.Value((curve.FirstParameter() + curve.LastParameter()) / 2)
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, props)
    out: dict[str, Any] = {"midpoint": _r3(middle), "length": round(float(props.Mass()), 3)}
    if curve.GetType() == GeomAbs_Circle:
        out["radius"] = round(float(curve.Circle().Radius()), 4)
    return out


def _on_face(edge: Any, face: Any, tol: float) -> bool:
    """중간면의 모서리가 그 면 **위에** 놓였나 — 양 끝과 가운데가 다 면에 닿는다."""
    curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge))
    first, last = curve.FirstParameter(), curve.LastParameter()
    for parameter in (first, (first + last) / 2, last):
        point = curve.Value(parameter)
        vertex = BRepBuilderAPI_MakeVertex(point).Vertex()
        if _distance(vertex, face) > tol:
            return False
    return True


def _mapped(what: str, feature: Any, thickness: float, shell: Any) -> list[dict[str, Any]]:
    """원래 솔리드의 면 · 엣지 · 점 하나 → 중간면의 그것들.

    - 면: 면 안의 한 점이 중간면에서 **t/2** 떨어져 있으면 겉면이다 — 가장 가까운 중간면의 면.
      아니면 두께 쪽 면(끝면 · 옆면 · 구멍 벽)이다 — 그 면 위에 놓인 중간면의 모서리들.
    - 엣지: 가장 가까운(t/2 남짓) 중간면의 모서리, 길이가 비슷한 것.
    - 점: 중간면 위로 내린 점."""
    tol = max(1e-3, thickness * 0.05)
    if what == "faces":
        found = _inside_point(Face(feature.wrapped))
        if found is None:
            return []
        point, normal = found
        vertex = _vertex(point)
        faces = _subshapes(shell, TopAbs_FACE)
        if not faces:
            return []
        distance, nearest = min(
            ((_distance(vertex, one), one) for one in faces), key=lambda x: x[0]
        )
        if abs(distance - thickness / 2) <= tol:
            return [{"face": _mid_face(nearest, normal)}]
        return [
            {"edge": _mid_edge(edge)}
            for edge in _subshapes(shell, TopAbs_EDGE)
            if _on_face(edge, feature.wrapped, tol)
        ]
    if what == "vertices":
        found_point = BRepExtrema_DistShapeShape(feature.wrapped, shell)
        found_point.Perform()
        if not found_point.IsDone() or found_point.NbSolution() == 0:
            return []
        return [{"point": _r3(found_point.PointOnShape2(1))}]
    curve = BRepAdaptor_Curve(TopoDS.Edge_s(feature.wrapped))
    middle = curve.Value((curve.FirstParameter() + curve.LastParameter()) / 2)
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(feature.wrapped, props)
    length = float(props.Mass())
    best: tuple[float, Any] | None = None
    for edge in _subshapes(shell, TopAbs_EDGE):
        mine = GProp_GProps()
        BRepGProp.LinearProperties_s(edge, mine)
        if abs(float(mine.Mass()) - length) > max(tol, length * 0.05):
            continue
        gap = _distance(BRepBuilderAPI_MakeVertex(middle).Vertex(), edge)
        if gap <= thickness / 2 * 1.5 + tol and (best is None or gap < best[0]):
            best = (gap, edge)
    return [{"edge": _mid_edge(best[1])}] if best else []


def attach(
    regions: dict[str, list[dict[str, Any]]],
    shape: Shape,
    surface: MidSurface,
    definitions: list[dict[str, Any]] | None = None,
    tags: dict[str, list[int]] | None = None,
) -> None:
    """쉘 파트에 걸린 영역을 **중간면 기준으로도** — 지문마다 `mid` 를 붙인다(제자리에서).

    쉘 요소는 중간면 위에 있다. 원래 솔리드의 겉면 하중은 중간면의 면으로, 끝면 · 옆면 · 구멍
    벽의 구속은 중간면의 모서리로 옮겨야 받는 쪽이 건다(SimEngBay, 2026-10-04). `mid` 의 면에는
    **원래 겉면의 바깥 법선**을 둔다 — 쉘은 앞뒤가 없어 어느 쪽에서 눌렀는지를 따로 알려야
    한다. 못 옮긴 것은 `mid: []` 다. 쉘 파트가 아닌 지문에는 붙이지 않는다."""
    from app.core.recipe.query import select_features
    from app.core.recipe.topology import DEFAULT_REGIONS, _axis_matches

    if not surface.shells:
        return
    owners = [
        (
            body,
            {what: set(getattr(solid, what)()) for what in ("faces", "edges", "vertices")},
            shell,
        )
        for body, solid, shell in zip(
            surface.bodies, surface.solids, surface.shells, strict=True
        )
    ]
    for definition in definitions if definitions is not None else DEFAULT_REGIONS:
        prints = regions.get(definition["name"])
        if not prints:
            continue
        answer = select_features(shape, dict(definition.get("select") or {}), tags)
        rows = answer["items"]
        if definition.get("axis"):
            rows = [row for row in rows if _axis_matches(row, str(definition["axis"]))]
        if len(rows) != len(prints):
            continue
        what = str(answer["what"])
        every = getattr(shape, what)()
        for fingerprint, row in zip(prints, rows, strict=True):
            feature = every[row["index"]]
            for body, mine, shell in owners:
                if feature in mine[what]:
                    fingerprint["mid"] = _mapped(what, feature, body.thickness, shell)
                    break


def _one(solid: Any) -> tuple[Any, float, int]:
    """판 하나 — (중간면 셸, 두께, 모은 겉면 수)."""
    faces = list(solid.faces())
    planes = [one for one in faces if one.geom_type == GeomType.PLANE]
    if not planes:
        raise MidSurfaceError("평면이 없습니다. 판이 아닙니다.")
    base = max(planes, key=lambda one: float(one.area))
    found = _inside_point(base)
    thickness = _depth(solid, *found) if found is not None else None
    if thickness is None:
        raise MidSurfaceError("두께를 측정하지 못했습니다.")
    perimeter = sum(float(one.length) for one in base.edges())
    width = 2 * float(base.area) / perimeter if perimeter > 0 else 0.0
    if thickness >= width:
        raise MidSurfaceError(
            f"판이 아닙니다. 두께 {thickness:.3g} mm가 기준면의 폭({width:.3g} mm)보다 큽니다."
        )
    tol = max(1e-3, thickness * 0.02)

    index = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(solid.wrapped, TopAbs_FACE, index)
    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(solid.wrapped, TopAbs_EDGE, TopAbs_FACE, edge_faces)
    by_index = {index.FindIndex(one.wrapped): one for one in faces}

    def skin(face: Face) -> bool:
        point = _inside_point(face)
        depth = _depth(solid, *point) if point is not None else None
        return depth is not None and abs(depth - thickness) <= tol

    kept = {index.FindIndex(base.wrapped)}
    queue: deque[Face] = deque([base])
    while queue:
        current = queue.popleft()
        for edge in current.edges():
            for raw in edge_faces.FindFromKey(edge.wrapped):
                key = index.FindIndex(raw)
                if key in kept or key not in by_index:
                    continue
                if skin(by_index[key]):
                    kept.add(key)
                    queue.append(by_index[key])

    sewing = BRepBuilderAPI_Sewing(1e-6)
    for key in kept:
        sewing.Add(by_index[key].wrapped)
    sewing.Perform()
    offset = BRepOffsetAPI_MakeOffsetShape()
    offset.PerformByJoin(
        sewing.SewedShape(),
        -thickness / 2,
        1e-6,
        BRepOffset_Skin,
        False,
        False,
        GeomAbs_Intersection,
    )
    if not offset.IsDone():
        raise MidSurfaceError("겉면을 두께의 중간으로 오프셋하지 못했습니다.")
    mid = offset.Shape()
    if not BRepCheck_Analyzer(mid).IsValid():
        raise MidSurfaceError(
            "중간면이 유효하지 않습니다. 모서리가 지나치게 조밀하지 않은지 확인하십시오."
        )
    return mid, thickness, len(kept)
