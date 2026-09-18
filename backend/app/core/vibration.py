"""보(beam) 1차 굽힘 공진 — **가늠값** 계산기.

지그를 세트의 공진에 맞출 때, 튜닝부는 거의 언제나 「한쪽이 물린 납작한 보」다. 그 1차 굽힘
주파수는 닫힌 식으로 나온다 — 두께를 바꿔 가며 목표에 **가까운 값부터 찾아** 놓고, 그 다음에
실물이나 모달 해석으로 확인하면 된다.

**이것은 해석이 아니다.** 가정이 분명하다:

- 단면이 일정한 **직사각형 보**(폭 b, 두께 h), 길이 L. 끝에 붙은 것은 점질량으로 본다.
- 얇고 긴 보(L/h ≥ 5). 짧고 두꺼우면 전단 변형 때문에 실제가 더 낮다.
- 물린 자리는 **완전 고정**. 볼트 몇 개로 문 자리는 실제로 더 무르다 → 실제가 더 낮다.
- 감쇠 · 접촉 · 부품 자체의 유연함은 없다고 본다.

그래서 **±10% 는 흔하고, 물림이 무르면 더 벌어진다.** 목표 근처를 좁히는 데 쓰고, 마지막은
반드시 재어서 맞춘다.
"""

from __future__ import annotations

import math
from typing import Any

#: 재료의 탄성계수(MPa = N/mm²)와 밀도(g/cm³). 지그에 쓰는 것만.
MATERIALS: dict[str, dict[str, float]] = {
    "steel": {"youngs_mpa": 200_000, "density_g_per_cm3": 7.85},
    "stainless": {"youngs_mpa": 193_000, "density_g_per_cm3": 7.90},
    "aluminum": {"youngs_mpa": 70_000, "density_g_per_cm3": 2.70},
    "brass": {"youngs_mpa": 100_000, "density_g_per_cm3": 8.50},
    "abs": {"youngs_mpa": 2_300, "density_g_per_cm3": 1.05},
    "pla": {"youngs_mpa": 3_500, "density_g_per_cm3": 1.24},
    "nylon": {"youngs_mpa": 2_000, "density_g_per_cm3": 1.14},
    "pom": {"youngs_mpa": 2_800, "density_g_per_cm3": 1.41},
}

#: 물림에 따른 1차 모드 상수 β₁ (βL). 균일 보의 고전 해.
SUPPORTS: dict[str, float] = {
    "cantilever": 1.875104,  # 한쪽 고정 · 반대쪽 자유 — 지그 튜닝부의 기본
    "fixed": 4.730041,  # 양쪽 고정
    "simple": math.pi,  # 양쪽 단순 지지
}
#: 끝단 질량을 붙일 때 보 자신의 질량 중 「함께 움직이는 몫」(Rayleigh).
_EFFECTIVE_MASS = {"cantilever": 0.2427, "fixed": 0.3826, "simple": 0.4857}
#: 끝단(가운데) 강성 k = _STIFFNESS · E·I / L³.
_STIFFNESS = {"cantilever": 3.0, "fixed": 192.0, "simple": 48.0}


class VibrationError(ValueError):
    """값이 가정 밖이다 — 왜인지 말한다."""


def _material(name: str) -> dict[str, float]:
    found = MATERIALS.get(name.lower())
    if found is None:
        known = ", ".join(sorted(MATERIALS))
        raise VibrationError(f"모르는 재료입니다: {name} (아는 것: {known})")
    return found


def beam_frequency(
    *,
    length_mm: float,
    width_mm: float,
    thickness_mm: float,
    material: str = "aluminum",
    support: str = "cantilever",
    added_mass_g: float = 0.0,
) -> dict[str, Any]:
    """1차 굽힘 공진의 **가늠값**(Hz)과 그 근거."""
    if min(length_mm, width_mm, thickness_mm) <= 0:
        raise VibrationError("길이 · 폭 · 두께는 0 보다 커야 합니다")
    if support not in SUPPORTS:
        raise VibrationError(f"물림은 {', '.join(SUPPORTS)} 중 하나입니다")
    if added_mass_g < 0:
        raise VibrationError("붙는 질량은 0 이상이어야 합니다")
    spec = _material(material)
    youngs = spec["youngs_mpa"]  # N/mm²
    density = spec["density_g_per_cm3"] * 1e-9  # t/mm³ — mm · t · s · N 한 벌
    area = width_mm * thickness_mm
    second_moment = width_mm * thickness_mm**3 / 12  # mm⁴
    beam_mass_t = density * area * length_mm
    warnings: list[str] = []
    slender = length_mm / thickness_mm
    if slender < 5:
        warnings.append(
            f"길이/두께가 {slender:.1f} 로 짧고 두껍습니다 — 전단 때문에 실제는 더 낮습니다."
        )
    if width_mm > length_mm:
        warnings.append(
            "폭이 길이보다 넓습니다 — 보가 아니라 판에 가깝습니다(가늠값이 더 엇갑니다)."
        )

    if added_mass_g > 0:
        # 끝단 질량이 있으면 단일 자유도로 본다 — k 와 움직이는 질량으로.
        stiffness = _STIFFNESS[support] * youngs * second_moment / length_mm**3  # N/mm
        moving_t = _EFFECTIVE_MASS[support] * beam_mass_t + added_mass_g * 1e-6
        hertz = math.sqrt(stiffness / moving_t) / (2 * math.pi)
        how = "단일 자유도(강성 + 움직이는 질량) — 끝에 질량이 붙었을 때"
    else:
        beta = SUPPORTS[support]
        hertz = (beta**2 / (2 * math.pi)) * math.sqrt(
            youngs * second_moment / (density * area * length_mm**4)
        )
        how = "균일 보의 고전 해(βL 상수)"
    return {
        "hz": round(hertz, 2),
        "support": support,
        "material": material.lower(),
        "beam_mass_g": round(beam_mass_t * 1e6, 2),
        "added_mass_g": added_mass_g,
        "second_moment_mm4": round(second_moment, 3),
        "how": how,
        "warnings": warnings,
        "accuracy": (
            "**가늠값**입니다(±10% 는 흔합니다). 물림이 무르면 실제는 더 낮습니다 — "
            "목표 근처를 좁히는 데 쓰고 마지막은 재어서 맞추세요."
        ),
    }


def thickness_for_frequency(
    *,
    target_hz: float,
    length_mm: float,
    width_mm: float,
    material: str = "aluminum",
    support: str = "cantilever",
    added_mass_g: float = 0.0,
    bounds_mm: tuple[float, float] = (0.2, 100.0),
) -> dict[str, Any]:
    """목표 주파수를 내는 **두께**를 되짚는다 — 「세트와 같은 공진」 을 찾아가는 걸음.

    두께가 두꺼워질수록 주파수는 단조롭게 오른다(강성은 h³, 질량은 h). 그래서 이분법으로
    확실히 잡힌다. 범위 밖이면 그 사실을 말한다 — 폭 · 길이를 바꿔야 한다는 뜻이다."""
    if target_hz <= 0:
        raise VibrationError("목표 주파수는 0 보다 커야 합니다")
    low, high = bounds_mm

    def at(thickness: float) -> float:
        return float(
            beam_frequency(
                length_mm=length_mm,
                width_mm=width_mm,
                thickness_mm=thickness,
                material=material,
                support=support,
                added_mass_g=added_mass_g,
            )["hz"]
        )

    if at(low) > target_hz:
        raise VibrationError(
            f"{low} mm 로도 {at(low):.0f} Hz 라 목표 {target_hz:.0f} Hz 보다 높습니다 — "
            f"보를 길게 하거나 끝에 질량을 더하세요."
        )
    if at(high) < target_hz:
        raise VibrationError(
            f"{high} mm 로도 {at(high):.0f} Hz 라 목표 {target_hz:.0f} Hz 에 못 미칩니다 — "
            f"보를 짧게 하거나 재료를 바꾸세요."
        )
    for _ in range(60):
        middle = (low + high) / 2
        if at(middle) < target_hz:
            low = middle
        else:
            high = middle
    thickness = round((low + high) / 2, 3)
    got = beam_frequency(
        length_mm=length_mm,
        width_mm=width_mm,
        thickness_mm=thickness,
        material=material,
        support=support,
        added_mass_g=added_mass_g,
    )
    return {"thickness_mm": thickness, "target_hz": target_hz, **got}
