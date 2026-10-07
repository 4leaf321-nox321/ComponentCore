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

/** 규격 부품의 종류 — 지그 생성기가 놓을 줄 아는 것만. */
export type StandardKind = 'support' | 'pin' | 'clamp'

export const STANDARD_KINDS: { value: StandardKind; label: string; hint: string }[] = [
  { value: 'support', label: '받침', hint: '바닥 중심이 원점, 위가 +Z. 제품 바닥에 닿는 윗면 지름과 높이.' },
  { value: 'pin', label: '위치 핀', hint: '바닥 중심이 원점, 위가 +Z. 구멍에 들어가는 지름과 판 위 길이.' },
  { value: 'clamp', label: '토글 클램프', hint: '베이스 바닥 중심이 원점, 팔이 +X. 누른 상태의 패드 중심이 (도달 거리, 0, 누르는 높이).' },
]

/**
 * **규격 부품 묶음** — 개발 PC 에서 내보내 운영 서버에서 가져오는 JSON 파일 하나(서버
 * `parts.schemas.StandardBundle`). 형상이 레시피뿐이라 따라가야 할 파일이 없다.
 */
export interface StandardBundle {
  format: 'compcore.standard-parts'
  format_version: number
  exported_at: string
  exported_from: string
  items: {
    name: string
    description: string
    tags: string[]
    folder: string
    standard: Record<string, unknown>
    recipe: Recipe
    origin: Record<string, unknown>
  }[]
}

/** 가져오기의 항목마다 할 일 — 새 부품 · 새 버전(형상이 다름) · 사양 수정 · 변경 없음 · 건너뜀. */
export type StandardImportAction = 'create' | 'version' | 'spec' | 'same' | 'skip'

export interface StandardImportItem {
  part_no: string
  name: string
  kind: string
  action: StandardImportAction
  part_id: string | null
  version: number | null
  problems: string[]
}

export interface StandardImportResult {
  dry_run: boolean
  items: StandardImportItem[]
}

/**
 * **규격 사양** — 관리자가 공용 부품에 붙인다(서버 `parts.schemas.StandardSpec`). 지그 생성기가
 * 요구에 맞는 것을 골라 놓고 부품표에 품번 · 수량을 남긴다.
 */
export interface StandardSpec {
  kind: StandardKind
  part_no: string
  maker?: string
  version: number
  preference?: number
  top_diameter?: number | null
  height?: number | null
  height_param?: string | null
  height_min?: number | null
  height_max?: number | null
  diameter?: number | null
  length?: number | null
  length_param?: string | null
  length_min?: number | null
  length_max?: number | null
  reach?: number | null
  pad_height?: number | null
  pad_diameter?: number | null
  base_length?: number | null
  base_width?: number | null
  /** 클램프: 베이스를 판에 고정하는 나사(`M5` …) — 생성기가 판에 그 탭 구멍을 낸다. */
  mount_thread?: string | null
  /** 클램프: 고정 구멍 자리 [x, y] — 클램프 좌표(베이스 바닥 중심이 원점, 팔이 +X). */
  mount_holes?: [number, number][] | null
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
  /** 규격 사양 — 관리자가 붙였으면. */
  standard?: StandardSpec | null
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
  standard?: StandardSpec | null
  updated_at: string
  /** 최신 버전의 형상 색인 — 이 기능 전의 버전이면 없다. */
  shape?: ShapeIndex | null
}

/** 목록을 거르는 폴더 — null 이면 전부, '' 이면 폴더 없는 것만(그때는 하위를 안 본다). */
export interface FolderFilter {
  /** 규격 부품만 — `any` 또는 종류. */
  standard?: '' | 'any' | StandardKind
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
    if (filter.standard) query.set('standard', filter.standard)
    return api.get<Page<PartSummary>>(`/parts?${query}`)
  },
  /** 규격 사양을 붙이거나 고친다 — 시스템 관리자만. 형상이 기준을 어기면 400 과 `details.problems`. */
  setStandard: (id: string, spec: StandardSpec) => api.put<Part>(`/parts/${id}/standard`, spec),
  clearStandard: (id: string) => api.delete<Part>(`/parts/${id}/standard`),
  /** 규격 부품 묶음을 만든다 — 시스템 관리자만. `ids` 가 비면 규격 부품 전부. */
  exportStandard: (ids: string[]) => api.post<StandardBundle>('/parts/standard/export', { ids }),
  /** 묶음을 가져온다 — 시스템 관리자만. `dryRun` 이면 아무것도 바꾸지 않고 할 일만 돌려준다. */
  importStandard: (bundle: StandardBundle, dryRun: boolean) =>
    api.post<StandardImportResult>(`/parts/standard/import?dry_run=${dryRun}`, bundle),
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
