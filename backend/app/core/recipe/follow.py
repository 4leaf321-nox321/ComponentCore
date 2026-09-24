"""좌표가 든 선택 규칙이 **치수를 따라가게** — 실험계획의 설계점마다 `near` 를 옮긴다.

선택 그룹은 이름(무엇)과 규칙(어떻게 찾나)으로 저장되고, 위치는 **내보낼 때** 설계점마다
확정된다. 그런데 규칙에 좌표(`near` — 「+X 방향 평면 중 이 면」 의 「이」)가 들어 있으면 그
좌표는 **고른 때의 형상**에서의 자리다. 치수가 바뀌면 면이 움직이므로 그대로 쓰면 딴 면을
집는다(실측 2026-09-24: 판 길이 80 → 130 에서 +X 옆면 대신 구멍 원통면).

그래서 **그 면이 변수마다 얼마나 움직이는지**를 잰다. 기준 형상과, 실험계획의 변수 하나씩을
아주 조금 바꾼 형상에서 같은 면을 찾아(조금만 바꾸면 가장 가까운 것이 곧 그 면이다) 자리가
움직인 양을 바꾼 양으로 나눈다. 설계점에서는 **기준 자리 + Σ 빠르기 · (변수 차)** 로 옮겨
찾는다. CAD 치수는 대개 자리에 1차로 걸리므로(상자의 면은 길이/2, 구멍은 제 자리) 이 예측은
거의 정확하다. 형상을 (변수 수 + 1) 번 더 만들 뿐이다 — 설계점 수와 상관없다.

**못 따라가는 것**: 면이 생기거나 없어지는 변화(구멍 개수 · 패턴 수 · 구멍이 판 밖으로 나감).
그때는 예측한 자리에서 먼 것을 집게 되므로 **거리를 재어 알린다**(`drift`) — 부르는 쪽이 그
이름을 「못 풀었다」 로 돌린다. 말없이 딴 면에 하중이 걸리는 것이 가장 나쁘다.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from build123d import Shape

from app.core.recipe.query import find_features

#: 규칙이 가리키는 것의 대표 점 — `find_features` 가 `near` 를 잴 때 쓰는 칸과 같다.
_KEY = {"faces": "center", "edges": "midpoint", "vertices": "point"}

#: 형상을 만드는 쪽 — 덮어쓸 변수(`{이름: 값}`)를 받아 (형상, 태그)를 돌려준다. 레시피와
#: 파일 · 구성품을 푸는 길은 부르는 쪽이 안다(코어는 모른다).
Build = Callable[[dict[str, float]], tuple[Shape, dict[str, list[int]] | None]]


def _rules(select: dict[str, Any]) -> list[dict[str, Any]]:
    """셀렉터 안의 규칙들 — 여럿을 묶은 그룹(`{"any": [...]}`)이면 그 목록, 아니면 그것
    하나."""
    members = select.get("any")
    if isinstance(members, list):
        return [one for one in members if isinstance(one, dict)]
    return [select]


def _anchor(
    shape: Shape, rule: dict[str, Any], tags: dict[str, list[int]] | None
) -> list[float] | None:
    """규칙이 지금 집는 첫 것의 대표 점."""
    rows = find_features(shape, rule, tags)["items"]
    if not rows:
        return None
    value = rows[0].get(_KEY.get(str(rule.get("what", "faces")), "center"))
    return [float(one) for one in value] if isinstance(value, list) else None


@dataclass
class Track:
    """좌표 규칙 하나 — 기준 형상에서 가리킨 자리와, 변수마다 1 바꿀 때 움직이는 양."""

    base: list[float]
    rate: dict[str, list[float]] = field(default_factory=dict)


def measure(
    definitions: list[dict[str, Any]],
    base_values: dict[str, float],
    factors: list[str],
    build: Build,
) -> dict[tuple[int, int], Track]:
    """좌표 규칙마다 **변수 하나를 조금 바꾸면 얼마나 움직이나**를 잰다.

    열쇠는 (정의 순번, 그 안의 규칙 순번). 좌표 규칙이 없으면 형상을 만들지도 않는다.
    """
    wanted = [
        (i, j, rule)
        for i, definition in enumerate(definitions)
        for j, rule in enumerate(_rules(definition.get("select") or {}))
        if isinstance(rule.get("near"), list)
    ]
    if not wanted:
        return {}
    shape, tags = build({})
    tracks: dict[tuple[int, int], Track] = {}
    for i, j, rule in wanted:
        at = _anchor(shape, rule, tags)
        if at is not None:
            tracks[(i, j)] = Track(base=at)
    for name in factors:
        if name not in base_values:
            continue
        start = float(base_values[name])
        step = max(abs(start), 1.0) * 1e-3
        nudged: tuple[float, Shape, dict[str, list[int]] | None] | None = None
        # 앞으로 조금, 안 되면 뒤로 조금 — 범위 끝의 값이면 한쪽이 형상을 못 만들 수 있다.
        for delta in (step, -step):
            try:
                other, other_tags = build({name: start + delta})
            except Exception:
                # 커널 · 레시피 어느 쪽 실패든 「이 방향으로는 안 된다」 는 뜻이다.
                continue
            nudged = (delta, other, other_tags)
            break
        if nudged is None:
            # 이 변수로는 형상이 안 만들어진다 — 따라가지 않는다(움직임 0). 설계점에서 멀리
            # 떨어진 것을 집으면 `drift` 가 알린다.
            continue
        delta, other, other_tags = nudged
        for (i, j), track in tracks.items():
            rule = _rules(definitions[i]["select"])[j]
            moved = _anchor(other, {**rule, "near": track.base, "limit": 1}, other_tags)
            if moved is not None:
                track.rate[name] = [
                    (a - b) / delta for a, b in zip(moved, track.base, strict=True)
                ]
    return tracks


def follow(
    definitions: list[dict[str, Any]],
    tracks: dict[tuple[int, int], Track],
    base_values: dict[str, float],
    values: dict[str, Any],
) -> list[dict[str, Any]]:
    """설계점의 값으로 좌표 규칙을 옮긴 **새** 정의들. 좌표 규칙이 없으면 그대로 돌려준다."""
    if not tracks:
        return definitions
    out = deepcopy(definitions)
    for (i, j), track in tracks.items():
        shift = [0.0, 0.0, 0.0]
        for name, rate in track.rate.items():
            try:
                change = float(values.get(name, base_values[name])) - float(base_values[name])
            except (TypeError, ValueError):
                continue
            shift = [s + r * change for s, r in zip(shift, rate, strict=True)]
        _rules(out[i]["select"])[j]["near"] = [
            round(b + s, 6) for b, s in zip(track.base, shift, strict=True)
        ]
    return out


def drift(
    definitions: list[dict[str, Any]],
    tracks: dict[tuple[int, int], Track],
    shape: Shape,
    tags: dict[str, list[int]] | None,
    tolerance: float,
) -> dict[str, float]:
    """옮긴 자리에서 **실제로 집은 것**이 얼마나 떨어졌나 — 허용보다 먼 이름과 그 거리.

    1차로 걸리는 치수면 거의 0 이다. 멀다는 것은 면이 생기거나 없어져 **딴 것을 집었다**는
    뜻이다. 못 찾은 것(0 개)은 여기서 말하지 않는다 — 영역 풀기가 이미 「못 풀었다」 고 한다.
    """
    out: dict[str, float] = {}
    for i, j in tracks:
        definition = definitions[i]
        rule = _rules(definition.get("select") or {})[j]
        at = _anchor(shape, rule, tags)
        if at is None or not isinstance(rule.get("near"), list):
            continue
        gap = math.dist(at, [float(one) for one in rule["near"]])
        if gap > tolerance:
            name = str(definition.get("name", ""))
            out[name] = round(max(gap, out.get(name, 0.0)), 3)
    return out


def tolerance_for(shape: Shape) -> float:
    """「멀다」 의 문턱 — 형상 크기의 2 %(최소 0.5 mm). 1차로 걸리는 치수의 오차는 이보다
    훨씬 작다."""
    box = shape.bounding_box()
    return max(0.5, 0.02 * float(box.diagonal))
