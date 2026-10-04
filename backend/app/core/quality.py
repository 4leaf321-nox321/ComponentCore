"""형상 점검 — **해석이 메시를 못 만들 점을 보내기 전에** 안다.

DOE 는 치수를 끝까지 민다. 그러다 보면 형상은 멀쩡히 만들어지는데 해석(ANSYS)이 메시에서
막히는 점이 생긴다 — 구멍이 가장자리에 붙어 벽이 0.2 mm 가 되거나, 필렛이 깎여 0.05 mm 짜리
모서리 · 면이 남는다. 그런 점을 200개 중에서 해석이 하나씩 찾게 두지 않고, 만들 때 재서 표에
적는다(`manifest.csv` 의 `warnings`, 점 파일의 `quality`).

재는 것:

- **최소 벽 두께** — 면마다 몇 곳에서 면에 수직으로 **재료 안쪽으로** 광선을 쏘아 처음 닿는
  곳까지의 거리. 솔리드마다 따로 쏜다(맞닿은 다른 바디를 벽으로 읽지 않게).
- **짧은 모서리** · **좁은 면**(넓이의 두 배 / 둘레 — 가늘고 긴 띠는 폭이 된다).
- **형상이 올바른가**(BRepCheck), 솔리드 · 면 수. 기준 형상과 견줘 **바디가 쪼개지거나 합쳐진
  것**은 경고로, 면 수가 달라진 것은 알림으로 둔다(패턴 개수를 훑으면 면 수는 늘 바뀐다).

기준값은 스터디마다 바꾼다(`DoeStudy.checks`). 정밀한 두께 해석이 아니라 **눈에 띄게 나쁜 점을
거르는 체**다 — 광선을 쏜 곳 사이의 더 얇은 곳은 놓칠 수 있다.
"""

from __future__ import annotations

from typing import Any

#: 기준값(mm) — 이보다 작으면 경고. 지그 · 브래킷의 흔한 메시 크기에서 문제가 되는 수준.
DEFAULTS: dict[str, float] = {"min_wall": 0.5, "short_edge": 0.1, "narrow_face": 0.1}
#: 한 형상에 쏘는 광선 수의 상한 — 면이 수천 장인 조립에서도 점 하나가 몇 초를 넘지 않게.
MAX_RAYS = 6000
#: 광선의 출발점을 면에서 재료 안으로 이만큼 들여 놓는다 — 제 면에 닿는 것을 피한다.
_NUDGE = 1e-4


class QualityError(ValueError):
    """점검 기준이 틀렸다."""


def thresholds(raw: dict[str, Any] | None) -> dict[str, Any]:
    """스터디의 기준 — 준 것만 바꾸고 나머지는 기본값. `enabled` 가 거짓이면 재지 않는다."""
    out: dict[str, Any] = {"enabled": True, **DEFAULTS}
    for key, value in (raw or {}).items():
        if key == "enabled":
            out["enabled"] = bool(value)
            continue
        if key not in DEFAULTS:
            raise QualityError(
                f"알 수 없는 점검 기준입니다: {key} (선택 가능: {', '.join(DEFAULTS)})"
            )
        try:
            number = float(value)
        except (TypeError, ValueError) as failure:
            raise QualityError(f"점검 기준 {key} 값은 숫자(mm)여야 합니다.") from failure
        if number < 0:
            raise QualityError(f"점검 기준 {key} 값은 0 이상이어야 합니다.")
        out[key] = number
    return out


def _wall(solid: Any, samples: int) -> tuple[float | None, list[float] | None, int]:
    """솔리드 하나의 최소 벽 두께와 그 자리, 쏜 광선 수."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepTools import BRepTools
    from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Pnt2d
    from OCP.TopAbs import TopAbs_IN, TopAbs_REVERSED

    best: float | None = None
    where: list[float] | None = None
    rays = 0
    hit = BRepIntCurveSurface_Inter()
    for face in solid.faces():
        wrapped = face.wrapped
        try:
            umin, umax, vmin, vmax = BRepTools.UVBounds_s(wrapped)
            surface = BRepAdaptor_Surface(wrapped)
            inside = BRepTopAdaptor_FClass2d(wrapped, 1e-7)
        except Exception:  # 매개변수 범위가 없는 면 — 건너뛴다(체로 거르는 것이라 그만이다).
            continue
        reversed_face = wrapped.Orientation() == TopAbs_REVERSED
        for i in range(samples):
            for j in range(samples):
                u = umin + (umax - umin) * (i + 0.5) / samples
                v = vmin + (vmax - vmin) * (j + 0.5) / samples
                # 구멍 난 면의 가운데는 구멍 속이다 — 면 안의 점만 쏜다.
                if inside.Perform(gp_Pnt2d(u, v)) != TopAbs_IN:
                    continue
                props = BRepLProp_SLProps(surface, u, v, 1, 1e-7)
                if not props.IsNormalDefined():
                    continue
                normal = props.Normal()
                if reversed_face:
                    normal.Reverse()
                point = props.Value()
                # 바깥을 보는 법선의 반대 = 재료 안쪽.
                inward = gp_Dir(-normal.X(), -normal.Y(), -normal.Z())
                start = gp_Pnt(
                    point.X() + inward.X() * _NUDGE,
                    point.Y() + inward.Y() * _NUDGE,
                    point.Z() + inward.Z() * _NUDGE,
                )
                hit.Init(solid.wrapped, gp_Lin(start, inward), 1e-7)
                rays += 1
                nearest: float | None = None
                while hit.More():
                    distance = hit.W()
                    if distance > 1e-7 and (nearest is None or distance < nearest):
                        nearest = distance
                    hit.Next()
                if nearest is not None and (best is None or nearest + _NUDGE < best):
                    best = nearest + _NUDGE
                    where = [round(point.X(), 3), round(point.Y(), 3), round(point.Z(), 3)]
    return best, where, rays


def _degenerate(edge: Any) -> bool:
    from OCP.BRep import BRep_Tool

    return bool(BRep_Tool.Degenerated_s(edge.wrapped))


def inspect(shape: Any, limits: dict[str, Any] | None = None) -> dict[str, Any]:
    """형상 하나를 잰다. `warnings` 가 비면 기준을 다 지킨 것이다."""
    from OCP.BRepCheck import BRepCheck_Analyzer

    limits = thresholds(limits) if limits is None or "enabled" not in limits else limits
    solids = list(shape.solids())
    faces = list(shape.faces())
    edges = [one for one in shape.edges() if not _degenerate(one)]
    out: dict[str, Any] = {
        "valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
        "solids": len(solids),
        "faces": len(faces),
        "edges": len(edges),
    }
    # 면이 많으면 면마다 쏘는 수를 줄인다 — 점 하나가 몇 초를 넘지 않게.
    samples = 3 if len(faces) * 9 <= MAX_RAYS else 2 if len(faces) * 4 <= MAX_RAYS else 1
    wall: float | None = None
    wall_at: list[float] | None = None
    for solid in solids:
        found, at, _ = _wall(solid, samples)
        if found is not None and (wall is None or found < wall):
            wall, wall_at = found, at
    out["min_wall"] = round(wall, 4) if wall is not None else None
    out["min_wall_at"] = wall_at
    lengths = [float(one.length) for one in edges]
    short = [one for one in lengths if one < limits["short_edge"]]
    out["shortest_edge"] = round(min(lengths), 4) if lengths else None
    out["short_edges"] = len(short)
    widths = []
    for face in faces:
        perimeter = sum(float(edge.length) for edge in face.edges() if not _degenerate(edge))
        if perimeter > 0:
            widths.append(2 * float(face.area) / perimeter)
    narrow = [one for one in widths if one < limits["narrow_face"]]
    out["narrowest_face"] = round(min(widths), 4) if widths else None
    out["narrow_faces"] = len(narrow)
    out["warnings"] = _warnings(out, limits)
    return out


def _warnings(found: dict[str, Any], limits: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not found["valid"]:
        warnings.append(
            "형상이 유효하지 않습니다(BRepCheck). 해석 프로그램에서 읽지 못할 수 있습니다."
        )
    wall = found.get("min_wall")
    if wall is not None and wall < limits["min_wall"]:
        at = found.get("min_wall_at")
        where = f", 위치 ({', '.join(f'{v:g}' for v in at)}) 부근" if at else ""
        limit = limits["min_wall"]
        warnings.append(f"벽 두께 {wall:.3g} mm (기준 {limit:g}){where}")
    if found["short_edges"]:
        shortest = found["shortest_edge"]
        warnings.append(
            f"짧은 모서리 {found['short_edges']}개 (최소 {shortest:.3g} mm, "
            f"기준 {limits['short_edge']:g})"
        )
    if found["narrow_faces"]:
        narrowest = found["narrowest_face"]
        warnings.append(
            f"좁은 면 {found['narrow_faces']}개 (최소 {narrowest:.3g} mm, "
            f"기준 {limits['narrow_face']:g})"
        )
    return warnings


def compare(found: dict[str, Any], reference: dict[str, Any] | None) -> dict[str, Any]:
    """기준 형상과 견준다 — **바디가 쪼개지거나 합쳐진 것은 경고**(해석의 바디 · 재료 짝이
    어긋난다), 면 수가 달라진 것은 알림(`notes`)이다. 새 사본을 돌려준다."""
    out = {**found, "warnings": list(found.get("warnings") or []), "notes": []}
    if not reference:
        return out
    if reference.get("solids") != found.get("solids"):
        out["warnings"].append(
            f"바디 수가 기준과 다릅니다({reference.get('solids')} → {found.get('solids')})."
        )
    if reference.get("faces") != found.get("faces"):
        out["notes"].append(f"면 수 {reference.get('faces')} → {found.get('faces')}")
    return out
