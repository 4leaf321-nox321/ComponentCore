import type { Recipe } from '@/modules/cad/api'
import type { Job } from '@/modules/jobs/api'
import type { MeshData } from '@/shared/viewer/PickViewer'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'

export interface WorkVersion {
  id: string
  work_id: string
  number: number
  recipe: Recipe
  source: string
  note: string
  created_by_id: string | null
  created_by_name: string | null
  job: Job | null
  promoted_part_id: string | null
  promoted_part_version: number | null
  created_at: string
}

/**
 * 이 작업이 만드는 것.
 *
 * - `part` · `jig` 는 **그리는 것**이다. 둘은 서로 아무 관계가 없다 — 각자 제 도면이다.
 * - `assembly` 는 **놓는 것**이다. 부품 · 지그를 가져다 서로 위치시킨다.
 */
export type WorkKind = 'part' | 'jig' | 'assembly'

export interface Work {
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  kind: WorkKind
  jig_for_part_id: string | null
  jig_for_part_name: string | null
  current_version: number
  version_count: number
  current: WorkVersion | null
  jig_options: Record<string, unknown>
  jig_run_count: number
  last_jig_status: string | null
  promoted_part_id: string | null
  promoted_jig_id: string | null
  created_at: string
  updated_at: string
}

export interface WorkSummary {
  id: string
  name: string
  description: string
  kind: WorkKind
  owner_id: string
  owner_name: string
  current_version: number
  current_status: string | null
  jig_run_count: number
  last_jig_status: string | null
  promoted_part_id: string | null
  promoted_jig_id: string | null
  updated_at: string
}

export interface JigPreview {
  plan: {
    kind: 'clamped' | 'bolted' | 'bending' | 'drop'
    base_plate: Record<string, unknown>
    supports: unknown[]
    locators: { kind: string }[]
    clamps: unknown[]
    bolts: unknown[]
    rollers: unknown[]
    nose: Record<string, unknown> | null
    impactor: { kind: string } | null
    product_lift: number
    notes: string[]
  }
  interference: { ok: boolean; items: { a: string; b: string; ok: boolean; volume: number }[] }
  geometry: Record<string, unknown>
  mesh: MeshData
}

export const worksApi = {
  jigOptions: () => api.get<Record<string, unknown>>('/works/jig-options'),
  list: (offset = 0, limit = 50) => api.get<Page<WorkSummary>>(`/works?offset=${offset}&limit=${limit}`),
  get: (id: string) => api.get<Work>(`/works/${id}`),
  create: (body: {
    name: string
    description?: string
    /** 비우면 **버전 없이** 작업만 생긴다 — 조립처럼 만들어 놓고 채우는 것. */
    recipe?: Recipe | null
    source?: string
    note?: string
    kind?: WorkKind
    jig_for_part_id?: string | null
  }) =>
    api.post<Work>('/works', body),
  update: (
    id: string,
    body: { name?: string; description?: string; jig_options?: Record<string, unknown>; kind?: WorkKind; jig_for_part_id?: string | null },
  ) =>
    api.patch<Work>(`/works/${id}`, body),
  remove: (id: string) => api.delete<void>(`/works/${id}`),
  createFromStep: (file: File, name?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (name) form.append('name', name)
    return api.postForm<Work>('/works/from-step', form)
  },
  versions: (id: string) => api.get<WorkVersion[]>(`/works/${id}/versions`),
  addVersion: (id: string, body: { recipe: Recipe; source?: string; note?: string }) =>
    api.post<WorkVersion>(`/works/${id}/versions`, body),
  restore: (id: string, number: number) => api.post<WorkVersion>(`/works/${id}/versions/${number}/restore`),
  importStep: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<WorkVersion>(`/works/${id}/import-step`, form)
  },
  jigRuns: (id: string) => api.get<Job[]>(`/works/${id}/jig-runs`),
  /** 만들기 전 미리보기 — 계획 · 간섭 · 제품 + 지그 메시(면마다 `part` 이름표). 파일 · 작업은 안 생긴다. */
  jigPreview: (body: { source: string; options?: Record<string, unknown> }) => api.post<JigPreview>('/works/jig-from-part/preview', body),
  /** 부품에서 지그 작업을 **생성** — 지그 작업이 바로 생기고 생성이 걸린다. 끝나면 `adoptJigRun`. */
  jigFromPart: (body: { source: string; name?: string; options?: Record<string, unknown> }) => api.post<{ work: Work; job: Job }>('/works/jig-from-part', body),
  /** 끝난 생성 결과를 그 지그 작업의 버전으로 — 두 번 불러도 같은 버전. */
  adoptJigRun: (id: string, jobId: string) => api.post<WorkVersion>(`/works/${id}/jig-runs/${jobId}/adopt`, {}),
  promotePart: (id: string, body: { name?: string; note?: string }) =>
    api.post<{ part_id: string; number: number }>(`/works/${id}/promote/part`, body),
  /** 손으로 그린 지그(레시피 버전)를 지그 카탈로그로 — 생성기를 거치지 않는 길. */
  /** 생성기가 만든 지그를 **지그 작업으로** — 그 다음부터는 그냥 그린다. */
  promoteJigRecipe: (id: string, body: { number?: number; name?: string; note?: string; part_id?: string | null }) =>
    api.post<{ jig_id: string; jig_version: number }>(`/works/${id}/promote/jig-recipe`, body),
}
