import type { Recipe } from '@/modules/cad/api'
import type { Job } from '@/modules/jobs/api'
import type { Work } from '@/modules/works/api'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'
import type { FolderRow } from '@/shared/folders/paths'
import { addShapeParams } from '@/shared/components/ShapeFilter'
import type { ShapeIndex, ShapeQuery } from '@/shared/components/ShapeFilter'

export interface PartVersion {
  id: string
  part_id: string
  number: number
  recipe: Recipe
  /** 해석 조건 — 등록할 때 작업에서 함께 올렸으면 있다. 「내 작업 공간으로 복사」 가 옮긴다. */
  conditions?: Record<string, unknown>
  job: Job | null
  note: string
  promoted_by_id: string | null
  promoted_by_name: string | null
  work_version_id: string | null
  created_at: string
}

export interface Part {
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  work_id: string | null
  current_version: number
  version_count: number
  current: PartVersion | null
  jig_count: number
  /** 놓인 폴더 — `고객A/2026`, 빈 것이 맨 위. */
  folder: string
  created_at: string
  updated_at: string
}

export interface PartSummary {
  /** 꼬리표 — 승격이 내 작업의 것을 물려받는다. `?tag=` 로 거른다. */
  tags: string[]
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  current_version: number
  jig_count: number
  /** 놓인 폴더 — `고객A/2026`, 빈 것이 맨 위. 승격할 때 작업의 폴더를 한 번 물려받는다. */
  folder: string
  updated_at: string
  /** 최신 버전의 형상 색인 — 이 기능 전의 버전이면 없다. */
  shape?: ShapeIndex | null
}

/** 목록을 거르는 폴더 — null 이면 전부, '' 이면 폴더 없는 것만(그때는 하위를 안 본다). */
export interface FolderFilter {
  folder?: string | null
  /** 형상 조건 — 최신 버전의 형상 색인으로. */
  shape?: ShapeQuery
}

export const partsApi = {
  list: (offset = 0, limit = 50, q = '', tag = '', filter: FolderFilter = {}) => {
    const query = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    if (q) query.set('q', q)
    if (tag) query.set('tag', tag)
    if (filter.folder != null) query.set('folder', filter.folder)
    if (filter.folder === '') query.set('subfolders', 'false')
    addShapeParams(query, filter.shape)
    return api.get<Page<PartSummary>>(`/parts?${query}`)
  },
  /** 카탈로그의 폴더들 — 경로와 바로 그 폴더의 부품 수. */
  folders: () => api.get<FolderRow[]>('/parts/folders'),
  /** 폴더째 옮기기 · 이름 바꾸기(하위까지). 남의 부품이 든 폴더는 관리자만. */
  renameFolder: (path: string, to: string) => api.post<{ moved: number }>('/parts/folders/rename', { path, to }),
  /** 부품 여럿을 한 폴더로 — 올린 사람 · 관리자만. */
  move: (ids: string[], folder: string) => api.post<{ moved: number }>('/parts/move', { ids, folder }),
  /**
   * 꼬리표 전부 — 거르개 · 자동 완성. **승격이 내 작업의 것을 물려받는다**(붙여 둔 것이
   * 공용 공간으로 나가면서 없어지던 것을 고쳤다, 2026-09-24).
   */
  tags: () => api.get<string[]>('/parts/tags'),
  get: (id: string) => api.get<Part>(`/parts/${id}`),
  versions: (id: string) => api.get<PartVersion[]>(`/parts/${id}/versions`),
  update: (id: string, body: { name?: string; description?: string; folder?: string }) => api.patch<Part>(`/parts/${id}`, body),
  remove: (id: string) => api.delete<void>(`/parts/${id}`),
  copyToWork: (id: string, body: { name?: string; number?: number; conditions?: boolean }) =>
    api.post<Work>(`/parts/${id}/copy-to-work`, body),
}
