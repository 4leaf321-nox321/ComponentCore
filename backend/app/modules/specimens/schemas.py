from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class PresetOut(BaseModel):
    """시험 규격 프리셋 하나 — 공개 규격(`builtin`, 코드)과 사내 규격(`internal`, DB)이 같은
    모양이다. `preset` 은 `core.specimens.presets.Preset` 그대로(시편 치수 · 배치 규칙 · 해석
    기본값 · 출처 · 검토 여부)."""

    id: str
    origin: Literal["builtin", "internal"]
    test: str
    standard: str
    name: str
    preset: dict[str, Any]
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class PresetIn(BaseModel):
    """사내 규격 저장 — 프리셋 모양 그대로(`id` 는 서버가 정한다). 칸 검사는 코어가 한다."""

    preset: dict[str, Any]


class SpecimenRequest(BaseModel):
    preset_id: str = Field(min_length=1, max_length=64)
    length: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    thickness: float | None = Field(default=None, gt=0)
    """비우면 프리셋의 시편 치수."""
    dimensions: dict[str, Annotated[float, Field(gt=0)]] = Field(default_factory=dict)
    """그 밖의 시편 치수 — 프리셋 `specimen` 의 칸 이름 → 값(인장의 `gauge_width` ·
    `radius` …). 바꾼 치수도 프리셋과 같은 검사를 지난다."""
    fixture: bool = True
    """시험 지그를 함께 그린다 — 굽힘은 롤러 · 노즈, 인장 · 전단 · 이음은 그립이 무는 자리."""
    conditions: bool = True
    """해석 조건(구속 · 접촉 · 하중 · 해석 설정)을 붙인다 — 시험 지그가 있어야 한다."""


class SpecimenBuildOut(BaseModel):
    recipe: dict[str, Any]
    conditions: dict[str, Any] | None
    notes: list[str]
    values: dict[str, float] = Field(default_factory=dict)
    """레시피 변수를 푼 값 — 지지 간격 · 처짐 · 반지름을 화면이 식 없이 보인다."""


class SpecimenWorkRequest(SpecimenRequest):
    name: str | None = Field(default=None, max_length=120)
    """비우면 프리셋 이름."""
    folder: str = Field(default="", max_length=255)


class FacePickIn(BaseModel):
    """3D 에서 고른 면 — 누른 점, 그 자리의 법선, 면 종류(`plane` · `cylinder` …). 평면은
    「이 방향을 보는 면 중 이 점에서 가장 가까운 것」, 곡면은 「이 종류의 면 중 가장 가까운
    것」 으로 적힌다."""

    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    kind: str = Field(default="plane", min_length=1, max_length=20)


Picks = Annotated[list[FacePickIn], Field(max_length=20)]


class ProductTestRequest(BaseModel):
    """제품에 시험 규격을 건다 — 정하중 · 방향 하중 · 손잡이·벽걸이 · 압착 · 적층 압축 · 수압 ·
    비틀림 · 등가 가속도 · 진동 · 고유진동수. 제품 레시피는 그대로 쓰고 시험만 더한 새 작업."""

    preset_id: str = Field(min_length=1, max_length=64)
    source: str = Field(pattern=r"^(work|part):[0-9a-fA-F-]{36}$")
    """`work:<내 부품 작업 id>` 또는 `part:<공용 부품 id>`."""
    x: float | None = None
    y: float | None = None
    z: float | None = None
    """정하중을 누르는 자리 — 비우면 고른 점, 고른 면이 없으면 윗면 가운데(z 는 고른 면만)."""
    axis: Literal["x", "y", "z"] | None = None
    """진동 · 등가 가속도의 방향(비우면 Z) · 비틀림 축(비우면 가장 긴 축)."""
    faces: dict[Literal["support", "load", "twist"], Picks] = Field(default_factory=dict)
    """3D 에서 고른 자리 — support(고정 면) · load(하중 면 — 정하중 · 방향 하중 · 압착 · 수압)
    · twist(비트는 끝, 비틀림). 시험마다 고를 수 있는 자리가 다르다. 손잡이·벽걸이는 support,
    방향 하중은 load 가 꼭 있어야 한다."""
    mass: float | None = Field(default=None, gt=0)
    """제품 무게(kg) — 적층 압축."""
    direction: tuple[float, float, float] | None = None
    """방향 하중의 방향(힘의 방향 · 모멘트의 축) — 비우면 고른 평면에서 바깥으로(당김)."""
    name: str | None = Field(default=None, max_length=120)
    folder: str = Field(default="", max_length=255)


class ProductSourceRequest(BaseModel):
    """제품의 형상을 본다 — 「제품에 적용」 이 3D 에서 면을 고르게."""

    source: str = Field(pattern=r"^(work|part):[0-9a-fA-F-]{36}$")
