import type { Recipe } from '@/modules/cad/api'
import { api } from '@/shared/api/client'
import type { ShapeIndex } from '@/shared/components/ShapeFilter'

export type SimilarWhere = 'works' | 'parts' | 'jigs'

/** 닮은 것 한 줄 — 서버 `search/services.similar`. */
export interface SimilarItem {
  /** `work:<id>` · `part:<id>` · `jig:<id>` — 어디서 왔나는 접두가 말한다. */
  source: string
  /** 작업이면 그 종류(part · jig · assembly), 카탈로그면 part · jig. */
  kind: string
  name: string
  folder: string
  version: number
  /** 0 ~ 1. */
  score: number
  /** 성분별 닮음 — size · proportion · fill · holes · ops · solids(없는 성분은 빠진다). */
  parts: Record<string, number>
  /** 사람 말 — 「크기 비슷」 · 「구멍 같음」 … */
  why: string[]
  shape: Pick<ShapeIndex, 'size' | 'dims' | 'volume' | 'holes' | 'hole_count'>
  /** 부품이면 그 부품의 지그 — 지그를 새로 만들기 전에 다시 쓸 길. */
  jigs?: { source: string; name: string }[]
  /** 지그면 어느 부품의 지그인가. */
  part_name?: string | null
}

export interface SimilarAnswer {
  reference: { source: string | null } & Partial<ShapeIndex>
  /** 견준 후보 수(가장 긴 변이 네 배 안인 것). */
  compared: number
  items: SimilarItem[]
}

export const searchApi = {
  /** 닮은 형상 — 이미 있는 것(`source`) 또는 저장 전 레시피(`recipe`)와. */
  similar: (body: { source?: string; recipe?: Recipe; where?: SimilarWhere[]; limit?: number }) => api.post<SimilarAnswer>('/search/similar', body),
}

/** `work:<id>` → 그 화면의 주소와 이름표. */
export function placeOf(source: string): { to: string; label: string } {
  const [kind, id] = source.split(':')
  if (kind === 'work') return { to: `/works/${id}`, label: '내 작업' }
  if (kind === 'part') return { to: `/parts/${id}`, label: '부품' }
  return { to: `/jigs/${id}`, label: '지그' }
}
