import type { Recipe } from '@/modules/cad/api'
import type { Job } from '@/modules/jobs/api'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'
import type { MeshData } from '@/shared/viewer/PickViewer'

/**
 * 인자 하나 — 치수(고정 · 구간 · 값 목록)이거나, 형상을 안 바꾸는 셋 중 하나:
 * - `material`: `bodies` 에 붙일 재료를 `values`(조건에 담아 둔 재료의 이름 · 번호) 중에서.
 * - `choice`: 조건의 고르는 칸 하나(`target`)를 `values` 중에서.
 * - `scale`: `bodies` 재료의 물성 `property` 에 곱할 배율 `values`.
 */
export interface Factor {
  name: string
  mode: 'fixed' | 'range' | 'list' | 'material' | 'choice' | 'scale'
  value?: number | null
  start?: number | null
  end?: number | null
  /** 칸을 비우면 null — 다 지우고 처음부터 칠 수 있어야 한다. 비어 있으면 만들기가 막힌다. */
  steps?: number | null
  values?: (number | string | boolean | null)[]
  /** 재료 · 배율 인자 — 그 바디(단품이면 「전체」). */
  bodies?: string[]
  /** 고르기 인자 — 조건의 어느 칸인가(묶음 · 항목 이름 또는 1 부터의 번호 · 칸). */
  target?: { group: string; item?: string | number; field: string }
  /** 배율 인자 — 곱할 물성(「탄성계수」 · 표준 열쇠 · 밀도 · 푸아송비). */
  property?: string
  /** 값을 맞추는 가공 단위(mm). 없으면 0.1 — 0.333 같은 치수는 가공할 수 없다. */
  resolution?: number | null
}

export interface DoePoint {
  id: string
  number: number
  /** 설계점의 값 — 치수는 수, 재료 인자는 재료 이름. */
  params: Record<string, number | string | boolean | null>
  status: 'pending' | 'ok' | 'failed'
  error: string
  /** 해석 결과가 붙을 자리 — 붙이는 길이 아직 없어 지금은 늘 null. */
  metrics: Record<string, number | null> | null
  /** 조립이면 구성품끼리 겹침(ok · items · total_volume). 구성품이 하나면 null. */
  interference: { ok: boolean; total_volume: number; items: { a: string; b: string; volume: number; ok: boolean }[] } | null
  step_file: string
  /** 형상 점검 — 메시가 막힐 자리. 꺼 두었거나 아직이면 null. */
  quality?: Quality | null
  /** 측정값 — 스터디의 정의대로. 못 잰 것은 null(0 이 아니다). */
  measures?: Record<string, number | null> | null
}

/**
 * 측정값 정의 — 점마다 형상에서 바로 나오는 값을 표의 열로.
 * 부피 · 겉넓이 · 크기(축) · 선택 그룹 넓이 · 두 그룹 사이 거리 · 식(도면 변수와 앞의 측정값).
 */
export interface Measure {
  name: string
  kind: 'volume' | 'area' | 'size' | 'region_area' | 'distance' | 'expr'
  axis?: 'x' | 'y' | 'z'
  body?: string
  region?: string
  a?: string
  b?: string
  expr?: string
}

/** 형상 점검의 잰 값 — `warnings` 가 비면 기준을 다 지켰다. `notes` 는 알림(면 수 변화). */
export interface Quality {
  valid?: boolean
  solids?: number
  faces?: number
  min_wall?: number | null
  min_wall_at?: number[] | null
  shortest_edge?: number | null
  short_edges?: number
  narrowest_face?: number | null
  narrow_faces?: number
  warnings: string[]
  notes?: string[]
}

/** 형상 점검 기준(mm) — 바꿀 것만 보낸다. */
export interface Checks {
  enabled?: boolean
  min_wall?: number
  short_edge?: number
  narrow_face?: number
}

/** 서버의 기본 기준(core/quality.DEFAULTS)과 같다. */
export const CHECK_DEFAULTS = { min_wall: 0.5, short_edge: 0.1, narrow_face: 0.1 }

/** 설계점을 뽑는 방식 — 격자 · LHS · 직접 준 표 · 하나씩 바꾸기 · 중심 합성 · Box-Behnken · Sobol. */
export type DoeMethod = 'factorial' | 'lhs' | 'table' | 'oat' | 'ccd' | 'bbd' | 'sobol'

/** 방식의 사람 말 — 결과 화면 · 목록. */
export const METHOD_LABELS: Record<DoeMethod, string> = {
  factorial: '전체 조합',
  lhs: 'LHS',
  table: '직접 준 표',
  oat: '하나씩 바꾸기',
  ccd: '중심 합성',
  bbd: 'Box-Behnken',
  sobol: 'Sobol',
}

/** 표본 수 · 시드를 받는 방식(난수 · 수열). */
export const SAMPLED: DoeMethod[] = ['lhs', 'sobol']

/** 방식 배지 — 난수를 쓰는 방식은 시드를 함께 적는다(같은 표를 다시 만드는 열쇠). */
export function methodBadge(study: { method: DoeMethod; seed: number }): string {
  const label = METHOD_LABELS[study.method] ?? study.method
  return SAMPLED.includes(study.method) ? `${label} · 시드 ${study.seed}` : label
}

export interface DoeStudySummary {
  id: string
  name: string
  description: string
  work_id: string | null
  work_name: string | null
  work_kind: 'part' | 'jig' | 'assembly' | null
  method: DoeMethod
  samples: number
  seed: number
  point_count: number
  created_at: string
  /** 누구 것인가. 기계가 대행으로 만들었으면 **대행 대상인 사람**이다. */
  owner_name: string
  /**
   * `read`(기본) · `private`. **읽기는 모두에게**가 기본이다 — DOE 는 조직의 설계 이력이고,
   * 옆 사람이 같은 훑기를 다시 도는 것이 더 큰 손해다. 쓰는 일은 공개와 무관하게 소유자만.
   */
  visibility: string
}

export interface DoeStudy extends DoeStudySummary {
  recipe: Recipe
  factors: Factor[]
  /** 만들기 전에 거른 제약식(`간격 > 2 * 지름`). 점을 더할 때도 같은 것이 걸린다. */
  constraints?: string[]
  /** 형상 점검 기준(mm) — 비면 서버 기본값. */
  checks?: Checks
  /** 점마다 잰 값의 정의 — 표에 열로 붙는다. */
  measures?: Measure[]
  /** 점마다 더 내보내는 것 — `midsurface`(셸 해석용 중간면 STEP). */
  outputs?: string[]
  /** 만든 뒤 더한 설계점 묶음의 이력. */
  batches?: Batch[]
  /** 보낸 뒤에 점을 더했다 — 공유 폴더의 표가 옛것이다. */
  export_stale?: boolean
  /** 만들 때 박은 해석 조건 스냅샷 — 비었으면 형상만 훑었다. */
  conditions?: Record<string, unknown>
  /**
   * 서버 보관 폴더에 설계점 파일이 **아직 있나.** 보관 기한이 지나 치워졌으면 false —
   * 그러면 CSV 는 되지만(DB 에서 그린다) 「보내기」 는 막힌다. 「다시 만들기」 가 되살린다.
   */
  local_ready: boolean
  /** **누가 실제로 돌렸나** — 기계가 대행했을 때만 찬다(오케스트레이터의 서비스 계정). */
  requested_by_name: string
  /** 해석 쪽이 여는 경로(F:\…). 서버가 보는 경로는 안 내려온다. */
  export_dir_windows: string
  /** 마지막으로 공유 폴더에 보낸 때. 없으면 아직 서버 안에만 있다. */
  exported_at: string | null
  job: Job | null
  points: DoePoint[]
  done: number
  failed: number
}

/** 설계점 하나의 형상 — 스냅샷 레시피에 그 점의 값을 넣어 다시 만든 것. */
export interface PointMesh {
  number: number
  params: Record<string, number>
  summary: { bbox: { size: number[] } } & Record<string, unknown>
  mesh: MeshData
}

export interface Preview {
  /** 만들 설계점 수 — 제약이 있으면 거른 뒤의 수. */
  count: number
  /** 방식이 낸 수 — 격자 칸 수 · LHS 표본 수. */
  requested?: number
  max: number
  /** LHS 표본 수 상한 — 관리자 설정. */
  max_samples: number
  too_many: boolean
  /** 만들 설계점 전부(상한 안). */
  points: Record<string, number | string>[]
  varying: string[]
  /** 제약에 걸린 후보 수 · 훑어본 후보 수 · 제약마다 걸린 수 · LHS 가 못 채운 수. */
  rejected?: number
  candidates?: number
  hits?: number[]
  shortfall?: number
  /** 걸러진 후보 몇 줄 — 흩뿌림에 옅게 그린다. */
  rejected_points?: Record<string, number | string>[]
}

/** 「미리 만들어 보기」 의 한 점 — 끝 점(모두 최소 · 최대, 인자마다 최소 · 최대)과 가운데. */
export interface ProbePoint {
  label: string
  params: Record<string, number | string | boolean | null>
  /** 만듦 · 실패 · 건너뜀(제약을 어김 · 시간이 다 됨). */
  status: 'ok' | 'failed' | 'skipped'
  error: string
  ms?: number
  /** 이 점에서 못 찾은 선택 그룹 — 해석이 하중 · 구속을 붙일 자리가 없다. */
  unresolved?: string[]
  /** 예측한 자리에서 멀리 집은 그룹 — 딴 면을 집었을 수 있어 못 푼 것으로 돌렸다. */
  drift?: { name: string; distance: number }[]
  interference?: DoePoint['interference']
  solids?: number
  faces?: number
  /** 레시피 평가의 경고(면 지우기를 다 못 했다 등). */
  warnings?: string[]
  quality?: Quality | null
  measures?: Record<string, number | null>
}

export interface ProbeResult {
  points: ProbePoint[]
  /** 만든 점의 평균 시간 — 전체 시간을 가늠한다. */
  mean_ms: number | null
  /** 선택 그룹이 치수를 따라가는지 재는 데 든 시간(스터디마다 한 번). */
  setup_ms: number
  /** 이 조건의 선택 그룹 이름들. */
  regions: string[]
}

/** 만든 뒤 더한 설계점 묶음 하나 — 방식 · 시드 · 번호 구간. */
export interface Batch {
  number: number
  method: DoeMethod
  samples: number
  seed: number
  factors: Factor[]
  from: number
  to: number
  added: number
  /** 이미 있는 점과 값이 같아 뺀 수. */
  skipped: number
  /** 제약에 걸린 후보 수. */
  rejected?: number
  at?: string
  requested_by?: string
  reused?: boolean
}

/** 점 더하기 — 방식 · 표본 수 · 시드 · **바꿀 변수만** · 표. */
export interface ExtendBody {
  method: DoeMethod
  samples?: number
  seed?: number | null
  factors?: Factor[]
  table?: Record<string, unknown>[]
  idempotency_key?: string
}

/** 미리보기 · 만들기가 함께 받는 계획 — 인자 · 방식 · 제약. */
export interface PlanBody {
  factors: Factor[]
  method?: string
  samples?: number
  seed?: number
  /** 변수끼리의 조건 — 어긴 조합은 만들기 전에 거른다. */
  constraints?: string[]
  /** 제약식이 인자 아닌 치수를 부를 때 풀 도면. */
  recipe?: Recipe
  /** 형상 점검 기준(mm) — 바꿀 것만. */
  checks?: Checks
  /** `method='table'` 의 설계점 — 줄마다 `{변수: 값}`. 값은 그대로 만든다. */
  table?: Record<string, unknown>[]
  /** 점마다 잴 값 — 표에 열로 붙는다. */
  measures?: Measure[]
}

export const doeApi = {
  preview: (body: PlanBody) => api.post<Preview>('/doe/preview', body),
  /**
   * **끝 점 몇 개를 먼저 만들어 본다** — 실패 · 못 푼 영역 · 어긋남 · 겹침 · 시간. 파일은 안
   * 쓴다. 조건은 `work_id` 작업의 것(만들 때와 같다)이고, 대상이 없으면 `conditions` 로.
   */
  probe: (body: PlanBody & { recipe: Recipe; work_id?: string | null; conditions?: Record<string, unknown> }) =>
    api.post<ProbeResult>('/doe/probe', body),
  /** `scope='all'` 이면 **남이 공개한 것까지** — 같은 훑기를 다시 도는 것이 가장 큰 낭비다. */
  list: (options: { workId?: string; offset?: number; limit?: number; scope?: 'mine' | 'all' } = {}) => {
    const query = new URLSearchParams({ offset: String(options.offset ?? 0), limit: String(options.limit ?? 50), scope: options.scope ?? 'mine' })
    if (options.workId) query.set('work_id', options.workId)
    return api.get<Page<DoeStudySummary>>(`/doe?${query}`)
  },
  get: (id: string) => api.get<DoeStudy>(`/doe/${id}`),
  create: (body: {
    name: string
    description?: string
    recipe: Recipe
    factors: Factor[]
    method?: string
    samples?: number
    seed?: number
    constraints?: string[]
    checks?: Checks
    table?: Record<string, unknown>[]
    measures?: Measure[]
    /** `['midsurface']` 면 점마다 중간면 STEP(`<형상>_mid.step`)도. */
    outputs?: 'midsurface'[]
    work_id?: string | null
    /**
     * 해석 조건 — **안 보내면 `work_id` 작업의 현재 조건**을 서버가 싣는다. 대상 작업이 없는
     * 「다시 만들기」 처럼 스냅샷으로 만들 때만 보낸다.
     */
    conditions?: Record<string, unknown>
  }) => api.post<DoeStudy>('/doe', body),
  /** 설계점 하나의 형상 — 화면이 점마다 3D 로 본다. */
  pointMesh: (id: string, number: number) => api.get<PointMesh>(`/doe/${id}/points/${number}/mesh`),
  /**
   * **점을 더한다** — 번호를 이어서 같은 폴더에. 스터디의 제약이 걸리고 이미 있는 값은 뺀다.
   * `dryRun` 이면 세기만 한다.
   */
  extend: (id: string, body: ExtendBody, dryRun = false) =>
    api.post<{ batch: Batch; study: DoeStudy }>(`/doe/${id}/extend${dryRun ? '?dry_run=true' : ''}`, body),
  /** 만들기를 멈춘다 — 만든 점과 표는 남고, 남은 점은 「다시 만들기」 가 잇는다. */
  cancel: (id: string) => api.post<DoeStudy>(`/doe/${id}/cancel`, {}),
  /** 서버 보관 폴더의 STEP · 표를 공유 폴더로 — 해석은 그때부터 읽는다. 다시 누르면 덮어쓴다. */
  export: (id: string) => api.post<DoeStudy>(`/doe/${id}/export`),
  /**
   * **다시 만들기** — 스냅샷(레시피 · 인자 · 시드 · 조건)으로 설계점 파일을 되살린다.
   * 같은 스터디에 같은 것이 다시 난다. `only='failed'` 면 실패한 점만.
   */
  rerun: (id: string, only: 'all' | 'failed' = 'all') => api.post<DoeStudy>(`/doe/${id}/rerun?only=${only}`),
  /** 누가 보나 — `read`(모두) · `private`(나와 관리자만). 소유자만 바꾼다. */
  setVisibility: (id: string, value: 'read' | 'private') => api.post<DoeStudy>(`/doe/${id}/visibility?value=${value}`),
  remove: (id: string) => api.delete<void>(`/doe/${id}`),
  manifestUrl: (id: string) => `/api/doe/${id}/manifest.csv`,
}
