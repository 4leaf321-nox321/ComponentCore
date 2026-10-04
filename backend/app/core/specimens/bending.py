"""굽힘 — 규격 규칙(간격비 · 두께에 따른 반지름 · 4점의 하중 간격)과 시편 · 시험 지그 ·
해석 조건.

좌표: 시편은 길이가 X, 폭이 Y, 두께가 Z — XY 가운데가 원점, 아랫면이 z=0. 지지 롤러는
아래에서(축 = Y, 아랫면에 닿게), 노즈는 위에서 누른다. 지그 생성기(`planning._plan_bending`)도
같은 규칙 함수를 쓴다 — 시편 템플릿과 지그가 같은 규격에서 다른 간격을 내면 안 된다.

**두께를 훑으면 따라온다.** 간격비 규격(16:1)은 레시피 변수 `지지_간격 = 간격비 * 두께`,
처짐은 `변형률 · (3L² - 4s²) / (12h)` 식이다 — DOE 가 두께를 바꾸면 간격 · 하중이 같이
움직인다. 두께에 따라 갈리는 반지름(ISO 178)만은 식으로 쓸 수 없어(치수 식에 조건문이 없다)
만들 때의 두께로 정하고 메모로 말한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.specimens.presets import BendingPreset, BendingSetup, Radius

#: 시편 바디 · 조건의 이름 — 지그 생성기의 이름표(`롤러_1` · `로딩_노즈`)와 같다.
SPECIMEN = "시편"
ROLLERS = ("롤러_1", "롤러_2")
#: 대칭점 구속을 거는 아랫면 한가운데의 작은 원(태그).
CENTER_TAG = "시편_중앙"
#: 롤러 · 노즈가 시편 폭보다 양쪽으로 더 긴 길이(합, mm).
ROLLER_EXTRA = 10.0


def noses(points: int) -> tuple[str, ...]:
    """노즈 바디 이름 — 3점은 하나(`로딩_노즈`), 4점은 둘."""
    return ("로딩_노즈",) if points == 3 else ("로딩_노즈_1", "로딩_노즈_2")


def radius_at(rule: Radius, thickness: float) -> float:
    if isinstance(rule, int | float):
        return float(rule)
    for one in rule:
        if one.max_thickness is None or thickness <= one.max_thickness + 1e-9:
            return float(one.radius)
    return float(rule[-1].radius)


def span_at(setup: BendingSetup, thickness: float) -> float:
    if setup.span.to_thickness is not None:
        return round(setup.span.to_thickness * thickness, 4)
    return float(setup.span.value or 0.0)


def load_span_at(setup: BendingSetup, span: float) -> float:
    """4점의 하중 간격 — 3점이면 0."""
    rule = setup.load_span
    if setup.points == 3 or rule is None:
        return 0.0
    if rule.to_span is not None:
        return round(rule.to_span * span, 4)
    return float(rule.value or 0.0)


def overhang_at(setup: BendingSetup, span: float) -> float:
    return max(setup.overhang.to_span * span, setup.overhang.min)


def deflection(strain: float, span: float, load_span: float, thickness: float) -> float:
    """바깥 섬유 변형률이 `strain` 이 되는 중앙 처짐 — 3점이면 εL²/(6h)(D790 의 식), 4점이면
    εu(3L² - 4s²)/(12h), s = (L - 하중 간격)/2(하중 간격 1/3 이면 0.213εL²/h — D6272 의 식)."""
    s = (span - load_span) / 2
    return strain * (3 * span**2 - 4 * s**2) / (12 * thickness)


def _radius_note(name: str, rule: Radius, thickness: float) -> str | None:
    if isinstance(rule, int | float):
        return None
    lines = ", ".join(
        f"{one.max_thickness:g} mm 이하 {one.radius:g}"
        if one.max_thickness is not None
        else f"나머지 {one.radius:g}"
        for one in rule
    )
    return (
        f"{name}은 두께 {thickness:g} mm 기준 {radius_at(rule, thickness):g} mm입니다"
        f"(규격: {lines}). 두께를 바꾸면 반지름을 확인하십시오."
    )


@dataclass
class SpecimenBuild:
    recipe: dict[str, Any]
    conditions: dict[str, Any] | None
    notes: list[str] = field(default_factory=list)


def build(
    preset: BendingPreset,
    *,
    length: float | None = None,
    width: float | None = None,
    thickness: float | None = None,
    fixture: bool = True,
    conditions: bool = True,
) -> SpecimenBuild:
    """프리셋으로 시편(과 시험 지그 · 해석 조건)을 그린다. 치수는 주면 그것, 아니면 프리셋 값.

    해석 조건은 시험 지그가 있어야 한다(롤러 · 노즈에 건다). 지그 없이 시편만이면 비운다."""
    setup = preset.setup
    size = preset.specimen
    length = float(length or size.length)
    width = float(width or size.width)
    thickness = float(thickness or size.thickness)
    span = span_at(setup, thickness)
    load_span = load_span_at(setup, span)
    notes: list[str] = []
    if span >= length:
        raise ValueError(f"지지 간격({span:g} mm)이 시편 길이({length:g} mm)보다 깁니다.")
    need = span + 2 * overhang_at(setup, span)
    if length < need - 1e-6:
        notes.append(
            f"시편 길이({length:g} mm)가 규격의 돌출을 담지 못합니다(최소 {need:g} mm)."
        )
    for name, rule in (
        ("지지 반지름", setup.support_radius),
        ("노즈 반지름", setup.nose_radius),
    ):
        said = _radius_note(name, rule, thickness)
        if said:
            notes.append(said)
    if not preset.verified:
        notes.append(
            f"규격값을 아직 규격서와 대조하지 않았습니다(출처: {preset.source or '없음'})."
        )

    params: dict[str, Any] = {"길이": length, "폭": width, "두께": thickness}
    if setup.span.to_thickness is not None:
        params["간격비"] = setup.span.to_thickness
        params["지지_간격"] = "=간격비 * 두께"
    else:
        params["지지_간격"] = span
    nodes: list[dict[str, Any]] = [
        {
            "id": f"{SPECIMEN}_몸통" if conditions and fixture else SPECIMEN,
            "op": "box",
            "label": "시편",
            "length": "=길이",
            "width": "=폭",
            "height": "=두께",
            "align": ["center", "center", "min"],
        }
    ]
    with_conditions = conditions and fixture
    if with_conditions:
        # 대칭점 — 아랫면 한가운데의 작은 원. 시편이 X · Y 로 대칭이라 이 자리는 원래 X · Y
        # 로 움직이지 않는다. 구속해도 결과를 비틀지 않고, 접촉만으로 놓인 시편의 강체 운동을
        # 막는다.
        nodes.append(
            {
                "id": SPECIMEN,
                "op": "divide_face",
                "label": "대칭점",
                "target": f"{SPECIMEN}_몸통",
                "on": {"role": "bottom"},
                "shape": "circle",
                "radius": round(min(0.5, width / 8, length / 8), 3),
                "tag": CENTER_TAG,
            }
        )
    if not fixture:
        return SpecimenBuild(
            recipe={"version": 1, "params": params, "nodes": nodes},
            conditions=None,
            notes=notes,
        )

    params["지지_반지름"] = radius_at(setup.support_radius, thickness)
    params["노즈_반지름"] = radius_at(setup.nose_radius, thickness)
    params["롤러_길이"] = f"=폭 + {ROLLER_EXTRA:g}"
    if setup.points == 4:
        if setup.load_span and setup.load_span.to_span is not None:
            params["하중_간격_비"] = setup.load_span.to_span
            params["하중_간격"] = "=지지_간격 * 하중_간격_비"
        else:
            params["하중_간격"] = load_span

    def lying(node_id: str, label: str, radius: str, x: Any, z: Any) -> dict[str, Any]:
        return {
            "id": node_id,
            "op": "cylinder",
            "label": label,
            "radius": radius,
            "height": "=롤러_길이",
            "axis": "Y",
            "at": [x, 0, z],
        }

    nodes += [
        lying(ROLLERS[0], "지지 롤러", "=지지_반지름", "=-지지_간격 / 2", "=-지지_반지름"),
        lying(ROLLERS[1], "지지 롤러", "=지지_반지름", "=지지_간격 / 2", "=-지지_반지름"),
    ]
    nose_names = noses(setup.points)
    nose_x: list[Any] = [0] if setup.points == 3 else ["=-하중_간격 / 2", "=하중_간격 / 2"]
    for name, x in zip(nose_names, nose_x, strict=True):
        nodes.append(lying(name, "로딩 노즈", "=노즈_반지름", x, "=두께 + 노즈_반지름"))
    nodes.append(
        {
            "id": "굽힘_시험",
            "op": "group",
            "label": f"{setup.points}점 굽힘",
            "targets": [SPECIMEN, *ROLLERS, *nose_names],
        }
    )
    if not conditions:
        return SpecimenBuild(
            recipe={"version": 1, "params": params, "nodes": nodes},
            conditions=None,
            notes=notes,
        )

    analysis = preset.analysis
    params["변형률"] = analysis.strain
    params["마찰계수"] = analysis.friction
    if setup.points == 3:
        params["처짐"] = "=변형률 * 지지_간격 ** 2 / (6 * 두께)"
    else:
        params["처짐"] = (
            "=변형률 * (3 * 지지_간격 ** 2 - (지지_간격 - 하중_간격) ** 2) / (12 * 두께)"
        )
    notes.append(
        f"노즈를 바깥 섬유 변형률 {analysis.strain:g}에 해당하는 처짐"
        f"({deflection(analysis.strain, span, load_span, thickness):.3g} mm)만큼 내립니다"
        "(해석 기본값이며 규격의 판정 기준이 아닙니다). 시편의 물성을 지정하십시오."
    )
    recipe = {"version": 1, "params": params, "nodes": nodes}
    return SpecimenBuild(recipe=recipe, conditions=_conditions(nose_names), notes=notes)


def _faces(body: str, **query: Any) -> dict[str, Any]:
    return {"what": "faces", "body": body, **query}


def _conditions(nose_names: tuple[str, ...]) -> dict[str, Any]:
    """굽힘 시험의 해석 조건 — 롤러 · 노즈는 강체, 롤러 고정, 노즈를 원격 변위로 내린다,
    시편과 마찰 접촉, 아랫면 한가운데 대칭점 구속, 정적 대변형. 숫자는 레시피 변수(`처짐` ·
    `마찰계수`)를 가리켜 DOE 의 설계점마다 따라간다."""
    cylinder = {"kind": "cylinder"}
    noses_select = (
        _faces(nose_names[0], **cylinder)
        if len(nose_names) == 1
        else {"any": [_faces(one, **cylinder) for one in nose_names]}
    )
    contact = {
        "type": "frictional",
        "friction": "=마찰계수",
        "behavior": "asymmetric",
        "interface_treatment": "adjust_to_touch",
    }
    return {
        "schema_version": 1,
        "named_selections": [
            {
                "name": "시편 아랫면",
                "entity": "face",
                "select": _faces(SPECIMEN, normal=[0, 0, -1]),
            },
            {
                "name": "시편 윗면",
                "entity": "face",
                "select": _faces(SPECIMEN, normal=[0, 0, 1]),
            },
            {
                "name": "시편 중앙",
                "entity": "face",
                "select": {"what": "faces", "tag": CENTER_TAG},
            },
            {
                "name": "지지 롤러",
                "entity": "face",
                "select": {"any": [_faces(one, **cylinder) for one in ROLLERS]},
            },
            {"name": "로딩 노즈", "entity": "face", "select": noses_select},
        ],
        "constraints": [
            {"name": "지지 롤러 고정", "type": "fixed_support", "on": "지지 롤러"},
            {
                "name": "시편 중앙 대칭",
                "type": "displacement",
                "on": "시편 중앙",
                "x": 0,
                "y": 0,
                "z": None,
            },
            {
                "name": "노즈 가압",
                "type": "remote_displacement",
                "on": "로딩 노즈",
                "behavior": "rigid",
                "x": 0,
                "y": 0,
                "z": "=-처짐",
                "rx": 0,
                "ry": 0,
                "rz": 0,
            },
        ],
        "contacts": [
            {
                "name": "시편-지지 롤러",
                "source": "시편 아랫면",
                "target": "지지 롤러",
                **contact,
            },
            {
                "name": "시편-로딩 노즈",
                "source": "시편 윗면",
                "target": "로딩 노즈",
                **contact,
            },
        ],
        "analysis": {"type": "static", "large_deflection": True, "substeps": 20},
        "body_settings": [
            {"name": one, "behavior": "rigid"} for one in (*ROLLERS, *nose_names)
        ],
    }
