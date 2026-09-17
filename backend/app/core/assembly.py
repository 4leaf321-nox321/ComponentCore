"""4단계 — Jig 자동 생성(조립).

계획을 부품으로 만들고 한 Compound 로 묶는다. 제품도 같은 좌표계로 올린다(`product_lift`).
"""

from __future__ import annotations

from build123d import Compound, Location, Shape

from app.core import elements
from app.core.model import FixturePlan, JigElements, ProductGeometry
from app.core.options import JigOptions


def build_elements(plan: FixturePlan, opts: JigOptions) -> JigElements:
    lift = plan.product_lift
    return JigElements(
        base_plate=elements.build_base_plate(plan.base_plate),
        supports=[elements.build_support(one, lift) for one in plan.supports],
        locators=[elements.build_locator(one, lift) for one in plan.locators],
        clamps=[elements.build_clamp(one, lift, opts) for one in plan.clamps],
    )


def assemble(built: JigElements) -> Compound:
    jig = Compound(children=built.all_parts())
    jig.label = "jig"
    return jig


def lifted_product(geometry: ProductGeometry, plan: FixturePlan) -> Shape:
    product = geometry.shape.moved(Location((0, 0, plan.product_lift)))
    product.label = "product"
    return product
