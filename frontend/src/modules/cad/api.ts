import { api, postForBlob } from '@/shared/api/client'
import type { DatumRow, FrameRow, MeshData } from '@/shared/viewer/PickViewer'

/** 레시피 — 서버 `core/recipe/schema.py` 가 정본. 화면은 JSON 으로만 다룬다. */
export type Recipe = {
  version?: number
  /**
   * 이름 붙인 치수 — 칸에 `"=이름 * 2"` 로 쓰면 하나를 고칠 때 다 따라온다. 값은 숫자 또는 다른
   * 변수로 쓴 식(`"=간격비 * 두께"`)이다.
   */
  params?: Record<string, number | string>
  nodes: Record<string, unknown>[]
  result?: string | null
  /** 이름 붙인 좌표계 — 형상과 무관하고 해석 조건의 `cs` 가 가리킨다. 식(`"=길이/2"`)을 쓴다. */
  coordinate_systems?: RecipeFrame[]
}

/** 도면의 표제란 · 용지. */
export interface DrawingOptions {
  title?: string
  sheet?: 'A3' | 'A4'
  material?: string
  note?: string
}

/** 도면 요약 — 서버 `core/drawing.Sheet.summary`. */
export interface DrawingSummary {
  sheet: string
  scale: string
  holes: { label: string; spec: string; view: string; x: number; y: number }[]
  dimensions: { value: number; direction: string }[]
  notes: string[]
}

/** 전개도 요약 — 서버 `core/recipe/unfold.Unfolded.summary`. */
export interface UnfoldSummary {
  thickness: number
  k_factor: number
  size: [number, number]
  area: number
  bends: { start: [number, number]; end: [number, number]; angle: number; radius: number; direction: 'up' | 'down'; allowance: number }[]
  notes: string[]
}

/**
 * 도면의 좌표계 하나 — 원점과 방향. 방향은 **X · Y 방향 벡터**(`x_axis` · `y_axis`) 또는
 * **회전**(`rotate` — X · Y · Z 축 순서, 도) 중 하나. 벡터가 있으면 벡터를 쓴다.
 */
export interface RecipeFrame {
  name: string
  origin?: (number | string)[]
  x_axis?: (number | string)[]
  y_axis?: (number | string)[]
  rotate?: (number | string)[]
}

/** 조립 구속 하나 — 서버 `schema.Mate`. `this` 는 구성품 자신(가져온 도면의 좌표)의 질의. */
export interface Mate {
  type: 'touch' | 'flush' | 'concentric' | 'parallel' | 'perpendicular' | 'angle'
  this: Record<string, unknown>
  /** 앞에 놓인 피처 id, 또는 기준(`X` · `XY` …). */
  to: string
  select?: Record<string, unknown> | null
  offset?: number | string
  angle?: number | string | null
  flip?: boolean
}

/** 구성품의 자리 — 회전 행렬 · 이동, 구속이 있으면 남은 움직임까지. */
export interface Placement {
  rotation: number[][]
  translation: number[]
  mates?: number
  free_rotation?: number
  free_translation?: number
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
  nodes: { id: string; op: string; kind: string; volume: number | null; faces: number; placement?: Placement | null }[]
  warnings: string[]
}

/**
 * 상태 없는 레시피 API — 검증 · 미리보기 · 내려받기. 저장은 남의 일이다:
 * 버전은 `works`, 시작점(템플릿)은 `templates`.
 */
/** 구조 프레임의 절단 목록 — 서버 `frame.cut_list`. 각은 도(0 = 직각). */
export interface CutList {
  node: string
  profile: string
  section_area: number
  items: { path: number; member: number; length: number; start_cut: number; end_cut: number; volume: number }[]
  count: number
  total_length: number
  total_volume: number
}

export const cadApi = {
  schema: () => api.get<RecipeSchema>('/cad/recipe/schema'),
  check: (recipe: Recipe) => api.post<{ ok: boolean; problems: string[] }>('/cad/recipe/check', { recipe }),
  info: (recipe: Recipe) => api.post<{ summary: RecipeSummary }>('/cad/recipe/info', { recipe }),
  preview: (recipe: Recipe) => postForBlob('/cad/recipe/preview', { recipe }),
  mesh: (recipe: Recipe) =>
    api.post<{ summary: RecipeSummary; mesh: MeshData; frames?: FrameRow[]; datums?: DatumRow[] }>('/cad/recipe/mesh', { recipe }),
  /** 구성품을 다른 것의 면에 얹는 translate — 서버가 경계 상자로 잰다. */
  place: (recipe: Recipe, body: { mover: string; onto: string; face: string; offset: number; align: string }) =>
    api.post<{ recipe: Recipe; translate: number[]; problems: string[] }>('/cad/recipe/place', { recipe, ...body }),
  /** 조립 구속을 눌러서 — 3D 에서 누른 면을 구속의 질의로(`this` 는 구성품 자신의 좌표로). */
  matePick: (recipe: Recipe, body: { node: string; side: 'this' | 'to'; target?: string; what?: 'faces' | 'edges'; point: number[] }) =>
    api.post<{ select: Record<string, unknown>; label: string }>('/cad/recipe/mate-pick', { recipe, ...body }),
  /** 조립의 구성품끼리 겹치는가 — 모든 쌍의 겹침 부피. */
  interference: (recipe: Recipe, tolerance?: number) => api.post<Interference>('/cad/recipe/interference', { recipe, tolerance }),
  /** 구조 프레임의 절단 목록 — 부재마다 자를 길이 · 끝의 각 · 부피. */
  cutList: (recipe: Recipe, node: string) => api.post<CutList>('/cad/recipe/cutlist', { recipe, node }),
  step: (recipe: Recipe) => postForBlob('/cad/recipe/step', { recipe }),
  /**
   * 전개도 — 굽힌 판을 펼친 모양. DXF 는 층으로 가른다(외곽 `OUTLINE` · 굽힘선 `BEND_UP` ·
   * `BEND_DOWN` · 글씨 `BEND_TEXT`). 판금이 아니면 400 과 까닭.
   */
  flat: (recipe: Recipe, format: 'dxf' | 'svg', options: { k_factor?: number; flip?: boolean } = {}) =>
    postForBlob(`/cad/recipe/unfold?format=${format}`, { recipe, ...options }),
  /**
   * 도면 — 3각법 세 뷰 · 전체 치수 · 구멍표 · 표제란. `pdf` · `dxf`(진짜 치수 객체) · `svg` ·
   * `png`. 축척은 표준 축척 중 들어가는 가장 큰 것.
   */
  drawing: (recipe: Recipe, format: 'pdf' | 'dxf' | 'svg' | 'png', options: DrawingOptions = {}) =>
    postForBlob(`/cad/recipe/drawing?format=${format}`, { recipe, ...options }),
  /** 구속 윤곽을 풀어 본다 — 점의 자리와 남은 움직임. 맞지 않는 구속은 400 과 몇째인지. */
  sketchSolve: (shape: Record<string, unknown>, params: Record<string, number>) =>
    api.post<{ points: Record<string, number[]>; free: number }>('/cad/recipe/sketch-solve', { shape, params }),
  /** 중간면 STEP — 얇은 판의 두께 가운데 면(셸 요소 해석용). 판이 아니면 400 과 까닭. */
  midsurface: (recipe: Recipe) => postForBlob('/cad/recipe/midsurface?format=step', { recipe }),
  /** 도면 요약 — 용지 · 축척 · 구멍표 · 치수 값. */
  drawingSummary: (recipe: Recipe, options: DrawingOptions = {}) => api.post<DrawingSummary>('/cad/recipe/drawing?format=json', { recipe, ...options }),
  /** 전개도 요약 — 두께 · 크기 · 넓이 · 굽힘(선 · 각 · 안쪽 반지름 · 위/아래 · 굽힘 여유). */
  unfold: (recipe: Recipe, options: { k_factor?: number; flip?: boolean } = {}) => api.post<UnfoldSummary>('/cad/recipe/unfold?format=json', { recipe, ...options }),
  stl: (recipe: Recipe) => postForBlob('/cad/recipe/stl', { recipe }),
  dxf: (recipe: Recipe) => postForBlob('/cad/recipe/dxf', { recipe }),
  svg: (recipe: Recipe) => postForBlob('/cad/recipe/svg', { recipe }),
}
