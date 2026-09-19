"""4단계 — Jig 자동 생성(조립).

계획을 부품으로 만들고 한 Compound 로 묶는다. 제품도 같은 좌표계로 올린다(`product_lift`).
"""

from __future__ import annotations

from build123d import Compound, Location, Part, Shape

from app.core import elements
from app.core.model import FixturePlan, JigElements, ProductGeometry
from app.core.options import JigOptions


def build_elements(plan: FixturePlan, opts: JigOptions) -> JigElements:
    lift = plan.product_lift
    others: list[Part] = []
    for bolt in plan.bolts:
        if lift > 0:
            x, y, _ = bolt.position
            others.append(
                elements.build_spacer(
                    x, y, bolt.hole_diameter, lift, f"스페이서 {bolt.label[-1]}"
                )
            )
        others.append(elements.build_bolt(bolt, lift))
    others += [elements.build_roller(one, lift) for one in plan.rollers]
    if plan.nose is not None:
        others.append(elements.build_nose(plan.nose, lift))
    if plan.impactor is not None:
        others.append(elements.build_impactor(plan.impactor, lift))
    return JigElements(
        base_plate=elements.build_base_plate(plan.base_plate),
        supports=[elements.build_support(one, lift) for one in plan.supports],
        locators=[elements.build_locator(one, lift) for one in plan.locators],
        clamps=[elements.build_clamp(one, lift, opts) for one in plan.clamps],
        others=others,
    )


def assemble(built: JigElements) -> Compound:
    jig = Compound(children=built.all_parts())
    jig.label = "jig"
    return jig


def lifted_product(geometry: ProductGeometry, plan: FixturePlan) -> Shape:
    product = geometry.shape.moved(Location((0, 0, plan.product_lift)))
    product.label = "product"
    return product
