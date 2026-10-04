"""접촉 자리 새기기 — 조립의 바디끼리 닿는 자리를 서로의 면에 새겨 나눈다(`imprint`).

판 위에 블록이 앉으면 판 윗면은 통째로 한 면(6000 mm²), 블록 아랫면은 1600 mm² 다. 접촉을
「블록 아랫면 ↔ 판 윗면」 으로 걸면 받는 쪽(Mechanical)이 넓이가 다른 두 면을 짝지어야 하고,
닿지 않은 판 윗면까지 접촉 후보가 된다. 새기면 판 윗면이 **닿는 1600 과 나머지 4400 으로
갈린다** — 짝이 넓이 · 무게중심까지 꼭 같아진다.

OCC 의 일반 융합(`BOPAlgo_Builder`)이 바디들을 서로 자르고 닿는 면을 **나눠 갖게** 만든다.
나눠 가진 면은 면 목록에 한 번만 나와(방향이 한쪽 것) 「블록의 아랫면(-Z)」 을 고르는
규칙이 깨진다 — 그래서 새긴 뒤 바디마다 따로 복사해 각자 제 면을 갖게 한다.

닿는 자리마다 태그가 붙는다: `받침판/블록` 은 받침판 쪽 면(블록이 닿는 자리), `블록/받침판`
은 블록 쪽 면. 조건이 `{"what": "faces", "tag": "받침판/블록"}` 로 집는다.
"""

from __future__ import annotations

import copy
from typing import Any

from build123d import Face, Part, Shape, Solid
from OCP.BOPAlgo import BOPAlgo_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.TopoDS import TopoDS

from app.core.recipe.query import body_parts


class ImprintError(ValueError):
    """사람이 읽고 고칠 수 있는 실패 — 평가기가 노드 id 를 붙인다."""


def imprint(shape: Shape) -> tuple[Part, dict[str, dict[str, Any]]]:
    """(새긴 조립, 태그 → 패치). 패치는 평가기의 면 나누기 패치와 같은 모양이라 태그로
    되찾는다."""
    bodies = body_parts(shape)
    if len(bodies) < 2:
        raise ImprintError(
            "조립(group)이어야 합니다. 접촉 위치가 생기려면 바디가 2개 이상이어야 합니다."
        )
    builder = BOPAlgo_Builder()
    owners: list[tuple[str, Solid]] = []
    for name, body in bodies.items():
        for solid in body.solids():
            builder.AddArgument(solid.wrapped)
            owners.append((name, solid))
    builder.SetRunParallel(False)
    builder.SetNonDestructive(True)
    builder.Perform()
    if builder.HasErrors():
        raise ImprintError("바디 간 분할에 실패했습니다. 바디가 유효한지 확인하십시오.")

    cut: dict[str, list[Solid]] = {name: [] for name in bodies}
    for name, solid in owners:
        pieces = [Solid(TopoDS.Solid_s(one)) for one in builder.Modified(solid.wrapped)]
        if len(pieces) > 1:
            raise ImprintError(
                f"‘{name}’이(가) 다른 바디와 겹칩니다(간섭). 임프린트는 접촉만 하는 바디에 "
                "적용됩니다. 겹침은 조립의 간섭 검사로 확인하십시오."
            )
        cut[name].append(pieces[0] if pieces else solid)

    patches = _contacts(cut)
    children = []
    for name, solids in cut.items():
        # 나눠 가진 면을 끊는다 — 바디마다 제 면(제 방향)을 갖게.
        own = [
            Solid(TopoDS.Solid_s(BRepBuilderAPI_Copy(one.wrapped).Shape())) for one in solids
        ]
        child = Part(children=own)
        child.label = name
        children.append(child)
    return Part(children=children), patches


def _contacts(cut: dict[str, list[Solid]]) -> dict[str, dict[str, Any]]:
    names = list(cut)
    patches: dict[str, dict[str, Any]] = {}
    for i, first in enumerate(names):
        mine = [face for solid in cut[first] for face in solid.faces()]
        for second in names[i + 1 :]:
            theirs = [face for solid in cut[second] for face in solid.faces()]
            shared = [one for one in mine if any(one.is_same(other) for other in theirs)]
            if not shared:
                continue
            patches[f"{first}/{second}"] = _patch(shared)
            patches[f"{second}/{first}"] = _patch(
                [other for other in theirs if any(other.is_same(one) for one in shared)]
            )
    return patches


def _patch(faces: list[Face]) -> dict[str, Any]:
    """면 나누기 패치와 같은 모양 — 가운데 · 법선 · 크기 · 영역. 법선은 그 바디 쪽 면의 것
    (나눠 가진 면도 바디마다 제 방향을 들고 있다)."""
    first = faces[0]
    normal = first.normal_at(first.center())
    box = faces[0].bounding_box()
    for one in faces[1:]:
        box = box.add(one.bounding_box())  # 새 상자를 돌려준다 — 제자리에서 안 키운다(실측)
    middle = box.center()
    return {
        "at": [round(float(v), 3) for v in (middle.X, middle.Y, middle.Z)],
        "normal": [round(float(v), 3) for v in (normal.X, normal.Y, normal.Z)],
        "extent": round(float(max(box.size.X, box.size.Y, box.size.Z)) / 2, 3),
        "region": [copy.copy(one) for one in faces],
    }
