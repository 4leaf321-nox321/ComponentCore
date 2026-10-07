/**
 * 시험 규격 — 공개 규격(ASTM · ISO · IEC, 서버 코드)과 사내 규격(DB)이 같은 모양의 프리셋이다
 * (ADR 0006). 시편 시험(굽힘 · 인장 · 전단 · 접착 이음)은 시편 · 시험 지그 · 해석 조건이 붙은 내
 * 작업을 만들고, 제품 시험(정하중 · 손잡이 · 압축 · 비틀림 · 진동 · 고유진동수)은 사용자의 제품에
 * 건다. 사내 규격은 시스템 관리자만 더하고 고친다(판정은 서버).
 */

import type { Recipe } from '@/modules/cad/api'
import type { Work } from '@/modules/works/api'
import { api } from '@/shared/api/client'
import type { MeshData } from '@/shared/viewer/PickViewer'

/** 두께에 따라 갈리는 반지름 한 줄 — 앞에서부터 처음 맞는 줄. 마지막 줄은 `max_thickness` 가 없다. */
export interface RadiusRule {
  radius: number
  max_thickness?: number | null
}

export type Radius = number | RadiusRule[]

/** 프리셋마다 있는 칸 — 규격 번호 · 이름 · 출처 · 검토 여부. */
interface PresetCommon {
  id: string
  standard: string
  name: string
  source: string
  verified: boolean
  note: string
}

/** 굽힘 프리셋(서버 `core.specimens.presets.BendingPreset`) — 시편을 그린다. */
export interface BendingPreset extends PresetCommon {
  test: 'bending'
  family: 'bend_bar'
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
}

/** 정하중 프리셋(IEC 62368-1 부속서 T 등) — 제품 윗면을 원형 접촉면으로 누른다. */
export interface ForcePreset extends PresetCommon {
  test: 'force'
  setup: { force: number; probe_diameter: number }
  analysis: { large_deflection: boolean }
}

/** 정현파 진동 프리셋(IEC 60068-2-6) — 아랫면을 고정하고 한 축으로 가속도를 준다. */
export interface VibrationPreset extends PresetCommon {
  test: 'vibration'
  setup: { freq_min: number; freq_max: number; acceleration_g: number; damping_ratio: number; modes: number; points: number }
}

/** 인장 프리셋(ASTM E8 · D638 · D3039, ISO 527) — 도그본은 평행부 · 반지름이 있고 띠는 없다. */
export interface TensilePreset extends PresetCommon {
  test: 'tensile'
  family: 'dogbone' | 'strip' | 'open_hole'
  specimen: {
    length: number
    width: number
    thickness: number
    gauge_length: number
    grip_length: number
    gauge_width?: number | null
    parallel_length?: number | null
    radius?: number | null
    hole_diameter?: number | null
  }
  analysis: { strain: number; large_deflection: boolean }
}

/** V 노치 전단 프리셋(ASTM D5379 · D7078). */
export interface ShearPreset extends PresetCommon {
  test: 'shear'
  family: 'v_notch'
  specimen: { length: number; width: number; thickness: number; notch_depth: number; notch_angle: number; notch_radius: number; grip_gap: number }
  analysis: { shear_strain: number }
}

/** 접착 겹치기 이음 프리셋(ASTM D1002 · D5868, ISO 4587). */
export interface LapPreset extends PresetCommon {
  test: 'lap'
  family: 'single_lap'
  specimen: { length: number; width: number; thickness: number; overlap: number; bondline: number; grip_length: number }
  analysis: { displacement: number; large_deflection: boolean }
}

/** 손잡이 · 벽걸이(IEC 62368-1 8.8 · 8.7) — 고른 자리를 고정하고 무게의 배수를 아래로. */
export interface HandlePreset extends PresetCommon {
  test: 'handle'
  setup: { weight_factor: number }
  analysis: { large_deflection: boolean }
}

/** 적층 압축(ASTM D642 · ISO 12048 · ISTA) — 단수 또는 적재 높이 중 하나. */
export interface CompressionPreset extends PresetCommon {
  test: 'compression'
  setup: { layers?: number | null; stack_height?: number | null; factor: number }
  analysis: { large_deflection: boolean }
}

/** 비틀림 — 긴 축의 한쪽 끝을 고정하고 다른 끝을 돌린다. */
export interface TorsionPreset extends PresetCommon {
  test: 'torsion'
  setup: { angle: number }
  analysis: { large_deflection: boolean }
}

/** 고유진동수(진동 응답 조사 · 자유-자유 공진). */
export interface ModalPreset extends PresetCommon {
  test: 'modal'
  setup: { modes: number; freq_min: number; freq_max?: number | null; support: 'fixed' | 'free' }
}

/** 압축 시편(ASTM D695 · D6641 · D6484 · E9, ISO 604 · 14126) — 세운 각기둥 · 원기둥, 눕힌 띠 · 구멍 띠. */
export interface CompressivePreset extends PresetCommon {
  test: 'compressive'
  family: 'prism' | 'cylinder' | 'strip' | 'open_hole'
  specimen: { length: number; width: number; thickness?: number | null; grip_length?: number | null; hole_diameter?: number | null }
  analysis: { strain: number; large_deflection: boolean }
}

/** 체결부(ASTM D5961 핀 베어링 · D7332 뽑힘). */
export interface FastenerPreset extends PresetCommon {
  test: 'fastener'
  family: 'bearing' | 'pull_through'
  specimen: {
    length: number
    width: number
    thickness: number
    hole_diameter: number
    edge_distance?: number | null
    grip_length?: number | null
    head_diameter?: number | null
    head_height?: number | null
    support_diameter?: number | null
  }
  analysis: { displacement: number; friction: number; large_deflection: boolean }
}

/** 압착(IEC 62133-2 · UN 38.3) — 평판 둘 사이에서 누른다. */
export interface CrushPreset extends PresetCommon {
  test: 'crush'
  setup: { force: number }
  analysis: { large_deflection: boolean }
}

/** 수압(IEC 60529) — 바깥 면에 물 깊이만큼의 압력. */
export interface PressurePreset extends PresetCommon {
  test: 'pressure'
  setup: { depth: number; factor: number }
  analysis: { large_deflection: boolean }
}

/** 등가 정적 가속도(IEC 60068-2-27 · ISO 16750-3) — 충격을 정적 가속도로 근사. */
export interface AccelerationPreset extends PresetCommon {
  test: 'acceleration'
  setup: { acceleration_g: number; duration_ms?: number | null; factor: number }
  analysis: { large_deflection: boolean }
}

/** 방향 하중(IEC 60335-1 코드 고정 · USB Type-C 렌칭) — 고른 면에 정한 방향의 힘 · 모멘트. */
export interface DirectedPreset extends PresetCommon {
  test: 'directed'
  setup: { force?: number | null; torque?: number | null }
  analysis: { large_deflection: boolean }
}

export type AnyPreset =
  | BendingPreset
  | TensilePreset
  | CompressivePreset
  | ShearPreset
  | LapPreset
  | FastenerPreset
  | ForcePreset
  | DirectedPreset
  | HandlePreset
  | CrushPreset
  | CompressionPreset
  | PressurePreset
  | TorsionPreset
  | AccelerationPreset
  | VibrationPreset
  | ModalPreset
export type TestKey = AnyPreset['test']
/** 저장할 프리셋 — id 는 서버가 정한다. 종류마다 나눠 뺀다(합친 타입에 Omit 을 걸면 공통 칸만 남는다). */
export type NewPreset<P extends AnyPreset = AnyPreset> = P extends AnyPreset ? Omit<P, 'id'> : never
/** 시편을 그리는 시험. */
export type SpecimenPreset = BendingPreset | CouponPreset
/** 제품에 거는 시험 — 시편을 그리지 않는다. */
export type ProductPreset = ForcePreset | DirectedPreset | HandlePreset | CrushPreset | CompressionPreset | PressurePreset | TorsionPreset | AccelerationPreset | VibrationPreset | ModalPreset
/** 굽힘이 아닌 시편 — 칸 정의(`kinds.ts`)로 그린다. */
export type CouponPreset = TensilePreset | CompressivePreset | ShearPreset | LapPreset | FastenerPreset

export interface PresetRow<P extends AnyPreset = AnyPreset> {
  id: string
  origin: 'builtin' | 'internal'
  test: string
  standard: string
  name: string
  preset: P
  updated_at?: string | null
  updated_by_name?: string | null
}

/** 제품에 거는 시험의 종류 — 서버 `core.specimens.PRODUCT_TESTS` 와 같다. */
export const PRODUCT_TESTS: TestKey[] = ['force', 'directed', 'handle', 'crush', 'compression', 'pressure', 'torsion', 'acceleration', 'vibration', 'modal']
/** 굽힘이 아닌 시편 시험. */
export const COUPON_TESTS: TestKey[] = ['tensile', 'compressive', 'shear', 'lap', 'fastener']

export const isBending = (row: PresetRow): row is PresetRow<BendingPreset> => row.preset.test === 'bending'
export const isProduct = (row: PresetRow): row is PresetRow<ProductPreset> => PRODUCT_TESTS.includes(row.preset.test)
export const isCoupon = (row: PresetRow): row is PresetRow<CouponPreset> => COUPON_TESTS.includes(row.preset.test)

/** 3D 에서 고른 면 — 누른 점, 그 자리의 법선, 면 종류. */
export interface FacePick {
  point: [number, number, number]
  normal: [number, number, number]
  kind: string
}

/** 고를 수 있는 자리 — support(고정 면) · load(누를 면) · twist(비트는 끝). */
export type FaceSlot = 'support' | 'load' | 'twist'

export interface ProductTestRequest {
  preset_id: string
  /** `work:<내 부품 작업 id>` 또는 `part:<공용 부품 id>`. */
  source: string
  x?: number | null
  y?: number | null
  z?: number | null
  /** 진동 · 등가 가속도 방향(비우면 Z) · 비틀림 축(비우면 가장 긴 축). */
  axis?: 'x' | 'y' | 'z' | null
  faces?: Partial<Record<FaceSlot, FacePick[]>>
  /** 제품 무게(kg) — 적층 압축. */
  mass?: number | null
  /** 방향 하중의 방향(힘의 방향 · 모멘트 축) — 비우면 고른 평면에서 바깥으로. */
  direction?: [number, number, number] | null
  name?: string
  folder?: string
}

export interface SpecimenRequest {
  preset_id: string
  length?: number | null
  width?: number | null
  thickness?: number | null
  /** 그 밖의 시편 치수 — 프리셋 `specimen` 의 칸 이름 → 값. */
  dimensions?: Record<string, number>
  fixture?: boolean
  conditions?: boolean
}

export interface SpecimenBuild {
  recipe: Recipe
  conditions: Record<string, unknown> | null
  notes: string[]
  values: Record<string, number>
}

/** 시험 종류 — 서버 `core.specimens.TESTS` 와 같다(이 순서로 보인다). */
export const TESTS: { value: TestKey; label: string }[] = [
  { value: 'bending', label: '굽힘' },
  { value: 'tensile', label: '인장' },
  { value: 'compressive', label: '압축' },
  { value: 'shear', label: '전단' },
  { value: 'lap', label: '접착 이음' },
  { value: 'fastener', label: '체결부' },
  { value: 'force', label: '정하중' },
  { value: 'directed', label: '방향 하중' },
  { value: 'handle', label: '손잡이·벽걸이' },
  { value: 'crush', label: '압착' },
  { value: 'compression', label: '적층 압축' },
  { value: 'pressure', label: '수압' },
  { value: 'torsion', label: '비틀림' },
  { value: 'acceleration', label: '등가 가속도' },
  { value: 'vibration', label: '진동' },
  { value: 'modal', label: '고유진동수' },
]

export const specimensApi = {
  list: (test = '') => api.get<PresetRow[]>(`/specimens/presets${test ? `?test=${encodeURIComponent(test)}` : ''}`),
  get: (id: string) => api.get<PresetRow>(`/specimens/presets/${encodeURIComponent(id)}`),
  /** 사내 규격을 더한다 — 시스템 관리자만. 값이 틀리면 400 과 `details.problems`. */
  create: (preset: NewPreset) => api.post<PresetRow>('/specimens/presets', { preset }),
  update: (id: string, preset: NewPreset) => api.put<PresetRow>(`/specimens/presets/${encodeURIComponent(id)}`, { preset }),
  remove: (id: string) => api.delete<void>(`/specimens/presets/${encodeURIComponent(id)}`),
  /** 시편(과 시험 지그 · 해석 조건)을 그려 본다 — 저장하지 않는다. */
  build: (request: SpecimenRequest) => api.post<SpecimenBuild>('/specimens/build', request),
  /** 내 작업을 만든다 — 첫 버전이 시편 레시피, 해석 조건까지. */
  createWork: (request: SpecimenRequest & { name?: string; folder?: string }) => api.post<Work>('/specimens/works', request),
  /** 제품에 시험 규격을 건 새 작업. 제품의 물성은 그대로 따라온다. */
  applyProductTest: (request: ProductTestRequest) => api.post<Work>('/specimens/product-tests', request),
  /** 제품의 면 · 엣지 메시 — 「제품에 적용」 이 3D 에서 면을 고르게. */
  productMesh: (source: string) => api.post<{ summary: { bbox: { min: number[]; max: number[] } }; mesh: MeshData }>('/specimens/product-mesh', { source }),
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
