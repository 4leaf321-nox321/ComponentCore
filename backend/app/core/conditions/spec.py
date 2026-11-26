"""사양표 — 화면과 AI 가 같은 것을 본다.

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`)."""

from __future__ import annotations

from typing import Any

from app.core import units as unit_systems
from app.core.conditions.analysis import _ANALYSIS_INTRO, ANALYSIS_NOTES, Analysis
from app.core.conditions.bodies import BodyMesh, BodySetting, MeshHint
from app.core.conditions.common import INPUT_SYSTEM, Units
from app.core.conditions.contacts import CONTACT_NOTES, Contact
from app.core.conditions.loads import (
    CONSTRAINT_NOTES,
    IMPLIED_HOLDS,
    INITIAL_NOTES,
    LOAD_DIMENSIONS,
    LOAD_NOTES,
    Constraint,
    Initial,
    Load,
)
from app.core.conditions.model import (
    CONSTRAINT_ACCEPTS,
    CONTACT_ACCEPTS,
    INITIAL_ACCEPTS,
    LOAD_ACCEPTS,
    MESH_ACCEPTS,
)

# ── 사양표 — 화면과 AI 가 같은 것을 본다 ─────────────────────────────────────


def spec() -> dict[str, Any]:
    """조건마다 **어떤 칸이 있는가**. 화면은 이것으로 폼을 그리고, AI 는 이것을 읽고 쓴다.

    종류가 열 몇이고 칸이 제각각이다(고정 지지에는 값이 없고, 압력에는 크기와 방향이,
    볼트에는 N 또는 mm 가 있다). 화면에 `if` 를 늘어놓으면 종류를 더할 때마다 화면을 고쳐야
    한다 — CAD 리본이 `OP_SPECS` 로 푸는 것과 같은 방식이다. **정본은 이 서버**다.

    JSON Schema 를 그대로 주는 것은 Pydantic 이 이미 만든다(`model_json_schema`). 사람이
    읽을 이름과 묶음(어느 탭에 놓을 것인가)만 여기서 더한다.
    """
    groups: dict[str, Any] = {
        "constraints": {
            "label": "구속",
            "model": Constraint,
            "implied": IMPLIED_HOLDS,
            "notes": CONSTRAINT_NOTES,
            "accepts": CONSTRAINT_ACCEPTS,
        },
        "loads": {
            "label": "하중",
            "model": Load,
            "notes": LOAD_NOTES,
            "dimensions": LOAD_DIMENSIONS,
            "accepts": LOAD_ACCEPTS,
        },
        "contacts": {
            "label": "접촉",
            "model": Contact,
            "notes": CONTACT_NOTES,
            "accepts": CONTACT_ACCEPTS,
            "intro": "두 선택 그룹이 맞닿는 영역을 정의합니다. 접촉면과 대상면을 선택하고, "
            "접합 여부와 미끄러짐 여부를 접촉 종류로 지정합니다. 확실하지 않은 항목은 "
            "‘프로그램 제어’로 두십시오.",
        },
        "initial": {
            "label": "초기조건",
            "model": Initial,
            "notes": INITIAL_NOTES,
            "accepts": INITIAL_ACCEPTS,
            "intro": "해석 시작 시점의 상태를 정의합니다. 기준 온도, 초기 온도와 속도, "
            "선행 해석의 응력을 지정할 수 있습니다.",
        },
        "mesh_hints": {
            "label": "국부 메시",
            "model": MeshHint,
            "accepts": MESH_ACCEPTS,
            "intro": "면·엣지 선택 그룹의 요소를 더 작게 지정합니다(국부 세분화). ‘전체’에는 "
            "모델 전체의 값(기본 요소 크기, 요소 형상, 차수, 무시할 형상 크기, 경계층)을 "
            "지정합니다. 파트 하나 전체의 메시는 ‘파트별 설정’ 표에서 지정하십시오. 메시는 "
            "해석 플랫폼(SimEngBay)에서 생성하며, 여기에 입력하는 값은 권장 사항입니다.",
        },
    }
    out: dict[str, Any] = {
        "schema_version": 1,
        "units": Units().model_dump(),
        # 조건의 값을 적는 계 — 화면이 칸마다 단위(mm · N · MPa)를 붙인다. `units.system` 은
        # 내보내기 계다.
        "input_system": INPUT_SYSTEM,
        # **고를 수 있는 단위계.** 화면에 목록을 박으면 계를 더할 때마다 화면을 고쳐야
        # 한다 — 조건 종류와 같은 까닭으로 정본은 서버다.
        "unit_systems": [
            {"key": one.key, "label": one.label, **one.names}
            for one in unit_systems.SYSTEMS.values()
        ],
        # 해석 설정은 한 벌에 하나라 묶음(`groups`)이 아니지만, 화면은 같은 폼으로 그린다 —
        # 종류마다 한 줄 설명과 창 맨 위 안내를 함께 싣는다.
        "analysis": {
            **Analysis.model_json_schema(),
            "notes": ANALYSIS_NOTES,
            "intro": _ANALYSIS_INTRO,
        },
        "groups": {},
        # 파트별 설정 — 묶음처럼 「+ 추가」 하는 것이 아니라 파트마다 한 줄인 표다. 열 이름 ·
        # 선택지 · 설명을 여기서 준다(메시 열은 `mesh_fields`).
        "body_settings": {
            "label": "파트별 설정",
            "intro": "파트마다 물성, 거동, 표현, 해석 포함 여부와 메시를 한 표에서 "
            "지정합니다. 파트 메시는 국부 메시 ‘전체’보다 우선하고, 면·엣지 국부 메시가 "
            "파트 메시보다 우선합니다.",
            "fields": BodySetting.model_json_schema().get("properties", {}),
            "mesh_fields": BodyMesh.model_json_schema().get("properties", {}),
        },
    }
    for key, one in groups.items():
        model = one["model"]
        schema = model.model_json_schema()
        kinds = schema.get("properties", {}).get("type", {})
        out["groups"][key] = {
            "label": one["label"],
            # 이 묶음에 무엇을 더할 수 있나 — 화면의 「+ 조건」 목록이 이것이다.
            "types": kinds.get("enum", kinds.get("const", [])),
            "fields": schema.get("properties", {}),
            "required": schema.get("required", []),
            # 종류가 스스로 정하는 방향 — 화면이 잠긴 칸으로 보여 준다.
            "implied": one.get("implied", {}),
            # 종류마다 한 줄 설명, 그리고 크기의 차원(단위계 이름표의 열쇠 — 화면이 단위를
            # 붙인다).
            "notes": one.get("notes", {}),
            # 묶음 전체에 대한 한두 줄 — 창 맨 위에 보인다.
            "intro": one.get("intro", ""),
            "dimensions": one.get("dimensions", {}),
            # 종류마다 받는 선택 그룹 — `[{entity, kind?}]`. 없는 종류는 대상이 없다.
            "accepts": one.get("accepts", {}),
        }
    out["entities"] = ["face", "edge", "vertex", "body"]
    return out
