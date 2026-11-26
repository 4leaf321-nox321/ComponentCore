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
  - 앞 케이스에 **중력**이 있으면 뒤에도 적는다 — 하중이 이어지지 않고, Mechanical 은
    중력을 단계마다 끄지 못한다.
- 내보내기는 `model.resolve` — 케이스가 하나면 v1 그대로(받는 쪽이 바뀌는 것이 없다), 여럿이면
  받는 쪽이 v2 를 받기 전에는 까닭을 말하고 막는다.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from app.core.conditions.analysis import Analysis
from app.core.conditions.common import Base, ConditionError
from app.core.conditions.loads import Constraint, Initial, Load

#: 케이스마다 적는 칸 — 나머지는 공유다.
CASE_FIELDS = ("analysis", "constraints", "loads", "initial")

#: 케이스가 여럿인 조건을 내보내려 할 때 — 받는 쪽이 v2 를 받으면 연다(설계 9장).
MULTI_CASE_BLOCKED = (
    "해석 케이스가 {count}개인 조건은 아직 내보낼 수 없습니다 — 해석 쪽(SimEngBay)이 케이스가 "
    "여럿인 조건(schema_version 2)을 받기 전입니다. 케이스를 하나만 남기거나 케이스마다 "
    "따로 내보내십시오."
)


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
            f"해석 케이스가 있으면 맨 위의 {', '.join(top)}을(를) 비우십시오 — 케이스마다 "
            "적습니다."
        )
    seen: dict[str, int] = {}
    after: dict[str, str] = {}  # 앞 케이스 → 그 뒤 케이스
    tightened: dict[str, dict[tuple[str, str], str]] = {}  # 케이스 → 그때까지 조인 볼트
    for index, case in enumerate(cases):
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
                        "이 케이스보다 뒤에 있습니다 — 앞 케이스를 먼저 적으십시오."
                        if later
                        else "없습니다."
                    )
                )
            before = cases[seen[case.depends_on]]
            if before.target.solver != case.target.solver:
                raise ConditionError(
                    f"cases[{index}]: ‘{case.name}’의 대상 솔버"
                    f"(‘{case.target.solver or '지정 안 함'}’)가 앞 케이스 ‘{before.name}’"
                    f"(‘{before.target.solver or '지정 안 함'}’)와 다릅니다 — 이어지는 "
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


def _bolt(load: Load) -> tuple[str, str]:
    """볼트 예압이 조이는 볼트 — 선택 그룹과 단면 좌표계(바디에 건 예압)."""
    return (load.on, load.cs)


def _constraints(case: Case) -> list[str]:
    """구속을 비교할 꼴 — 적은 차례는 보지 않는다."""
    return sorted(json.dumps(one.model_dump(), sort_keys=True) for one in case.constraints)


def _check_follows(
    index: int, case: Case, before: Case, tightened: dict[tuple[str, str], str]
) -> None:
    """뒤 케이스가 앞 케이스에 이어질 수 있나 — 받는 쪽(SimEngBay) 첫 판이 막는 것."""
    if _constraints(case) != _constraints(before):
        raise ConditionError(
            f"cases[{index}].constraints: 앞 케이스 ‘{before.name}’과(와) 구속이 다릅니다 — "
            "한 사슬 안에서는 아직 구속을 바꿀 수 없습니다(해석 쪽 첫 판). 앞 케이스의 "
            "구속을 그대로 적으십시오."
        )
    for at, load in enumerate(case.loads):
        if load.type == "bolt_pretension" and _bolt(load) in tightened:
            raise ConditionError(
                f"cases[{index}].loads[{at}]: 볼트 예압 ‘{load.name}’의 볼트(‘{load.on}’)는 "
                f"앞 케이스 ‘{tightened[_bolt(load)]}’에서 이미 조였습니다 — 뒤 케이스에서는 "
                "조인 길이로 잠기므로 예압을 다시 적지 않습니다."
            )
    gravity = "standard_earth_gravity"
    if any(one.type == gravity for one in before.loads) and not any(
        one.type == gravity for one in case.loads
    ):
        raise ConditionError(
            f"cases[{index}].loads: 앞 케이스 ‘{before.name}’에 중력이 있습니다 — 이 "
            "케이스에도 중력을 적으십시오. 하중은 앞 케이스에서 이어지지 않고, 중력은 도중에 "
            "끌 수 없습니다."
        )


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
