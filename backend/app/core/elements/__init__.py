"""지그 부품 — 계획(FixturePlan)을 build123d 형상으로.

**전부 최종 좌표계다**: 판 윗면이 z=0, 제품은 `product_lift` 만큼 떠 있다. 계획은 제품
좌표계(제품 바닥 z=0)로 적혀 있으므로, 여기서 `lift` 를 더해 옮긴다.
"""

from app.core.elements.base_plate import build_base_plate
from app.core.elements.bolt import build_bolt, build_spacer
from app.core.elements.clamp import build_clamp
from app.core.elements.impactor import build_impactor
from app.core.elements.locator import build_locator
from app.core.elements.roller import build_nose, build_roller
from app.core.elements.support import build_support

__all__ = [
    "build_base_plate",
    "build_bolt",
    "build_clamp",
    "build_impactor",
    "build_locator",
    "build_nose",
    "build_roller",
    "build_spacer",
    "build_support",
]
