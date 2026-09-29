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
}

export interface DoeStudySummary {
  id: string
  name: string
  description: string
  work_id: string | null
  work_name: string | null
  work_kind: 'part' | 'jig' | 'assembly' | null
  method: 'factorial' | 'lhs'
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
  count: number
  max: number
  /** LHS 표본 수 상한 — 관리자 설정. */
  max_samples: number
  too_many: boolean
  points: Record<string, number>[]
  varying: string[]
}

export const doeApi = {
  preview: (body: { factors: Factor[]; method?: string; samples?: number; seed?: number }) =>
    api.post<Preview>('/doe/preview', body),
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
    work_id?: string | null
    /**
     * 해석 조건 — **안 보내면 `work_id` 작업의 현재 조건**을 서버가 싣는다. 대상 작업이 없는
     * 「다시 만들기」 처럼 스냅샷으로 만들 때만 보낸다.
     */
    conditions?: Record<string, unknown>
  }) => api.post<DoeStudy>('/doe', body),
  /** 설계점 하나의 형상 — 화면이 점마다 3D 로 본다. */
  pointMesh: (id: string, number: number) => api.get<PointMesh>(`/doe/${id}/points/${number}/mesh`),
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
