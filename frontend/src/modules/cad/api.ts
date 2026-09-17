import { api, postForBlob } from '@/shared/api/client'

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

/** 상태 없는 레시피 API — 검증 · 미리보기 · 일회용 STEP. 저장은 `works` 의 일이다. */
export const cadApi = {
  schema: () => api.get<RecipeSchema>('/cad/recipe/schema'),
  check: (recipe: Recipe) => api.post<{ ok: boolean; problems: string[] }>('/cad/recipe/check', { recipe }),
  info: (recipe: Recipe) => api.post<{ summary: RecipeSummary }>('/cad/recipe/info', { recipe }),
  preview: (recipe: Recipe) => postForBlob('/cad/recipe/preview', { recipe }),
  step: (recipe: Recipe) => postForBlob('/cad/recipe/step', { recipe }),
}
