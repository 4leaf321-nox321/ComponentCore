"""4단계 — Jig 자동 생성(조립).

계획을 부품으로 만들고 한 Compound 로 묶는다. 제품도 같은 좌표계로 올린다(`product_lift`).

**이름표는 레시피의 노드 id 와 같다**(`jig_recipe` — 바닥판 · 받침_1 · 위치_핀_1 · 클램프_1 …,
제품은 `제품`). 생성 결과의 간섭 보고 · 미리보기 · 지그 작업의 편집기가 한 이름을 쓴다 — 셋이
`support-1` · `받침 1` · `받침_1` 로 갈려 있어 편집한 요소를 간섭 보고와 짝지을 수 없었다.
"""

from __future__ import annotations

from build123d import Box, Compound, Cylinder, Location, Part, Pos, Shape

from app.core import elements, fasteners, standard
from app.core.model import (
    ClampSpec,
    FixturePlan,
    JigElements,
    LocatorSpec,
    ProductGeometry,
    SupportSpec,
)
from app.core.options import JigOptions

#: 제품의 이름표 — 미리보기 · 간섭 보고 · 편집기에서 같다.
PRODUCT = "제품"


def _labeled(part: Part, label: str) -> Part:
    part.label = label
    return part


def _support(spec: SupportSpec, lift: float, shapes: standard.Shapes) -> Part:
    if spec.standard is None:
        return elements.build_support(spec, lift)
    x, y, _ = spec.position
    return _labeled(shapes.placed(spec.standard, lift, (x, y, 0.0)), spec.label)


def _locator(spec: LocatorSpec, lift: float, shapes: standard.Shapes) -> Part:
    if spec.standard is None:
        return elements.build_locator(spec, lift)
    x, y, _ = spec.position
    return _labeled(shapes.placed(spec.standard, lift, (x, y, 0.0)), spec.label)


def _clamp(spec: ClampSpec, lift: float, opts: JigOptions, shapes: standard.Shapes) -> Part:
    """규격 토글 클램프 — 받침 블록(누르는 높이가 모자란 만큼) 위에 베이스, 팔이 패드 쪽.
    고정 나사가 있으면 블록에 그 여유 구멍이 난다(나사는 블록을 지나 판의 탭 구멍에 박힌다)."""
    if spec.standard is None:
        return elements.build_clamp(spec, lift, opts)
    bx, by, _ = spec.post_position
    body = shapes.placed(spec.standard, lift, (bx, by, spec.riser), spec.angle)
    if spec.riser > 0.5:
        riser: Part = Pos(bx, by, spec.riser / 2) * Box(
            spec.base_size, spec.base_size, spec.riser
        )
        if spec.mount_thread:
            clearance = fasteners.THREADS[spec.mount_thread][1]
            for x, y in spec.mount_holes:
                riser = riser - Pos(x, y, spec.riser / 2) * Cylinder(
                    clearance / 2, spec.riser * 2
                )
        body = riser + body
    return _labeled(body, spec.label)


def build_elements(
    plan: FixturePlan, opts: JigOptions, library: list[standard.LibraryPart] | None = None
) -> JigElements:
    """계획 → 부품. 규격 부품을 고른 자리는 그 형상(`core.standard`), 나머지는 즉석 도형."""
    lift = plan.product_lift
    shapes = standard.Shapes(library or [])
    others: list[Part] = []
    for index, bolt in enumerate(plan.bolts, start=1):
        if lift > 0:
            x, y, _ = bolt.position
            others.append(
                elements.build_spacer(x, y, bolt.hole_diameter, lift, f"스페이서_{index}")
            )
        others.append(elements.build_bolt(bolt, lift))
    others += [elements.build_roller(one, lift) for one in plan.rollers]
    others += [elements.build_nose(one, lift) for one in plan.noses]
    if plan.impactor is not None:
        others.append(elements.build_impactor(plan.impactor, lift))
    plate = elements.build_base_plate(plan.base_plate)
    plate.label = "바닥" if plan.kind == "drop" else "바닥판"
    return JigElements(
        base_plate=plate,
        supports=[_support(one, lift, shapes) for one in plan.supports],
        locators=[_locator(one, lift, shapes) for one in plan.locators],
        clamps=[_clamp(one, lift, opts, shapes) for one in plan.clamps],
        others=others,
    )


def assemble(built: JigElements) -> Compound:
    jig = Compound(children=built.all_parts())
    jig.label = "지그"
    return jig


def lifted_product(geometry: ProductGeometry, plan: FixturePlan) -> Shape:
    product = geometry.shape.moved(Location((0, 0, plan.product_lift)))
    product.label = PRODUCT
    return product
