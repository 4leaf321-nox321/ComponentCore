/**
 * 시험 규격 — 공개 규격(ASTM · ISO, 서버 코드)과 사내 규격(DB)이 같은 모양의 프리셋이다(ADR 0006).
 * 프리셋으로 시편 · 시험 지그 · 해석 조건이 붙은 내 작업을 만든다. 사내 규격은 시스템 관리자만
 * 더하고 고친다(판정은 서버).
 */

import type { Recipe } from '@/modules/cad/api'
import type { Work } from '@/modules/works/api'
import { api } from '@/shared/api/client'

/** 두께에 따라 갈리는 반지름 한 줄 — 앞에서부터 처음 맞는 줄. 마지막 줄은 `max_thickness` 가 없다. */
export interface RadiusRule {
  radius: number
  max_thickness?: number | null
}

export type Radius = number | RadiusRule[]

/** 굽힘 프리셋(서버 `core.specimens.presets.BendingPreset`). */
export interface BendingPreset {
  id: string
  test: 'bending'
  family: 'bend_bar'
  standard: string
  name: string
  specimen: { length: number; width: number; thickness: number }
  setup: {
    points: 3 | 4
    span: { to_thickness?: number | null; value?: number | null }
    load_span?: { to_span?: number | null; value?: number | null } | null
    support_radius: Radius
    nose_radius: Radius
    overhang?: { to_span: number; min: number }
  }
  analysis: { strain: number; friction: number }
  source: string
  verified: boolean
  note: string
}

export interface PresetRow {
  id: string
  origin: 'builtin' | 'internal'
  test: string
  standard: string
  name: string
  preset: BendingPreset
  updated_at?: string | null
  updated_by_name?: string | null
}

export interface SpecimenRequest {
  preset_id: string
  length?: number | null
  width?: number | null
  thickness?: number | null
  fixture?: boolean
  conditions?: boolean
}

export interface SpecimenBuild {
  recipe: Recipe
  conditions: Record<string, unknown> | null
  notes: string[]
  values: Record<string, number>
}

/** 시험 종류 — 서버 `core.specimens.TESTS` 와 같다. */
export const TESTS: { value: string; label: string }[] = [{ value: 'bending', label: '굽힘' }]

export const specimensApi = {
  list: (test = '') => api.get<PresetRow[]>(`/specimens/presets${test ? `?test=${encodeURIComponent(test)}` : ''}`),
  get: (id: string) => api.get<PresetRow>(`/specimens/presets/${encodeURIComponent(id)}`),
  /** 사내 규격을 더한다 — 시스템 관리자만. 값이 틀리면 400 과 `details.problems`. */
  create: (preset: Omit<BendingPreset, 'id'> & { id?: string }) => api.post<PresetRow>('/specimens/presets', { preset }),
  update: (id: string, preset: Omit<BendingPreset, 'id'> & { id?: string }) => api.put<PresetRow>(`/specimens/presets/${encodeURIComponent(id)}`, { preset }),
  remove: (id: string) => api.delete<void>(`/specimens/presets/${encodeURIComponent(id)}`),
  /** 시편(과 시험 지그 · 해석 조건)을 그려 본다 — 저장하지 않는다. */
  build: (request: SpecimenRequest) => api.post<SpecimenBuild>('/specimens/build', request),
  /** 내 작업을 만든다 — 첫 버전이 시편 레시피, 해석 조건까지. */
  createWork: (request: SpecimenRequest & { name?: string; folder?: string }) => api.post<Work>('/specimens/works', request),
}

/** 지지 간격의 규칙을 사람 말로 — `16 × 두께` 또는 `40 mm`. */
export function spanText(preset: BendingPreset): string {
  const span = preset.setup.span
  return span.to_thickness ? `${span.to_thickness} × 두께` : `${span.value} mm`
}

/** 반지름 — 하나면 그 값, 두께별이면 `2 (두께 3 이하) / 5`. */
export function radiusText(radius: Radius): string {
  if (typeof radius === 'number') return `${radius}`
  return radius.map((one) => (one.max_thickness ? `${one.radius} (두께 ${one.max_thickness} 이하)` : `${one.radius}`)).join(' / ')
}

/** 4점 굽힘의 하중 간격 — `지지 간격의 0.3333` 또는 `20 mm`. 3점이면 빈 글자. */
export function loadSpanText(preset: BendingPreset): string {
  const rule = preset.setup.load_span
  if (preset.setup.points === 3 || !rule) return ''
  return rule.to_span ? `지지 간격 × ${rule.to_span}` : `${rule.value} mm`
}
