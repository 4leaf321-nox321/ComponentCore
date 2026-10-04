"""측정값 — 설계점마다 **형상에서 바로 나오는 값**을 표의 열로.

해석 결과는 이 플랫폼에 돌아오지 않는다(2026-09-23 결정). 그래도 「질량 최소」 · 「두 구멍 사이
거리」 처럼 **형상만 보면 아는 값**은 해석 쪽이 목표 · 제약으로 쓰는데, 그것을 알려고 STEP 을
다시 열게 할 까닭이 없다. 고른 것만 잰다 — 기본은 아무것도 재지 않는다(표는 바꾼 변수와 파일이
주인이다, 2026-09-19).

종류:

- `volume` · `area` — 부피(mm³) · 겉넓이(mm²). `body` 를 주면 그 바디만.
- `size` — 경계상자의 크기(mm), `axis` 는 x · y · z.
- `region_area` — 선택 그룹(`region`)에 든 면들의 넓이 합(mm²).
- `distance` — 두 선택 그룹(`a` · `b`) 사이의 가장 가까운 거리(mm).
- `expr` — 식. 도면의 변수와 **앞에 적은 측정값**을 부른다 — `부피 * 7.85e-6`(kg) 처럼 밀도를
  곱해 질량을 만든다(재료는 조건의 것이고 단위계가 해석마다 달라 우리가 곱하지 않는다).
"""

from __future__ import annotations

from typing import Any

from app.core.recipe import params

KINDS = ("volume", "area", "size", "region_area", "distance", "expr")
#: 형상을 봐야 하는 것 — 같은 형상의 점끼리는 한 번만 잰다.
GEOMETRIC = ("volume", "area", "size", "region_area", "distance")
#: 표의 열 이름과 겹치면 안 되는 것(manifest.csv 의 고정 열).
RESERVED = {
    "point",
    "status",
    "step_file",
    "point_file",
    "unresolved",
    "interference",
    "warnings",
    "error",
}
MAX_MEASURES = 20


class MeasureError(ValueError):
    """측정값 정의가 틀렸다."""


def parse(
    raw: list[dict[str, Any]] | None,
    *,
    taken: set[str],
    variables: set[str],
    regions: set[str] | None = None,
    bodies: list[str] | None = None,
) -> list[dict[str, Any]]:
    """측정값 정의를 다듬고 본다. `taken` 은 열 이름으로 이미 쓰는 것(인자 이름),
    `variables` 는 식이 부를 수 있는 도면 변수. 선택 그룹 · 바디를 모르면(None) 이름을
    견주지 않는다."""
    items = list(raw or [])
    if len(items) > MAX_MEASURES:
        raise MeasureError(f"측정값은 최대 {MAX_MEASURES}개까지 지정할 수 있습니다.")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, one in enumerate(items, start=1):
        if not isinstance(one, dict):
            raise MeasureError(f"측정값 {index}: 이름과 종류를 함께 지정해야 합니다.")
        name = str(one.get("name") or "").strip()
        kind = str(one.get("kind") or "")
        where = f"측정값 ‘{name or index}’"
        if not name or len(name) > 40:
            raise MeasureError(f"측정값 {index}: 이름은 1~40자여야 합니다.")
        if name in seen or name in taken or name in RESERVED:
            raise MeasureError(f"{where}: 이름이 다른 열과 중복됩니다.")
        if kind not in KINDS:
            raise MeasureError(f"{where}: 종류는 {', '.join(KINDS)} 중 하나여야 합니다.")
        item: dict[str, Any] = {"name": name, "kind": kind}
        if kind in ("volume", "area", "size") and one.get("body"):
            body = str(one["body"])
            if bodies is not None and body not in bodies:
                raise MeasureError(
                    f"{where}: 도면에 바디 ‘{body}’이(가) 없습니다"
                    f"(존재하는 바디: {', '.join(bodies)})."
                )
            item["body"] = body
        if kind == "size":
            axis = str(one.get("axis") or "").lower()
            if axis not in ("x", "y", "z"):
                raise MeasureError(f"{where}: 크기의 축(axis)은 x, y, z 중 하나여야 합니다.")
            item["axis"] = axis
        if kind == "region_area":
            item["region"] = _region(one.get("region"), regions, where)
        if kind == "distance":
            item["a"] = _region(one.get("a"), regions, where)
            item["b"] = _region(one.get("b"), regions, where)
        if kind == "expr":
            text = str(one.get("expr") or "").strip()
            if not text:
                raise MeasureError(f"{where}: 식이 없습니다.")
            unknown = sorted(params.names_in(text) - variables - seen)
            if unknown:
                raise MeasureError(
                    f"{where}: 알 수 없는 이름이 있습니다({', '.join(unknown)}). 식에는 도면 "
                    "변수와 앞선 측정값만 사용할 수 있습니다."
                )
            try:
                params.evaluate_expression(text, dict.fromkeys(variables | seen, 1.0))
            except params.ExpressionError as failure:
                raise MeasureError(f"{where}: {failure}") from failure
            except (ArithmeticError, ValueError):
                pass  # 시험값 1 로 못 푼 것뿐 — 실제 값으로는 풀릴 수 있다.
            item["expr"] = text
        seen.add(name)
        out.append(item)
    return out


def _region(value: Any, regions: set[str] | None, where: str) -> str:
    name = str(value or "").strip()
    if not name:
        raise MeasureError(f"{where}: 선택 그룹 이름이 없습니다.")
    if regions is not None and name not in regions:
        known = ", ".join(sorted(regions)) or "(없음)"
        raise MeasureError(
            f"{where}: 해석 조건에 선택 그룹 ‘{name}’이(가) 없습니다"
            f"(정의된 선택 그룹: {known})."
        )
    return name


def _volume(shape: Any) -> float:
    """부피 — 정확도를 정해 잰다(기본값은 곡면에서 어긋난다)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props, 1e-6)
    return abs(float(props.Mass()))


def _area(shape: Any) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape.wrapped, props, 1e-6)
    return float(props.Mass())


def _body(shape: Any, name: str | None) -> Any:
    if not name:
        return shape
    from app.core.recipe.evaluate import _labeled_children

    for child in _labeled_children(shape):
        if str(getattr(child, "label", "")) == name:
            return child
    return None


def _picked(shape: Any, select: dict[str, Any], tags: dict[str, list[int]] | None) -> Any:
    """선택 그룹이 집은 것들을 한 덩어리로 — 거리를 잴 수 있게. 못 집으면 None."""
    from build123d import Compound

    from app.core.recipe.query import select_features

    found = select_features(shape, select, tags)
    pool = {"faces": shape.faces, "edges": shape.edges, "vertices": shape.vertices}.get(
        str(found["what"]), shape.faces
    )()
    picked = [pool[row["index"]] for row in found["items"] if 0 <= row["index"] < len(pool)]
    return Compound(picked) if picked else None


def geometric(
    shape: Any,
    measures: list[dict[str, Any]],
    *,
    topology_doc: dict[str, Any] | None = None,
    definitions: list[dict[str, Any]] | None = None,
    tags: dict[str, list[int]] | None = None,
) -> dict[str, float | None]:
    """형상을 봐야 하는 측정값들. 못 재면(그룹을 못 찾음 · 바디가 없음) None — 빈 칸이지 0 이
    아니다(0 으로 적으면 「질량 0」 인 점이 최적으로 뽑힌다)."""
    regions = (topology_doc or {}).get("regions") or {}
    selects = {str(one["name"]): one.get("select") or {} for one in definitions or []}
    out: dict[str, float | None] = {}
    for one in measures:
        kind = one["kind"]
        if kind not in GEOMETRIC:
            continue
        value: float | None = None
        try:
            if kind in ("volume", "area", "size"):
                target = _body(shape, one.get("body"))
                if target is not None:
                    if kind == "volume":
                        value = _volume(target)
                    elif kind == "area":
                        value = _area(target)
                    else:
                        size = target.bounding_box().size
                        value = float({"x": size.X, "y": size.Y, "z": size.Z}[one["axis"]])
            elif kind == "region_area":
                faces = regions.get(one["region"])
                if faces:
                    value = float(sum(float(row.get("area") or 0) for row in faces))
            elif kind == "distance":
                if one["a"] in regions and one["b"] in regions:
                    a = _picked(shape, selects.get(one["a"], {}), tags)
                    b = _picked(shape, selects.get(one["b"], {}), tags)
                    if a is not None and b is not None:
                        value = float(a.distance_to(b))
        except Exception:  # 재다 깨지면 빈 칸 — 형상은 만들어졌으니 점을 실패로 돌리지 않는다.
            value = None
        out[one["name"]] = round(value, 4) if value is not None else None
    return out


def derived(
    measures: list[dict[str, Any]],
    variables: dict[str, float],
    measured: dict[str, float | None],
) -> dict[str, float | None]:
    """식 측정값까지 채운 전부 — 적은 차례대로 푼다(앞의 측정값을 부를 수 있게). 부른 값이
    비었으면 그 식도 빈 칸이다."""
    out: dict[str, float | None] = {}
    known: dict[str, float] = dict(variables)
    for one in measures:
        name = one["name"]
        if one["kind"] == "expr":
            needed = params.names_in(one["expr"])
            value: float | None = None
            if all(n in known for n in needed):
                try:
                    value = round(params.evaluate_expression(one["expr"], known), 6)
                except (params.ExpressionError, ArithmeticError, ValueError):
                    value = None
        else:
            value = measured.get(name)
        out[name] = value
        if value is not None:
            known[name] = value
    return out
