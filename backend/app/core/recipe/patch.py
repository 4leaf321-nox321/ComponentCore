"""레시피 부분 수정 — JSON 전체를 다시 쓰지 않고 **연산 몇 개**로 고친다.

AI 가 레시피 전체를 되보내면 크고 실수가 난다(칸 하나 빠뜨림 · id 오타). 여기 연산은 작고
검증된 것만 한다. 순수 함수 — 새 레시피를 돌려주고 원본은 두지 않는다. 검사는 호출부가
`check` 로 한다.

연산(op):
  set_param    {name, value}                     변수 값(없으면 만든다)
  remove_param {name}
  add_node     {node, before?}                   피처 추가(before 가 있으면 그 앞에)
  set_field    {id, field, value}                피처의 칸 하나
  remove_node  {id}                              피처 제거(다른 피처가 가리키면 거절)
  move_node    {id, before}                      순서 옮김(before 가 None 이면 끝으로)
  rename_node  {id, new_id}                      id 바꾸기(가리키는 곳도 같이)
"""

from __future__ import annotations

import copy
from typing import Any


class PatchError(ValueError):
    """어느 연산이 왜 안 되는지 — 그대로 화면 · AI 에 간다."""


#: 다른 피처의 id 를 담는 칸들 — 지우기 · 이름 바꾸기가 이것을 본다.
_REF_FIELDS = ("target", "targets", "tools", "sketch", "path", "profile", "sketches")


def _nodes(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = recipe.setdefault("nodes", [])
    if not isinstance(nodes, list):
        raise PatchError("nodes 가 목록이 아닙니다")
    return nodes


def _index(nodes: list[dict[str, Any]], node_id: str, what: str) -> int:
    for i, one in enumerate(nodes):
        if one.get("id") == node_id:
            return i
    raise PatchError(f"{what}: 피처 '{node_id}' 가 없습니다")


def _referrers(nodes: list[dict[str, Any]], node_id: str) -> list[str]:
    out = []
    for one in nodes:
        for key in _REF_FIELDS:
            value = one.get(key)
            if value == node_id or (isinstance(value, list) and node_id in value):
                out.append(str(one.get("id")))
                break
    return out


def apply(recipe: dict[str, Any], ops: list[dict[str, Any]]) -> dict[str, Any]:
    out = copy.deepcopy(recipe)
    for n, op in enumerate(ops, start=1):
        kind = op.get("op")
        where = f"{n}번 {kind}"
        nodes = _nodes(out)
        if kind == "set_param":
            name = str(op.get("name") or "").strip()
            if not name:
                raise PatchError(f"{where}: 변수 이름이 없습니다")
            params = out.setdefault("params", {})
            params[name] = op.get("value")
        elif kind == "remove_param":
            params = out.get("params") or {}
            params.pop(str(op.get("name")), None)
        elif kind == "add_node":
            node = op.get("node")
            if not isinstance(node, dict) or not node.get("id") or not node.get("op"):
                raise PatchError(f"{where}: node 에 id 와 op 가 있어야 합니다")
            if any(one.get("id") == node["id"] for one in nodes):
                raise PatchError(f"{where}: 피처 '{node['id']}' 가 이미 있습니다")
            before = op.get("before")
            at = _index(nodes, before, where) if before else len(nodes)
            nodes.insert(at, copy.deepcopy(node))
        elif kind == "set_field":
            i = _index(nodes, str(op.get("id")), where)
            field = str(op.get("field") or "")
            if not field or field in ("id", "op"):
                raise PatchError(f"{where}: id · op 는 set_field 로 못 바꿉니다(rename_node)")
            if op.get("value") is None:
                nodes[i].pop(field, None)
            else:
                nodes[i][field] = op["value"]
        elif kind == "remove_node":
            node_id = str(op.get("id"))
            i = _index(nodes, node_id, where)
            users = _referrers(nodes, node_id)
            if users:
                raise PatchError(
                    f"{where}: '{node_id}' 는 {', '.join(users)} 가 가리킵니다 — 그것부터 "
                    "고치세요"
                )
            del nodes[i]
        elif kind == "move_node":
            node_id = str(op.get("id"))
            i = _index(nodes, node_id, where)
            node = nodes.pop(i)
            before = op.get("before")
            at = _index(nodes, before, where) if before else len(nodes)
            nodes.insert(at, node)
        elif kind == "rename_node":
            old, new = str(op.get("id")), str(op.get("new_id") or "").strip()
            i = _index(nodes, old, where)
            if not new:
                raise PatchError(f"{where}: 새 id 가 없습니다")
            if any(one.get("id") == new for one in nodes):
                raise PatchError(f"{where}: 피처 '{new}' 가 이미 있습니다")
            nodes[i]["id"] = new
            for one in nodes:
                for key in _REF_FIELDS:
                    value = one.get(key)
                    if value == old:
                        one[key] = new
                    elif isinstance(value, list) and old in value:
                        one[key] = [new if v == old else v for v in value]
            if out.get("result") == old:
                out["result"] = new
        else:
            raise PatchError(f"{where}: 모르는 연산입니다")
    return out


# --- 면 기준 놓기 -----------------------------------------------------------------

BBox = tuple[tuple[float, float, float], tuple[float, float, float]]
_FACES = {
    "top": (2, +1),
    "bottom": (2, -1),
    "+x": (0, +1),
    "-x": (0, -1),
    "+y": (1, +1),
    "-y": (1, -1),
}


def place_on(
    mover: BBox,
    mover_translate: list[float],
    target: BBox,
    *,
    face: str = "top",
    offset: float = 0.0,
    align: str = "center",
) -> list[float]:
    """`mover` 를 `target` 의 `face` 에 얹는 translate 를 낸다 — 「지그 윗면에 부품 바닥을」.

    경계 상자로 잰다(형상이 닿는 면이 평면일 때 정확하다). `face` 축의 반대쪽 면끼리 닿고
    (`offset` 만큼 띄움), 나머지 두 축은 `align`(center | min | max) 으로 맞춘다. `mover` 의
    상자는 지금 translate 가 **이미 적용된** 것이므로, 그만큼 빼서 원래 자리 기준으로
    돌려준다."""
    if face not in _FACES:
        raise PatchError(f"face 는 {' · '.join(_FACES)} 중 하나입니다")
    axis, sign = _FACES[face]
    (mmin, mmax), (tmin, tmax) = mover, target
    out = list(mover_translate)
    for i in range(3):
        if i == axis:
            if sign > 0:
                out[i] += tmax[i] + offset - mmin[i]
            else:
                out[i] += tmin[i] - offset - mmax[i]
        else:
            if align == "min":
                out[i] += tmin[i] - mmin[i]
            elif align == "max":
                out[i] += tmax[i] - mmax[i]
            else:
                out[i] += (tmin[i] + tmax[i]) / 2 - (mmin[i] + mmax[i]) / 2
    return [round(v, 3) for v in out]
