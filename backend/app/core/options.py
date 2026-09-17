"""지그 생성 옵션 — 화면이 고치는 값의 정본.

기본값은 **손바닥만 한 부품(100mm 급)** 을 기준으로 잡았다. 큰 부품은 화면에서 바꾼다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class JigOptions:
    plate_margin: float = 25.0
    """제품 외곽에서 판 가장자리까지."""
    plate_thickness: float = 15.0
    plate_mount_hole_diameter: float = 8.5

    support_count: int = 4
    """3 또는 4. 3 이면 삼각 배치(3-2-1 원칙), 4 면 네 모서리."""
    support_diameter: float = 12.0
    support_height: float = 25.0
    support_inset: float = 6.0
    """바닥면 가장자리에서 받침 중심까지 들여 놓는 거리."""

    locator_pin_clearance: float = 0.05
    """핀 지름 = 구멍 지름 - 2 x 이 값."""
    locator_pin_max_engagement: float = 15.0
    locator_pin_max_count: int = 2
    locator_rest_size: tuple[float, float, float] = (12.0, 12.0, 20.0)

    clamp_count: int = 2
    clamp_pad_diameter: float = 16.0
    clamp_arm_width: float = 16.0
    clamp_arm_thickness: float = 10.0
    clamp_post_size: float = 20.0
    clamp_clearance_above: float = 12.0
    """클램프 팔의 아래면이 제품 윗면에서 얼마나 떠 있나(패드가 그 사이를 메운다)."""

    interference_tolerance: float = 0.5
    """이 부피(mm³) 이하의 겹침은 접촉으로 본다 — 닿는 면의 수치 오차가 이 아래로 나온다."""

    export_gltf: bool = True
    export_stl: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> JigOptions:
        """모르는 키는 버리고, 아는 키만 받는다 — 옛 실행의 옵션이 새 코드에서도 읽혀야
        한다."""
        known = {f.name for f in fields(cls)}
        picked = {key: value for key, value in (raw or {}).items() if key in known}
        if "locator_rest_size" in picked and isinstance(picked["locator_rest_size"], list):
            picked["locator_rest_size"] = tuple(picked["locator_rest_size"])
        return cls(**picked)
