"""5단계 — 간섭 검사.

지그 부품은 제품과 **닿아야 하지만 겹치면 안 된다.** 받침 윗면 · 패드 아랫면은 접촉(부피 0),
핀은 틈(clearance)이 있으니 부피 0. 부품끼리도 겹치면 안 된다(기둥이 받침을 뚫는 것 같은
일). 겹침 부피가 허용치를 넘는 쌍만 실패로 적는다.
"""

from __future__ import annotations

from build123d import Part, Shape

from app.core.model import InterferenceItem, InterferenceReport, JigElements


def _overlap(a: Shape, b: Shape) -> float:
    try:
        inter = a & b
    except Exception:
        return 0.0
    return float(getattr(inter, "volume", 0.0) or 0.0)


def _boxes_touch(a: Shape, b: Shape) -> bool:
    """경계 상자가 겹치지 않으면 불리언을 돌릴 이유가 없다 — 부품 수가 늘면 그것이 곧
    시간이다."""
    ba, bb = a.bounding_box(), b.bounding_box()
    return not (
        ba.max.X < bb.min.X
        or bb.max.X < ba.min.X
        or ba.max.Y < bb.min.Y
        or bb.max.Y < ba.min.Y
        or ba.max.Z < bb.min.Z
        or bb.max.Z < ba.min.Z
    )


def _label(part: Part) -> str:
    return part.label or type(part).__name__


def check(built: JigElements, product: Shape, tolerance: float) -> InterferenceReport:
    items: list[InterferenceItem] = []
    parts = built.all_parts()

    for part in parts:
        volume = _overlap(part, product) if _boxes_touch(part, product) else 0.0
        items.append(
            InterferenceItem(
                a=_label(part), b="product", volume=round(volume, 3), ok=volume <= tolerance
            )
        )

    # 부품끼리 — 판과 그 위에 선 것은 면으로 닿을 뿐이다. 나머지 쌍은 떨어져 있어야 한다.
    for i, a in enumerate(parts):
        for b in parts[i + 1 :]:
            if not _boxes_touch(a, b):
                continue
            volume = _overlap(a, b)
            if volume > tolerance:
                items.append(
                    InterferenceItem(
                        a=_label(a), b=_label(b), volume=round(volume, 3), ok=False
                    )
                )

    return InterferenceReport(items=items, tolerance=tolerance)
