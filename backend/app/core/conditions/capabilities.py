"""받는 쪽 **능력표** — 솔버마다 받는 해석 · 항목 · 칸(`docs/해석-확장-설계.md` 5장).

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`).

받는 쪽(SimEngBay v0.36.0 부터)이 `GET /api/simulations/capabilities` 로 낸다 — 늘 배열이고
설치가 받는 솔버마다 한 장이다. CompCore 는 관리 화면에서 갱신해 **복사본**을 두고
(`modules/server`), 그것으로 거른다 — 받는 쪽이 꺼져 있어도 저장이 막히지 않게.

- **대상 솔버가 정해진 케이스만** 본다(v2 의 `target.solver`). v1 조건과 접어 낸 한 벌은 보지
  않는다 — 솔버는 받는 쪽이 고른다.
- **막는 것은 둘뿐이다** — 표에 없는 해석 종류, 묶음(구속 · 하중 · 접촉 · 초기조건)에 없는
  항목 종류. 받는 쪽이 작업을 만들 때 거절할 것을 저장할 때 먼저 말한다.
- **칸은 막지 않는다** — `fields.<묶음>` 에 없는 칸에 기본값이 아닌 값이 적혀 있으면 「받는
  쪽이 읽지 않음」 알림이다(SimEngBay, 2026-11-27). 묶음이 `fields` 에 없으면 그 묶음의 칸은
  거르지 않는다. 항목의 `note`(조건부로 거절되거나 달리 풀리는 것)도 알림이다.
- CompCore 쪽에만 있는 칸은 거르지 않는다 — 하중의 `curve` 는 내보낼 때 표로 풀려 받는 쪽에
  가지 않는다.
- 복사본에 없는 솔버는 막지 않는다(알림만).
- 표는 1차 거르기다. note 까지 포함한 최종 판정은 받는 쪽이 작업을 만들 때 한다.
- **모르는 키는 버리고 읽는다** — 받는 쪽이 칸을 더해도(v2 판의 `follows`) 깨지지 않는다.
- 재료(`materials`)는 정적에서 재료 모델로 거른다(② 소성 — 이선형 · 다선형). 모드 해석은 소성을
  읽지 않고 탄성으로 푼다(알림).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.conditions.analysis import Analysis
from app.core.conditions.common import ConditionError
from app.core.conditions.contacts import CONTACT_LABELS, Contact
from app.core.conditions.curves import with_tables
from app.core.conditions.loads import (
    CONSTRAINT_LABELS,
    INITIAL_LABELS,
    LOAD_LABELS,
    Constraint,
    Initial,
    Load,
)
from app.core.conditions.materials import MATERIAL_MODELS
from app.core.conditions.registry import ANALYSES
from app.core.conditions.steps import RESULT_CHANGING

if TYPE_CHECKING:
    from app.core.conditions.model import Conditions


class _Loose(BaseModel):
    """받는 쪽의 모양 — 모르는 키는 버린다."""

    model_config = ConfigDict(extra="ignore")


class Item(_Loose):
    """표의 한 줄 — 이름만(`"force"`) 또는 `{"name", "note"}`."""

    name: str = Field(min_length=1)
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _bare_name(cls, value: Any) -> Any:
        return {"name": value} if isinstance(value, str) else value


class AnalysisTable(_Loose):
    """해석 하나에서 받는 것. 묶음이 없으면(`None`) 그 묶음은 거르지 않는다."""

    constraints: list[Item] | None = None
    loads: list[Item] | None = None
    contacts: list[Item] | None = None
    initial: list[Item] | None = None
    fields: dict[str, list[Item]] = Field(default_factory=dict)
    materials: list[Item] | None = None

    def listed(self, group: str) -> list[Item] | None:
        one: list[Item] | None = getattr(self, group)
        return one


class Table(_Loose):
    """솔버 한 장. `version` 은 솔버의 판(모르면 `None`), `receiver_version` 은 받는 쪽의
    판."""

    receiver: str = ""
    solver: str = Field(min_length=1)
    version: str | None = None
    receiver_version: str = ""
    contract: list[int] = Field(default_factory=list)
    analyses: dict[str, AnalysisTable] = Field(default_factory=dict)


class CapabilityError(ValueError):
    """받은 능력표가 약속한 모양이 아니다 — 어느 자리가 틀렸는지 말한다."""


def read(raw: Any) -> list[Table]:
    """받은 응답(또는 복사본)을 읽는다. 같은 솔버가 두 장이면 어느 것으로 거를지 몰라
    막는다."""
    if not isinstance(raw, list):
        raise CapabilityError("능력표는 배열이어야 합니다.")
    tables: list[Table] = []
    for index, one in enumerate(raw):
        try:
            tables.append(Table.model_validate(one))
        except ValidationError as failure:
            first = failure.errors()[0]
            where = ".".join(str(part) for part in first["loc"])
            raise CapabilityError(f"[{index}].{where}: {first['msg']}") from failure
    solvers = [one.solver for one in tables]
    twice = sorted({one for one in solvers if solvers.count(one) > 1})
    if twice:
        raise CapabilityError(f"솔버 {', '.join(twice)}의 능력표가 둘 이상입니다.")
    return tables


def table_for(tables: list[Table] | None, solver: str) -> Table | None:
    return next((one for one in tables or [] if one.solver == solver), None)


#: 묶음 → (종류 이름표, 모델). 접촉은 공유 칸이라 케이스마다 그 케이스의 해석으로 본다.
_GROUPS: tuple[tuple[str, dict[str, str], type[BaseModel]], ...] = (
    ("constraints", CONSTRAINT_LABELS, Constraint),
    ("loads", LOAD_LABELS, Load),
    ("contacts", CONTACT_LABELS, Contact),
    ("initial", INITIAL_LABELS, Initial),
)

#: CompCore 쪽에만 있는 칸 — 받는 쪽에 가지 않으므로 `fields` 로 거르지 않는다.
_COMPCORE_ONLY: dict[str, frozenset[str]] = {"loads": frozenset({"curve"})}

_UNREAD = "적은 값은 해석에 반영되지 않습니다."
_CHANGES = (
    "받지 않으면 해석 결과가 달라지므로 저장할 수 없습니다. 대상 솔버를 바꾸거나 이 칸을 "
    "비우십시오."
)


@dataclass(frozen=True)
class Finding:
    """거른 것 하나. `warn` 은 저장 · 내보내기를 막는다(`check`), `info` 는 알림이다."""

    level: Literal["warn", "info"]
    #: 오류의 자리 — `loads[0]` · `analysis`(케이스 보기의 자리, `in_case` 가 케이스를 붙인다).
    at: str
    #: 사람이 읽는 자리 — 「힘 ‘누름’」.
    where: str
    text: str
    group: str = ""
    index: int = -1
    #: 저장을 막을 때의 말 — 비우면 「자리: 이름은(는) 글」(`check`).
    error: str = ""

    def note(self) -> dict[str, Any]:
        """준비 점검의 줄(식 알림과 같은 꼴) — 항목이면 그 창을 여는 자리를 붙인다."""
        out: dict[str, Any] = {"level": self.level, "where": self.where, "text": self.text}
        if self.index >= 0:
            out["open"] = {"kind": "item", "group": self.group, "index": self.index}
        return out


def _title(model: type[BaseModel], name: str) -> str:
    return model.model_fields[name].title or name


def _where(labels: dict[str, str], item: Any) -> str:
    what = labels.get(item.type, item.type)
    name = getattr(item, "name", "")
    return f"{what} ‘{name}’" if name else what


def findings(view: Conditions, table: Table) -> list[Finding]:
    """케이스 하나(v1 모양의 케이스 보기)를 솔버 한 장으로 거른다 — 막을 것이 먼저다."""
    # 곡선이 채우는 표(시간별 배율 …)도 적은 표와 같게 본다 — 곡선 이름은 CompCore 쪽 칸이다.
    view = with_tables(view)
    solver = table.solver
    kind = view.analysis.type
    registered = ANALYSES[kind]
    caps = table.analyses.get(kind)
    if caps is None:
        return [
            Finding(
                "warn",
                "analysis",
                "해석 설정",
                f"대상 솔버 ‘{solver}’은(는) {registered.label} 해석을 받지 않습니다(해석 쪽 "
                "능력표). 대상 솔버나 해석 종류를 바꾸십시오.",
                group="analysis",
            )
        ]
    refused: list[Finding] = []
    noted: list[Finding] = []
    for group, labels, _ in _GROUPS:
        listed = caps.listed(group)
        if listed is None:
            continue
        by_name = {one.name: one for one in listed}
        seen: dict[str, list[int]] = {}
        items = getattr(view, group)
        for index, item in enumerate(items):
            if item.type not in by_name:
                refused.append(
                    Finding(
                        "warn",
                        f"{group}[{index}]",
                        _where(labels, item),
                        f"대상 솔버 ‘{solver}’의 {registered.label} 해석에서 받지 않습니다"
                        "(해석 쪽 능력표). 대상 솔버를 바꾸거나 이 항목을 삭제하십시오.",
                        group,
                        index,
                    )
                )
            elif by_name[item.type].note:
                seen.setdefault(item.type, []).append(index)
        # 안내는 종류마다 한 줄 — 같은 종류의 하중 여럿에 같은 글을 거듭 달지 않는다.
        for type_, indexes in seen.items():
            names = [getattr(items[one], "name", "") for one in indexes]
            what = labels.get(type_, type_)
            where = f"{what} {', '.join(f'‘{one}’' for one in names)}" if any(names) else what
            noted.append(
                Finding(
                    "info",
                    f"{group}[{indexes[0]}]",
                    where,
                    f"대상 솔버 ‘{solver}’ 안내: {by_name[type_].note}",
                    group,
                    indexes[0],
                )
            )
    refused += _materials(view, caps, solver, registered.label)
    return refused + _unread_fields(view, caps, solver) + noted


def _materials(
    view: Conditions, caps: AnalysisTable, solver: str, label: str
) -> list[Finding]:
    """재료 모델 — 정적에서만 거른다(받는 쪽은 소성을 정적에서만 읽고, 모드 해석은 탄성으로
    푼다 — SimEngBay 2026-11-27). 파트에 붙은 재료만 본다."""
    out: list[Finding] = []
    for index, one in enumerate(view.materials):
        if not one.apply_to or one.model == "linear_elastic":
            continue
        name = one.ref.name or one.ref.code or "이름 없음"
        model = MATERIAL_MODELS[one.model]
        if view.analysis.type != "static":
            out.append(
                Finding(
                    "info",
                    f"materials[{index}]",
                    f"재료 ‘{name}’",
                    f"{label} 해석에서는 {model} 대신 탄성 값으로 풉니다.",
                    "materials",
                )
            )
            continue
        listed = caps.materials
        if listed is not None and one.model not in {item.name for item in listed}:
            out.append(
                Finding(
                    "warn",
                    f"materials[{index}]",
                    f"재료 ‘{name}’",
                    f"대상 솔버 ‘{solver}’의 {label} 해석에서 {model}을(를) 받지 "
                    "않습니다(해석 쪽 능력표). 재료 모델이나 대상 솔버를 바꾸십시오.",
                    "materials",
                    error=f"materials[{index}]: 재료 ‘{name}’의 {model}을(를) 대상 솔버 "
                    f"‘{solver}’의 {label} 해석에서 받지 않습니다(해석 쪽 능력표). 재료 "
                    "모델이나 대상 솔버를 바꾸십시오.",
                )
            )
    return out


def _unread_fields(view: Conditions, caps: AnalysisTable, solver: str) -> list[Finding]:
    """`fields.<묶음>` 에 없는 칸 중 **기본값이 아닌 값**이 적힌 것 — 받는 쪽이 읽지 않는다.
    결과를 바꾸는 칸(하중 단계 · 시간별 배율 · 적용 단계 · 볼트 동작 —
    `steps.RESULT_CHANGING`)은 막는다 — 받는 쪽은 모르는 칸을 말없이 버리고 한 단계로 푼다
    (SimEngBay, 2026-11-27)."""
    out: list[Finding] = []
    read = caps.fields.get("analysis")
    if read is not None:
        names = {one.name for one in read}
        # 이 종류가 쓰는(내보내는) 칸만 — 다른 종류의 칸은 내보내지 않는다(`_filled_analysis`).
        for name in ANALYSES[view.analysis.type].fields:
            info = Analysis.model_fields[name]
            if name in names or getattr(view.analysis, name) == info.get_default(
                call_default_factory=True
            ):
                continue
            title = _title(Analysis, name)
            if name in RESULT_CHANGING["analysis"]:
                text = (
                    f"대상 솔버 ‘{solver}’은(는) ‘{title}’ 칸을 아직 받지 않습니다"
                    "(해석 쪽 능력표). "
                )
                out.append(
                    Finding(
                        "warn", "analysis", f"해석 설정 ‘{title}’", text + _CHANGES, "analysis"
                    )
                )
                continue
            out.append(
                Finding(
                    "info",
                    "analysis",
                    f"해석 설정 ‘{title}’",
                    f"대상 솔버 ‘{solver}’은(는) 이 칸을 읽지 않습니다(해석 쪽 능력표). "
                    + _UNREAD,
                    group="analysis",
                )
            )
    for group, labels, model in _GROUPS:
        read = caps.fields.get(group)
        if read is None:
            continue
        names = {one.name for one in read} | _COMPCORE_ONLY.get(group, frozenset())
        changing = RESULT_CHANGING.get(group, frozenset())
        for index, item in enumerate(getattr(view, group)):
            unread = [
                name
                for name, info in model.model_fields.items()
                if name not in names
                and not info.is_required()
                and getattr(item, name) != info.get_default(call_default_factory=True)
            ]
            where = _where(labels, item)
            stopped = [f"‘{_title(model, one)}’" for one in unread if one in changing]
            if stopped:
                text = (
                    f"{', '.join(stopped)} 칸을 대상 솔버 ‘{solver}’이(가) 아직 받지 "
                    f"않습니다(해석 쪽 능력표). {_CHANGES}"
                )
                out.append(
                    Finding(
                        "warn",
                        f"{group}[{index}]",
                        where,
                        text,
                        group,
                        index,
                        error=f"{group}[{index}]: {where}의 {text}",
                    )
                )
            rest = [f"‘{_title(model, one)}’" for one in unread if one not in changing]
            if rest:
                out.append(
                    Finding(
                        "info",
                        f"{group}[{index}]",
                        where,
                        f"대상 솔버 ‘{solver}’은(는) {', '.join(rest)} 칸을 읽지 않습니다"
                        f"(해석 쪽 능력표). {_UNREAD}",
                        group,
                        index,
                    )
                )
    return out


def check(view: Conditions, table: Table, case: str = "") -> None:
    """막을 것이 있으면 첫 것을 말한다 — 저장 · 내보내기(`model.parse`). 접촉은 공유 칸이라
    어느 케이스에서 걸렸는지 붙인다."""
    for one in findings(view, table):
        if one.level != "warn":
            continue
        if one.error:
            raise ConditionError(one.error)
        scope = f"케이스 ‘{case}’에서 " if case and one.group == "contacts" else ""
        subject = "" if one.group == "analysis" else f"{one.where}은(는) "
        raise ConditionError(f"{one.at}: {scope}{subject}{one.text}")


def notes(view: Conditions, tables: list[Table] | None, solver: str) -> list[dict[str, Any]]:
    """준비 점검의 줄 — 고치는 중인 케이스 하나(`/cad/conditions/notes`). 솔버가 비면 없다.
    복사본이 없거나 그 솔버의 표가 없으면 「확인하지 않았다」 를 한 줄로 말한다."""
    if not solver:
        return []
    if tables is None:
        return [
            {
                "level": "info",
                "where": "대상 솔버",
                "text": f"해석 쪽 능력표를 아직 받지 않아 ‘{solver}’이(가) 받는 항목을 "
                "확인하지 않았습니다. 시스템 관리자가 ‘서버’ 화면에서 능력표를 갱신할 수 "
                "있습니다.",
            }
        ]
    table = table_for(tables, solver)
    if table is None:
        return [
            {
                "level": "info",
                "where": "대상 솔버",
                "text": f"해석 쪽 능력표에 ‘{solver}’이(가) 없어 받는 항목을 확인하지 "
                "않았습니다. 해석 쪽이 이 솔버를 받는지 확인하십시오.",
            }
        ]
    return [one.note() for one in findings(view, table)]
