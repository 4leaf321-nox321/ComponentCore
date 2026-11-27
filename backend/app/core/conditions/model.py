"""조건 한 벌 — 모델 · 무엇에 거는가(종류마다 받는 선택 그룹) · 읽기(`parse`) ·
풀기(`resolve`) · 실험계획의 고르기 인자 · 값 칸 · 식 알림.

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, ValidationError

from app.core import units as unit_systems
from app.core.conditions.analysis import (
    Analysis,
    _check_analysis,
    _filled_analysis,
    _integerized,
)
from app.core.conditions.bodies import BodySetting, MeshHint, _check_body_settings
from app.core.conditions.cases import (
    CASE_FIELDS,
    MULTI_CASE_BLOCKED,
    Case,
    check_cases,
    fold_chain,
    in_case,
    raw_views,
)
from app.core.conditions.common import (
    ALL_BODIES,
    GLOBAL_FRAMES,
    INPUT_SYSTEM,
    Base,
    ConditionError,
    Frame,
    NamedSelection,
    Units,
)
from app.core.conditions.contacts import CONTACT_LABELS, Contact, _check_contact
from app.core.conditions.curves import Curve, check_curves, check_uses, filled, with_tables
from app.core.conditions.loads import (
    AXIS_CHOICES,
    CONSTRAINT_LABELS,
    INITIAL_LABELS,
    LOAD_DIMENSIONS,
    LOAD_LABELS,
    Constraint,
    Initial,
    Load,
    _check_excitation,
    _check_initial,
    _check_load,
    _check_section,
    _filled_initial,
    _filled_load,
)
from app.core.conditions.materials import Material, _with_converted
from app.core.conditions.registry import ANALYSES, GROUP_LABELS, REFUSED_WHY, accepting
from app.core.recipe.params import ExpressionError, resolve_params
from app.core.recipe.params import evaluate_expression as _expr


class Conditions(Base):
    """한 벌. 작업 버전에 붙고, 실험계획이 스냅샷을 뜬다.

    v1(`schema_version: 1`)은 해석 하나 — 맨 위의 해석 설정 · 구속 · 하중 · 초기조건이 그
    케이스다. v2 는 그것을 `cases` 에 여럿 적고 맨 위는 비운다(`cases` 모듈)."""

    schema_version: Literal[1, 2] = 1
    units: Units = Field(default_factory=Units)
    named_selections: list[NamedSelection] = Field(default_factory=list)
    materials: list[Material] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    loads: list[Load] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    initial: list[Initial] = Field(default_factory=list)
    analysis: Analysis = Field(default_factory=Analysis)
    mesh_hints: list[MeshHint] = Field(default_factory=list)
    body_settings: list[BodySetting] = Field(default_factory=list)
    coordinate_systems: list[Frame] = Field(default_factory=list)
    """해석 조건에서 정한 좌표계. 도면(레시피)의 좌표계와 **이름이 겹치면 안 된다** — 둘 다
    `cs` 가 이름으로 가리킨다."""
    curves: list[Curve] = Field(default_factory=list)
    """곡선 — 하중이 이름으로 가리킨다(`curves` 모듈). 내보낼 때 하중 안의 표로 풀려 이 칸은
    나가지 않는다."""
    cases: list[Case] = Field(default_factory=list)
    """해석 케이스(v2) — 비면 v1(맨 위가 케이스 하나). v1 로 내보낼 때는 이 칸을 싣지
    않는다."""


#: 빈 한 벌 — 내보내는 v1 모양(케이스 · 곡선 칸 없음).
EMPTY: dict[str, Any] = Conditions().model_dump(exclude={"cases", "curves"})


def views(conditions: Conditions) -> list[tuple[str, Conditions]]:
    """케이스마다 **v1 모양의 한 벌** — `(케이스 이름, 한 벌)`. 공유 칸은 같이 쓰고 케이스 칸만
    그 케이스의 것이다. v1 이면 그 자체 하나(이름 `""`). 점검 · 풀기는 모두 이것으로 한다 —
    케이스 안의 규칙이 v1 과 하나도 다르지 않다."""
    if not conditions.cases:
        return [("", conditions)]
    return [
        (
            case.name,
            conditions.model_copy(
                update={
                    "schema_version": 1,
                    "cases": [],
                    **{key: getattr(case, key) for key in CASE_FIELDS},
                }
            ),
        )
        for case in conditions.cases
    ]


def _top_fields(conditions: Conditions) -> list[str]:
    """맨 위의 케이스 칸 중 기본값이 아닌 것 — v2 에서 섞였나."""
    empty = Conditions()
    return [key for key in CASE_FIELDS if getattr(conditions, key) != getattr(empty, key)]


# ── 검증 ──────────────────────────────────────────────────────────────────────


# ── 무엇에 거는가 — 종류마다 받는 선택 그룹 ─────────────────────────────────

_FACE: dict[str, str] = {"entity": "face"}
_EDGE: dict[str, str] = {"entity": "edge"}
_VERTEX: dict[str, str] = {"entity": "vertex"}
_BODY: dict[str, str] = {"entity": "body"}
_CYLINDER_FACE: dict[str, str] = {"entity": "face", "kind": "cylinder"}
_SPOTS = [_FACE, _EDGE, _VERTEX]
_FACE_EDGE = [_FACE, _EDGE]

#: 종류 → **받는 선택 그룹**(종류 · 면의 모양). 화면은 이것으로 고를 수 있는 그룹과 3D 에서
#: 누를 수 있는 것을 좁히고, AI 는 사양표(`accepts`)에서 읽는다. 없는 종류는 대상이 없다
#: (중력처럼 몸 전체). `kind` 가 있으면 **선택 규칙에 그 모양이 적혀 있어야** 한다 — 「이
#: 자리에 가까운 면」 만으로는 치수가 바뀐 설계점에서 다른 모양의 면을 집을 수 있다.
CONSTRAINT_ACCEPTS: dict[str, list[dict[str, str]]] = {
    "fixed_support": _SPOTS,
    "displacement": _SPOTS,
    # 원격 변위는 면 · 엣지를 한 점에 묶는다 — 점 하나를 묶는 것은 뜻이 없다(Mechanical).
    "remote_displacement": _FACE_EDGE,
    "frictionless": [_FACE],
    "cylindrical": [_CYLINDER_FACE],
    "compression_only": [_FACE],
    "elastic_support": [_FACE],
}
LOAD_ACCEPTS: dict[str, list[dict[str, str]]] = {
    "pressure": [_FACE],
    "force": _SPOTS,
    "moment": _FACE_EDGE,
    "bearing": [_CYLINDER_FACE],
    "bolt_pretension": [_CYLINDER_FACE, _BODY],
}
CONTACT_ACCEPTS: dict[str, list[dict[str, str]]] = {kind: [_FACE] for kind in CONTACT_LABELS}
#: 국부 메시는 종류가 없다 — `*` 가 모든 경우. 「전체」 는 그룹이 아니라 늘 된다. **바디는
#: 받지 않는다** — 파트 하나 전체의 메시는 파트별 설정이 든다(2026-10-04). 그 전에 바디 그룹에
#: 건 힌트는 저장된 조건 · DOE 스냅샷에 남아 있어 **읽기는 한다**(`_check_targets`) — 화면은
#: 열 때 파트별 설정으로 옮긴다.
MESH_ACCEPTS: dict[str, list[dict[str, str]]] = {"*": [_FACE, _EDGE]}
INITIAL_ACCEPTS: dict[str, list[dict[str, str]]] = {
    "temperature": [_BODY],
    "velocity": [_BODY],
}

_ENTITY_LABELS = {"face": "면", "edge": "엣지", "vertex": "점", "body": "바디"}
_KIND_LABELS = {"cylinder": "원통면"}


def _accepts_label(options: list[dict[str, str]]) -> str:
    """「원통면 · 바디」 처럼 — 받는 것을 사람 말로."""
    return ", ".join(
        _KIND_LABELS.get(one.get("kind", ""), "") or _ENTITY_LABELS[one["entity"]]
        for one in options
    )


def _check_target(
    where: str, label: str, accepts: list[dict[str, str]], selection: NamedSelection
) -> None:
    """선택 그룹이 이 조건이 받는 종류 · 모양인가. 아니면 **어떻게 고칠지까지** 말한다 — 화면을
    쓰는 사람과 MCP 로 조건을 짓는 AI 가 같은 말을 듣는다."""
    fits = [one for one in accepts if one["entity"] == selection.entity]
    if not fits:
        raise ConditionError(
            f"{where}: {label}에는 {_accepts_label(accepts)} 선택 그룹만 지정할 수 있습니다. "
            f"선택 그룹 ‘{selection.name}’의 종류는 {_ENTITY_LABELS[selection.entity]}입니다."
        )
    if not all(one.get("kind") for one in fits):
        return
    kinds = {one["kind"] for one in fits}
    members = selection.select.get("any") or [selection.select]
    if any(str(one.get("kind", "")) not in kinds for one in members):
        wanted = ", ".join(_KIND_LABELS.get(kind, kind) for kind in sorted(kinds))
        raise ConditionError(
            f"{where}: {label}에는 {wanted}만 지정할 수 있습니다. 선택 그룹 "
            f"‘{selection.name}’의 규칙에 kind: {', '.join(sorted(kinds))} 조건이 없어, "
            "치수가 바뀐 설계점에서 다른 형상의 면이 선택될 수 있습니다. 3D에서 선택할 때 "
            "원통면 규칙을 사용하십시오"
            '(셀렉터의 경우 {"what": "faces", "kind": "cylinder", …}).'
        )


def _check_targets(conditions: Conditions) -> None:
    """조건마다 가리키는 선택 그룹이 **받을 수 있는 것**인가."""
    selections = {one.name: one for one in conditions.named_selections}

    def check(where: str, label: str, accepts: list[dict[str, str]] | None, name: str) -> None:
        if accepts and name in selections:
            _check_target(where, label, accepts, selections[name])

    for index, one in enumerate(conditions.constraints):
        label = f"{CONSTRAINT_LABELS[one.type]} ‘{one.name}’"
        check(f"constraints[{index}]", label, CONSTRAINT_ACCEPTS.get(one.type), one.on)
    for index, load in enumerate(conditions.loads):
        label = f"{LOAD_LABELS[load.type]} ‘{load.name}’"
        check(f"loads[{index}]", label, LOAD_ACCEPTS.get(load.type), load.on)
    for index, contact in enumerate(conditions.contacts):
        accepts = CONTACT_ACCEPTS.get(contact.type)
        label = f"접촉 ‘{contact.name}’"
        check(f"contacts[{index}]", f"{label}의 접촉면", accepts, contact.source)
        check(f"contacts[{index}]", f"{label}의 대상면", accepts, contact.target)
    for index, initial in enumerate(conditions.initial):
        label = INITIAL_LABELS[initial.type]
        check(f"initial[{index}]", label, INITIAL_ACCEPTS.get(initial.type), initial.on)
    for index, hint in enumerate(conditions.mesh_hints):
        legacy = hint.on in selections and selections[hint.on].entity == "body"
        if not legacy:
            check(f"mesh_hints[{index}]", f"국부 메시 ‘{hint.on}’", MESH_ACCEPTS["*"], hint.on)


def _known_names(conditions: Conditions) -> set[str]:
    return {one.name for one in conditions.named_selections}


#: 받는 항목을 보는 묶음 — 종류 이름표.
_TYPE_LABELS: dict[str, dict[str, str]] = {
    "constraints": CONSTRAINT_LABELS,
    "loads": LOAD_LABELS,
    "contacts": CONTACT_LABELS,
    "initial": INITIAL_LABELS,
}


def _check_accepted(conditions: Conditions) -> None:
    """해석 종류가 **받는 항목**인가, 꼭 있어야 하는 항목이 있나 — 등록부(`registry.ANALYSES`)
    대로. 받지 않는 항목이 실리면 받는 쪽이 거절하거나 무엇으로 풀지 모른다(정적의 가속도
    PSD) — 보내기 전에, 저장할 때 말한다."""
    registered = ANALYSES[conditions.analysis.type]
    for group, labels in _TYPE_LABELS.items():
        accepted = registered.accepts.get(group, ())
        for index, item in enumerate(getattr(conditions, group)):
            if item.type in accepted:
                continue
            name = getattr(item, "name", "")
            label = f"{labels[item.type]} ‘{name}’" if name else labels[item.type]
            others = [ANALYSES[one].label for one in accepting(group, item.type)]
            where = (
                f"{', '.join(others)} 해석에서만 사용할 수 있습니다"
                if 0 < len(others) <= 2
                else f"{registered.label} 해석에서는 사용할 수 없습니다"
            )
            why = REFUSED_WHY.get(
                (group, item.type), "해석 종류를 바꾸거나 이 항목을 삭제하십시오."
            )
            raise ConditionError(f"{group}[{index}]: {label}은(는) {where}. {why}")
    for need in registered.needs:
        if not any(one.type == need.type for one in getattr(conditions, need.group)):
            what = _TYPE_LABELS[need.group][need.type]
            raise ConditionError(
                f"{need.group}: {registered.label} 해석에는 {GROUP_LABELS[need.group]} "
                f"‘{what}’이(가) 하나 이상 있어야 합니다."
                + (f" {need.why}" if need.why else "")
            )


def parse(
    raw: dict[str, Any] | None,
    bodies: list[str] | None = None,
    frames: list[str] | None = None,
    sheets: set[str] | None = None,
) -> Conditions:
    """읽어서 검증한다. **틀린 자리를 짚어 말한다** — 「조건이 잘못됐습니다」 로는 못 고친다.

    `bodies` 를 주면 **물성이 붙은 바디가 진짜 있는지**도 본다(`topology.bodies` 의 이름).
    없는 이름에 물성을 붙이면 해석 쪽이 그 바디에 아무 물성도 못 얹고, 그 사실은 푸는
    날에야 드러난다 — 이름표를 가리킬 때와 같은 까닭이다.

    `frames` 는 도면(레시피)의 좌표계 이름들 — 주면 조건의 `cs` 가 **있는 좌표계**를
    가리키는지 본다. 안 주면 조건 안의 좌표계만 알고, 모르는 이름은 넘어간다(도면을 못 보는
    자리에서 저장을 막지 않으려고).

    `sheets` 는 그 가운데 **시트 바디**(셸 모델 — `topology.bodies` 의 `kind="sheet"`)의 이름 —
    주면 파트 설정이 형상과 맞는지도 본다: 시트는 쉘로만, 솔리드는 두께를 형상에서 잰다.
    """
    if not raw:
        return Conditions()
    try:
        conditions = Conditions.model_validate(raw)
    except ValidationError as failure:
        first = failure.errors()[0]
        where = ".".join(str(one) for one in first["loc"])
        raise ConditionError(f"{where}: {first['msg']}") from failure
    check_cases(conditions.cases, _top_fields(conditions), conditions.schema_version)
    for index, (_, view) in enumerate(views(conditions)):
        try:
            _check(view, bodies, frames, sheets)
        except ConditionError as failure:
            if not conditions.cases:
                raise
            raise ConditionError(in_case(index, str(failure))) from failure
    return conditions


def _check(
    conditions: Conditions,
    bodies: list[str] | None,
    frames: list[str] | None,
    sheets: set[str] | None,
) -> None:
    """v1 모양 한 벌(케이스 하나)의 점검 — `parse` 가 케이스마다 부른다. 곡선을 가리키는
    하중은 그 표를 채운 사본으로 본다 — 표를 적은 것과 같은 점검을 지난다."""
    check_curves(conditions.curves)
    check_uses(conditions)
    conditions = with_tables(conditions)
    names = _known_names(conditions)
    if len(names) != len(conditions.named_selections):
        raise ConditionError(
            "선택 그룹 이름이 중복됩니다. 조건이 어느 선택 그룹을 가리키는지 알 수 없습니다."
        )

    # **가리키는 선택 그룹이 없으면 지금 말한다.** 안 그러면 내보낸 뒤 해석 쪽에서 0 개를 집고,
    # 하중 없는 해석이 끝까지 돈다.
    for group, items in (
        ("constraints", conditions.constraints),
        ("loads", conditions.loads),
        ("contacts", conditions.contacts),
        ("initial", conditions.initial),
        ("mesh_hints", conditions.mesh_hints),
    ):
        for index, item in enumerate(items):
            targets = []
            if isinstance(item, Contact):
                targets = [item.source, item.target]
            else:
                on = getattr(item, "on", "")
                targets = [on] if on and on != "전체" else []
            for target in targets:
                if target not in names:
                    raise ConditionError(
                        f"{group}[{index}]: 선택 그룹 ‘{target}’이(가) 없습니다"
                        f"(정의된 선택 그룹: {', '.join(sorted(names)) or '없음'})."
                    )

    # **받을 수 있는 것인가** — 압력을 엣지에, 베어링을 평면에 걸면 받는 쪽이 거절하거나
    # 엉뚱하게 푼다. 저장할 때 말한다.
    _check_targets(conditions)

    # **좌표계** — 이름이 겹치지 않고, 면에 붙인 것은 있는 선택 그룹을 가리키고, 조건의
    # `cs` 는 있는 좌표계를 가리킨다. 모르는 좌표계를 조용히 전역으로 읽으면 성분이 딴
    # 방향으로 걸린다.
    local = [one.name for one in conditions.coordinate_systems]
    for index, frame in enumerate(conditions.coordinate_systems):
        if frame.name in GLOBAL_FRAMES:
            raise ConditionError(
                f"coordinate_systems[{index}]: ‘{frame.name}’은(는) 전역 좌표계용으로 "
                "예약된 이름입니다."
            )
        if local.count(frame.name) > 1 or frame.name in (frames or []):
            raise ConditionError(
                f"coordinate_systems[{index}]: 좌표계 이름 ‘{frame.name}’이(가) 중복됩니다"
                "(도면의 좌표계와도 이름이 달라야 합니다)."
            )
        if frame.on and frame.on not in names:
            raise ConditionError(
                f"coordinate_systems[{index}]: 선택 그룹 ‘{frame.on}’이(가) 없습니다."
            )
    known_frames = GLOBAL_FRAMES | set(local) | set(frames or [])
    defined_frames = ", ".join(sorted(known_frames - GLOBAL_FRAMES)) or "없음"
    for index, item in enumerate(conditions.constraints):
        if item.type == "elastic_support" and item.stiffness is None:
            raise ConditionError(
                f"constraints[{index}]: 탄성 지지 ‘{item.name}’에 기초 강성이 없습니다."
            )
        if (
            item.type == "remote_displacement"
            and item.location == "cs_origin"
            and item.cs in GLOBAL_FRAMES
        ):
            raise ConditionError(
                f"constraints[{index}]: ‘{item.name}’의 원격점을 좌표계 원점으로 지정하려면 "
                "좌표계를 선택하십시오. 전역 좌표계의 원점은 모델과 무관한 위치입니다."
            )
        if frames is not None and item.cs not in known_frames:
            raise ConditionError(
                f"constraints[{index}]: 좌표계 ‘{item.cs}’이(가) 없습니다"
                f"(정의된 좌표계: {defined_frames})."
            )

    _check_analysis(conditions.analysis)
    for index, contact in enumerate(conditions.contacts):
        _check_contact(f"contacts[{index}]", contact)
    for index, initial in enumerate(conditions.initial):
        _check_initial(f"initial[{index}]", initial)
    # 환경 온도는 모델에 하나 — 물성의 온도별 값을 고르는 기준이기도 해서 둘이면 받는 쪽이
    # 어느 것을 쓸지 모른다(2026-11-17).
    environments = [one for one in conditions.initial if one.type == "environment_temperature"]
    if len(environments) > 1:
        raise ConditionError(
            f"환경 온도가 {len(environments)}개입니다. 모델 전체의 기준 온도라 하나만 둡니다."
        )
    entity_of = {one.name: one.entity for one in conditions.named_selections}
    for index, load in enumerate(conditions.loads):
        _check_load(f"loads[{index}]", load)
        if frames is not None and load.cs not in known_frames:
            raise ConditionError(
                f"loads[{index}]: 좌표계 ‘{load.cs}’이(가) 없습니다"
                f"(정의된 좌표계: {defined_frames})."
            )
        if load.type == "bolt_pretension" and load.on in entity_of:
            _check_section(f"loads[{index}]", load, entity_of[load.on] == "body")
    # **해석 종류가 받는 것인가** — 정적의 가속도 PSD, 구조 해석의 바디 온도, 고정 지지 없는
    # 랜덤 진동(등록부).
    _check_accepted(conditions)
    _check_excitation(conditions)

    # **물성이 붙은 바디가 진짜 있나.** 「전체」 는 늘 된다(모든 바디).
    known = set(bodies) if bodies is not None else None
    owner: dict[str, int] = {}
    for index, material in enumerate(conditions.materials):
        for where in material.apply_to:
            if known is not None and where != ALL_BODIES and where not in known:
                raise ConditionError(
                    f"materials[{index}]: 바디 ‘{where}’이(가) 없습니다"
                    f"(존재하는 바디: {', '.join(sorted(known)) or '없음'})."
                )
            # **바디 하나에 물성 하나.** 둘이면 해석 쪽이 어느 것으로 풀지 모른다 — 먼저 온
            # 것을 쓰든 나중 것을 쓰든, 사람이 고른 것과 다를 수 있다.
            if where in owner:
                raise ConditionError(
                    f"materials[{index}]: ‘{where}’에 물성이 2개 지정되었습니다. "
                    f"materials[{owner[where]}]와(과) 중복됩니다. "
                    "바디 하나에는 물성을 하나만 지정할 수 있습니다."
                )
            owner[where] = index
    if ALL_BODIES in owner and len(owner) > 1:
        other = next(name for name in owner if name != ALL_BODIES)
        raise ConditionError(
            f"materials[{owner[ALL_BODIES]}]이(가) ‘{ALL_BODIES}’에 지정되어 있는데 "
            f"materials[{owner[other]}]이(가) ‘{other}’에도 지정되었습니다. "
            f"‘{other}’에 물성이 2개 지정됩니다."
        )
    _check_body_settings(conditions, known, sheets)


def resolve(
    raw: dict[str, Any] | None,
    params: dict[str, Any],
    keys: dict[str, str] | None = None,
    *,
    cases: bool = False,
) -> dict[str, Any]:
    """`"=식"` 을 그 설계점의 값으로 바꾼 **새 사본**. 레시피와 같은 문법이다.

    받는 쪽은 식을 풀 수 없다 — 설계점마다 **풀린 값**을 내보내야 한다.

    `keys` 는 물성 이름 사전(`{사람이 쓰는 이름: 표준 열쇠}`)이다. **코어는 그것을 가져오지
    않는다** — 네트워크는 바깥 층의 일이고(아키텍처 시험이 지킨다), 여기는 받은 것으로 풀기만
    한다. 안 주면 표준 열쇠만 안 붙는다(값은 그대로 나간다).

    여기서 **내보내기 단위계로 옮긴다**: 값은 입력 계(`INPUT_SYSTEM`, mm · N · t)로 적혔고 식도
    도면 치수(mm)로 그 계에서 푼다. 풀린 수를 칸마다 차원대로 내보내기 계로 옮기고, `units` 를
    닫힌 선언으로 펼친다. 물성은 그 계로 옮긴 값(`converted`)을 **원본 옆에** 놓는다 — MatNexus
    가 밀도만 `tonne/mm3` 로 주고 나머지는 SI 로 주므로, 이것이 없으면 받는 쪽이 밀도는 맞고
    탄성계수는 10⁶ 배 틀린 채로 푼다.

    **해석 케이스**(`schema_version: 2`): 하나면 **v1 그대로** 낸다 — 받는 쪽이 바뀌는 것이
    없다. 여럿이면 받는 쪽이 v2 를 받기 전이라 까닭을 말하고 막는다 — 「정적 → 모달」 ·
    「볼트 예압 → 외력」 사슬만 v1 한 벌로 접어 낸다(`_folded`). `cases=True`(DOE 의
    `doe_conditions_v2` · v2 픽스처를 만드는 시험)일 때만 v2 로 낸다 — 공유 칸은 한 벌,
    케이스마다 v1 과 같은 길로 푼 칸.
    """
    parsed = parse(raw)
    if len(parsed.cases) > 1 and not cases:
        parsed = _folded(parsed)
    seen = views(parsed)
    values = resolve_params({"params": params})
    solved = []
    for index, (_, view) in enumerate(seen):
        try:
            solved.append(_resolved(view.model_dump(exclude={"cases"}), values, keys))
        except ConditionError as failure:
            if not parsed.cases:
                raise
            raise ConditionError(in_case(index, str(failure))) from failure
    if len(solved) == 1:
        return solved[0]
    out = {key: one for key, one in solved[0].items() if key not in CASE_FIELDS}
    out["schema_version"] = 2
    out["cases"] = [
        {
            "name": case.name,
            "depends_on": case.depends_on,
            "target": case.target.model_dump(),
            **{key: one[key] for key in CASE_FIELDS},
        }
        for case, one in zip(parsed.cases, solved, strict=True)
    ]
    return out


def _folded(conditions: Conditions) -> Conditions:
    """케이스가 여럿인 한 벌을 **v1 한 벌**로 — 「정적 → 모달」(선응력 모달) · 「볼트 예압 →
    외력」(볼트 정적) 사슬만 접는다(`cases.fold_chain`). 못 접으면 그 까닭을 붙여 막는다.
    접은 한 벌도 v1 으로 다시 점검한다 — 하중을 합친 것이 v1 의 규칙을 어기면 받는 쪽보다
    먼저 말한다."""
    blocked = MULTI_CASE_BLOCKED.format(count=len(conditions.cases))
    got = fold_chain(conditions.cases)
    if isinstance(got, str):
        why = f" v1 한 벌로 접지 못한 까닭: {got}" if got else ""
        raise ConditionError(blocked + why)
    one = conditions.model_copy(update={"schema_version": 1, "cases": [], **got})
    try:
        return parse(one.model_dump())
    except ConditionError as failure:
        raise ConditionError(
            f"{blocked} v1 한 벌로 접은 것이 맞지 않습니다: {failure}"
        ) from failure


def _resolved(
    conditions: dict[str, Any], values: dict[str, Any], keys: dict[str, str] | None
) -> dict[str, Any]:
    """v1 모양 한 벌(케이스 하나)을 푼다 — 식 · 계 옮기기 · 채우기(`resolve`)."""

    def walk(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("="):
            return _expr(value, values)
        # 좌표계 원점 같은 세 성분은 모델에서 **튜플**로 나온다 — 목록만 훑으면 그 안의 식이
        # 안 풀린 채 나갔다(2026-09-28 에 잡았다).
        if isinstance(value, list | tuple):
            return [walk(one) for one in value]
        if isinstance(value, dict):
            return {key: walk(one) for key, one in value.items()}
        return value

    try:
        out = {key: walk(one) for key, one in conditions.items()}
    except ExpressionError as failure:
        raise ConditionError(f"조건의 식을 풀지 못했습니다: {failure}") from failure
    out = filled(out)
    system = str((out.get("units") or {}).get("system") or unit_systems.DEFAULT_SYSTEM)
    target = unit_systems.system_of(system)
    source = unit_systems.system_of(INPUT_SYSTEM)
    for item, key, dimension, _ in _value_fields(out, source):
        factor = source.factor(dimension) / target.factor(dimension)
        item[key] = _times(item.get(key), factor)
    out["units"] = unit_systems.declaration(target.key)
    kind = str((out.get("analysis") or {}).get("type") or "modal")
    out["loads"] = [_filled_load(one, target.key, kind) for one in out.get("loads", [])]
    out["initial"] = [_filled_initial(one, target.key) for one in out.get("initial", [])]
    out["analysis"] = _filled_analysis(_integerized(out.get("analysis") or {}, "analysis"))
    out["mesh_hints"] = [
        _integerized(one, f"mesh_hints[{i}]")
        for i, one in enumerate(out.get("mesh_hints", []))
    ]
    out["materials"] = [
        _with_converted(one, target.key, keys or {}) for one in out.get("materials", [])
    ]
    return out


def _times(value: Any, factor: float) -> Any:
    """풀린 값을 배수만큼 — 수 · 수의 목록만. 비었으면 그대로(자유는 자유)."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return float(f"{value * factor:.12g}")
    if isinstance(value, list):
        return [_times(one, factor) for one in value]
    return value


# ── 칸 하나 바꾸기 · 물성 배율 — 실험계획의 고르기 · 배율 인자 ──────────────────

#: 항목을 이름으로 찾을 칸 — 이름이 없는 묶음은 다른 칸으로(초기조건은 종류, 메시 힌트는 대상).
_ITEM_KEY = {"initial": "type", "mesh_hints": "on"}


def _case_scope(out: dict[str, Any], group: str) -> dict[str, Any]:
    """고르기 인자가 바꿀 자리 — 케이스 칸(`CASE_FIELDS`)이면 그 케이스. 케이스가 여럿이면 어느
    케이스인지 고를 칸이 아직 없다(여럿이면 내보내기도 막힌다)."""
    cases = out.get("cases")
    if group not in CASE_FIELDS or not isinstance(cases, list) or not cases:
        return out
    if len(cases) > 1:
        raise ConditionError(
            f"해석 케이스가 {len(cases)}개입니다 — 고르기 인자는 아직 케이스가 하나인 "
            "조건에만 걸 수 있습니다."
        )
    scope: dict[str, Any] = cases[0]
    return scope


def _target_item(out: dict[str, Any], group: str, item: Any) -> dict[str, Any]:
    out = _case_scope(out, group)
    if group == "analysis":
        analysis = out.get("analysis")
        if not isinstance(analysis, dict):
            analysis = {"type": "modal"}
            out["analysis"] = analysis
        return analysis
    rows = out.get(group) or []
    if isinstance(item, int) and not isinstance(item, bool):
        if not 1 <= item <= len(rows):
            raise ConditionError(
                f"{group}에 {item}번째 항목이 없습니다(항목 수: {len(rows)}개)."
            )
        found: dict[str, Any] = rows[item - 1]
        return found
    key = _ITEM_KEY.get(group, "name")
    hits = [one for one in rows if str(one.get(key, "")) == str(item)]
    if not hits:
        have = ", ".join(str(one.get(key, "?")) for one in rows) or "없음"
        raise ConditionError(f"{group}에 ‘{item}’이(가) 없습니다(정의된 항목: {have}).")
    if len(hits) > 1:
        raise ConditionError(
            f"{group}에 ‘{item}’이(가) 여러 개 있습니다. 번호(1부터 시작)로 지정하십시오."
        )
    return hits[0]


def with_choice(raw: dict[str, Any], target: Any, value: Any) -> dict[str, Any]:
    """설계점 하나의 조건 — `target`(묶음 · 항목 · 칸)의 값을 `value` 로 바꾼 **사본**.

    접촉 종류(본딩 ↔ 마찰), 구속 종류, 해석 종류, 선택 그룹, 정식화, 하중의 축(`direction` 에
    `"x"` · `"y"` · `"z"` — `AXIS_CHOICES`) … 고르는 칸이면 무엇이든.
    바꾼 한 벌이 조건으로서 온전한지는 부르는 쪽이 `parse` 로 본다(마찰로 바꾸면 마찰계수가
    있어야 한다 — 그것은 미리 적어 둔다)."""
    from copy import deepcopy

    group, item, field = (
        (target["group"], target.get("item"), target["field"])
        if isinstance(target, dict)
        else target
    )
    out = deepcopy(raw or {})
    _target_item(out, str(group), item)[str(field)] = choice_value(str(field), value)
    return out


def choice_value(field: str, value: Any) -> Any:
    """고르기 인자의 값을 칸에 넣을 값으로 — 하중 `direction` 의 축 이름(`"x"` · `"-z"` …)은
    성분으로 바꾼다. 나머지는 그대로."""
    if field == "direction" and isinstance(value, str) and value.lower() in AXIS_CHOICES:
        return list(AXIS_CHOICES[value.lower()])
    return value


# ── 값 칸 — 내보낼 때 계를 옮긴다 ────────────────────────────────────────────

#: 조건의 칸 → 차원(`core/units.py`). 여기 없는 칸은 계와 상관없다(도 · 온도 · 마찰계수 ·
#: 진동수 · 방향 벡터).
_LENGTH = unit_systems.LENGTH
_VELOCITY: unit_systems.Dimension = (0, 1, -1, 0)
_STIFFNESS: unit_systems.Dimension = (1, -2, -2, 0)  # 응력 / 길이 — 기초 강성
_LOAD_DIMENSION: dict[str, unit_systems.Dimension] = {
    "stress": unit_systems.STRESS,
    "force": unit_systems.FORCE,
    "moment": unit_systems.ENERGY,  # N·mm 과 mJ 는 같은 차원
    "acceleration": (0, 1, -2, 0),
    "angular_velocity": (0, 0, -1, 0),
}


def _value_fields(
    conditions: dict[str, Any], system: unit_systems.System
) -> list[tuple[dict[str, Any], str, Any, str]]:
    """**계를 따르는 값 칸**들 — `(항목, 칸, 차원, 사람이 읽는 이름)`. 내보낼 때 옮기는 목록이
    하나다(칸을 더하고 여기를 빠뜨리면 그 칸만 mm 로 나간다). 볼트는 적힌 단위로 가른다."""
    out: list[tuple[dict[str, Any], str, Any, str]] = []
    for one in conditions.get("constraints") or []:
        name = f"구속 ‘{one.get('name', '')}’"
        for axis in ("x", "y", "z"):
            out.append((one, axis, _LENGTH, f"{name} {axis.upper()} 변위량"))
        out.append((one, "stiffness", _STIFFNESS, f"{name} 기초 강성"))
    for one in conditions.get("loads") or []:
        name = f"하중 ‘{one.get('name', '')}’"
        kind = str(one.get("type", ""))
        if kind == "bolt_pretension":
            by_length = one.get("unit") == system.names["length"]
            dimension = _LENGTH if by_length else unit_systems.FORCE
            out.append(
                (one, "preload", dimension, f"{name} {'조임량' if by_length else '예압'}")
            )
        elif kind in LOAD_DIMENSIONS:
            out.append(
                (one, "magnitude", _LOAD_DIMENSION[LOAD_DIMENSIONS[kind]], f"{name} 크기")
            )
    for one in conditions.get("contacts") or []:
        out.append((one, "pinball", _LENGTH, f"접촉 ‘{one.get('name', '')}’ pinball 반경"))
    for index, one in enumerate(conditions.get("initial") or []):
        if one.get("type") == "velocity":
            out.append((one, "vector", _VELOCITY, f"초기조건 {index + 1} 속도"))
    for one in conditions.get("mesh_hints") or []:
        name = f"국부 메시 ‘{one.get('on', '')}’"
        out.append((one, "element_size", _LENGTH, f"{name} 요소 크기"))
        out.append((one, "defeature_size", _LENGTH, f"{name} 무시할 형상 크기"))
    for one in conditions.get("body_settings") or []:
        name = f"파트 ‘{one.get('name', '')}’"
        if one.get("thickness") is not None:
            # 시트의 쉘 두께 — 빠뜨려 SI 에서도 mm 로 나갔다(2026-10-16). 중간면 요약
            # (`midsurface.bodies[].thickness`)은 계와 상관없이 mm(`length_units.midsurface`).
            out.append((one, "thickness", _LENGTH, f"{name} 쉘 두께"))
        mesh = one.get("mesh")
        if isinstance(mesh, dict):
            out.append((mesh, "element_size", _LENGTH, f"{name} 요소 크기"))
    return out


def expression_notes(raw: dict[str, Any], params: dict[str, Any]) -> list[dict[str, str]]:
    """값 칸의 식 중 **풀리지 않는 것** — `{where, level, text}`. 고치는 중에 알린다(저장 ·
    내보내기에서 막히기 전에). 식은 입력 계(mm · N · t)에서 도면 치수 그대로 푼다."""
    try:
        values = resolve_params({"params": params or {}})
    except ExpressionError:
        return []
    notes: list[dict[str, str]] = []
    system = unit_systems.system_of(INPUT_SYSTEM)
    for prefix, part in _note_parts(raw):
        for item, key, _, label in _value_fields(part, system):
            texts = item.get(key)
            for text in texts if isinstance(texts, list) else [texts]:
                if isinstance(text, str) and text.startswith("="):
                    try:
                        _expr(text, values)
                    except ExpressionError as failure:
                        notes.append(
                            {"where": prefix + label, "level": "warn", "text": str(failure)}
                        )
    return notes


def _note_parts(raw: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    """식 알림을 볼 묶음 — v1 은 한 벌 그대로, v2 는 공유 한 번 · 케이스마다 그 케이스 칸
    (「케이스 ‘예압’ · 하중 ‘누름’ 크기」 — 같은 이름의 하중이 케이스마다 있을 수 있다)."""
    raw = raw or {}
    if not raw.get("cases"):
        return [("", raw)]
    shared = {key: one for key, one in raw.items() if key not in ("cases", *CASE_FIELDS)}
    return [("", shared)] + [
        (f"케이스 ‘{name}’ · ", {key: view.get(key) for key in CASE_FIELDS})
        for name, view in raw_views(raw)
    ]
