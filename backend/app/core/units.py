"""단위계 — **차원으로 환산한다.** 항목 이름은 보지 않는다.

## 왜 있어야 하나

MatNexus 가 주는 값은 **한 계로 모여 있지 않다**(2026-09-24 실측): 밀도만 `tonne/mm3`
(mm·tonne·s 계)이고 나머지 `value_si` 는 진짜 SI(`Pa` · `W/(m.K)` · `J/(kg.K)` · `1/K`)다.
우리 STEP 은 mm 이므로 해석은 mm·tonne·s 로 풀 텐데, 그대로 넣으면 밀도는 맞고 탄성계수는
**10⁶ 배 틀린다**. 결과가 안 나오는 것이 아니라 **그럴듯한 값이 나오고 틀린다** — 제일 나쁜
종류다.

## 「어느 것이 영률인가」 는 여전히 안 본다

환산에 필요한 것은 **단위 문자열뿐**이다. `2.06e11 Pa` → `206000 MPa` 는 그 값이 무슨
물리량인지 몰라도 된다. 「어느 것이 영률인가」 를 푸는 쪽(해석 플랫폼)의 일로 둔 결정은
그대로다 — 이것은 다른 축이다.

## 모르는 단위는 **건드리지 않는다**

표에 없는 단위 문자열이 오면 값을 그대로 두고 「못 바꿨다」 고 말한다. 짐작해서 바꾸면
틀린 값이 맞는 얼굴로 나간다.

**우리가 내보내는 이름은 우리가 읽을 수 있어야 한다.** 각 계의 파생 단위 이름
(`tonne/mm^3` · `mJ/(tonne.K)` · `mW/(mm.K)`)도 표에 있다 — 없으면 한 번 바꾼 값을 되돌릴
길이 없고, 그것은 한쪽으로만 나는 문이다(시험이 왕복으로 지킨다).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: 차원 지수 — (질량 M, 길이 L, 시간 T, 온도 Θ). 무차원은 전부 0.
Dimension = tuple[int, int, int, int]

STRESS: Dimension = (1, -1, -2, 0)
DENSITY: Dimension = (1, -3, 0, 0)
CONDUCTIVITY: Dimension = (1, 1, -3, -1)  # W/(m·K) = kg·m/s³/K
SPECIFIC_HEAT: Dimension = (0, 2, -2, -1)  # J/(kg·K) = m²/s²/K
PER_TEMPERATURE: Dimension = (0, 0, 0, -1)
NONE: Dimension = (0, 0, 0, 0)


@dataclass(frozen=True)
class Unit:
    """단위 문자열 하나 — SI 로 가는 배수와 그 차원."""

    to_si: float
    dimension: Dimension


#: **우리가 아는 단위 전부.** MatNexus 에 실제로 나오는 것(2026-09-24: 여섯 종)에 흔한 몇을
#: 더했다. 여기 없는 것은 환산하지 않는다 — 표를 늘리는 것은 싸지만, 짐작은 비싸다.
KNOWN: dict[str, Unit] = {
    "Pa": Unit(1.0, STRESS),
    "kPa": Unit(1e3, STRESS),
    "MPa": Unit(1e6, STRESS),
    "GPa": Unit(1e9, STRESS),
    "psi": Unit(6894.757293168361, STRESS),
    "kg/m^3": Unit(1.0, DENSITY),
    "kg/m3": Unit(1.0, DENSITY),
    "g/cm3": Unit(1e3, DENSITY),
    "tonne/mm3": Unit(1e12, DENSITY),
    "tonne/mm^3": Unit(1e12, DENSITY),
    "t/mm^3": Unit(1e12, DENSITY),
    "W/(m.K)": Unit(1.0, CONDUCTIVITY),
    "W/(m*K)": Unit(1.0, CONDUCTIVITY),
    # mW/(mm·K) 는 W/(m·K) 와 **숫자가 같다**(10⁻³ / 10⁻³). 그래도 적어 둔다 — 우리가
    # 내보내는 이름을 우리가 못 읽으면 되돌릴 길이 없다(시험이 그걸 잡았다).
    "mW/(mm.K)": Unit(1.0, CONDUCTIVITY),
    "J/(kg.K)": Unit(1.0, SPECIFIC_HEAT),
    "kJ/(kg.K)": Unit(1e3, SPECIFIC_HEAT),
    "mJ/(tonne.K)": Unit(1e-6, SPECIFIC_HEAT),
    "1/K": Unit(1.0, PER_TEMPERATURE),
    "1/C": Unit(1.0, PER_TEMPERATURE),
    "1": Unit(1.0, NONE),
    "": Unit(1.0, NONE),
}


@dataclass(frozen=True)
class System:
    """닫히는 단위계 하나.

    **닫힌다**는 것은 기본 단위에서 파생 단위가 저절로 나온다는 뜻이다. `mm·kg·s` 에서 힘은
    N 이 아니라 μN 인데, 그런 계를 「mm · kg · N」 이라고 적어 두면 아무도 안 볼 때까지
    아무 일도 안 일어나다가 어느 날 10⁶ 배 틀린다. 그래서 **기본 셋만 적고 나머지는 계산한다.**
    """

    key: str
    label: str
    #: SI 기준 배수 — 질량 · 길이 · 시간 · 온도.
    mass: float
    length: float
    time: float
    temperature: float
    #: 사람과 해석기에게 보일 이름.
    names: dict[str, str]

    def factor(self, dimension: Dimension) -> float:
        """SI 값을 이 계의 값으로 나눌 수. 차원 지수대로 기본 단위를 곱한 것이다."""
        m, length, t, theta = dimension
        return self.mass**m * self.length**length * self.time**t * self.temperature**theta


SYSTEMS: dict[str, System] = {
    "mm-t-s": System(
        key="mm-t-s",
        label="mm · tonne · s (힘 N · 응력 MPa)",
        mass=1e3,  # tonne
        length=1e-3,  # mm
        time=1.0,
        temperature=1.0,
        names={
            "length": "mm",
            "mass": "tonne",
            "time": "s",
            "force": "N",
            "stress": "MPa",
            "temperature": "C",
            "density": "tonne/mm^3",
            "conductivity": "mW/(mm.K)",
            "specific_heat": "mJ/(tonne.K)",
            "per_temperature": "1/K",
        },
    ),
    "si": System(
        key="si",
        label="SI — m · kg · s (힘 N · 응력 Pa)",
        mass=1.0,
        length=1.0,
        time=1.0,
        temperature=1.0,
        names={
            "length": "m",
            "mass": "kg",
            "time": "s",
            "force": "N",
            "stress": "Pa",
            "temperature": "C",
            "density": "kg/m^3",
            "conductivity": "W/(m.K)",
            "specific_heat": "J/(kg.K)",
            "per_temperature": "1/K",
        },
    ),
}

DEFAULT_SYSTEM = "mm-t-s"
"""**CAD 가 mm 라 해석도 mm 으로 푼다**(FE 의 사실상 표준). MatNexus 의 밀도도 이미 이 계다."""

#: 차원 → 이름표의 열쇠. 모르는 차원은 단위 이름을 지어 내지 않는다.
_NAME_OF: dict[Dimension, str] = {
    STRESS: "stress",
    DENSITY: "density",
    CONDUCTIVITY: "conductivity",
    SPECIFIC_HEAT: "specific_heat",
    PER_TEMPERATURE: "per_temperature",
}


def system_of(key: str) -> System:
    return SYSTEMS.get(key) or SYSTEMS[DEFAULT_SYSTEM]


def convert(value: float, unit: str, system: str) -> tuple[float, str, bool]:
    """값 하나를 그 계로. `(값, 단위 이름, 바꿨나)`.

    **못 바꾸면 그대로 돌려주고 거짓을 준다** — 짐작해서 바꾸면 틀린 값이 맞는 얼굴로 나간다.
    """
    known = KNOWN.get((unit or "").strip())
    if known is None:
        return value, unit, False
    target = system_of(system)
    si = value * known.to_si
    made = si / target.factor(known.dimension)
    if known.dimension == NONE:
        return made, unit or "1", True
    name = _NAME_OF.get(known.dimension)
    return made, (target.names.get(name or "") or unit), True


def declaration(system: str) -> dict[str, Any]:
    """조건에 싣는 **단위계 선언** — 받는 쪽이 「무슨 계로 푼 값인가」 를 읽을 곳."""
    target = system_of(system)
    return {"system": target.key, "label": target.label, **target.names}
