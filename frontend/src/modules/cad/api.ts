import { api, postForBlob } from '@/shared/api/client'
import type { MeshData } from '@/shared/viewer/PickViewer'

/** 레시피 — 서버 `core/recipe/schema.py` 가 정본. 화면은 JSON 으로만 다룬다. */
export type Recipe = { version?: number; nodes: Record<string, unknown>[]; result?: string | null }

export interface RecipeSchema {
  schema: Record<string, unknown>
  templates: Record<string, Recipe>
  template_labels: Record<string, string>
}

export interface RecipeSummary {
  bbox: { min: number[]; max: number[]; size: number[] }
  volume: number
  surface_area: number
  solid_count: number
  face_count: number
  edge_count: number
  nodes: { id: string; op: string; kind: string; volume: number | null; faces: number }[]
  warnings: string[]
}

export interface RecipeTemplate {
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  recipe: Recipe
  is_shared: boolean
  mine: boolean
  updated_at: string
}

/** 상태 없는 레시피 API — 검증 · 미리보기 · 일회용 STEP — 와 저장한 템플릿. 작업 저장은 `works`. */
export const cadApi = {
  templates: () => api.get<RecipeTemplate[]>('/cad/templates'),
  createTemplate: (body: { name: string; description?: string; recipe: Recipe; is_shared?: boolean }) =>
    api.post<RecipeTemplate>('/cad/templates', body),
  updateTemplate: (id: string, body: { name?: string; description?: string; recipe?: Recipe; is_shared?: boolean }) =>
    api.patch<RecipeTemplate>(`/cad/templates/${id}`, body),
  removeTemplate: (id: string) => api.delete<void>(`/cad/templates/${id}`),
  schema: () => api.get<RecipeSchema>('/cad/recipe/schema'),
  check: (recipe: Recipe) => api.post<{ ok: boolean; problems: string[] }>('/cad/recipe/check', { recipe }),
  info: (recipe: Recipe) => api.post<{ summary: RecipeSummary }>('/cad/recipe/info', { recipe }),
  preview: (recipe: Recipe) => postForBlob('/cad/recipe/preview', { recipe }),
  mesh: (recipe: Recipe) => api.post<{ summary: RecipeSummary; mesh: MeshData }>('/cad/recipe/mesh', { recipe }),
  step: (recipe: Recipe) => postForBlob('/cad/recipe/step', { recipe }),
}
