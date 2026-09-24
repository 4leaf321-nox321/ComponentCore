"""우리 단위 환산이 **MatNexus 와 같은 말을 하는가.**

그쪽은 지금도 고쳐지고 있다(이 대화 중에 `density_si` 칸이 생겼다). 사람이 눈으로 맞춰 보는
것은 오래 못 간다 — 어긋나면 **검사가 말하게** 둔다.

우리는 그쪽 등록부를 런타임에 의존하지 않는다(꺼져 있어도 내보내기는 돼야 하고, 올려 둔
사본으로 골라도 마찬가지다). 이것은 **맞춰 보기**이지 가져오기가 아니다.
"""

from __future__ import annotations

from typing import Any

from app.core import units


def compare(theirs: list[dict[str, Any]]) -> dict[str, Any]:
    """그쪽 등록부와 우리 표를 맞춰 본다 — **다른 것만** 돌려준다.

    보는 것 셋:

    - **계 이름**: 우리가 아는 계를 그쪽도 아는가(열쇠를 맞춰 뒀다).
    - **기호표**: 같은 SI 단위를 그 계에서 같은 이름으로 부르는가. 표가 아니라 **실제로
      환산해 보고** 그 답을 비교한다 — 표만 맞춰 보면 「값이 안 바뀌면 들어온 기호를 그대로
      둔다」 같은 규칙을 놓친다.
    - **모르는 단위**: 그쪽 기호표에 있는데 우리 표에 없는 것 — 그것이 오는 날 우리는
      환산을 포기하고 `unconverted` 에 적는다(조용히 틀리지는 않지만, 알고는 있어야 한다).
    """
    problems: list[str] = []
    seen: set[str] = set()
    for one in theirs:
        key = str(one.get("key") or "")
        seen.add(key)
        ours = units.SYSTEMS.get(key)
        if ours is None:
            problems.append(f"그쪽에만 있는 계: {key} ({one.get('label')})")
            continue
        for si_name, their_name in (one.get("symbols") or {}).items():
            if si_name not in units.KNOWN:
                problems.append(f"우리가 못 읽는 SI 기호: {si_name} ({key} 에서 {their_name})")
                continue
            # **표가 아니라 행동을 본다.** 표를 맞춰 보면 「값은 안 바뀌니 들어온 기호를
            # 그대로 둔다」 같은 규칙을 놓친다 — 실제로 환산해 보고 그 답을 비교한다.
            _, our_name, ok = units.convert(1.0, si_name, key)
            if not ok:
                problems.append(f"{key}.{si_name}: 우리가 환산을 포기한다")
            elif our_name != their_name:
                problems.append(
                    f"{key}.{si_name}: 그쪽 「{their_name}」 · 우리 「{our_name}」"
                )
    for key in units.SYSTEMS:
        if key not in seen:
            problems.append(f"우리에게만 있는 계: {key}")
    return {"ok": not problems, "problems": problems, "compared": sorted(seen)}
