"""메시 힌트 · 파트별 설정 — 쉘 · 강체 · 해석 제외, 바디 그룹 · 볼트 예압 단면.

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, field_validator

from app.core.conditions.common import (
    ALL_BODIES,
    Base,
    ConditionError,
    Integer,
    NamedSelection,
    Number,
    _extra,
    _integer_or_expr,
)
from app.core.conditions.loads import CONSTRAINT_LABELS

if TYPE_CHECKING:
    from app.core.conditions.model import Conditions


class MeshHint(Base):
    """**국부 메시** — 면 · 엣지 선택 그룹을 촘촘하게(국부 세분화), 또는 「전체」 에 모델
    전체의 값(기본 요소 크기 · 요소 형상 · 차수 · 무시할 형상 크기 · 경계층). 파트 하나
    전체의 메시는 파트별 설정(`body_settings[].mesh`)이 든다 — 2026-10-04 에 바디 대상을
    그리로 옮겼다.

    메시는 받는 쪽이 만든다 — 여기 적는 것은 **바람**이다. 비운 칸은 받는 쪽이 정한다."""

    on: str = Field(
        "전체",
        title="적용 대상",
        description="‘전체’ 또는 면·엣지 선택 그룹입니다. 파트 하나 전체의 메시는 "
        "‘파트별 설정’ 표에서 지정하십시오.",
        json_schema_extra=_extra({"whole": "전체"}),
    )
    element_size: Number | None = Field(
        None,
        title="요소 크기",
        description="요소 한 변의 평균 길이입니다. 작을수록 정확하지만 계산이 느려집니다. "
        "판은 두께의 1/2~1/3 정도가 적당합니다.",
        json_schema_extra=_extra({"unit": "mm"}),
    )
    method: Literal["automatic", "tetrahedrons", "hex_dominant", "sweep", "multizone"] = Field(
        "automatic",
        title="요소 형상",
        description="확실하지 않으면 ‘자동’을 선택하십시오. 스윕과 멀티존은 스윕 "
        "형상(판, 축)을 육면체 요소로 채웁니다. ‘전체’에만 지정합니다.",
        json_schema_extra=_extra(
            {
                "whole_only": True,
                "labels": {
                    "automatic": "자동",
                    "tetrahedrons": "사면체",
                    "hex_dominant": "육면체 우세",
                    "sweep": "스윕(육면체)",
                    "multizone": "멀티존(육면체)",
                },
            }
        ),
    )
    order: Literal["program_controlled", "linear", "quadratic"] = Field(
        "program_controlled",
        title="요소 차수",
        description="2차 요소가 응력과 굽힘 계산에 정확합니다(권장). 1차 요소는 "
        "빠르지만 사면체에서는 강성이 과대평가됩니다. ‘전체’에만 지정합니다.",
        json_schema_extra=_extra(
            {
                "whole_only": True,
                "labels": {
                    "program_controlled": "프로그램 제어",
                    "linear": "1차(빠름)",
                    "quadratic": "2차(정확)",
                },
            }
        ),
    )
    inflation_layers: Integer | None = Field(
        None,
        title="경계층 수",
        description="벽면 근처를 얇은 층으로 분할합니다. 유동·열 경계층용이며, 구조 "
        "해석에서는 비워 두십시오.",
        json_schema_extra=_extra({"integer": True}),
    )
    defeature_size: Number | None = Field(
        None,
        title="무시할 형상 크기",
        description="이보다 작은 모서리, 구멍, 필렛은 메시 생성 시 무시합니다.",
        json_schema_extra=_extra({"unit": "mm"}),
    )

    @field_validator("method", "order", mode="before")
    @classmethod
    def _blank(cls, value: Any, info: Any) -> Any:
        """예전에 비워 둔 칸(`""`)은 기본값으로."""
        if value in ("", None):
            return cls.model_fields[info.field_name].default
        return value

    @field_validator("inflation_layers", mode="before")
    @classmethod
    def _integer(cls, value: Any) -> Any:
        return _integer_or_expr(value)


# ── 파트별 설정 ───────────────────────────────────────────────────────────────


class BodyMesh(Base):
    """파트 하나의 메시 — 그 파트 전체의 기본값. 국부 메시와 같은 칸이고 같은 「바람」이다.

    겹치면 **좁은 것이 이긴다**: 국부 메시 「전체」 < 파트 메시 < 면 · 엣지 국부 메시."""

    element_size: Number | None = Field(
        default=None,
        title="요소 크기",
        description="이 파트의 요소 한 변의 평균 길이입니다. 비워 두면 국부 메시 ‘전체’ "
        "또는 해석 플랫폼의 기본값을 따릅니다.",
        json_schema_extra=_extra({"unit": "mm"}),
    )
    method: Literal["automatic", "tetrahedrons", "hex_dominant", "sweep", "multizone"] = Field(
        default="automatic",
        title="요소 형상",
        json_schema_extra=_extra(
            {
                "labels": {
                    "automatic": "자동",
                    "tetrahedrons": "사면체",
                    "hex_dominant": "육면체 우세",
                    "sweep": "스윕(육면체)",
                    "multizone": "멀티존(육면체)",
                }
            }
        ),
    )
    order: Literal["program_controlled", "linear", "quadratic"] = Field(
        default="program_controlled",
        title="요소 차수",
        json_schema_extra=_extra(
            {
                "labels": {
                    "program_controlled": "프로그램 제어",
                    "linear": "1차(빠름)",
                    "quadratic": "2차(정확)",
                }
            }
        ),
    )


class BodySetting(Base):
    """파트(바디) 하나를 **해석에서 어떻게 다루나** — 거동 · 표현 · 해석 포함 · 메시.

    적지 않은 파트는 기본값(변형체 · 솔리드 · 포함 · 국부 메시 「전체」 를 따름)이다. 화면은
    파트마다 한 줄인 표로 고치고, 기본값으로 돌아온 줄은 빼고 저장한다."""

    name: str = Field(
        min_length=1,
        max_length=60,
        title="파트",
        description="파트(바디) 이름입니다. 단일 파트이면 ‘전체’입니다.",
    )
    behavior: Literal["deformable", "rigid"] = Field(
        "deformable",
        title="거동",
        description="강체로 지정하면 이 파트는 변형하지 않는 것으로 계산합니다. 요소 수가 "
        "크게 줄지만 이 파트의 응력은 계산되지 않습니다.",
        json_schema_extra=_extra({"labels": {"deformable": "변형체", "rigid": "강체"}}),
    )
    representation: Literal["solid", "shell"] = Field(
        "solid",
        title="표현",
        description="쉘은 두께가 일정한 판을 중간면과 두께로 계산합니다. 쉘 파트가 있으면 "
        "설계점마다 중간면 STEP이 함께 생성됩니다.",
        json_schema_extra=_extra({"labels": {"solid": "솔리드", "shell": "쉘"}}),
    )
    thickness: float | None = Field(
        None,
        gt=0,
        le=1000,
        title="두께(mm)",
        description="시트 바디(셸 모델 — 형상이 이미 중간면)의 쉘 두께입니다. 솔리드를 쉘로 "
        "풀 때는 비워 둡니다(두께를 형상에서 잽니다). 쉘 파트에만 적습니다.",
    )
    suppressed: bool = Field(
        False,
        title="해석 제외",
        description="형상에는 남기고 해석에서만 제외합니다.",
    )
    mesh: BodyMesh = Field(default_factory=BodyMesh, title="메시")


def shell_parts(raw: dict[str, Any] | None) -> list[str]:
    """쉘로 푸는 파트들(해석에서 뺀 것 제외) — 이 파트들만 중간면을 만든다."""
    settings = raw.get("body_settings") if isinstance(raw, dict) else None
    if not isinstance(settings, list):
        return []  # 모양이 틀렸으면 검증(`parse`)이 말한다
    return [
        str(one.get("name"))
        for one in settings
        if isinstance(one, dict)
        and one.get("representation") == "shell"
        and not one.get("suppressed")
    ]


def _check_sheet_setting(
    where: str, one: BodySetting, sheet: bool, known: set[str] | None
) -> None:
    """파트 설정이 **형상의 종류**와 맞나(2026-10-16, SimEngBay 의 부탁).

    시트 바디는 두께가 없어 솔리드 요소로 풀 수 없다 — 쉘이거나 해석 제외뿐이다. 받는 쪽은
    그 밖이면 작업을 만들 때 막는데, 그때는 이미 내보낸 뒤다. 솔리드를 쉘로 풀 때 두께는
    **형상에서 잰다** — 적은 두께는 쓰이지 않아 점 파일의 두 두께(`body_settings[].thickness`
    · `midsurface.bodies[].thickness`)가 갈렸다."""
    if sheet:
        if one.behavior == "rigid":
            raise ConditionError(
                f"{where}: 파트 ‘{one.name}’은(는) 시트 바디(셸 모델)라 강체로 둘 수 "
                "없습니다. 변형체 쉘로 두거나 해석에서 제외하십시오."
            )
        if one.representation != "shell":
            raise ConditionError(
                f"{where}: 파트 ‘{one.name}’은(는) 시트 바디(셸 모델)라 쉘로만 풀 수 "
                "있습니다. 표현을 쉘로 두고 두께를 적으십시오."
            )
    elif one.thickness is not None and (known is None or one.name in known):
        raise ConditionError(
            f"{where}: 파트 ‘{one.name}’은(는) 솔리드라 쉘 두께를 형상에서 잽니다 — 두께를 "
            "비우십시오. 두께는 시트 바디(셸 모델)에만 적습니다."
        )


def sheets_as_shell(resolved: dict[str, Any], sheets: list[str]) -> dict[str, Any]:
    """점 파일의 조건에서 **시트 파트는 늘 쉘**이다 — 설정 줄이 없거나 표현을 안 적었어도.

    시트는 쉘로만 풀린다(검증이 솔리드로 적은 것을 막는다). 받는 쪽이 「표현이 솔리드이거나
    설정이 없다」 로 작업을 막지 않게, 내보내는 조건에 그렇게 적어 준다. 해석 제외한 줄은
    그대로 둔다."""
    if not sheets:
        return resolved
    rows = [dict(one) for one in resolved.get("body_settings") or []]
    have = {one.get("name") for one in rows}
    for row in rows:
        if row.get("name") in sheets and not row.get("suppressed"):
            row["representation"] = "shell"
            row["behavior"] = "deformable"
    rows.extend(
        BodySetting.model_validate({"name": name, "representation": "shell"}).model_dump(
            mode="json"
        )
        for name in sheets
        if name not in have
    )
    return {**resolved, "body_settings": rows}


def shell_thicknesses(raw: dict[str, Any] | None) -> dict[str, float]:
    """파트 이름 → 사람이 정한 쉘 두께(mm) — 시트 바디(셸 모델)의 중간면이 쓴다. 솔리드를 쉘로
    푸는 파트는 두께를 형상에서 재므로 여기 없어도 된다."""
    settings = raw.get("body_settings") if isinstance(raw, dict) else None
    if not isinstance(settings, list):
        return {}
    out: dict[str, float] = {}
    for one in settings:
        if not isinstance(one, dict) or one.get("suppressed"):
            continue
        value = one.get("thickness")
        if isinstance(value, int | float) and value > 0:
            out[str(one.get("name"))] = float(value)
    return out


def has_shell(raw: dict[str, Any] | None) -> bool:
    """쉘로 푸는 파트가 있나 — 있으면 설계점마다 중간면이 필요하다(옛 조건은 칸이 없다)."""
    return bool(shell_parts(raw))


def mesh_skips(raw: dict[str, Any] | None) -> tuple[frozenset[str], frozenset[str]]:
    """전역 요소 크기 제안이 **뺄 파트** — (벽 두께에서, 크기에서).

    벽에서는 해석 제외 · 쉘(두께 방향으로 요소를 쌓지 않는다) · 강체(요소를 촘촘히 안 짓는다)를
    뺀다. 크기에서는 해석 제외만 — 쉘 · 강체도 모델의 크기다."""
    settings = raw.get("body_settings") if isinstance(raw, dict) else None
    wall: set[str] = set()
    size: set[str] = set()
    for one in settings or []:
        if not isinstance(one, dict) or not one.get("name"):
            continue
        name = str(one["name"])
        if one.get("suppressed"):
            wall.add(name)
            size.add(name)
        elif one.get("representation") == "shell" or one.get("behavior") == "rigid":
            wall.add(name)
    return frozenset(wall), frozenset(size)


def body_regions(
    raw: dict[str, Any] | None, bodies: list[dict[str, Any]]
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """**바디 그룹 → 그 바디의 `bodies[]` 줄** — 점 파일의 `regions` 에 면 지문 대신 싣는다.
    그리고 못 푼 이름들.

    면 · 엣지 · 점 그룹은 지문이 있는데 바디 그룹만 `regions` 에 없어, 받는 쪽이 바디에 건
    조건(바디 예압 등)을 받지 못했다. SimEngBay 와 정한 꼴(2026-10-28): `bodies[]` 의 그 줄
    그대로 — 짝짓는 법이 `bodies[]` 와 같다(이름 → STEP product → 부피 · 무게중심).

    규칙에 바디 이름이 없거나 「전체」 면 모든 바디다. **적힌 바디가 하나라도 없으면 못 푼
    것**이다 — 있는 것만 실으면 조건이 일부 바디에만 걸린 채 해석이 돈다."""
    rows = {str(one.get("name")): one for one in bodies}
    found: dict[str, list[dict[str, Any]]] = {}
    missing: list[str] = []
    for one in (raw or {}).get("named_selections") or []:
        if not isinstance(one, dict) or one.get("entity") != "body" or not one.get("name"):
            continue
        select = one.get("select") or {}
        members = select.get("any") or [select]
        names = [str(rule.get("body") or "") for rule in members if isinstance(rule, dict)]
        if not names or "" in names or ALL_BODIES in names:
            picked = list(bodies)
        elif all(name in rows for name in names):
            picked = [rows[name] for name in dict.fromkeys(names)]
        else:
            picked = []
        if picked:
            found[str(one["name"])] = [dict(row) for row in picked]
        else:
            missing.append(str(one["name"]))
    return found, missing


def pretension_misses(
    raw: dict[str, Any] | None,
    regions: dict[str, list[dict[str, Any]]],
    frames: list[dict[str, Any]],
) -> list[str]:
    """**단면이 바디를 지나지 않는** 바디 예압 — 그 까닭 한 줄씩.

    단면은 예압 하중의 좌표계다(원점을 지나고 Z 에 수직인 평면). 치수를 바꾼 설계점에서
    볼트가 옮겨 가면 평면이 볼트 밖에 남을 수 있다 — 받는 쪽(SimEngBay)은 그 점을 막으므로
    내보낼 때 알린다. 바디의 경계상자로 본다(상자를 안 지나면 바디도 안 지난다). `frames` ·
    `regions` 는 도면의 mm 다."""
    by_name = {str(one.get("name")): one for one in frames}
    out: list[str] = []
    for load in (raw or {}).get("loads") or []:
        if not isinstance(load, dict) or load.get("type") != "bolt_pretension":
            continue
        frame = by_name.get(str(load.get("cs")))
        rows = regions.get(str(load.get("on"))) or []
        if frame is None or not rows or "volume" not in rows[0]:
            continue  # 면에 건 예압 · 못 푼 좌표계는 다른 자리가 말한다
        origin = [float(v) for v in frame.get("origin") or (0, 0, 0)]
        axis = [float(v) for v in frame.get("z") or (0, 0, 1)]
        for row in rows:
            low, high = row.get("bbox") or [[0, 0, 0], [0, 0, 0]]
            sides = {
                sum((corner[i] - origin[i]) * axis[i] for i in range(3)) > 0
                for corner in (
                    (x, y, z)
                    for x in (low[0], high[0])
                    for y in (low[1], high[1])
                    for z in (low[2], high[2])
                )
            }
            if len(sides) == 1:
                out.append(
                    f"볼트 예압 ‘{load.get('name')}’의 단면(좌표계 ‘{load.get('cs')}’)이 "
                    f"바디 ‘{row.get('name')}’을(를) 지나지 않습니다"
                )
    return out


def has_global_mesh(raw: dict[str, Any] | None) -> bool:
    """사람이 **전역 요소 크기**를 적었나 — 국부 메시 「전체」 의 요소 크기(식이어도 적은
    것이다). 안 적었으면 받는 쪽은 점 파일의 제안값(`mesh_suggestion`)을 쓴다."""
    hints = (raw or {}).get("mesh_hints") if isinstance(raw, dict) else None
    for one in hints or []:
        if not isinstance(one, dict) or one.get("on", ALL_BODIES) != ALL_BODIES:
            continue
        if one.get("element_size") not in (None, ""):
            return True
    return False


#: 강체 면에 걸 수 있는 구속 — 받는 쪽(Ansys · CalculiX)은 강체에 하중 · 다른 구속을 걸지
#: 못하고 멈춘다(SimEngBay, 2026-10-04). 저장할 때 미리 말한다.
RIGID_CONSTRAINTS = ("fixed_support", "remote_displacement")


def _check_rigid(conditions: Conditions, rigid: set[str]) -> None:
    """강체 파트에는 고정 지지 · 원격 변위만, 강체끼리는 접촉하지 않는다. 어느 파트의 것인지
    아는 선택 그룹(바디 그룹 · 파트로 거른 그룹)만 본다."""
    selections = {one.name: one for one in conditions.named_selections}

    def on_rigid(name: str) -> set[str] | None:
        selection = selections.get(name)
        bodies = _bodies_of(selection) if selection else None
        return bodies if bodies and bodies <= rigid else None

    for index, item in enumerate(conditions.constraints):
        bodies = on_rigid(item.on)
        if bodies and item.type not in RIGID_CONSTRAINTS:
            raise ConditionError(
                f"constraints[{index}]: 강체 파트({', '.join(sorted(bodies))})에는 고정 "
                f"지지와 원격 변위만 지정할 수 있습니다(‘{item.name}’은(는) "
                f"{CONSTRAINT_LABELS[item.type]}). 파트를 변형체로 바꾸거나 구속을 바꾸십시오."
            )
    for index, load in enumerate(conditions.loads):
        bodies = on_rigid(load.on) if load.on else None
        if bodies:
            raise ConditionError(
                f"loads[{index}]: 강체 파트({', '.join(sorted(bodies))})에는 하중을 지정할 수 "
                f"없습니다(‘{load.name}’). 파트를 변형체로 바꾸거나 원격 변위로 거십시오."
            )
    for index, contact in enumerate(conditions.contacts):
        if on_rigid(contact.source) and on_rigid(contact.target):
            raise ConditionError(
                f"contacts[{index}]: ‘{contact.name}’은(는) 강체 파트끼리의 접촉입니다. "
                "한쪽을 변형체로 바꾸십시오."
            )


def _bodies_of(selection: NamedSelection) -> set[str] | None:
    """선택 그룹이 **어느 파트의 것인가** — 규칙마다 `body` 가 적혀 있을 때만 안다(바디 그룹,
    「블록의 아랫면」 같은 파트로 거른 그룹). 좌표만 적힌 규칙이면 모른다(None)."""
    members = selection.select.get("any") or [selection.select]
    names = {str(one.get("body", "")) for one in members}
    return None if "" in names else names


def _check_body_settings(
    conditions: Conditions, known: set[str] | None, sheets: set[str] | None = None
) -> None:
    """파트별 설정 — 파트가 있고 한 번씩만 적혔나, 뜻이 서로 맞나, 해석할 것이 남나."""
    settings = conditions.body_settings
    names = [one.name for one in settings]
    for index, one in enumerate(settings):
        where = f"body_settings[{index}]"
        if names.count(one.name) > 1:
            raise ConditionError(
                f"{where}: 파트 ‘{one.name}’의 설정이 2개입니다. 파트마다 하나만 지정할 수 "
                "있습니다."
            )
        if known is not None and one.name != ALL_BODIES and one.name not in known:
            raise ConditionError(
                f"{where}: 파트 ‘{one.name}’이(가) 없습니다"
                f"(존재하는 파트: {', '.join(sorted(known)) or '없음'})."
            )
        if one.behavior == "rigid" and one.representation == "shell":
            raise ConditionError(
                f"{where}: 강체 파트 ‘{one.name}’은(는) 쉘로 표현할 수 없습니다. 거동을 "
                "변형체로 바꾸거나 표현을 솔리드로 두십시오."
            )
        sheet = sheets is not None and one.name in sheets
        if sheet and "representation" not in one.model_fields_set:
            # 시트는 쉘로만 풀린다 — 표현을 안 적은 줄은 쉘이다(내보낼 때도 그렇게 적는다).
            one.representation = "shell"
        if one.thickness is not None and one.representation != "shell":
            raise ConditionError(
                f"{where}: 두께는 쉘 파트에만 적습니다 — 파트 ‘{one.name}’의 표현을 쉘로 "
                "바꾸거나 두께를 비우십시오."
            )
        if sheets is not None and not one.suppressed:
            _check_sheet_setting(where, one, sheet, known)
    if ALL_BODIES in names and len(names) > 1:
        raise ConditionError(
            f"파트별 설정에 ‘{ALL_BODIES}’와(과) 개별 파트가 함께 있습니다. ‘{ALL_BODIES}’는 "
            "단일 파트일 때만 사용하십시오."
        )
    rigid = {one.name for one in settings if one.behavior == "rigid" and not one.suppressed}
    if rigid:
        _check_rigid(conditions, rigid)
    off = {one.name for one in settings if one.suppressed}
    everything = ALL_BODIES in off or (known is not None and bool(known) and known <= off)
    if everything:
        raise ConditionError(
            "모든 파트가 해석에서 제외되었습니다. 하나 이상의 파트를 해석에 포함하십시오."
        )
    if not off:
        return
    # **제외한 파트에 조건을 걸면** 받는 쪽은 없는 형상에 하중을 얹으려다 멈추거나 조용히
    # 버린다. 어느 파트의 것인지 아는 선택 그룹(바디 그룹 · 파트로 거른 그룹)만 본다.
    selections = {one.name: one for one in conditions.named_selections}
    used: list[tuple[str, str]] = []
    for group in ("constraints", "loads", "initial"):
        for index, item in enumerate(getattr(conditions, group)):
            used.append((f"{group}[{index}]", str(getattr(item, "on", ""))))
    for index, contact in enumerate(conditions.contacts):
        used += [
            (f"contacts[{index}]", contact.source),
            (f"contacts[{index}]", contact.target),
        ]
    for where, name in used:
        selection = selections.get(name)
        bodies = _bodies_of(selection) if selection else None
        if bodies and bodies <= off:
            raise ConditionError(
                f"{where}: 선택 그룹 ‘{name}’은(는) 해석에서 제외한 파트"
                f"({', '.join(sorted(bodies))})에 있습니다. 조건을 지우거나 파트를 해석에 "
                "포함하십시오."
            )
