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
from dataclasses import dataclass, field
from typing import Any

from build123d import Compound, Face, GeomType, Shape
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepOffset import BRepOffset_Skin
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
from OCP.GeomAbs import GeomAbs_Intersection
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS_Compound
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape

from app.core.recipe.unfold import _depth, _inside_point

#: 중간면 넓이 x t 와 부피가 이만큼 넘게 어긋나면 두께가 곳곳에 다르다고 본다.
_COVER_TOL = 0.02


class MidSurfaceError(ValueError):
    """사람이 읽고 고칠 수 있는 실패."""


@dataclass
class MidBody:
    """판 하나의 중간면."""

    name: str
    thickness: float
    area: float
    faces: int


@dataclass
class MidSurface:
    shape: Shape
    """중간면들 — 판마다 셸 하나(면 여럿)."""
    bodies: list[MidBody]
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "bodies": [
                {
                    "name": one.name,
                    "thickness": round(one.thickness, 4),
                    "area": round(one.area, 2),
                    "faces": one.faces,
                }
                for one in self.bodies
            ],
            "area": round(sum(one.area for one in self.bodies), 2),
            "notes": list(self.notes),
        }


def _area(shape: Any) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return float(props.Mass())


def midsurface(shape: Shape) -> MidSurface:
    """판(솔리드)마다 중간면 — 조립이면 구성품 이름을 붙인다."""
    from app.core.recipe.evaluate import _labeled_children

    children = _labeled_children(shape)
    named = (
        [(str(child.label), solid) for child in children for solid in child.solids()]
        if children
        else [(f"판 {index}", solid) for index, solid in enumerate(shape.solids(), start=1)]
    )
    if not named:
        raise MidSurfaceError(
            "솔리드가 없습니다. 중간면은 판(두께가 균일한 솔리드)에서만 추출할 수 있습니다."
        )
    if len(named) == 1 and not children:
        named = [("판", named[0][1])]
    shells: list[Any] = []
    bodies: list[MidBody] = []
    notes: list[str] = []
    for name, solid in named:
        try:
            mid, thickness, count = _one(solid)
        except MidSurfaceError as failure:
            if len(named) == 1:
                raise
            raise MidSurfaceError(f"{name}: {failure}") from failure
        area = _area(mid)
        shells.append(mid)
        bodies.append(MidBody(name=name, thickness=thickness, area=area, faces=count))
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
    return MidSurface(shape=Compound(together), bodies=bodies, notes=notes)


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
