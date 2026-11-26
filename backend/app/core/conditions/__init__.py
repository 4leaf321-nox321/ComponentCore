"""해석 조건 — **솔버를 모르는 중립 표현.**

경계조건 · 하중 · 접촉 · 초기조건 · 해석 설정 · 물성을 한 벌로 적는다. 이 플랫폼은 메시도
솔브도 하지 않고 결과도 받지 않는다 — 조건을 **파일로 넘기는 데까지**가 일이다. 받는 쪽이
하나가 아니므로(Ansys · 그 밖) 여기 적힌 말은 어느 솔버의 것도 아니어야 하고, 솔버별 매핑은
받는 쪽이 들고 있다. 설계는 `docs/해석-조건-설계.md`.

## 조건은 면을 직접 가리키지 않는다

모든 조건은 **선택 그룹(named_selections)** 만 가리킨다. 선택 그룹은 좌표가 아니라
**셀렉터**(`query.find_features` 의 말)로 적혀 있어서, 실험계획이 치수를 바꿔도 설계점마다 다시
풀린다. (화면의 말은 「선택 그룹」 이다 — 예전 문서 · 주석의 「이름표」 와 같은 것이다.)
「(30, 15, 5) 의 면」 은 두께를 바꾸는 순간 그 자리에 없지만 「아래쪽 면」 은 남는다.

그리고 같은 면에 하중과 메시 힌트를 따로 걸어도 **고칠 자리가 하나**다.

## 숫자 칸에는 식을 쓸 수 있다

레시피와 **같은 자리, 같은 문법**이다 — `"=압력"` · `"=두께 * 120"`. 변수는 레시피의
`params` 를 그대로 쓰므로, 실험계획이 그 변수를 훑으면 **형상과 조건이 함께 움직인다.**
푸는 것은 `core/recipe/params.resolve()` — dict 를 훑는 함수라 조건에도 그대로 듣는다.
"""

from __future__ import annotations

from app.core.conditions.analysis import (
    ANALYSIS_LABELS,
    ANALYSIS_NOTES,
    Analysis,
)
from app.core.conditions.bodies import (
    RIGID_CONSTRAINTS,
    BodyMesh,
    BodySetting,
    MeshHint,
    body_regions,
    has_global_mesh,
    has_shell,
    mesh_skips,
    pretension_misses,
    sheets_as_shell,
    shell_parts,
    shell_thicknesses,
)
from app.core.conditions.cases import (
    CASE_FIELDS,
    MULTI_CASE_BLOCKED,
    Case,
    Target,
    raw_views,
)
from app.core.conditions.common import (
    ALL_BODIES,
    ENTITY_WHAT,
    GLOBAL_FRAMES,
    INPUT_SYSTEM,
    Base,
    ConditionError,
    Frame,
    Integer,
    NamedSelection,
    Number,
    Units,
    applied_bodies,
    selection_query,
)
from app.core.conditions.contacts import (
    CONTACT_LABELS,
    CONTACT_NOTES,
    Contact,
)
from app.core.conditions.loads import (
    AXIS_CHOICES,
    AXIS_LABELS,
    BODY_LOADS,
    CONSTRAINT_LABELS,
    CONSTRAINT_NOTES,
    DIRECTED_LOADS,
    HARMONIC_LOADS,
    IMPLIED_HOLDS,
    INITIAL_LABELS,
    INITIAL_NOTES,
    LOAD_DIMENSIONS,
    LOAD_LABELS,
    LOAD_NOTES,
    PSD_UNIT,
    UNTARGETED_LOADS,
    Constraint,
    Hold,
    Initial,
    Load,
    psd_grms,
)
from app.core.conditions.materials import (
    DENSITY_KEY,
    POISSON_KEY,
    STRUCTURAL_KEYS,
    Material,
    MaterialRef,
    body_density,
    converted_material,
    has_property,
    material_index,
    material_warnings,
    missing_structural,
    unmaterialed,
    with_material,
    with_scale,
)
from app.core.conditions.model import (
    CONSTRAINT_ACCEPTS,
    CONTACT_ACCEPTS,
    EMPTY,
    INITIAL_ACCEPTS,
    LOAD_ACCEPTS,
    MESH_ACCEPTS,
    Conditions,
    choice_value,
    expression_notes,
    parse,
    resolve,
    views,
    with_choice,
)
from app.core.conditions.spec import (
    spec,
)

__all__ = [
    "ALL_BODIES",
    "ANALYSIS_LABELS",
    "ANALYSIS_NOTES",
    "AXIS_CHOICES",
    "AXIS_LABELS",
    "BODY_LOADS",
    "CASE_FIELDS",
    "CONSTRAINT_ACCEPTS",
    "CONSTRAINT_LABELS",
    "CONSTRAINT_NOTES",
    "CONTACT_ACCEPTS",
    "CONTACT_LABELS",
    "CONTACT_NOTES",
    "DENSITY_KEY",
    "DIRECTED_LOADS",
    "EMPTY",
    "ENTITY_WHAT",
    "GLOBAL_FRAMES",
    "HARMONIC_LOADS",
    "IMPLIED_HOLDS",
    "INITIAL_ACCEPTS",
    "INITIAL_LABELS",
    "INITIAL_NOTES",
    "INPUT_SYSTEM",
    "LOAD_ACCEPTS",
    "LOAD_DIMENSIONS",
    "LOAD_LABELS",
    "LOAD_NOTES",
    "MESH_ACCEPTS",
    "MULTI_CASE_BLOCKED",
    "POISSON_KEY",
    "PSD_UNIT",
    "RIGID_CONSTRAINTS",
    "STRUCTURAL_KEYS",
    "UNTARGETED_LOADS",
    "Analysis",
    "Base",
    "BodyMesh",
    "BodySetting",
    "Case",
    "ConditionError",
    "Conditions",
    "Constraint",
    "Contact",
    "Frame",
    "Hold",
    "Initial",
    "Integer",
    "Load",
    "Material",
    "MaterialRef",
    "MeshHint",
    "NamedSelection",
    "Number",
    "Target",
    "Units",
    "applied_bodies",
    "body_density",
    "body_regions",
    "choice_value",
    "converted_material",
    "expression_notes",
    "has_global_mesh",
    "has_property",
    "has_shell",
    "material_index",
    "material_warnings",
    "mesh_skips",
    "missing_structural",
    "parse",
    "pretension_misses",
    "psd_grms",
    "raw_views",
    "resolve",
    "selection_query",
    "sheets_as_shell",
    "shell_parts",
    "shell_thicknesses",
    "spec",
    "unmaterialed",
    "views",
    "with_choice",
    "with_material",
    "with_scale",
]
