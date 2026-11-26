"""접촉 — 종류 · 라벨 · 안내 · 모델과 그 점검.

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from app.core.conditions.common import Base, ConditionError, Number, _extra

CONTACT_LABELS: dict[str, str] = {
    "bonded": "본딩(접합)",
    "no_separation": "분리 없음",
    "frictional": "마찰",
    "frictionless": "마찰 없음",
    "rough": "거친 접촉",
}

CONTACT_NOTES: dict[str, str] = {
    "bonded": "두 면이 접합되어 하나의 물체처럼 거동합니다. 미끄러지거나 분리되지 "
    "않습니다(선형). 볼트, 용접, 접착을 단순화할 때 사용합니다.",
    "no_separation": "분리되지 않으며, 면을 따라 약간 미끄러질 수 있습니다"
    "(마찰 없음, 선형에 가까움).",
    "frictional": "압축 시 마찰계수만큼 저항하다가 미끄러지며, 분리될 수도 있습니다"
    "(비선형). 실제 접촉에 가장 가깝습니다.",
    "frictionless": "마찰 없이 미끄러지며, 분리될 수도 있습니다(비선형).",
    "rough": "미끄러지지 않지만 분리될 수는 있습니다(마찰 무한대, 비선형).",
}

#: 틈 · 겹침을 다루는 방법 — 떨어질 수 있는(비선형) 접촉만 쓴다.
_NONLINEAR_CONTACTS = ["no_separation", "frictional", "frictionless", "rough"]


class Contact(Base):
    """접촉 — 두 선택 그룹이 만나는 자리. 접촉면(`source`)이 대상면(`target`)을 검사한다."""

    name: str = Field(min_length=1, max_length=60)
    type: Literal["bonded", "no_separation", "frictional", "frictionless", "rough"] = Field(
        json_schema_extra=_extra({"labels": CONTACT_LABELS})
    )
    source: str = Field(
        title="접촉면(contact)",
        description="일반적으로 더 작거나, 볼록하거나, 연한 쪽 면입니다.",
    )
    target: str = Field(
        title="대상면(target)",
        description="일반적으로 더 크거나, 오목하거나, 단단한 쪽 면입니다.",
    )
    friction: Number | None = Field(
        None,
        title="마찰계수",
        description="0~1 범위입니다. 강재 간 건조 접촉은 약 0.15~0.2입니다.",
        json_schema_extra=_extra({"only_for": ["frictional"]}),
    )
    formulation: Literal[
        "program_controlled", "pure_penalty", "augmented_lagrange", "normal_lagrange", "mpc"
    ] = Field(
        "program_controlled",
        title="정식화",
        description="확실하지 않으면 ‘프로그램 제어’를 선택하십시오. MPC는 본딩과 분리 없음 "
        "접촉에만 사용합니다.",
        json_schema_extra=_extra(
            {
                "labels": {
                    "program_controlled": "프로그램 제어",
                    "pure_penalty": "페널티",
                    "augmented_lagrange": "증강 라그랑주",
                    "normal_lagrange": "라그랑주(법선)",
                    "mpc": "MPC(구속식)",
                }
            }
        ),
    )
    behavior: Literal["program_controlled", "symmetric", "asymmetric", "auto_asymmetric"] = (
        Field(
            "program_controlled",
            title="검사 방향",
            description="대칭: 두 면이 서로를 검사합니다. 비대칭: 접촉면만 대상면을 "
            "검사합니다.",
            json_schema_extra=_extra(
                {
                    "labels": {
                        "program_controlled": "프로그램 제어",
                        "symmetric": "대칭",
                        "asymmetric": "비대칭",
                        "auto_asymmetric": "자동 비대칭",
                    }
                }
            ),
        )
    )
    pinball: Number | None = Field(
        None,
        title="pinball 반경",
        description="이 거리 안에 있는 면만 접촉으로 판정합니다. 비워 두면 프로그램이 "
        "결정합니다. 간극이 있는 본딩 접촉에서는 간극보다 크게 지정하십시오.",
        json_schema_extra=_extra({"unit": "mm"}),
    )
    interface_treatment: Literal[
        "add_offset_ramped", "add_offset_no_ramp", "adjust_to_touch"
    ] = Field(
        "add_offset_ramped",
        title="초기 간극·겹침",
        description="형상에 작은 간극이나 겹침이 있을 때의 처리 방법입니다. ‘접촉 상태로 "
        "조정’은 간극과 겹침을 제거한 상태로 시작합니다.",
        json_schema_extra=_extra(
            {
                "only_for": _NONLINEAR_CONTACTS,
                "labels": {
                    "add_offset_ramped": "형상 유지(점진 적용)",
                    "add_offset_no_ramp": "형상 유지(즉시 적용)",
                    "adjust_to_touch": "접촉 상태로 조정",
                },
            }
        ),
    )

    @field_validator("formulation", "behavior", "interface_treatment", mode="before")
    @classmethod
    def _blank(cls, value: Any, info: Any) -> Any:
        """예전에 비워 둔 칸(`""`)은 기본값으로 — 고를 것을 정한 뒤로 빈 글자는 뜻이 없다."""
        if value in ("", None):
            return cls.model_fields[info.field_name].default
        return value


def _check_contact(where: str, contact: Contact) -> None:
    """접촉 하나 — 종류에 빠진 값 · 맞지 않는 선택을 **저장할 때** 말한다."""
    label = f"{CONTACT_LABELS[contact.type]} 접촉 ‘{contact.name}’"
    if contact.type == "frictional" and contact.friction is None:
        raise ConditionError(f"{where}: {label}에 마찰계수가 없습니다.")
    if contact.formulation == "mpc" and contact.type not in ("bonded", "no_separation"):
        raise ConditionError(
            f"{where}: {label}에는 MPC 정식화를 사용할 수 없습니다. MPC는 본딩과 분리 없음 "
            "접촉에만 사용합니다."
        )
    if contact.source and contact.source == contact.target:
        raise ConditionError(f"{where}: {label}의 접촉면과 대상면이 같습니다.")
