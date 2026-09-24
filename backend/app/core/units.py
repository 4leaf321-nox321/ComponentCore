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
TEMPERATURE: Dimension = (0, 0, 0, 1)
TIME: Dimension = (0, 0, 1, 0)
FREQUENCY: Dimension = (0, 0, -1, 0)
VISCOSITY: Dimension = (1, -1, -1, 0)  # Pa·s
LENGTH: Dimension = (0, 1, 0, 0)
FORCE: Dimension = (1, 1, -2, 0)
FORCE_PER_LENGTH: Dimension = (1, 0, -2, 0)  # N/m — 표면장력 · 단위길이 강성
ENERGY_PER_AREA: Dimension = (1, 0, -2, 0)  # J/m² — 파괴에너지. N/m 과 **같은 차원이다**
DIFFUSIVITY: Dimension = (0, 2, -1, 0)  # m²/s
ENERGY: Dimension = (1, 2, -2, 0)
NONE: Dimension = (0, 0, 0, 0)


@dataclass(frozen=True)
class Unit:
    """단위 문자열 하나 — SI 로 가는 배수와 그 차원."""

    to_si: float
    dimension: Dimension


#: **우리가 아는 단위 전부.**
#:
#: 재료 API 에는 여섯 종만 나오지만, **물성 카드에는 `K` · `s` · `1/s` · `Hz` · `Pa.s` 가
#: 더 있어 열한 종이다**(2026-09-24 MatNexus 가 알려 줬다). 여섯 종으로 굳혀 두면 점탄성이나
#: 속도별 카드를 받는 날 조용히 지나간다 — 그쪽 기호표와 맞춰 둔다.
#:
#: 여기 없는 것은 환산하지 않는다 — 표를 늘리는 것은 싸지만, 짐작은 비싸다.
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
    # 카드 쪽에 나오는 것들 — 온도 · 시간 · 변형률 속도 · 진동수 · 점도.
    "K": Unit(1.0, TEMPERATURE),
    "s": Unit(1.0, TIME),
    "ms": Unit(1e-3, TIME),
    "1/s": Unit(1.0, FREQUENCY),
    "Hz": Unit(1.0, FREQUENCY),
    "Pa.s": Unit(1.0, VISCOSITY),
    "N.s/mm2": Unit(1e6, VISCOSITY),
    # **문헌 물성 카탈로그**(`/api/catalog`)가 쓰는 것들. 그쪽은 곱을 `*` 로 적고 재료 API 는
    # `.` 로 적는다 — 같은 뜻이라 둘 다 든다(2026-09-24 실측).
    "J/(kg*K)": Unit(1.0, SPECIFIC_HEAT),
    "kJ/(kg*K)": Unit(1e3, SPECIFIC_HEAT),
    "Pa*s": Unit(1.0, VISCOSITY),
    "m": Unit(1.0, LENGTH),
    "mm": Unit(1e-3, LENGTH),
    "um": Unit(1e-6, LENGTH),
    "N": Unit(1.0, FORCE),
    "kN": Unit(1e3, FORCE),
    "N/m": Unit(1.0, FORCE_PER_LENGTH),
    "N/mm": Unit(1e3, FORCE_PER_LENGTH),
    "J/m^2": Unit(1.0, ENERGY_PER_AREA),
    "J": Unit(1.0, ENERGY),
    "mJ": Unit(1e-3, ENERGY),
    "m^2/s": Unit(1.0, DIFFUSIVITY),
    "mm^2/s": Unit(1e-6, DIFFUSIVITY),
    "1": Unit(1.0, NONE),
    "": Unit(1.0, NONE),
}

#: **환산하지 않기로 한 것.** 차원이 우리 넷(M·L·T·Θ)에 안 담기거나(전기 · 자기 · 몰),
#: 단위가 아니라 **척도**다(경도 HV). 「모른다」 와 구별해 두면, 나중에 표를 늘릴 때 무엇이
#: 빠졌고 무엇이 일부러 빠졌는지 안다.
OUT_OF_SCOPE: frozenset[str] = frozenset(
    {
        "ohm*m",
        "ohm",
        "S/m",
        "V/m",
        "A/m",
        "T",
        "eV",
        "J/mol",
        "mol/(m*s*Pa)",
        "kg/(m^2*s)",
        "HV",
        "Pa*m^0.5",
        "deg",
        "1/Pa",
    }
)


@dataclass(frozen=True)
class System:
    """닫히는 단위계 하나.

    **닫힌다**는 것은 기본 단위에서 파생 단위가 저절로 나온다는 뜻이다. `mm·kg·s` 에서 힘은
    N 이 아니라 **mN** 이고 응력은 kPa 인데, 그런 계를 「mm · kg · N」 이라고 적어 두면
    아무도 안 볼 때까지 아무 일도 안 일어나다가 어느 날 10³ 배 틀린다. 그래서 **기본 셋만
    적고 나머지는 계산한다.**
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
    # **열쇠를 MatNexus 와 맞춘다**(그쪽 `/api/fitting/unit-systems`). 같은 계를 두 이름으로
    # 부르면, 두 플랫폼이 같은 말을 하는지 사람이 눈으로 맞춰 봐야 한다.
    "mm_n_tonne": System(
        key="mm_n_tonne",
        label="mm · N · tonne (MPa)",
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
            "density": "tonne/mm3",
            "conductivity": "mW/(mm.K)",
            "specific_heat": "mJ/(tonne.K)",
            "per_temperature": "1/K",
            "temperature_abs": "K",
            "duration": "s",
            "frequency": "1/s",
            "viscosity": "N.s/mm2",
            "force_per_length": "N/mm",
            "diffusivity": "mm^2/s",
            "energy": "mJ",
        },
    ),
    "si": System(
        key="si",
        label="SI (kg · m · s · Pa)",
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
            "density": "kg/m3",
            "conductivity": "W/(m.K)",
            "specific_heat": "J/(kg.K)",
            "per_temperature": "1/K",
            "temperature_abs": "K",
            "duration": "s",
            "frequency": "1/s",
            "viscosity": "Pa.s",
            "force_per_length": "N/m",
            "diffusivity": "m^2/s",
            "energy": "J",
        },
    ),
}

DEFAULT_SYSTEM = "mm_n_tonne"
"""**CAD 가 mm 라 해석도 mm 으로 푼다**(FE 의 사실상 표준). MatNexus 의 밀도도 이미 이 계다."""

#: 차원 → 이름표의 열쇠. 모르는 차원은 단위 이름을 지어 내지 않는다.
_NAME_OF: dict[Dimension, str] = {
    STRESS: "stress",
    DENSITY: "density",
    CONDUCTIVITY: "conductivity",
    SPECIFIC_HEAT: "specific_heat",
    PER_TEMPERATURE: "per_temperature",
    TEMPERATURE: "temperature_abs",
    TIME: "duration",
    FREQUENCY: "frequency",
    VISCOSITY: "viscosity",
    LENGTH: "length",
    FORCE: "force",
    # N/m 과 J/m² 는 차원이 같아 한 이름으로 나온다 — 값은 맞고, 이름만 그쪽 것을 잃는다.
    FORCE_PER_LENGTH: "force_per_length",
    DIFFUSIVITY: "diffusivity",
    ENERGY: "energy",
}


#: **모든 계가 똑같이 부르는 차원.** 그런 것은 이름을 바꿀 일이 없으므로 들어온 기호를 둔다.
_SAME_EVERYWHERE: frozenset[str] = frozenset(
    field
    for field in set().union(*(one.names for one in SYSTEMS.values()))
    if len({one.names.get(field) for one in SYSTEMS.values()}) == 1
)


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
    field = _NAME_OF.get(known.dimension)
    # **어느 계도 다시 이름 짓지 않는 차원은 들어온 기호를 그대로 둔다.** 시간 · 온도 ·
    # 진동수는 계가 달라도 기본 단위가 같아 바꿀 것이 없는데, 거기에 우리 이름을 씌우면
    # `Hz` 가 `1/s` 가 되어 나간다 — 값은 같아도 **그쪽이 쓴 말을 우리가 바꾼 것**이고,
    # 그러면 되돌아온 파일이 원본과 안 맞는다(MatNexus 와 맞춰 보다 잡았다, 2026-09-24).
    #
    # 「지금 계에서 SI 와 같은 이름인가」 로 가르면 안 된다 — SI 로 갈 때는 늘 참이라
    # `tonne/mm3` 를 `kg/m3` 로 고쳐야 할 자리에서도 그대로 둔다(시험이 잡았다).
    if field and field in _SAME_EVERYWHERE and unit:
        return made, unit, True
    return made, (target.names.get(field or "") or unit), True


def declaration(system: str) -> dict[str, Any]:
    """조건에 싣는 **단위계 선언** — 받는 쪽이 「무슨 계로 푼 값인가」 를 읽을 곳."""
    target = system_of(system)
    return {"system": target.key, "label": target.label, **target.names}
