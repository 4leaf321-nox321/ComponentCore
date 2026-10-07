from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core import fasteners
from app.modules.jobs.schemas import JobOut


class PartVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    part_id: uuid.UUID
    number: int
    recipe: dict[str, Any]
    conditions: dict[str, Any] = Field(default_factory=dict)
    """해석 조건 — 등록할 때 작업에서 함께 올렸으면 있다. 「내 작업으로 복사」 가 옮긴다."""
    job: JobOut | None
    note: str
    promoted_by_id: uuid.UUID | None
    promoted_by_name: str | None
    work_version_id: uuid.UUID | None
    created_at: datetime


class PartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    tags: list[str] = Field(default_factory=list)
    """꼬리표 — 승격이 내 작업의 것을 물려받는다. 목록에서 이것으로 거른다(`?tag=`)."""
    description: str
    owner_id: uuid.UUID
    owner_name: str
    work_id: uuid.UUID | None
    current_version: int
    version_count: int
    current: PartVersionOut | None
    jig_count: int
    """이 부품을 잡는 지그(카탈로그) 수."""
    folder: str = ""
    standard: dict[str, Any] | None = None
    """규격 사양 — 관리자가 붙였으면(`StandardSpec`). 비면 일반 부품."""
    created_at: datetime
    updated_at: datetime


class PartSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    tags: list[str] = Field(default_factory=list)
    """꼬리표 — **목록에도 보여야 한다.** 거르개로 쓰는 자리가 목록이다."""
    description: str
    owner_id: uuid.UUID
    """누가 올렸나 — 화면이 「옮길 수 있나」 를 미리 가린다(판정은 서버)."""
    owner_name: str
    current_version: int
    jig_count: int
    folder: str = ""
    """놓인 폴더 — `고객A/2026`, 빈 것이 맨 위."""
    standard: dict[str, Any] | None = None
    """규격 사양 — 관리자가 붙였으면(`StandardSpec`). 비면 일반 부품."""
    shape: dict[str, Any] | None = None
    """최신 버전의 형상 색인(`core/shape_index.py`) — 크기 · 세 변 · 부피 · 구멍 · 쓴 연산 ·
    나사 · 변수. 색인이 없으면(이 기능 전의 버전) 비어 있다."""
    updated_at: datetime


#: 종류마다 꼭 있어야 하는 칸 — 생성기가 고르고 놓는 데 쓴다(`core.standard`).
STANDARD_FIELDS: dict[str, tuple[str, ...]] = {
    "support": ("top_diameter", "height"),
    "pin": ("diameter", "length"),
    "clamp": ("reach", "pad_height", "pad_diameter", "base_length", "base_width"),
}
#: 변수로 움직이는 치수 — (변수 이름 칸, 최소, 최대).
STANDARD_RANGES: dict[str, tuple[str, str, str]] = {
    "support": ("height_param", "height_min", "height_max"),
    "pin": ("length_param", "length_min", "length_max"),
}


class StandardSpec(BaseModel):
    """**규격 사양** — 관리자가 공용 부품에 붙인다. 종류마다 쓰는 칸이 다르다.

    형상의 기준: 받침 · 핀은 바닥 중심이 원점이고 위가 +Z, 토글 클램프는 베이스 바닥 중심이
    원점이고 팔이 +X 로 뻗어 누른 상태의 패드 중심이 (reach, 0, pad_height). 형상은 레시피로만
    그린다(공급사 STEP 은 받아서 다시 그린다)."""

    kind: Literal["support", "pin", "clamp"]
    part_no: str = Field(min_length=1, max_length=80)
    """품번 — 부품표에 이대로 나간다."""
    maker: str = Field(default="", max_length=80)
    version: int = Field(ge=1)
    """쓰는 버전(사내에서 그린 것). 새 버전을 올려도 이것을 바꾸기 전까지는 그대로다."""
    preference: int = Field(default=100, ge=0, le=1000)
    """작을수록 먼저 — 같은 요구를 만족하면 앞의 것을 고른다."""
    top_diameter: float | None = Field(default=None, gt=0)
    """받침: 제품 바닥에 닿는 윗면 지름."""
    height: float | None = Field(default=None, gt=0)
    """받침: 그린 그대로의 높이."""
    height_param: str | None = Field(default=None, max_length=60)
    height_min: float | None = Field(default=None, gt=0)
    height_max: float | None = Field(default=None, gt=0)
    diameter: float | None = Field(default=None, gt=0)
    """핀: 구멍에 들어가는 지름."""
    length: float | None = Field(default=None, gt=0)
    """핀: 그린 그대로 판 위로 선 길이."""
    length_param: str | None = Field(default=None, max_length=60)
    length_min: float | None = Field(default=None, gt=0)
    length_max: float | None = Field(default=None, gt=0)
    reach: float | None = Field(default=None, gt=0)
    """클램프: 베이스 중심에서 패드 중심까지 수평 거리."""
    pad_height: float | None = Field(default=None, gt=0)
    """클램프: 누른 상태에서 패드가 닿는 높이(베이스 바닥에서)."""
    pad_diameter: float | None = Field(default=None, gt=0)
    base_length: float | None = Field(default=None, gt=0)
    base_width: float | None = Field(default=None, gt=0)
    mount_thread: str | None = Field(default=None, max_length=10)
    """클램프: 베이스를 판에 고정하는 나사(M1.6 ~ M24) — 생성기가 판에 그 탭 구멍을 낸다."""
    mount_holes: list[tuple[float, float]] | None = Field(default=None, max_length=12)
    """클램프: 고정 구멍 자리 (x, y) — 클램프 좌표(베이스 바닥 중심이 원점, 팔이 +X)."""

    @model_validator(mode="after")
    def _filled(self) -> StandardSpec:
        missing = [name for name in STANDARD_FIELDS[self.kind] if getattr(self, name) is None]
        if missing:
            raise ValueError(f"{self.kind}에 필요한 칸이 비었습니다: {', '.join(missing)}")
        span = STANDARD_RANGES.get(self.kind)
        if span is not None and getattr(self, span[0]):
            low, high = getattr(self, span[1]), getattr(self, span[2])
            if low is None or high is None or low >= high:
                raise ValueError(f"{span[0]}를 주면 {span[1]} < {span[2]} 범위가 필요합니다.")
        if self.kind == "clamp":
            self._check_mount()
        return self

    def _check_mount(self) -> None:
        """고정 나사와 구멍 자리 — 둘 다 비거나 둘 다 있고, 구멍은 베이스 안에 든다. 비어도
        된다(그 클램프를 고르면 판에 탭 구멍을 못 냈다고 생성기가 말한다)."""
        if not self.mount_thread and not self.mount_holes:
            return
        if not self.mount_thread or not self.mount_holes:
            raise ValueError("고정 나사와 고정 구멍 자리는 함께 적어야 합니다.")
        if self.mount_thread not in fasteners.THREADS:
            raise ValueError(
                f"mount_thread: 지원하지 않는 나사입니다: {self.mount_thread} (M1.6 ~ M24)."
            )
        length, width = float(self.base_length or 0), float(self.base_width or 0)
        outside = [
            f"({x:g}, {y:g})"
            for x, y in self.mount_holes
            if abs(x) > length / 2 or abs(y) > width / 2
        ]
        if outside:
            raise ValueError(
                f"고정 구멍 자리가 베이스({length:g} x {width:g}) 밖입니다: "
                + ", ".join(outside)
            )

    def stored(self) -> dict[str, Any]:
        """저장할 모양 — 이 종류가 쓰는 칸만."""
        keep = {
            "kind",
            "part_no",
            "maker",
            "version",
            "preference",
            *STANDARD_FIELDS[self.kind],
        }
        span = STANDARD_RANGES.get(self.kind)
        if span is not None and getattr(self, span[0]):
            keep.update(span)
        if self.kind == "clamp" and self.mount_thread:
            keep.update(("mount_thread", "mount_holes"))
        # json 모양으로 — 구멍 자리가 튜플이 아니라 목록이어야 DB 에서 읽은 것과 같다
        # (가져오기의 「같음」 비교).
        dumped = self.model_dump(mode="json")
        return {key: value for key, value in dumped.items() if key in keep}


#: 규격 부품 **묶음 파일**의 형식 — 개발 PC 에서 그린 규격품을 운영 서버로 옮긴다.
BUNDLE_FORMAT: Final = "compcore.standard-parts"
#: 이 서버가 읽는 가장 높은 판. 판을 올리면 가져오기가 옛 판을 읽는 길을 남긴다.
BUNDLE_VERSION = 1


class StandardExportRequest(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    """내보낼 규격 부품 — 비우면 규격 부품 전부."""


class StandardBundleItem(BaseModel):
    """묶음의 규격 부품 하나 — 카탈로그 정보 · 사양 · 쓰는 버전의 레시피."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    folder: str = Field(default="", max_length=255)
    standard: dict[str, Any]
    """`StandardSpec` 에서 `version` 을 뺀 것 — 버전은 가져오는 서버에서 정해진다. 칸은 가져올
    때 항목마다 본다(하나가 틀려도 나머지는 가져온다)."""
    recipe: dict[str, Any]
    origin: dict[str, Any] = Field(default_factory=dict)
    """내보낸 서버의 부품 id · 버전 — 가져온 버전의 메모에 남는다."""


class StandardBundle(BaseModel):
    """규격 부품 묶음 — JSON 파일 하나. 형상이 레시피뿐이라(STEP · 다른 도면을 가리키지
    않는다) 따라가야 할 파일이 없다."""

    format: Literal["compcore.standard-parts"]
    format_version: int = Field(ge=1)
    exported_at: datetime
    exported_from: str = Field(default="", max_length=300)
    """내보낸 서버 — 앱 이름 · 버전 · 주소."""
    items: list[StandardBundleItem] = Field(max_length=500)


class StandardImportItemOut(BaseModel):
    part_no: str
    name: str
    kind: str
    action: Literal["create", "version", "spec", "same", "skip"]
    """`create` 새 부품 · `version` 형상이 달라 새 버전 · `spec` 사양만 고침 · `same` 같아서
    그대로 · `skip` 문제가 있어 건너뜀(`problems`)."""
    part_id: uuid.UUID | None = None
    """이 서버의 부품 — 새로 만들 것이면 미리 보기에서는 비어 있다."""
    version: int | None = None
    """가져온 뒤 사양이 쓰는 버전."""
    problems: list[str] = Field(default_factory=list)


class StandardImportOut(BaseModel):
    dry_run: bool
    """미리 보기였나 — 그러면 아무것도 바꾸지 않았다."""
    items: list[StandardImportItemOut]


class PartUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    folder: str | None = Field(default=None, max_length=255)
    """옮길 폴더 — 빈 문자열이면 맨 위로."""


class CopyToWorkRequest(BaseModel):
    """부품(버전)의 레시피로 내 작업을 새로 만든다 — 「내 공간으로 복사」."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    number: int | None = None
    """비우면 현재 버전."""
    conditions: bool = True
    """그 버전의 해석 조건도 새 작업에 옮긴다(기본). 같은 형상이라 선택 그룹이 그대로
    맞는다."""
