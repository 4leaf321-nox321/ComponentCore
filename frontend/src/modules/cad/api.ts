import { api, postForBlob } from '@/shared/api/client'
import type { MeshData } from '@/shared/viewer/PickViewer'

/** 레시피 — 서버 `core/recipe/schema.py` 가 정본. 화면은 JSON 으로만 다룬다. */
export type Recipe = {
  version?: number
  /** 이름 붙인 치수 — 칸에 `"=이름 * 2"` 로 쓰면 하나를 고칠 때 다 따라온다. */
  params?: Record<string, number>
  nodes: Record<string, unknown>[]
  result?: string | null
}

export interface Interference {
  ok: boolean
  tolerance: number
  total_volume: number
  items: { a: string; b: string; volume: number; ok: boolean }[]
  parts: string[]
  checked_pairs: number
}

export interface RecipeSchema {
  schema: Record<string, unknown>
  templates: Record<string, Recipe>
  template_labels: Record<string, string>
}

export interface RecipeSummary {
  /** 아직 2D — 스케치까지만 그렸다. 저장 · 지그는 입체여야 한다. */
  is_sketch: boolean
  bbox: { min: number[]; max: number[]; size: number[] }
  volume: number
  surface_area: number
  solid_count: number
  face_count: number
  edge_count: number
  nodes: { id: string; op: string; kind: string; volume: number | null; faces: number }[]
  warnings: string[]
}

/**
 * 상태 없는 레시피 API — 검증 · 미리보기 · 내려받기. 저장은 남의 일이다:
 * 버전은 `works`, 시작점(템플릿)은 `templates`.
 */
export const cadApi = {
  schema: () => api.get<RecipeSchema>('/cad/recipe/schema'),
  check: (recipe: Recipe) => api.post<{ ok: boolean; problems: string[] }>('/cad/recipe/check', { recipe }),
  info: (recipe: Recipe) => api.post<{ summary: RecipeSummary }>('/cad/recipe/info', { recipe }),
  preview: (recipe: Recipe) => postForBlob('/cad/recipe/preview', { recipe }),
  mesh: (recipe: Recipe) => api.post<{ summary: RecipeSummary; mesh: MeshData }>('/cad/recipe/mesh', { recipe }),
  /** 구성품을 다른 것의 면에 얹는 translate — 서버가 경계 상자로 잰다. */
  place: (recipe: Recipe, body: { mover: string; onto: string; face: string; offset: number; align: string }) =>
    api.post<{ recipe: Recipe; translate: number[]; problems: string[] }>('/cad/recipe/place', { recipe, ...body }),
  /** 조립의 구성품끼리 겹치는가 — 모든 쌍의 겹침 부피. */
  interference: (recipe: Recipe, tolerance?: number) => api.post<Interference>('/cad/recipe/interference', { recipe, tolerance }),
  step: (recipe: Recipe) => postForBlob('/cad/recipe/step', { recipe }),
  stl: (recipe: Recipe) => postForBlob('/cad/recipe/stl', { recipe }),
  dxf: (recipe: Recipe) => postForBlob('/cad/recipe/dxf', { recipe }),
  svg: (recipe: Recipe) => postForBlob('/cad/recipe/svg', { recipe }),
}
