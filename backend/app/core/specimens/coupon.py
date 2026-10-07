"""시편 공통 — 물림 자리(면 나누기)와 메모.

인장 · 전단 · 겹치기 이음은 **그립 바디를 그리지 않는다.** 그립이 무는 자리를 시편의 면을
나눠 표시하고(윗면 · 아랫면의 양 끝), 그 자리에 구속을 바로 건다 — 물린 면은 그립과 함께
움직이므로 접촉 없이도 같은 결과이고, 모델이 가볍다.
"""

from __future__ import annotations

from typing import Any

#: 물림 자리를 면 테두리에서 띄우는 양(mm) — 테두리와 겹치면 면을 나누지 못한다.
MARGIN = 0.5


def patch(tag: str, side: str, at: list[Any], size: list[Any], label: str) -> dict[str, Any]:
    """사각 면 나누기 하나 — 대상(`target`)과 id 는 `chain` 이 채운다. `side` 는 윗면(top) ·
    아랫면(bottom)."""
    return {
        "op": "divide_face",
        "label": label,
        "on": {"role": side},
        "shape": "rect",
        "size": size,
        "at": at,
        "tag": tag,
    }


def chain(base: str, final: str, patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """몸통 `base` 에 면 나누기를 차례로 — 마지막 노드의 id 가 `final`(바디 이름이 된다)."""
    nodes: list[dict[str, Any]] = []
    target = base
    for index, one in enumerate(patches):
        node_id = final if index == len(patches) - 1 else f"{final}_{one['tag']}"
        nodes.append({"id": node_id, "target": target, **one})
        target = node_id
    return nodes


def tagged(*tags: str) -> dict[str, Any]:
    """태그 붙은 면들 — 하나면 그대로, 여럿이면 `any`."""
    if len(tags) == 1:
        return {"what": "faces", "tag": tags[0]}
    return {"any": [{"what": "faces", "tag": one} for one in tags]}


def review(verified: bool, source: str) -> list[str]:
    if verified:
        return []
    return [f"규격값을 아직 규격서와 대조하지 않았습니다(출처: {source or '없음'})."]
