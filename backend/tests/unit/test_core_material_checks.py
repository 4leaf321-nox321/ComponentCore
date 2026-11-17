"""담아 둔 재료가 **조용히 틀리지 않는가**(2026-11-17).

- MatNexus 의 온도별 값은 켈빈(`temperature_k`)으로 온다 — 그것을 안 읽어 온도가 모두 빠졌다.
- 탄성계수가 빠졌거나 단위를 못 바꾼 재료는 고를 때만 말하고, 내보낼 때는 조용했다 — 이제
  점마다 경고(manifest `warnings`)로 적는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core import conditions

MATNEXUS = Path(__file__).parents[1] / "fixtures" / "matnexus"
KEYS = json.loads((MATNEXUS / "property_keys.json").read_text(encoding="utf-8"))


def _payload(code: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (MATNEXUS / f"{code}.json").read_text(encoding="utf-8")
    )["payload"]
    return payload


def test_실제_재료의_탄성계수_밀도가_계마다_맞는_단위로_나간다() -> None:
    """SECC(205 GPa) · Al5052(70.3 GPa) — MatNexus 2026-09-28 스냅샷 그대로."""
    for code, modulus, density in (("M-000138", 205e9, 7850.0), ("M-000158", 70.3e9, 2680.0)):
        for system, scale, rho in (("mm_n_tonne", 1e-6, 1e-12), ("si", 1.0, 1.0)):
            made = conditions.converted_material(_payload(code), system, KEYS)
            (E,) = [
                one
                for one in made["properties"]
                if one.get("key") == "mechanical.youngs_modulus"
            ]
            assert E["points"][0]["value"] == pytest.approx(modulus * scale), (code, system)
            assert E["unit"] == ("MPa" if system == "mm_n_tonne" else "Pa")
            assert made["density"] == pytest.approx(density * rho)
            assert "missing_structural" not in made and "unconverted" not in made


def test_온도별_값은_켈빈을_섭씨로_읽는다() -> None:
    made = conditions.converted_material(
        {
            "declared_properties": [
                {
                    "item": "탄성계수",
                    "si_unit": "Pa",
                    "points": [
                        {"temperature_k": 296.15, "value_si": 2.05e11},
                        {"temperature_k": 358.15, "value_si": 1.95e11},
                        {"temperature_k": None, "value_si": 2.0e11},
                    ],
                }
            ]
        },
        "mm_n_tonne",
        KEYS,
    )
    points = made["properties"][0]["points"]
    assert [one["temperature_C"] for one in points] == [
        pytest.approx(23.0),
        pytest.approx(85.0),
        None,
    ]
    assert [one["value"] for one in points] == [
        pytest.approx(205000),
        pytest.approx(195000),
        pytest.approx(200000),
    ]
    # 섭씨로 준 것은 그대로.
    again = conditions.converted_material(
        {
            "declared_properties": [
                {
                    "item": "탄성계수",
                    "si_unit": "Pa",
                    "points": [{"temperature_C": 20, "value_si": 7e10}],
                }
            ]
        },
        "si",
        KEYS,
    )
    assert again["properties"][0]["points"][0]["temperature_C"] == 20


def _resolved(
    payload: dict[str, Any], analysis: str = "static", apply_to: list[str] | None = None
) -> dict[str, Any]:
    raw = {
        "materials": [
            {
                "apply_to": ["전체"] if apply_to is None else apply_to,
                "ref": {"source": "matnexus", "name": "시험재"},
                "payload": payload,
            }
        ],
        "analysis": {"type": analysis},
    }
    return conditions.resolve(raw, {}, KEYS)


def test_탄성계수가_빠진_재료는_내보낼_때도_경고한다() -> None:
    no_modulus = {
        "density": 2700.0,
        "density_unit": "kg/m3",
        "poisson_ratio": 0.33,
        "declared_properties": [
            {"item": "비열", "si_unit": "J/(kg.K)", "points": [{"value_si": 900.0}]}
        ],
    }
    assert conditions.material_warnings(_resolved(no_modulus)) == [
        "재료 ‘시험재’: 탄성계수 없음 — 구조 해석에 필요합니다"
    ]
    # 열 해석은 탄성계수가 필요 없다 · 파트에 안 붙은 재료는 쓰이지 않는다.
    assert conditions.material_warnings(_resolved(no_modulus, "thermal")) == []
    assert conditions.material_warnings(_resolved(no_modulus, apply_to=[])) == []
    # 다 있는 실제 재료는 조용하다.
    assert conditions.material_warnings(_resolved(_payload("M-000138"))) == []


def test_단위를_못_바꾼_물성도_경고한다() -> None:
    odd = {
        **_payload("M-000158"),
        "declared_properties": [
            *_payload("M-000158")["declared_properties"],
            {"item": "열전도율", "si_unit": "BTU/(h.ft.F)", "points": [{"value_si": 80.0}]},
        ],
    }
    (warning,) = conditions.material_warnings(_resolved(odd))
    assert warning == "재료 ‘시험재’: 단위를 바꾸지 못한 물성 열전도율(BTU/(h.ft.F))"


def test_환경_온도는_하나_물성의_온도별_값을_고르는_기준이다() -> None:
    """받는 쪽(SimEngBay)은 온도별 물성에서 환경 온도(없으면 22 °C)에 가장 가까운 점 하나를
    쓴다 — 둘이면 어느 것을 기준으로 할지 모른다."""
    one = {"type": "environment_temperature", "value": 85}
    conditions.parse({"initial": [one]})
    with pytest.raises(conditions.ConditionError, match="환경 온도가 2개"):
        conditions.parse({"initial": [one, {**one, "value": 22}]})
    # 설계점마다 바꿀 수 있다 — 식으로 적으면 풀린 값이 그 점의 기준 온도.
    resolved = conditions.resolve(
        {"initial": [{**one, "value": "=시험_온도"}]}, {"시험_온도": 60.0}
    )
    assert resolved["initial"][0]["value"] == 60.0
    assert "가장 가까운 값" in conditions.INITIAL_NOTES["environment_temperature"]


def test_초기_온도는_열_해석에서만_구조_해석은_받는_쪽이_거절한다() -> None:
    """구조 해석에 건 바디 온도는 열 하중인데, 받는 쪽은 열팽창을 넣지 않아 아직 거절한다
    (SimEngBay, 2026-11-18) — 보내고 나서가 아니라 저장할 때 말한다."""
    body = {
        "named_selections": [{"name": "몸", "entity": "body", "select": {"what": "bodies"}}],
        "initial": [{"type": "temperature", "on": "몸", "value": 80}],
    }
    for kind in ("static", "modal"):
        with pytest.raises(conditions.ConditionError, match=r"열 해석에서만.*환경 온도"):
            conditions.parse({**body, "analysis": {"type": kind}})
    conditions.parse({**body, "analysis": {"type": "thermal"}})
