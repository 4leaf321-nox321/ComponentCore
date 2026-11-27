"""해석 케이스 — 공유 모델 위에 해석을 여럿(ADR 0013, `docs/해석-확장-설계.md` 2장).

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`).

한 벌은 **공유**(단위 · 좌표계 · 선택 그룹 · 재료 · 파트 설정 · 접촉 · 메시 힌트)와 **케이스**
(해석 설정 · 구속 · 하중 · 초기조건 — `CASE_FIELDS`, 그리고 앞 케이스 · 대상 솔버)로 나뉜다.
「볼트 예압 → 외력」 처럼 이어지는 해석을 한 벌에 적는다.

- **옛 모양(v1, `schema_version: 1`)은 케이스 하나다** — 맨 위의 `analysis` · `constraints` ·
  `loads` · `initial` 이 그 케이스다. 점검 · 풀기는 케이스마다 그 모양(**케이스 보기** —
  `model.views` · `raw_views`)으로 한다. 지금의 점검을 그대로 쓰므로 케이스 안의 규칙이 v1 과
  하나도 다르지 않다.
- v2(`schema_version: 2`)는 케이스를 `cases` 에 적고 맨 위의 케이스 칸은 비운다(섞으면 막는다 —
  어느 쪽이 그 케이스인지 모른다).
- 앞 케이스(`depends_on`)는 **앞에 적힌** 케이스만 가리킨다 — 고리가 생기지 않는다. 결과를
  이어받는 것은 받는 쪽의 일이고 CompCore 는 「이 케이스는 저 케이스 뒤」 만 적는다. 한 사슬의
  대상 솔버(`target.solver`)는 같아야 한다 — 받는 쪽이 사슬을 작업 하나로 푼다(SimEngBay,
  2026-11-25).
- **뜻**(SimEngBay 와 정함, 2026-11-26): 뒤 케이스는 앞 케이스의 끝 상태(변위 · 응력 ·
  접촉 상태)에서 시작하고, 앞에서 조인 볼트는 조인 길이로 잠긴다. **하중은 이어지지
  않는다** — 케이스의 `loads` 가 그 케이스에 걸린 하중 전부다(예외는 잠긴 볼트).
- 받는 쪽 첫 판이 막는 것은 저장에서 먼저 막는다(`_check_follows`).
  - **사슬만** — 한 케이스 뒤에는 하나. 갈래는 앞 케이스를 하나 더 적는다(받는 쪽도 갈래마다
    앞 케이스부터 다시 푼다).
  - 사슬 안의 **구속은 같다**.
  - 조인 볼트에 **예압을 다시 적지 않는다**.
  - **중력은 사슬 안에서 같다** — 있고 없음, 방향(좌표계 포함). 하중이 이어지지 않으므로
    케이스마다 같은 중력을 적는다. Mechanical 은 한 해석에 중력 하나를 모든 단계에 걸고 끄지도
    방향을 바꾸지도 못한다(SimEngBay 실측, 2026-11-26). 솔버와 상관없이 막는다 — 대상 솔버가
    비면 저장할 때 솔버를 모른다. 가속도 · 회전 속도는 단계마다 끌 수 있어 막지 않는다.
- 내보내기는 `model.resolve` — 케이스가 하나면 v1 그대로(받는 쪽이 바뀌는 것이 없다), 여럿이면
  받는 쪽이 v2 를 받기 전에는 까닭을 말하고 막는다. 예외는 v1 한 벌과 같은 뜻인 두 사슬 —
  **「정적 → 모달」**(선응력 모달)과 **「볼트 예압 → 외력」**(볼트 정적)이다(`fold_chain`,
  SimEngBay 와 정함 2026-11-27).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from app.core.conditions.analysis import Analysis
from app.core.conditions.common import Base, ConditionError
from app.core.conditions.loads import Constraint, Initial, Load
from app.core.conditions.registry import ANALYSES, analyses_with

#: 케이스마다 적는 칸 — 나머지는 공유다.
CASE_FIELDS = ("analysis", "constraints", "loads", "initial")

#: 케이스가 여럿인 조건을 내보내려 할 때 — 받는 쪽이 v2 를 받으면 연다(설계 9장).
MULTI_CASE_BLOCKED = (
    "해석 케이스가 {count}개인 조건은 아직 내보낼 수 없습니다. 해석 쪽(SimEngBay)이 케이스가 "
    "여럿인 조건(schema_version 2)을 받기 전입니다. 「정적 → 모달」, 「볼트 예압 → 외력」 "
    "사슬만 한 해석으로 접어 내보냅니다. 케이스를 하나만 남기거나 케이스마다 따로 "
    "내보내십시오."
)

_GRAVITY = "standard_earth_gravity"
_BOLT = "bolt_pretension"


class Target(Base):
    """케이스를 풀 솔버 — 비우면 거르지 않는다(받는 쪽이 고른다). 받는 쪽 능력표의 `solver`
    이름(`calculix` · `ansys` …)이다."""

    solver: str = Field(default="", max_length=40, title="대상 솔버")


class Case(Base):
    """해석 하나 — 공유 모델 위의 해석 설정 · 구속 · 하중 · 초기조건."""

    name: str = Field(min_length=1, max_length=60, title="케이스 이름")
    depends_on: str = Field(
        "",
        title="앞 케이스",
        description="이 케이스가 이어받는 앞 케이스입니다. 해석 쪽이 앞 케이스의 결과(응력, "
        "변형, 접촉 상태)에서 시작하고, 앞에서 조인 볼트는 그 길이로 잠깁니다. 하중은 "
        "이어지지 않습니다 — 이 케이스에 적은 하중이 전부입니다. 비워 두면 처음 상태에서 "
        "시작합니다.",
    )
    target: Target = Field(default_factory=Target)
    analysis: Analysis = Field(default_factory=Analysis)
    constraints: list[Constraint] = Field(default_factory=list)
    loads: list[Load] = Field(default_factory=list)
    initial: list[Initial] = Field(default_factory=list)


def check_cases(cases: list[Case], top: list[str], version: int) -> None:
    """케이스끼리의 규칙 — 판 · 섞임 · 이름 · 앞 케이스 · 사슬(솔버 · 갈래 · 구속 · 볼트 ·
    중력). `top` 은 맨 위의 케이스 칸(`CASE_FIELDS`)이 기본값에서 바뀐 것."""
    if not cases:
        if version == 2:
            raise ConditionError(
                "cases: schema_version 2 에는 해석 케이스가 하나 이상 있어야 합니다."
            )
        return
    if version != 2:
        raise ConditionError("cases: 해석 케이스는 schema_version 2 에서만 씁니다.")
    if top:
        raise ConditionError(
            f"해석 케이스가 있으면 맨 위의 {', '.join(top)}을(를) 비우십시오. 케이스마다 "
            "적습니다."
        )
    seen: dict[str, int] = {}
    after: dict[str, str] = {}  # 앞 케이스 → 그 뒤 케이스
    tightened: dict[str, dict[tuple[str, str], str]] = {}  # 케이스 → 그때까지 조인 볼트
    for index, case in enumerate(cases):
        _check_no_prestress(index, case)
        if case.name in seen:
            raise ConditionError(
                f"cases[{index}]: 케이스 이름 ‘{case.name}’이(가) 중복됩니다"
                f"(cases[{seen[case.name]}])."
            )
        if case.depends_on:
            if case.depends_on == case.name:
                raise ConditionError(
                    f"cases[{index}]: ‘{case.name}’이(가) 자기 자신 뒤에 올 수 없습니다."
                )
            if case.depends_on not in seen:
                later = any(one.name == case.depends_on for one in cases[index + 1 :])
                raise ConditionError(
                    f"cases[{index}]: 앞 케이스 ‘{case.depends_on}’이(가) "
                    + (
                        "이 케이스보다 뒤에 있습니다. 앞 케이스를 먼저 적으십시오."
                        if later
                        else "없습니다."
                    )
                )
            before = cases[seen[case.depends_on]]
            if before.target.solver != case.target.solver:
                raise ConditionError(
                    f"cases[{index}]: ‘{case.name}’의 대상 솔버"
                    f"(‘{case.target.solver or '지정 안 함'}’)가 앞 케이스 ‘{before.name}’"
                    f"(‘{before.target.solver or '지정 안 함'}’)와 다릅니다. 이어지는 "
                    "케이스는 한 솔버가 풉니다."
                )
            if case.depends_on in after:
                raise ConditionError(
                    f"cases[{index}]: 앞 케이스 ‘{before.name}’ 뒤에는 이미 "
                    f"‘{after[before.name]}’이(가) 있습니다 — 케이스는 사슬로만 잇습니다(한 "
                    "케이스 뒤에 하나). 갈래가 필요하면 앞 케이스를 다른 이름으로 하나 더 "
                    "적어 따로 이으십시오."
                )
            after[before.name] = case.name
            _check_follows(index, case, before, tightened.get(before.name, {}))
        tightened[case.name] = {
            **tightened.get(case.depends_on, {}),
            **{
                _bolt(load): case.name for load in case.loads if load.type == "bolt_pretension"
            },
        }
        seen[case.name] = index


#: 케이스의 선응력은 앞 케이스가 말한다 — 화면에 그대로 뜬다.
_PRESTRESS_BY_CHAIN = "앞 케이스(정적)를 지정하면 그 정적이 끝난 상태가 선응력이 됩니다."


def _check_no_prestress(index: int, case: Case) -> None:
    """케이스에서는 v1 의 선응력(해석 설정 `prestressed` · 초기조건 `prestress`)을 쓰지
    않는다 — 선응력은 `depends_on` 이 말한다. 둘을 함께 두면 뜻이 둘로 갈린다(「앞 케이스의
    끝 상태」 와 「같은 하중의 정적」). 받는 쪽도 같은 것을 막는다(SimEngBay, 2026-11-27).
    그 칸을 쓰지 않는 해석 종류에 남은 값(감춘 칸)은 보지 않는다 — 내보내지 않는다."""
    if case.analysis.prestressed and case.analysis.type in analyses_with("prestressed"):
        raise ConditionError(
            f"cases[{index}].analysis: 해석 케이스에서는 ‘선응력 반영’을 쓰지 않습니다. "
            + _PRESTRESS_BY_CHAIN
        )
    for at, item in enumerate(case.initial):
        if item.type == "prestress":
            raise ConditionError(
                f"cases[{index}].initial[{at}]: 해석 케이스에서는 초기조건 ‘선응력’을 쓰지 "
                "않습니다. " + _PRESTRESS_BY_CHAIN
            )


def _bolt(load: Load) -> tuple[str, str]:
    """볼트 예압이 조이는 볼트 — 선택 그룹과 단면 좌표계(바디에 건 예압)."""
    return (load.on, load.cs)


def _constraints(case: Case) -> list[str]:
    """구속을 비교할 꼴 — 적은 차례는 보지 않는다."""
    return sorted(json.dumps(one.model_dump(), sort_keys=True) for one in case.constraints)


def _check_follows(
    index: int, case: Case, before: Case, tightened: dict[tuple[str, str], str]
) -> None:
    """뒤 케이스가 앞 케이스에 이어질 수 있나 — 받는 쪽(SimEngBay) 첫 판이 막는 것.

    - **앞 케이스는 정적만** — 모달 · 조화 · 랜덤에는 이어받을 끝 상태(변위 · 응력)가 없다(두
      솔버 모두, SimEngBay 2026-11-27).
    - **중력은 정적 케이스끼리 같다**(2026-11-27 좁힘) — 모드 해석 케이스(모달 · 랜덤)는 앞
      정적의 끝 상태에 든 중력을 쓴다. 적지 않아도 되고, 적었다면 앞 정적과 같아야 한다. 조화의
      중력은 등록부가 막는다."""
    if before.analysis.type != "static":
        raise ConditionError(
            f"cases[{index}]: 앞 케이스 ‘{before.name}’이(가) "
            f"{ANALYSES[before.analysis.type].label} 해석입니다. 앞 케이스는 정적 구조만 "
            "지정할 수 있습니다(이어받을 변위와 응력이 없습니다)."
        )
    if _constraints(case) != _constraints(before):
        raise ConditionError(
            f"cases[{index}].constraints: 앞 케이스 ‘{before.name}’과(와) 구속이 다릅니다. "
            "한 사슬 안에서는 아직 구속을 바꿀 수 없습니다(해석 쪽 첫 판). 앞 케이스의 "
            "구속을 그대로 적으십시오."
        )
    for at, load in enumerate(case.loads):
        if load.type == "bolt_pretension" and _bolt(load) in tightened:
            raise ConditionError(
                f"cases[{index}].loads[{at}]: 볼트 예압 ‘{load.name}’의 볼트(‘{load.on}’)는 "
                f"앞 케이스 ‘{tightened[_bolt(load)]}’에서 이미 조였습니다. 뒤 케이스에서는 "
                "조인 길이로 잠기므로 예압을 다시 적지 않습니다."
            )
    mine, theirs = _gravity(case), _gravity(before)
    if case.analysis.type != "static":
        if mine and mine != theirs:
            raise ConditionError(
                f"cases[{index}].loads: 중력이 앞 케이스 ‘{before.name}’과(와) 다릅니다. "
                f"{ANALYSES[case.analysis.type].label} 케이스는 앞 정적이 끝난 상태의 중력을 "
                "쓰므로 중력을 적지 않거나 앞 케이스와 같게 적으십시오."
            )
        return
    if mine != theirs:
        what = (
            f"앞 케이스 ‘{before.name}’에는 중력이 있고 이 케이스에는 없습니다"
            if not mine
            else f"이 케이스에만 중력이 있습니다(앞 케이스 ‘{before.name}’에는 없음)"
            if not theirs
            else f"중력의 방향 또는 좌표계가 앞 케이스 ‘{before.name}’과(와) 다릅니다"
        )
        raise ConditionError(
            f"cases[{index}].loads: {what}. 이어지는 정적 케이스끼리는 중력의 유무와 "
            "방향(좌표계 포함)이 같아야 합니다. 하중은 앞 케이스에서 이어지지 않으므로 같은 "
            "중력을 케이스마다 적으십시오(Ansys Mechanical은 중력 하나를 모든 단계에 겁니다)."
        )


def _gravity(case: Case) -> list[str]:
    """케이스의 중력을 비교할 꼴 — (좌표계, 방향). 비운 방향은 -Z(내보낼 때 채우는 값), 수로
    적은 방향은 길이를 뺀다(길이는 상관없다). 식이 든 방향은 적힌 그대로 견준다."""
    out = []
    for load in case.loads:
        if load.type != "standard_earth_gravity":
            continue
        direction: Any = [0, 0, -1] if load.direction is None else load.direction
        if isinstance(direction, list) and not any(isinstance(one, str) for one in direction):
            length = sum(float(one) ** 2 for one in direction) ** 0.5 or 1.0
            direction = [round(float(one) / length, 9) + 0.0 for one in direction]
        out.append(json.dumps([load.cs, direction]))
    return sorted(out)


def fold_chain(cases: list[Case]) -> dict[str, Any] | str:
    """케이스 사슬을 **v1 한 벌**의 케이스 칸으로 — 받는 쪽이 v2 를 받기 전에도 나가는 둘
    (SimEngBay 와 정함, 2026-11-27). 못 접으면 그 까닭(사슬이 아니거나 모양이 아예 다르면
    `""`).

    - 모달(조화 · 랜덤)로 끝나면 **선응력 모달**(`_fold_prestressed`).
    - 정적 둘이면 **볼트 정적**(`_fold_static`).

    v1 의 볼트 정적은 두 솔버 모두 ① 볼트 예압 + 중력 → ② 조인 길이로 잠그고 나머지 하중,
    두 단계로 푼다 — 「예압 → 외력」 사슬 그대로다. 강제 변위는 ① 부터 걸린다(사슬의 구속은
    같다)."""
    kind = cases[-1].analysis.type
    if kind in ("modal", "harmonic", "random"):
        return _fold_prestressed(cases)
    if all(one.analysis.type == "static" for one in cases):
        return _fold_static(cases)
    return ""


#: 접을 수 없는 사슬 — 화면에 그대로 뜬다.
_NOT_CHAINED = (
    "케이스가 차례로 이어진 한 사슬이 아닙니다. 각 케이스의 앞 케이스는 바로 앞에 적힌 "
    "케이스여야 합니다."
)


def _chained(cases: list[Case]) -> bool:
    """차례로 이어진 한 사슬인가 — 첫 케이스는 앞이 없고, 다음은 바로 앞 케이스 뒤."""
    return not cases[0].depends_on and all(
        one.depends_on == before.name for one, before in zip(cases[1:], cases, strict=False)
    )


def _unread(case: Case, keys: tuple[str, ...]) -> list[str]:
    """해석 설정 중 기본값이 아닌 칸의 이름 — v1 이 그 자리에서 읽지 않는 것."""
    return [
        str(Analysis.model_fields[key].title)
        for key in keys
        if getattr(case.analysis, key) != Analysis.model_fields[key].default
    ]


def _preload_then_outer(preload: Case, outer: Case) -> list[Load] | str:
    """「예압 → 외력」 의 하중을 v1 한 벌로 — 예압 + 외력(중력은 사슬 안에서 같으니
    한 번, `_check_follows`). v1 은 볼트 예압을 ① 에, 나머지를 ② 에 걸므로 「예압」 에는 볼트
    예압(+ 중력)만, 「외력」 에는 새 볼트가 없어야 한다. 둘째 케이스의 초기조건은 v1 에 둘
    자리가 없다."""
    if not any(load.type == _BOLT for load in preload.loads):
        return (
            f"‘{preload.name}’에 볼트 예압이 없습니다. 정적 둘은 「볼트 예압 → 외력」만 "
            "접힙니다."
        )
    other = [load.name for load in preload.loads if load.type not in (_BOLT, _GRAVITY)]
    if other:
        return (
            f"‘{preload.name}’에 볼트 예압 외의 하중({', '.join(other)})이 있습니다. 볼트 "
            "예압 외의 하중은 둘째 단계에 걸리므로 "
            f"‘{outer.name}’(으)로 옮기십시오."
        )
    bolts = [load.name for load in outer.loads if load.type == _BOLT]
    if bolts:
        return (
            f"‘{outer.name}’에서 볼트({', '.join(bolts)})를 조입니다. 볼트는 모두 첫 "
            f"단계에 조이므로 접을 수 없습니다. ‘{preload.name}’에 적으십시오."
        )
    if outer.initial:
        return (
            f"‘{outer.name}’에 초기조건이 있습니다. 접으면 첫 케이스 ‘{preload.name}’의 "
            "초기조건만 쓰므로 그 케이스로 옮기십시오."
        )
    if any(item.type == "prestress" for item in preload.initial):
        return (
            f"‘{preload.name}’에 초기조건 ‘선응력’이 있습니다. 정적에는 쓰지 않으므로 "
            "삭제하십시오."
        )
    return [*preload.loads, *(load for load in outer.loads if load.type != _GRAVITY)]


def _fold_static(cases: list[Case]) -> dict[str, Any] | str:
    """「예압 → 외력」 정적 사슬을 **v1 볼트 정적** 하나로 — 하중 = 예압 + 외력, 구속 ·
    초기조건은 첫 케이스의 것, 해석은 정적 두 단계(`steps: 2` — 받는 쪽은 읽지 않지만 v1
    「조건_볼트예압_정적」 이 그렇게 적는다).

    v1 은 대변형 · 초기 부단계를 두 단계에 같이 건다 — 두 케이스가 같아야 한다. 단계 수 ·
    솔버는 받는 쪽이 읽지 않는다 — 기본값이어야 한다(SimEngBay, 2026-11-27)."""
    if not cases[-1].depends_on:
        return ""
    if not _chained(cases):
        return _NOT_CHAINED
    if len(cases) > 2:
        return f"정적이 {len(cases)}개입니다. 정적은 둘(볼트 예압 → 외력)까지만 접힙니다."
    preload, outer = cases
    for one in cases:
        unread = _unread(one, ("steps", "solver"))
        if unread:
            return (
                f"‘{one.name}’의 해석 설정({', '.join(unread)})은 해석 쪽이 읽지 않습니다. "
                "기본값으로 두십시오(볼트가 있으면 두 단계로 저절로 풉니다)."
            )
    differ = [
        str(Analysis.model_fields[key].title)
        for key in ("large_deflection", "substeps")
        if getattr(preload.analysis, key) != getattr(outer.analysis, key)
    ]
    if differ:
        return (
            f"두 케이스의 해석 설정({', '.join(differ)})이 다릅니다. 두 단계에 같은 "
            "설정이 걸리므로 같게 적으십시오."
        )
    loads = _preload_then_outer(preload, outer)
    if isinstance(loads, str):
        return loads
    return {
        "analysis": preload.analysis.model_copy(update={"steps": 2}),
        "constraints": list(preload.constraints),
        "loads": loads,
        "initial": list(preload.initial),
    }


def _fold_prestressed(cases: list[Case]) -> dict[str, Any] | str:
    """「정적 → 모달」 사슬을 **v1 선응력 모달** 하나로.

    v1 의 선응력 모달(`prestressed` + 초기조건 `prestress`, `from_step` 비움)이 같은 뜻이다:
    같은 하중의 정적을 풀고 그 끝의 응력 · 접촉 상태에서 모달을 푼다(볼트가 있으면 그
    정적을 두 단계로). 그래서 접히는 것은 둘뿐이다.

    - **정적 → 모달** — 하중 · 구속 · 초기조건은 정적의 것.
    - **예압 → 외력 → 모달** — 하중 = 예압 + 외력(`_preload_then_outer`).

    v1 이 못 적는 것은 접지 않는다: 앞 정적의 해석 설정(v1 선응력은 읽지 않는다 —
    종류뿐이어야 한다), 모달에 걸린 하중(중력 말고) · 초기조건. 조화 · 랜덤의 선응력은 받는
    쪽이 v2 를 받는 판에서 케이스 사슬로 읽는다(조화는 두 솔버 모두, 랜덤은 Ansys 가 v1
    선응력을 받지 않는다)."""
    *statics, last = cases
    kind = last.analysis.type
    if kind in ("harmonic", "random") and last.depends_on:
        return (
            f"‘{last.name}’({ANALYSES[kind].label})의 선응력은 해석 쪽이 케이스를 받는 "
            "판부터 읽습니다. 지금은 모달만 접습니다."
        )
    if kind != "modal" or not last.depends_on:
        return ""
    if not _chained(cases):
        return _NOT_CHAINED
    if len(statics) > 2:
        return (
            f"모달 앞의 정적이 {len(statics)}개입니다. 선응력 모달로는 정적 둘(볼트 "
            "예압 → 외력)까지만 접힙니다."
        )
    for one in statics:
        if one.analysis.type != "static":
            return (
                f"앞 케이스 ‘{one.name}’이(가) 정적 구조가 아닙니다. 선응력은 정적이 "
                "끝난 상태입니다."
            )
        changed = _unread(one, ANALYSES["static"].fields)
        if changed:
            return (
                f"앞 정적 ‘{one.name}’의 해석 설정({', '.join(changed)})은 선응력 "
                "모달에서 읽지 않습니다. 기본값으로 두십시오(볼트가 있으면 두 단계로 "
                "저절로 풉니다)."
            )
        if any(item.type == "prestress" for item in one.initial):
            return (
                f"앞 정적 ‘{one.name}’에 초기조건 ‘선응력’이 있습니다. 사슬에서는 앞 "
                "케이스가 선응력이므로 삭제하십시오."
            )
    first = statics[0]
    if last.initial:
        return (
            f"‘{last.name}’에 초기조건이 있습니다. 접으면 첫 케이스 ‘{first.name}’의 "
            "초기조건만 쓰므로 그 케이스로 옮기십시오."
        )
    extra = [load.name for load in last.loads if load.type != _GRAVITY]
    if extra:
        return (
            f"모달 ‘{last.name}’에 하중({', '.join(extra)})이 있습니다. 선응력 모달의 "
            "하중은 앞 정적의 것뿐이므로 중력 외의 하중은 앞 케이스에 적으십시오."
        )
    if len(statics) == 2:
        loads = _preload_then_outer(*statics)
        if isinstance(loads, str):
            return loads
    else:
        loads = list(first.loads)
    return {
        "analysis": last.analysis.model_copy(update={"prestressed": True}),
        "constraints": list(first.constraints),
        "loads": loads,
        "initial": [*first.initial, Initial.model_validate({"type": "prestress"})],
    }


def in_case(index: int, message: str) -> str:
    """케이스 보기의 오류를 그 케이스 자리로 — 케이스 칸(`loads[0]: …`)이면 `cases[1].` 을
    붙인다. 공유 칸의 오류는 그대로(케이스마다 같다)."""
    for field in CASE_FIELDS:
        if message.startswith(field) and message[len(field) : len(field) + 1] in (
            "[",
            ":",
            ".",
        ):
            return f"cases[{index}].{message}"
    return message


def raw_views(raw: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    """저장된 그대로의 한 벌을 **케이스 보기**(v1 모양)로 — `(케이스 이름, 한 벌)`. 검증하지
    않은 한 벌(고치는 중의 알림)을 읽는 자리가 쓴다. v1 이면 그 자체 하나(이름 `""`)."""
    raw = raw or {}
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        return [("", raw)]
    shared = {key: one for key, one in raw.items() if key not in ("cases", *CASE_FIELDS)}
    shared["schema_version"] = 1
    return [
        (
            str(case.get("name") or ""),
            {**shared, **{key: case[key] for key in CASE_FIELDS if key in case}},
        )
        for case in cases
        if isinstance(case, dict)
    ]
