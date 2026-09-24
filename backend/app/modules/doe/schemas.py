from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FactorIn(BaseModel):
    """인자 하나 — 고정이거나, 구간이거나, 값 목록."""

    name: str = Field(min_length=1, max_length=40)
    mode: str = "fixed"
    value: float | None = None
    start: float | None = None
    end: float | None = None
    steps: int = 5
    values: list[float] = Field(default_factory=list)
    resolution: float | None = Field(default=None, gt=0)
    """값을 맞추는 가공 단위(mm). 없으면 0.1 — 0.333 같은 치수는 가공할 수 없다."""


class PreviewRequest(BaseModel):
    factors: list[FactorIn]
    method: str = "factorial"
    samples: int = Field(default=20, ge=1)
    """LHS 표본 수. 상한은 서버 설정(관리자가 바꾼다) — 서비스가 본다."""
    seed: int = 1


class StudyCreateRequest(PreviewRequest):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    recipe: dict[str, Any]
    conditions: dict[str, Any] = Field(default_factory=dict)
    """해석 조건 한 벌 — 대상 버전의 것을 그대로 넘기면 스냅샷으로 박힌다.
    비면 형상만 훑는다."""
    work_id: uuid.UUID | None = None
    on_behalf_of: str = Field(default="", max_length=200)
    """**누구를 위해 만드나** — 계정(이메일) 또는 사용자 id. 기계(오케스트레이터)가 쓴다.

    이것을 주면 그 DOE 의 **소유자는 그 사람**이 되고, 부른 쪽(서비스 계정)은 「누가 돌렸나」
    칸에 남는다. 안 그러면 기계가 만든 DOE 가 서비스 계정 것으로만 남아 정작 사람이 제
    활동에서 못 찾는다.

    **남의 이름을 빌리는 일이라** 토큰에 `act_for_others` 범위가 있어야 한다."""
    idempotency_key: str = Field(default="", max_length=200)
    """**두 번 불러도 한 벌.** 같은 열쇠로 다시 부르면 이미 만든 것을 돌려준다(201 대신 200).

    기계는 재시도한다 — 망이 끊겨 답을 못 받았을 뿐인데 다시 걸면 스터디 둘 · 폴더 둘이
    생기고, 해석 쪽은 어느 것이 진짜인지 모른다. 사람은 비워 두면 된다(같은 설정으로 한 벌
    더 만드는 것은 정상이다)."""


class PointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    params: dict[str, Any]
    status: str
    error: str
    interference: dict[str, Any] | None = None
    """조립이면 구성품끼리 겹침 보고(ok · items · total_volume). 구성품이 하나면 None."""
    step_file: str
    point_file: str = ""
    """이 점의 모든 것(변수 · 영역 · 풀린 조건). 해석이 물을 유일한 창구다."""


class StudySummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    work_id: uuid.UUID | None
    work_name: str | None
    work_kind: str | None
    """대상 — 어느 도면(부품 · 지그 · 조립)을 훑는가. 지워졌으면 None(스냅샷은 남는다)."""
    method: str
    samples: int
    seed: int
    point_count: int
    created_at: datetime
    owner_name: str = ""
    """이 DOE 가 **누구 것인가.** 대행이면 대행 대상인 사람이다 — `scope=all` 로 찾으면 남의
    것이 섞이므로 목록에도 있어야 한다."""
    visibility: str = "read"
    """`read`(기본) · `private`. **읽기는 모두에게**가 기본이고 감추는 것이 예외다.
    쓰는 일(보내기 · 지우기 · 영구보관)은 공개와 무관하게 소유자와 관리자만."""


class StudyOut(StudySummaryOut):
    recipe: dict[str, Any]
    conditions: dict[str, Any] = Field(default_factory=dict)
    """이 스터디가 돌던 때의 해석 조건 — 작업이 나중에 바뀌어도 여기 남는다."""
    factors: list[dict[str, Any]]
    requested_by_name: str = ""
    """**누가 실제로 돌렸나** — 대행일 때만 찬다(오케스트레이터의 서비스 계정)."""
    keep_forever: bool = False
    """영구보관 — 보관 기한이 지나도 공유 폴더를 남긴다."""
    released_at: datetime | None = None
    """해석이 「다 읽었다」 고 알린 때 — 알린 폴더는 먼저 치워진다."""
    local_ready: bool = True
    """서버 보관 폴더에 설계점 파일이 **아직 있나.** 보관 기한이 지나 치워졌으면 False 다 —
    그때 화면은 「다시 만들기」 를 권하고, 내려받기 · 「보내기」 는 막힌다.

    DB 칸이 아니라 **폴더를 보고 그때그때 답한다**(`services.local_ready`). 두 곳에 적으면
    청소 · 백업 복원 · 사람 손에 어긋나는 날이 온다."""
    export_dir_windows: str
    """공유 폴더 경로(F:\\…). 아직 안 보냈으면 빈 문자열."""
    exported_at: datetime | None
    """화면 · 해석 쪽이 여는 경로(F:\\…). 서버가 보는 경로는 안 내보낸다."""
    job: dict[str, Any] | None = None
    points: list[PointOut] = Field(default_factory=list)
    done: int = 0
    failed: int = 0
