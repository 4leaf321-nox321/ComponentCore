import type { Job } from '@/modules/jobs/api'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'

export interface InterferenceItem {
  a: string
  b: string
  volume: number
  ok: boolean
}

/** Job(kind="jig") 의 summary — `core/model.py` 의 `JigResult.summary()`. */
export interface JigSummary {
  geometry: {
    bbox: { min: number[]; max: number[]; size: number[] }
    volume: number
    surface_area: number
    solid_count: number
    face_count: number
    edge_count: number
  }
  feature_counts: Record<string, number>
  plan: {
    base_plate: { length: number; width: number; thickness: number }
    supports: { label: string; position: number[]; diameter: number }[]
    locators: { label: string; kind: string; position: number[]; diameter: number | null }[]
    clamps: { label: string; pad_position: number[]; post_position: number[] }[]
    product_lift: number
    notes: string[]
  }
  interference: { ok: boolean; tolerance: number; total_volume: number; items: InterferenceItem[] }
  files: Record<string, string>
  stages: { name: string; millis: number; detail: string }[]
}

export interface JigVersion {
  id: string
  jig_id: string
  number: number
  job: Job | null
  options: Record<string, unknown>
  summary: JigSummary | null
  part_id: string | null
  part_name: string | null
  part_version: number | null
  note: string
  promoted_by_name: string | null
  created_at: string
}

export interface Jig {
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  work_id: string | null
  part_id: string | null
  part_name: string | null
  current_version: number
  version_count: number
  current: JigVersion | null
  created_at: string
  updated_at: string
}

export interface JigCatalogSummary {
  /** 꼬리표 — 승격이 내 작업의 것을 물려받는다. `?tag=` 로 거른다. */
  tags: string[]
  id: string
  name: string
  description: string
  owner_name: string
  part_id: string | null
  part_name: string | null
  current_version: number
  interference_ok: boolean | null
  updated_at: string
}

export const jigsApi = {
  list: (params: { part_id?: string; offset?: number; limit?: number; q?: string; tag?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.part_id) query.set('part_id', params.part_id)
    if (params.q) query.set('q', params.q)
    if (params.tag) query.set('tag', params.tag)
    query.set('offset', String(params.offset ?? 0))
    query.set('limit', String(params.limit ?? 50))
    return api.get<Page<JigCatalogSummary>>(`/jigs?${query.toString()}`)
  },
  /**
   * 꼬리표 전부 — 거르개 · 자동 완성. **승격이 내 작업의 것을 물려받는다**(붙여 둔 것이
   * 공용 공간으로 나가면서 없어지던 것을 고쳤다, 2026-09-24).
   */
  tags: () => api.get<string[]>('/jigs/tags'),
  get: (id: string) => api.get<Jig>(`/jigs/${id}`),
  versions: (id: string) => api.get<JigVersion[]>(`/jigs/${id}/versions`),
  update: (id: string, body: { name?: string; description?: string }) => api.patch<Jig>(`/jigs/${id}`, body),
  remove: (id: string) => api.delete<void>(`/jigs/${id}`),
}
