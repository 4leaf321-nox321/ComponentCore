import type { Recipe } from '@/modules/cad/api'
import type { Job } from '@/modules/jobs/api'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'

/** 인자 하나 — 고정이거나, 구간이거나, 값 목록. */
export interface Factor {
  name: string
  mode: 'fixed' | 'range' | 'list'
  value?: number | null
  start?: number | null
  end?: number | null
  steps?: number
  values?: number[]
}

export interface DoePoint {
  id: string
  number: number
  params: Record<string, number>
  status: 'pending' | 'ok' | 'failed'
  error: string
  metrics: Record<string, number | null> | null
  step_file: string
}

export interface DoeStudySummary {
  id: string
  name: string
  description: string
  work_id: string | null
  method: 'factorial' | 'lhs'
  samples: number
  seed: number
  material: string
  point_count: number
  created_at: string
}

export interface DoeStudy extends DoeStudySummary {
  recipe: Recipe
  factors: Factor[]
  /** 해석 쪽이 여는 경로(F:\…). 서버가 보는 경로는 안 내려온다. */
  export_dir_windows: string
  job: Job | null
  points: DoePoint[]
  done: number
  failed: number
}

export interface Preview {
  count: number
  max: number
  too_many: boolean
  points: Record<string, number>[]
  varying: string[]
}

export interface Condition {
  key: string
  op: 'lte' | 'gte' | 'between' | 'eq'
  value: number | null
  value2?: number | null
}

export const doeApi = {
  preview: (body: { factors: Factor[]; method?: string; samples?: number; seed?: number }) =>
    api.post<Preview>('/doe/preview', body),
  list: (options: { workId?: string; offset?: number; limit?: number } = {}) => {
    const query = new URLSearchParams({ offset: String(options.offset ?? 0), limit: String(options.limit ?? 50) })
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
    material?: string
    work_id?: string | null
  }) => api.post<DoeStudy>('/doe', body),
  filter: (id: string, conditions: Condition[]) => api.post<DoePoint[]>(`/doe/${id}/filter`, conditions),
  remove: (id: string) => api.delete<void>(`/doe/${id}`),
  manifestUrl: (id: string) => `/api/doe/${id}/manifest.csv`,
}
