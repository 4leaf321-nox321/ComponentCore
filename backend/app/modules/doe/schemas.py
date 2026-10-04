from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FactorIn(BaseModel):
    """인자 하나 — 치수(고정 · 구간 · 값 목록)이거나, 치수가 아닌 셋 중 하나.

    - `material`: `bodies` 에 붙일 재료를 `values`(해석 조건에 담아 둔 재료의 이름 · 번호)
      중에서 설계점마다 하나씩.
    - `choice`: 조건의 고르는 칸 하나(`target` = `{group, item, field}` — 예
      `{"group": "contacts", "item": "블록-판", "field": "type"}`)를 `values` 중에서.
    - `scale`: `bodies` 에 붙은 재료의 물성 `property`(「탄성계수」 · 표준 열쇠 · 밀도 ·
      푸아송비)에 곱할 배율 `values`. 원본은 그대로, 옮긴 값에만 곱한다.

    셋 다 형상은 그대로다(한 벌을 나눠 쓴다)."""

    name: str = Field(min_length=1, max_length=40)
    mode: str = "fixed"
    value: float | None = None
    start: float | None = None
    end: float | None = None
    steps: int = 5
    values: list[float | str | bool | None] = Field(default_factory=list)
    bodies: list[str] = Field(default_factory=list)
    """재료 · 배율 인자 — 그 바디(단품이면 `["전체"]`)."""
    target: dict[str, Any] | None = None
    """고르기 인자 — `{group, item, field}`. item 은 이름(초기조건은 종류, 메시 힌트는 대상)
    또는 1 부터의 번호. 해석 설정(`analysis`)은 item 이 없다."""
    property: str | None = None
    """배율 인자 — 곱할 물성."""
    resolution: float | None = Field(default=None, gt=0)
    """값을 맞추는 가공 단위(mm). 없으면 0.1 — 0.333 같은 치수는 가공할 수 없다."""


class PreviewRequest(BaseModel):
    factors: list[FactorIn] = Field(default_factory=list)
    method: str = "factorial"
    """`factorial`(격자) · `lhs` · `table`(직접 준 표 — `table`) · `oat`(하나씩 바꾸기) ·
    `ccd`(중심 합성, 면 중심) · `bbd`(Box-Behnken, 변수 셋 이상) · `sobol`(Sobol 수열 —
    `samples` · `seed`, 점을 더하면 이어 뽑는다)."""
    samples: int = Field(default=20, ge=1)
    """LHS 표본 수. 상한은 서버 설정(관리자가 바꾼다) — 서비스가 본다."""
    seed: int = 1
    constraints: list[str] = Field(default_factory=list, max_length=20)
    """변수끼리의 조건 — `간격 > 2 * 지름`, `4 <= 두께 <= 0.5 * 높이`. 어긴 조합은 **만들기
    전에** 거른다(격자는 빼고, LHS 는 표본 수가 찰 때까지 더 뽑는다). 도면의 다른 치수(식으로
    정해진 것까지)도 부를 수 있다."""
    recipe: dict[str, Any] | None = None
    """미리보기에서 제약식을 풀 도면 — 식이 인자 아닌 치수를 부를 때 필요하다."""
    table: list[dict[str, Any]] | None = None
    """`method="table"` 일 때의 설계점 — 줄마다 `{변수: 값}`. 엑셀로 짠 표나 해석 쪽 최적화기가
    고른 점을 **그대로** 만든다(가공 단위로 맞추지 않고, 겹친 줄도 둔다 — 번호가 표의 줄과
    같다). 표에만 있는 변수는 인자로 더해진다. 제약을 어긴 줄이 있으면 만들지 않는다."""
    measures: list[dict[str, Any]] | None = None
    """점마다 잴 값 — 표에 열로 붙는다.

    - `{"name": "부피", "kind": "volume"}` · `area` · `{"kind": "size", "axis": "z"}` — `body`
      를 주면 그 바디만.
    - `{"kind": "region_area", "region": "고정면"}` — 선택 그룹의 넓이.
    - `{"kind": "distance", "a": "구멍1", "b": "구멍2"}` — 두 선택 그룹 사이 거리.
    - `{"kind": "expr", "expr": "부피 * 7.85e-6"}` — 도면 변수와 앞의 측정값을 부른다."""
    checks: dict[str, Any] | None = None
    """형상 점검 기준(mm) — `{"min_wall": 0.5, "short_edge": 0.1, "narrow_face": 0.1}` 에서
    바꿀 것만. `{"enabled": false}` 면 재지 않는다. 기준보다 작은 것은 표의 `warnings` 로."""


class ProbeRequest(PreviewRequest):
    """「미리 만들어 보기」 — 만들 때와 같은 도면 · 인자 · 제약 · 조건으로 끝 점 몇 개만."""

    recipe: dict[str, Any]
    conditions: dict[str, Any] | None = None
    """안 주면 `work_id` 작업의 현재 조건(만들 때와 같다) — 영역이 따라가는지 보려면 있어야
    한다."""
    work_id: uuid.UUID | None = None


class ExtendRequest(BaseModel):
    """이미 만든 DOE 에 **점을 더한다** — 번호를 이어서, 같은 폴더에."""

    method: str = "lhs"
    samples: int = Field(default=10, ge=1)
    seed: int | None = None
    """안 주면 묶음마다 다르게(스터디 시드 + 묶음 수) — 같은 시드면 첫 묶음과 같은 점이
    나온다."""
    factors: list[FactorIn] = Field(default_factory=list)
    """**바꿀 변수만** — 범위를 좁히거나 단계를 바꾼다. 없는 변수를 더할 수는 없다(새 DOE)."""
    table: list[dict[str, Any]] | None = None
    """`method="table"` 의 설계점 — 해석 쪽 최적화기가 고른 다음 점들."""
    idempotency_key: str = Field(default="", max_length=200)
    """같은 열쇠의 묶음이 이미 있으면 더하지 않고 그것을 돌려준다(기계의 재시도)."""


class CloneRequest(BaseModel):
    """**내 것으로 복제** — 원본은 그대로, 같은 설계점 · 조건으로 내 소유의 새 DOE."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    """비우면 「원본 이름 (복제)」."""


class StudyCreateRequest(PreviewRequest):
    name: str = Field(min_length=1, max_length=120)
    outputs: list[Literal["midsurface"]] = Field(default_factory=list)
    """설계점마다 **더 내보낼 것** — `midsurface`: 두께가 한결같은 판이면 중간면 STEP
    (`<형상>_mid.step`, 셸 요소 해석용). 판이 아닌 점은 실패가 아니라 `warnings` 에 적힌다."""
    description: str = Field(default="", max_length=2000)
    recipe: dict[str, Any]
    conditions: dict[str, Any] | None = None
    """해석 조건 한 벌 — 스냅샷으로 박힌다. **안 주면 `work_id` 작업의 현재 버전 조건**을
    쓴다(화면 · MCP 가 따로 챙기지 않아도 저장된 조건이 따라간다). 조건 없이 형상만 훑으려면
    빈 한 벌(`{}`)."""
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
    quality: dict[str, Any] | None = None
    """형상 점검 — 최소 벽 두께 · 짧은 모서리 · 좁은 면 · 바디 수와 `warnings` · `notes`."""
    measures: dict[str, float | None] | None = None
    """측정값 — 스터디의 `measures` 정의대로. 못 잰 것은 None."""


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
    owner_id: uuid.UUID | None = None
    """소유자 — 화면이 고치는 단추(보내기 · 점 더하기 …)를 소유자에게만 보이는 데 쓴다."""
    owner_name: str = ""
    """이 DOE 가 **누구 것인가.** 대행이면 대행 대상인 사람이다 — `scope=all` 로 찾으면 남의
    것이 섞이므로 목록에도 있어야 한다."""
    visibility: str = "read"
    """`read`(기본) · `private`. **읽기는 모두에게**가 기본이고 감추는 것이 예외다.
    쓰는 일(보내기 · 지우기 · 영구보관)은 공개와 무관하게 소유자와 관리자만."""


class StudyOut(StudySummaryOut):
    cloned_from_id: uuid.UUID | None = None
    """「내 것으로 복제」 의 원본 DOE. 지워졌으면 None."""
    cloned_from_name: str = ""
    recipe: dict[str, Any]
    conditions: dict[str, Any] = Field(default_factory=dict)
    """이 스터디가 돌던 때의 해석 조건 — 작업이 나중에 바뀌어도 여기 남는다."""
    factors: list[dict[str, Any]]
    constraints: list[str] = Field(default_factory=list)
    """만들기 전에 거른 제약식 — 「설정 바꿔 다시 만들기」 가 그대로 채운다."""
    checks: dict[str, Any] = Field(default_factory=dict)
    measures: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    """설계점마다 더 내보내는 것 — `midsurface`."""
    batches: list[dict[str, Any]] = Field(default_factory=list)
    """만든 뒤 **더한** 묶음 — 방식 · 시드 · 범위 · 번호 구간(`from` · `to`)."""
    export_stale: bool = False
    """보낸 뒤에 점을 더했다 — 공유 폴더가 옛것이다(다시 보내야 한다)."""
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
