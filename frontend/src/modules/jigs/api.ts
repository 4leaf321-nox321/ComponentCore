import type { Job } from '@/modules/jobs/api'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'
import type { FolderRow } from '@/shared/folders/paths'
import { addShapeParams } from '@/shared/components/ShapeFilter'
import type { ShapeIndex, ShapeQuery } from '@/shared/components/ShapeFilter'

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
    /** 규격 부품표 — 품번마다 수량. 이 기능 전의 결과에는 없다. */
    bom?: { part_no: string; name: string; kind: string; count: number }[]
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
  /** 등록 시점의 레시피 — 「내 작업 공간으로 복사」 가 연다. 생성기로 만든 이전 버전은 없다. */
  recipe?: Record<string, unknown> | null
  /** 해석 조건 — 등록할 때 함께 올렸으면 있다. 복사가 옮긴다. */
  conditions?: Record<string, unknown>
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
  /** 놓인 폴더 — `고객A/2026`, 빈 것이 맨 위. */
  folder: string
  created_at: string
  updated_at: string
}

export interface JigCatalogSummary {
  /** 꼬리표 — 승격이 내 작업의 것을 물려받는다. `?tag=` 로 거른다. */
  tags: string[]
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  part_id: string | null
  part_name: string | null
  current_version: number
  interference_ok: boolean | null
  /** 놓인 폴더 — `고객A/2026`, 빈 것이 맨 위. 승격할 때 작업의 폴더를 한 번 물려받는다. */
  folder: string
  updated_at: string
  /** 최신 버전의 형상 색인 — 이 기능 전의 버전이면 없다. */
  shape?: ShapeIndex | null
}

export const jigsApi = {
  list: (params: { part_id?: string; offset?: number; limit?: number; q?: string; tag?: string; folder?: string | null; shape?: ShapeQuery } = {}) => {
    const query = new URLSearchParams()
    if (params.part_id) query.set('part_id', params.part_id)
    if (params.q) query.set('q', params.q)
    if (params.tag) query.set('tag', params.tag)
    // 폴더 — null 이면 전부, '' 이면 폴더 없는 것만(그때는 하위를 안 본다).
    if (params.folder != null) query.set('folder', params.folder)
    if (params.folder === '') query.set('subfolders', 'false')
    query.set('offset', String(params.offset ?? 0))
    query.set('limit', String(params.limit ?? 50))
    addShapeParams(query, params.shape)
    return api.get<Page<JigCatalogSummary>>(`/jigs?${query.toString()}`)
  },
  /**
   * 꼬리표 전부 — 거르개 · 자동 완성. **승격이 내 작업의 것을 물려받는다**(붙여 둔 것이
   * 공용 공간으로 나가면서 없어지던 것을 고쳤다, 2026-09-24).
   */
  tags: () => api.get<string[]>('/jigs/tags'),
  get: (id: string) => api.get<Jig>(`/jigs/${id}`),
  versions: (id: string) => api.get<JigVersion[]>(`/jigs/${id}/versions`),
  /** 지그(버전)의 레시피로 내 작업(종류 지그)을 새로 — 잡는 부품 · 해석 조건이 따라간다. */
  copyToWork: (id: string, body: { name?: string; number?: number; conditions?: boolean }) =>
    api.post<{ id: string }>(`/jigs/${id}/copy-to-work`, body),
  update: (id: string, body: { name?: string; description?: string; folder?: string }) => api.patch<Jig>(`/jigs/${id}`, body),
  /** 카탈로그의 폴더들 — 경로와 바로 그 폴더의 지그 수. */
  folders: () => api.get<FolderRow[]>('/jigs/folders'),
  /** 폴더째 옮기기 · 이름 바꾸기(하위까지). 남의 지그가 든 폴더는 관리자만. */
  renameFolder: (path: string, to: string) => api.post<{ moved: number }>('/jigs/folders/rename', { path, to }),
  /** 지그 여럿을 한 폴더로 — 올린 사람 · 관리자만. */
  move: (ids: string[], folder: string) => api.post<{ moved: number }>('/jigs/move', { ids, folder }),
  remove: (id: string) => api.delete<void>(`/jigs/${id}`),
}
