import type { Recipe } from '@/modules/cad/api'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'
import type { FolderRow } from '@/shared/folders/paths'

/** 목록용 — 레시피 본문 없이 크기(`node_count`)만. */
export interface TemplateSummary {
  /** 꼬리표 — 승격이 내 작업의 것을 물려받는다. `?tag=` 로 거른다. */
  tags: string[]
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  is_shared: boolean
  /** 내 것인가 — 고치고 지우는 것은 소유자뿐이다. */
  mine: boolean
  node_count: number
  /** 놓인 폴더 — `고객A/2026`, 빈 것이 맨 위. 내 것과 공용이 같은 나무를 쓴다. */
  folder: string
  updated_at: string
}

export interface Template extends TemplateSummary {
  recipe: Recipe
}

/** 자리 — 내 것 · 공용 · 둘 다. */
export type TemplateScope = 'all' | 'mine' | 'shared'

export const templatesApi = {
  list: (options: { scope?: TemplateScope; q?: string; tag?: string; folder?: string | null; offset?: number; limit?: number } = {}) => {
    const query = new URLSearchParams({
      scope: options.scope ?? 'all',
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 50),
    })
    if (options.q) query.set('q', options.q)
    if (options.tag) query.set('tag', options.tag)
    // 폴더 — null 이면 전부, '' 이면 폴더 없는 것만(그때는 하위를 안 본다).
    if (options.folder != null) query.set('folder', options.folder)
    if (options.folder === '') query.set('subfolders', 'false')
    return api.get<Page<TemplateSummary>>(`/templates?${query}`)
  },
  /** 보이는 템플릿의 폴더들 — 자리(scope)마다. 남의 비공개 템플릿이 놓인 폴더는 안 보인다. */
  folders: (scope: TemplateScope = 'all') => api.get<FolderRow[]>(`/templates/folders?scope=${scope}`),
  /** 폴더째 옮기기 · 이름 바꾸기(하위까지). 남의 공용 템플릿이 든 폴더는 관리자만. */
  renameFolder: (path: string, to: string) => api.post<{ moved: number }>('/templates/folders/rename', { path, to }),
  /** 템플릿 여럿을 한 폴더로 — 만든 사람 · 관리자만. */
  move: (ids: string[], folder: string) => api.post<{ moved: number }>('/templates/move', { ids, folder }),
  /**
   * 꼬리표 전부 — 거르개 · 자동 완성. **승격이 내 작업의 것을 물려받는다**(붙여 둔 것이
   * 공용 공간으로 나가면서 없어지던 것을 고쳤다, 2026-09-24).
   */
  tags: () => api.get<string[]>('/templates/tags'),
  get: (id: string) => api.get<Template>(`/templates/${id}`),
  create: (body: { name: string; description?: string; recipe: Recipe; is_shared?: boolean; tags?: string[]; folder?: string }) =>
    api.post<Template>('/templates', body),
  update: (id: string, body: { name?: string; description?: string; recipe?: Recipe; is_shared?: boolean; folder?: string }) =>
    api.patch<Template>(`/templates/${id}`, body),
  copy: (id: string) => api.post<Template>(`/templates/${id}/copy`, {}),
  remove: (id: string) => api.delete<void>(`/templates/${id}`),
}
