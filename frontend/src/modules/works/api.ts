import type { Recipe } from '@/modules/cad/api'
import type { Job } from '@/modules/jobs/api'
import type { MeshData } from '@/shared/viewer/PickViewer'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'
import type { FolderRow } from '@/shared/folders/paths'
import { addShapeParams } from '@/shared/components/ShapeFilter'
import type { ShapeIndex, ShapeQuery } from '@/shared/components/ShapeFilter'

export interface WorkVersion {
  id: string
  work_id: string
  number: number
  recipe: Recipe
  /** 해석 조건 한 벌 — 비어 있으면 아직 안 붙인 것이다(`modules/conditions`). */
  conditions?: Record<string, unknown>
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
  /** 기본 단위계(`mm_n_tonne` · `si`) — 새 시뮬레이션 조건이 이 계로 시작한다. 도면은 늘 mm. */
  unit_system: string
  jig_run_count: number
  last_jig_status: string | null
  promoted_part_id: string | null
  promoted_jig_id: string | null
  tags: string[]
  /** 놓인 폴더 — `고객A/2026` 같은 경로, 빈 것이 맨 위. */
  folder: string
  created_at: string
  updated_at: string
  deleted_at: string | null
}

/** 폴더 하나 — 공간마다 같은 모양(`@/shared/folders/paths`). */
export type { FolderRow }

export interface YearRow {
  year: number
  count: number
}

export interface WorkFilter {
  q?: string
  tag?: string
  kind?: string
  trashed?: boolean
  /** 폴더 — 주면 그 폴더(하위까지가 기본). 안 주면 모든 폴더. */
  folder?: string | null
  /** false 면 바로 그 폴더만. */
  subfolders?: boolean
  /** 만든 해. */
  year?: number | null
  /** 만든 순(연도별로 묶어 볼 때) · 고친 순(기본). */
  order?: 'updated' | 'created'
  /** 형상 조건 — 최신 버전의 형상 색인으로. */
  shape?: ShapeQuery
  /** 누구의 것 — 안 주면 내 것. `all`(모두) · 사람 id 는 시스템 관리자만(아니면 403). */
  owner?: string
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
  tags: string[]
  folder: string
  created_at: string
  updated_at: string
  deleted_at: string | null
  /** 최신 버전의 형상 색인 — 이 기능 전의 버전이면 없다. */
  shape?: ShapeIndex | null
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
  list: (offset = 0, limit = 50, filter: WorkFilter = {}) => {
    const query = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    if (filter.q) query.set('q', filter.q)
    if (filter.tag) query.set('tag', filter.tag)
    if (filter.kind) query.set('kind', filter.kind)
    if (filter.trashed) query.set('trashed', 'true')
    if (filter.folder != null) query.set('folder', filter.folder)
    if (filter.subfolders === false) query.set('subfolders', 'false')
    if (filter.year != null) query.set('year', String(filter.year))
    if (filter.order === 'created') query.set('order', 'created')
    if (filter.owner) query.set('owner', filter.owner)
    addShapeParams(query, filter.shape)
    return api.get<Page<WorkSummary>>(`/works?${query}`)
  },
  /** 내 작업이 놓인 폴더들 — 화면이 나무로 그린다. `owner` 는 `list` 와 같다(관리자만). */
  folders: (owner?: string) =>
    api.get<FolderRow[]>(owner ? `/works/folders?${new URLSearchParams({ owner })}` : '/works/folders'),
  /** 내 작업을 만든 해들 — 최근 해부터. */
  years: () => api.get<YearRow[]>('/works/years'),
  /** 폴더 이름 바꾸기 · 옮기기(하위까지). `to` 가 빈 문자열이면 맨 위로 합친다 — 폴더 지우기. */
  renameFolder: (path: string, to: string) => api.post<{ moved: number }>('/works/folders/rename', { path, to }),
  /** 작업 여럿을 한 폴더로. */
  move: (ids: string[], folder: string) => api.post<{ moved: number }>('/works/move', { ids, folder }),
  /** 내 작업에 붙은 꼬리표 — 많이 쓴 것부터. `owner` 는 `list` 와 같다(관리자만). */
  tags: (owner?: string) =>
    api.get<string[]>(owner ? `/works/tags?${new URLSearchParams({ owner })}` : '/works/tags'),
  /** 휴지통에서 되살린다. */
  restoreWork: (id: string) => api.post<Work>(`/works/${id}/restore`, {}),
  /** 현재 도면으로 새 작업 — 종류 · 꼬리표가 따라간다. */
  /** 현재 도면으로 새 작업. `conditions` 면 해석 조건도 복사한다(기본은 도면만). */
  duplicate: (id: string, name?: string, conditions = false) => {
    const query = new URLSearchParams()
    if (name) query.set('name', name)
    if (conditions) query.set('conditions', 'true')
    const suffix = query.toString() ? `?${query}` : ''
    return api.post<Work>(`/works/${id}/duplicate${suffix}`, {})
  },
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
    body: {
      name?: string
      description?: string
      jig_options?: Record<string, unknown>
      kind?: WorkKind
      jig_for_part_id?: string | null
      tags?: string[]
      unit_system?: string
      folder?: string
    },
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
  /** 부품 + 지그를 맞는 자리에 놓은 조립 작업. placement.mode 가 generated | guessed. */
  assemble: (body: { part_source: string; jig_work_id: string; name?: string }) =>
    api.post<{ work: Work; placement: { mode: 'generated' | 'guessed'; translate: number[]; product_lift: number; height_param: string } }>('/works/assemble', body),
  /** 끝난 생성 결과를 그 지그 작업의 버전으로 — 두 번 불러도 같은 버전. */
  adoptJigRun: (id: string, jobId: string) => api.post<WorkVersion>(`/works/${id}/jig-runs/${jobId}/adopt`, {}),
  promotePart: (id: string, body: { name?: string; note?: string }) =>
    api.post<{ part_id: string; number: number }>(`/works/${id}/promote/part`, body),
  /** 손으로 그린 지그(레시피 버전)를 지그 카탈로그로 — 생성기를 거치지 않는 길. */
  /** 생성기가 만든 지그를 **지그 작업으로** — 그 다음부터는 그냥 그린다. */
  promoteJigRecipe: (id: string, body: { number?: number; name?: string; note?: string; part_id?: string | null }) =>
    api.post<{ jig_id: string; jig_version: number }>(`/works/${id}/promote/jig-recipe`, body),
}
