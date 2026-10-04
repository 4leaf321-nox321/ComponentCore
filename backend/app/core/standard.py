"""규격 부품 — 공용 부품에 **규격 사양**을 붙인 받침 · 위치 핀 · 토글 클램프.

생성기는 계획의 요구(받침 높이 · 핀 지름 · 패드 자리)를 먼저 세우고, 이 목록에서 맞는 것을
고른다. 없으면 지금처럼 즉석 도형(원기둥 · 상자)이다. **DB 를 모른다** — 서버가 목록을 값으로
넘긴다(`LibraryPart`). 형상은 사내에서 그린 레시피다(공급사 STEP 을 받아 다시 그린 것 — STEP
가져오기 · 다른 도면 가져오기 없이 혼자 선다, 등록할 때 서버가 검사한다).

**형상의 기준**(등록할 때 지킨다) — 받침 · 핀: 바닥 중심이 원점, 위가 +Z. 토글 클램프: 베이스
바닥 중심이 원점, 팔이 +X 로 뻗고, 누른 상태에서 패드 중심이 (reach, 0, pad_height).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from build123d import Part, Pos, Rot, Shape

#: 사양의 종류 — 생성기가 놓을 줄 아는 것만.
KINDS: dict[str, str] = {"support": "받침", "pin": "위치 핀", "clamp": "토글 클램프"}

#: 핀이 구멍에 맞는 지름 차(구멍 - 핀)의 상한(mm). 이보다 헐거우면 위치를 못 잡는다.
PIN_FIT_GAP = 0.5
#: 핀이 구멍에 들어가는 최소 길이(mm).
PIN_MIN_ENGAGEMENT = 2.0


@dataclass
class LibraryPart:
    """규격 부품 하나 — 카탈로그의 부품 · 버전 · 사양 · 형상 레시피."""

    source: str
    """레시피가 가리키는 열쇠 — `part:<id>@<버전>`."""
    kind: str
    part_no: str
    name: str
    spec: dict[str, Any]
    recipe: dict[str, Any]
    preference: int = 100
    """작을수록 먼저 — 같은 요구를 만족하면 앞의 것을 쓴다."""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LibraryPart:
        return cls(
            source=str(raw["source"]),
            kind=str(raw["kind"]),
            part_no=str(raw.get("part_no") or ""),
            name=str(raw.get("name") or ""),
            spec=dict(raw.get("spec") or {}),
            recipe=dict(raw.get("recipe") or {}),
            preference=int(raw.get("preference", 100)),
        )


@dataclass
class StandardRef:
    """계획이 고른 규격 부품 — 레시피에서는 `component` 가 된다."""

    source: str
    kind: str
    part_no: str
    name: str
    lift_params: dict[str, float] = field(default_factory=dict)
    """받침 높이를 따라가는 변수 — 값 = 받침 높이 + 이 수. 레시피에서는 `=받침_높이 + 수`."""
    params: dict[str, float] = field(default_factory=dict)
    """고정 값으로 넘기는 변수."""

    def values(self, lift: float) -> dict[str, float]:
        """이 받침 높이에서 구성품에 넘길 변수 값."""
        return {
            **self.params,
            **{name: round(lift + offset, 3) for name, offset in self.lift_params.items()},
        }


def _of(library: list[LibraryPart], kind: str) -> list[LibraryPart]:
    return sorted((one for one in library if one.kind == kind), key=lambda one: one.preference)


def _ref(item: LibraryPart, **kw: Any) -> StandardRef:
    return StandardRef(
        source=item.source, kind=item.kind, part_no=item.part_no, name=item.name, **kw
    )


def _range(
    spec: dict[str, Any], param_key: str, low_key: str, high_key: str
) -> tuple[str, float, float] | None:
    name = spec.get(param_key)
    if not name:
        return None
    return str(name), float(spec[low_key]), float(spec[high_key])


def support_for(
    library: list[LibraryPart], lift: float
) -> tuple[StandardRef, float, float] | None:
    """받침 — (고른 것, 쓸 받침 높이, 윗면 지름). 높이를 변수로 바꿀 수 있으면 원하는 높이
    그대로, 고정이면 원하는 높이에 가장 가까운 것(받침 높이가 그 높이가 된다)."""
    best: tuple[float, int, StandardRef, float, float] | None = None
    for item in _of(library, "support"):
        spec = item.spec
        span = _range(spec, "height_param", "height_min", "height_max")
        if span is not None and span[1] <= lift <= span[2]:
            ref = _ref(item, lift_params={span[0]: 0.0})
            used = lift
        else:
            ref = _ref(item)
            used = float(spec["height"])
        miss = abs(used - lift)
        candidate = (miss, item.preference, ref, used, float(spec["top_diameter"]))
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        return None
    return best[2], best[3], best[4]


def pin_for(
    library: list[LibraryPart], hole_diameter: float, lift: float, wanted: float, limit: float
) -> tuple[StandardRef, float, float] | None:
    """위치 핀 — (고른 것, 핀 지름, 들어가는 길이). 구멍보다 조금(0 < 차 ≤ 0.5) 가는 것 중 가장
    굵은 것. 길이를 변수로 바꿀 수 있으면 원하는 만큼(`wanted`), 고정이면 판 위 길이에서 받침
    높이를 뺀 만큼이 들어간다 — `limit`(구멍 깊이)를 넘거나 2 mm 보다 짧으면 못 쓴다."""
    fits = [
        item
        for item in _of(library, "pin")
        if 0 < hole_diameter - float(item.spec["diameter"]) <= PIN_FIT_GAP
    ]
    fits.sort(key=lambda one: (-float(one.spec["diameter"]), one.preference))
    for item in fits:
        spec = item.spec
        span = _range(spec, "length_param", "length_min", "length_max")
        if span is not None:
            total = min(max(lift + wanted, span[1]), span[2])
            engagement = total - lift
            ref = _ref(item, lift_params={span[0]: round(engagement, 3)})
        else:
            engagement = float(spec["length"]) - lift
            ref = _ref(item)
        if PIN_MIN_ENGAGEMENT <= engagement <= limit:
            return ref, float(spec["diameter"]), round(engagement, 3)
    return None


def clamps(library: list[LibraryPart]) -> list[LibraryPart]:
    """토글 클램프 후보 — 선호 순, 같으면 도달 거리가 짧은 것(작고 단단하다)부터."""
    return sorted(
        _of(library, "clamp"), key=lambda one: (one.preference, float(one.spec["reach"]))
    )


class Shapes:
    """규격 부품의 형상 — 같은 변수면 한 번만 평가한다(한 지그에 같은 받침이 넷)."""

    def __init__(self, library: list[LibraryPart]) -> None:
        self._by_source = {one.source: one for one in library}
        self._cache: dict[tuple[str, tuple[tuple[str, float], ...]], Shape] = {}

    def recipe(self, source: str) -> dict[str, Any]:
        return self._by_source[source].recipe

    def shape(self, ref: StandardRef, lift: float) -> Shape:
        from app.core.recipe import evaluate, parse

        values = ref.values(lift)
        key = (ref.source, tuple(sorted(values.items())))
        if key not in self._cache:
            recipe = self.recipe(ref.source)
            merged = {**recipe, "params": {**(recipe.get("params") or {}), **values}}
            self._cache[key] = evaluate(parse(merged), resolve_file=None).shape
        return self._cache[key]

    def placed(
        self,
        ref: StandardRef,
        lift: float,
        at: tuple[float, float, float],
        angle: float = 0.0,
    ) -> Part:
        moved: Part = Pos(*at) * Rot(0, 0, angle) * self.shape(ref, lift)
        return moved
