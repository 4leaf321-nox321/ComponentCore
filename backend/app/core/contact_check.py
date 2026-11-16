"""조립의 **맞닿은 쌍과 접촉** — 빠뜨린 접촉, 채울 본딩, 모달에서 접촉이 풀리는 법.

실측(2026-11-16, CompCore → SimEngBay CalculiX): 판 · 받침 · 덮개 조립에 판-받침 본딩만 걸고
받침-덮개 접촉을 빠뜨렸더니 덮개가 떠 모드 여섯이 모두 0 Hz 였다 — 조건 점검도 형상 점검도,
받는 쪽도 말하지 않았다. 부품이 수십 개인 조립이면 하나쯤 빠뜨리기 쉬운 자리다.

맞닿은 쌍은 형상 점검이 잰다(`quality.touching` — 거리 0 · 맞닿은 넓이 > 0). 여기서는 그것을
**조건의 접촉과 견준다**: 접촉의 면 그룹이 어느 바디의 면인지 풀어 「선언된 쌍」 을 만들고,
맞닿은 쌍 중 선언되지 않은 것을 낸다. 그 쌍의 맞닿은 면을 찾아 **본딩으로 채울 그룹 · 접촉**도
낸다 — 면 규칙은 화면이 누른 면에 붙이는 것과 같다(`selector_candidates` 의 기본 후보).

모달(고유치)에는 비선형 접촉이 들지 않는다 — 마찰 · 거친 접촉은 붙은 것으로, 마찰 없음 · 분리
없음은 법선만 묶어 면을 따라 미끄러지는 것으로 풀린다(Ansys · CalculiX 같다). 미끄럼 접촉으로만
고정된 쪽에 이어진 부품에는 0 Hz 모드가 생긴다 — 그것도 여기서 말한다.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.core.recipe.query import (
    _EVERYTHING,
    body_parts,
    find_features,
    select_features,
    selector_candidates,
)

#: 고유치에서 법선만 묶이는(미끄러지는) 접촉.
SLIDING = frozenset({"frictionless", "no_separation"})
#: 고유치에서 붙은 것으로 풀리는 비선형 접촉.
STUCK_IN_EIGEN = frozenset({"frictional", "rough"})
#: 고유치를 푸는 해석 — 조화 응답도 모드를 겹쳐 푼다.
EIGEN_ANALYSES = frozenset({"modal", "harmonic"})
#: 이보다 작은 맞닿은 넓이(mm²)는 모서리 · 꼭짓점만 닿은 것이다.
_SHARED = 1e-6
_NAME = 60


def report(
    shape: Any,
    conditions: dict[str, Any],
    params: dict[str, Any] | None = None,
    tags: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    """조건 화면 · MCP 가 부르는 한 벌 — 맞닿은 쌍, 접촉 없이 맞닿은 쌍, 그 쌍을 본딩으로 채울
    그룹 · 접촉, 알림(`{where, level, text}` — 식 알림과 같은 꼴)."""
    from app.core import quality
    from app.core.recipe import follow
    from app.core.recipe import params as recipe_params
    from app.core.recipe.topology import named_parts

    solids = [(name, solid) for name, part in named_parts(shape) for solid in part.solids()]
    _, touching, skipped = quality._contacts(solids, 0.0)
    selections = [
        one for one in conditions.get("named_selections") or [] if isinstance(one, dict)
    ]
    # 식이 안 풀리면 저장된 그대로 — 식 알림이 따로 말한다.
    with contextlib.suppress(Exception):
        selections = follow.resolved(
            selections, recipe_params.resolve_params({"params": params})
        )
    bodies_of = region_bodies(shape, selections, tags)
    contacts = [one for one in conditions.get("contacts") or [] if isinstance(one, dict)]
    lacking = missing(touching, declared_pairs(contacts, bodies_of), excluded(conditions))
    taken = {str(one.get("name")) for one in selections} | {
        str(one.get("name")) for one in contacts
    }
    notes: list[dict[str, str]] = []
    if contacts:
        for one, text in zip(lacking, missing_warnings(lacking), strict=True):
            notes.append(
                {"where": f"바디 ‘{one['a']}’ · ‘{one['b']}’", "level": "warn", "text": text}
            )
    elif lacking:
        notes.append(
            {
                "where": "접촉",
                "level": "info",
                "text": f"맞닿은 바디 쌍이 {len(lacking)}개인데 접촉을 하나도 걸지 "
                "않았습니다 — 받는 쪽(SimEngBay)이 맞닿은 면을 모두 붙여 풉니다. 접촉을 "
                "하나라도 걸면 나머지 쌍은 떨어진 채로 풀리니, 그때는 「맞닿은 면으로 본딩 "
                "채우기」 로 함께 거십시오.",
            }
        )
    notes += eigen_notes(conditions, bodies_of)
    return {
        "touching": touching,
        "missing": lacking,
        "proposal": proposal(shape, [(one["a"], one["b"]) for one in lacking], taken, tags),
        "notes": notes,
        "skipped_pairs": skipped,
    }


def region_bodies(
    shape: Any,
    named_selections: list[dict[str, Any]],
    tags: dict[str, list[int]] | None = None,
) -> dict[str, set[str]]:
    """선택 그룹 → 그 면들이 속한 바디. 바디 그룹은 이름이 곧 바디다. 단품이면 「전체」 하나.

    규칙의 식(`=변수`)은 부른 쪽이 이미 풀어 둔다(`follow.resolved`)."""
    parts = body_parts(shape)
    out: dict[str, set[str]] = {}
    if not parts:
        return {str(one.get("name")): {"전체"} for one in named_selections}
    index = {face: i for i, face in enumerate(shape.faces())}
    owner: dict[int, str] = {}
    for name, part in parts.items():
        for face in part.faces():
            at = index.get(face)
            if at is not None:
                owner[at] = name
    for one in named_selections:
        name = str(one.get("name") or "")
        select = one.get("select") or {}
        if one.get("entity", "face") == "body":
            members = select["any"] if isinstance(select.get("any"), list) else [select]
            out[name] = {str(rule.get("body")) for rule in members if rule.get("body")}
            continue
        if one.get("entity", "face") != "face":
            continue
        try:
            rows = select_features(shape, {"what": "faces", **select}, tags)["items"]
        except Exception:
            continue
        out[name] = {owner[row["index"]] for row in rows if row["index"] in owner}
    return out


def declared_pairs(
    contacts: list[dict[str, Any]], bodies_of: dict[str, set[str]]
) -> set[frozenset[str]]:
    """접촉이 잇는 바디 쌍 — 접촉면 쪽 바디와 대상면 쪽 바디의 모든 짝(같은 바디끼리는
    빼고)."""
    pairs: set[frozenset[str]] = set()
    for one in contacts:
        for a in bodies_of.get(str(one.get("source") or ""), set()):
            for b in bodies_of.get(str(one.get("target") or ""), set()):
                if a != b:
                    pairs.add(frozenset((a, b)))
    return pairs


def missing(
    touching: list[dict[str, Any]],
    declared: set[frozenset[str]],
    skip: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """맞닿았는데 접촉이 없는 쌍 — `quality.touching` 의 줄 그대로. `skip`(해석 제외 파트)이 낀
    쌍은 뺀다 — 해석에 없는 파트는 이을 것이 없다(「조건_강체지그_쉘브래킷」 의 명판)."""
    return [
        one
        for one in touching
        if frozenset((one["a"], one["b"])) not in declared
        and one["a"] not in skip
        and one["b"] not in skip
    ]


def excluded(conditions: dict[str, Any]) -> set[str]:
    """해석에서 빠지는 파트 — 파트별 설정의 「해석 제외」."""
    return {
        str(one.get("name"))
        for one in conditions.get("body_settings") or []
        if isinstance(one, dict) and one.get("suppressed")
    }


def missing_warnings(rows: list[dict[str, Any]]) -> list[str]:
    """빠뜨린 접촉의 경고 줄 — 접촉을 하나라도 건 모델에서만 부른다(아무것도 안 걸면 받는 쪽이
    맞닿은 면을 다 붙인다)."""
    out = []
    for one in rows:
        area = f"넓이 {one['area']:g} mm², " if one.get("area") is not None else ""
        where = ", ".join(f"{v:g}" for v in one["at"])
        out.append(
            f"접촉 없이 맞닿은 바디 ‘{one['a']}’ · ‘{one['b']}’ ({area}위치 ({where}) 부근) — "
            "접촉을 건 모델에서는 이 쌍이 떨어진 채로 풀려 부품이 뜹니다. 붙어 있어야 하면 "
            "본딩을 거십시오(조건 화면의 「맞닿은 면으로 본딩 채우기」)."
        )
    return out


def eigen_notes(
    conditions: dict[str, Any], bodies_of: dict[str, set[str]]
) -> list[dict[str, str]]:
    """모달 · 조화 응답에서 접촉이 **어떻게 풀리나** — 접촉마다 한 줄, 그리고 미끄럼 접촉으로만
    고정된 쪽에 이어진 바디(0 Hz 모드가 생긴다)."""
    analysis = (conditions.get("analysis") or {}).get("type")
    if analysis not in EIGEN_ANALYSES:
        return []
    notes: list[dict[str, str]] = []
    contacts = [one for one in conditions.get("contacts") or [] if isinstance(one, dict)]
    for one in contacts:
        kind, where = one.get("type"), f"접촉 ‘{one.get('name', '')}’"
        if kind in STUCK_IN_EIGEN:
            notes.append(
                {
                    "where": where,
                    "level": "info",
                    "text": "고유치에는 마찰이 들지 않아 붙은 것(본딩)으로 풉니다 — 닫혀 있는 "
                    "면이면 본딩과 같은 주파수가 나옵니다.",
                }
            )
        elif kind in SLIDING:
            notes.append(
                {
                    "where": where,
                    "level": "info",
                    "text": "고유치에서는 법선 방향만 묶여 면을 따라 미끄러질 수 있습니다 — "
                    "이 접촉으로만 이어진 부품에는 0 Hz 모드가 생깁니다.",
                }
            )
    held: set[str] = set()
    for one in conditions.get("constraints") or []:
        if isinstance(one, dict):
            held |= bodies_of.get(str(one.get("on") or ""), set())
    if not held:
        # 아무것도 고정하지 않은 모달은 자유-자유다 — 강체 모드 여섯이 정상이다.
        return notes
    links: dict[str, set[str]] = {}
    slides: set[str] = set()
    for one in contacts:
        sources = bodies_of.get(str(one.get("source") or ""), set())
        targets = bodies_of.get(str(one.get("target") or ""), set())
        for a in sources:
            for b in targets:
                if a == b:
                    continue
                if one.get("type") in SLIDING:
                    slides |= {a, b}
                else:
                    links.setdefault(a, set()).add(b)
                    links.setdefault(b, set()).add(a)
    fixed = set(held)
    stack = list(held)
    while stack:
        for nxt in links.get(stack.pop(), set()) - fixed:
            fixed.add(nxt)
            stack.append(nxt)
    for body in sorted(slides - fixed - excluded(conditions)):
        notes.append(
            {
                "where": f"바디 ‘{body}’",
                "level": "warn",
                "text": "고정된 쪽과 미끄럼 접촉(마찰 없음 · 분리 없음)으로만 이어져 "
                "있습니다 — 모달에서 이 부품이 면을 따라 미끄러지는 0 Hz 모드가 생깁니다. "
                "붙어 있어야 하면 본딩으로 바꾸십시오.",
            }
        )
    return notes


def proposal(
    shape: Any,
    pairs: list[tuple[str, str]],
    taken: set[str],
    tags: dict[str, list[int]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """쌍마다 맞닿은 면을 찾아 **본딩으로 채울 것** — 면 그룹 둘(양쪽)과 접촉 하나.

    접촉면(`source`)은 맞닿은 넓이가 작은 쪽이다(화면의 안내: 「더 작은 쪽 면」). 이름은
    `taken`(이미 있는 그룹 · 접촉 이름)과 겹치지 않게 짓는다."""
    parts = body_parts(shape)
    faces = list(shape.faces())
    index = {face: i for i, face in enumerate(faces)}
    centers = {
        row["index"]: row.get("center")
        for row in find_features(shape, {"what": "faces", "limit": _EVERYTHING}, tags)["items"]
    }
    names = set(taken)
    selections: list[dict[str, Any]] = []
    contacts: list[dict[str, Any]] = []
    for a, b in pairs:
        if a not in parts or b not in parts:
            continue
        side_a = _touching_faces(parts[a], parts[b])
        side_b = _touching_faces(parts[b], parts[a])
        if not side_a or not side_b:
            continue
        rule_a = _rule(shape, [index[f] for f, _ in side_a if f in index], centers)
        rule_b = _rule(shape, [index[f] for f, _ in side_b if f in index], centers)
        if rule_a is None or rule_b is None:
            continue
        name_a = _unique(f"{a}-{b} {a}쪽", names)
        name_b = _unique(f"{a}-{b} {b}쪽", names)
        selections += [
            {"name": name_a, "entity": "face", "select": rule_a},
            {"name": name_b, "entity": "face", "select": rule_b},
        ]
        area_a = sum(area for _, area in side_a)
        area_b = sum(area for _, area in side_b)
        source, target = (name_a, name_b) if area_a <= area_b else (name_b, name_a)
        contacts.append(
            {
                "name": _unique(f"{a}-{b}", names),
                "type": "bonded",
                "source": source,
                "target": target,
            }
        )
    return {"named_selections": selections, "contacts": contacts}


def _touching_faces(part: Any, other: Any) -> list[tuple[Any, float]]:
    """`part` 의 면 중 `other` 와 넓이로 맞닿은 것 — (면, 맞닿은 넓이). 모서리만 닿은 옆면은
    거리가 0 이어도 넓이가 0 이라 빠진다."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    box = other.bounding_box()
    out = []
    for face in part.faces():
        if not _boxes_meet(face.bounding_box(), box):
            continue
        distance = BRepExtrema_DistShapeShape(face.wrapped, other.wrapped)
        if not distance.IsDone() or distance.Value() > 1e-6:
            continue
        shared = 0.0
        own = face.bounding_box()
        for mate in other.faces():
            if not _boxes_meet(own, mate.bounding_box()):
                continue
            try:
                shared += float(getattr(face & mate, "area", 0.0) or 0.0)
            except Exception:
                continue
        if shared > _SHARED:
            out.append((face, shared))
    return out


def _boxes_meet(first: Any, second: Any, slack: float = 1e-6) -> bool:
    return not (
        first.max.X + slack < second.min.X
        or second.max.X + slack < first.min.X
        or first.max.Y + slack < second.min.Y
        or second.max.Y + slack < first.min.Y
        or first.max.Z + slack < second.min.Z
        or second.max.Z + slack < first.min.Z
    )


def _rule(shape: Any, indices: list[int], centers: dict[int, Any]) -> dict[str, Any] | None:
    """면 번호들 → 저장할 규칙. 면마다 화면이 고르는 기본 후보(하나에만 맞고 치수에 흔들리지
    않는 것)를 쓰고, 여럿이면 합(`any`)."""
    rules = []
    for at in indices:
        point = centers.get(at)
        if not point:
            continue
        got = selector_candidates(shape, {"what": "faces", "point": point, "index": at})
        candidates = got.get("candidates") or []
        if not candidates:
            continue
        rules.append(candidates[_default(candidates)]["select"])
    if not rules:
        return None
    # 화면의 `groupSelect` 와 같은 꼴 — 하나면 그 규칙, 여럿이면 `{"any": [...]}`.
    return rules[0] if len(rules) == 1 else {"any": rules}


def _default(candidates: list[dict[str, Any]]) -> int:
    """화면의 `defaultRule` 과 같다 — 하나에만 맞고 흔들리지 않는 것, 없으면 하나에만 맞는
    것."""
    for i, one in enumerate(candidates):
        if one.get("matches") == 1 and one.get("stable") is not False:
            return i
    for i, one in enumerate(candidates):
        if one.get("matches") == 1:
            return i
    return 0


def _unique(base: str, taken: set[str]) -> str:
    name = base[:_NAME]
    number = 2
    while name in taken:
        suffix = f" {number}"
        name = base[: _NAME - len(suffix)] + suffix
        number += 1
    taken.add(name)
    return name
