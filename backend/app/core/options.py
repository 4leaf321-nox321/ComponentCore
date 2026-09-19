"""지그 생성 옵션 — 화면이 고치는 값의 정본.

기본값은 **손바닥만 한 부품(100mm 급)** 을 기준으로 잡았다. 큰 부품은 화면에서 바꾼다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

#: 지그 형식 — 어떤 규칙으로 놓나. 화면의 「형식」 과 같은 이름.
JIG_KINDS: dict[str, str] = {
    "clamped": "판 · 클램프 고정",
    "bolted": "볼트 고정 (진동 · 충격 시험)",
    "bending": "3점 굽힘 픽스처",
    "drop": "낙하 · 충격 자세",
}


@dataclass
class JigOptions:
    kind: str = "clamped"
    """clamped | bolted | bending | drop — 아래 옵션 중 그 형식이 쓰는 것만 뜻이 있다."""

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

    # --- 볼트 고정 --------------------------------------------------------------
    bolt_max_count: int = 4
    """부품의 수직 관통 구멍 중 몇 개에 볼트를 넣나. 서로 가장 멀리 떨어진 것부터."""
    bolt_head: str = "hex"
    """hex | socket — 육각 머리 · 소켓(원통) 머리."""
    bolt_washer: bool = True
    bolt_spacer_height: float = 0.0
    """0 이면 부품이 판에 바로 앉는다. 주면 볼트마다 그 높이의 스페이서를 넣는다."""
    bolt_plate_engagement: float = 1.5
    """볼트가 판에 박히는 깊이 = 호칭 지름 x 이 값."""

    # --- 3점 굽힘 ---------------------------------------------------------------
    bending_span_ratio: float = 0.8
    """지지 간격 = 부품의 긴 변 x 이 값. `bending_span` 을 주면 그것이 우선."""
    bending_span: float = 0.0
    bending_roller_diameter: float = 10.0
    bending_nose_diameter: float = 10.0
    bending_roller_margin: float = 5.0
    """롤러가 부품 폭보다 양쪽으로 얼마나 더 긴가."""
    bending_nose_stem_height: float = 30.0

    # --- 낙하 · 충격 -----------------------------------------------------------
    drop_orientation: str = "bottom"
    """무엇이 아래를 보나 — bottom | top | +x | -x | +y | -y | edge | corner."""
    drop_gap: float = 1.0
    """바닥과 부품 사이 틈(mm). 해석은 초기 속도로 낙하를 준다."""
    drop_impactor: str = "none"
    """none | ball | pen — 위에서 떨어지는 것(충격 시험). 부품이 떨어지는 낙하면 none."""
    drop_ball_diameter: float = 25.0
    drop_impactor_clearance: float = 1.0

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
