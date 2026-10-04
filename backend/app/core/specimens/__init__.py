"""시험 시편 — 규격 프리셋으로 시편 · 시험 지그 · 해석 조건을 그린다(ADR 0006).

공개 규격의 프리셋은 `data/*.json`, 사내 규격은 서버가 DB 에서 값으로 넘긴다 — 같은 모양
(`presets.Preset`)이고 같은 검사를 지난다. 시험 종류마다 모듈 하나(`bending` …).
"""

from __future__ import annotations

from typing import Any

from app.core.specimens import bending
from app.core.specimens.bending import SpecimenBuild
from app.core.specimens.presets import TESTS, Preset, builtin, find_builtin, parse_preset

__all__ = [
    "TESTS",
    "Preset",
    "SpecimenBuild",
    "build",
    "builtin",
    "find_builtin",
    "parse_preset",
]


def build(preset: Preset, **options: Any) -> SpecimenBuild:
    """프리셋의 시험 종류에 맞는 생성기로 — 치수(`length` · `width` · `thickness`)와
    `fixture` · `conditions` 를 받는다."""
    if preset.test == "bending":
        return bending.build(preset, **options)
    raise ValueError(f"아직 만들 수 없는 시험 종류입니다: {preset.test}")
