/**
 * 해석 조건 — 화면이 쓰는 말과 길.
 *
 * **칸 목록을 화면에 박지 않는다.** 조건 종류가 열 몇이고 칸이 제각각이라(고정 지지에는 값이
 * 없고, 압력에는 크기와 방향이, 볼트에는 N 이) 여기 적어 두면 종류를 더할 때마다 화면을
 * 고쳐야 한다. 정본은 서버(`GET /cad/conditions/schema`)이고 화면은 그것으로 폼을 그린다 —
 * CAD 리본이 `OP_SPECS` 로 하는 것과 같다.
 */

import type { Recipe } from '@/modules/cad/api'
import { api } from '@/shared/api/client'

export interface FieldSchema {
  title?: string
  type?: string
  enum?: string[]
  anyOf?: { type?: string; enum?: string[] }[]
  description?: string
  default?: unknown
}

export interface GroupSchema {
  label: string
  /** 이 묶음에 더할 수 있는 종류 — 화면의 「+ 조건」 목록. */
  types: string[]
  fields: Record<string, FieldSchema>
  required: string[]
}

/** 고를 수 있는 단위계 하나 — 서버가 정본이다(화면에 목록을 박지 않는다). */
export interface UnitSystem {
  key: string
  label: string
  length: string
  mass: string
  force: string
  stress: string
  density: string
  [field: string]: string
}

export interface ConditionsSchema {
  schema_version: number
  units: { system: string }
  /**
   * **닫히는 계만 고를 수 있다.** 낱낱이 적게 두면 `mm·kg·s·N` 같은 조합을 적을 수 있는데,
   * 그 계의 힘은 N 이 아니라 mN 이고 응력은 kPa 다 — 조용하다가 어느 날 10³ 배 틀린다.
   */
  unit_systems: UnitSystem[]
  analysis: { properties?: Record<string, FieldSchema> }
  groups: Record<string, GroupSchema>
  entities: string[]
}

/** 이름표 — 조건이 붙는 유일한 창구. 좌표가 아니라 **셀렉터**로 적힌다. */
export interface NamedSelection {
  name: string
  entity: string
  select: Record<string, unknown>
}

export interface ConditionItem {
  [key: string]: unknown
  name?: string
  type?: string
  on?: string
}

export interface Conditions {
  schema_version?: number
  units?: { system: string }
  named_selections: NamedSelection[]
  materials: ConditionItem[]
  constraints: ConditionItem[]
  loads: ConditionItem[]
  contacts: ConditionItem[]
  initial: ConditionItem[]
  analysis: Record<string, unknown>
  mesh_hints: ConditionItem[]
}

/** 조건이 담기는 묶음들 — 이름표와 해석 설정은 따로 다룬다. */
export const GROUP_KEYS = [
  'constraints',
  'loads',
  'contacts',
  'initial',
  'mesh_hints',
] as const

export function emptyConditions(): Conditions {
  return {
    schema_version: 1,
    // 기본은 mm·t·s — CAD 가 mm 라 해석도 mm 으로 푼다(FE 의 사실상 표준).
    units: { system: 'mm_n_tonne' },
    named_selections: [],
    materials: [],
    constraints: [],
    loads: [],
    contacts: [],
    initial: [],
    analysis: { type: 'modal', modes: 6 },
    mesh_hints: [],
  }
}

/** 서버가 준 것을 화면이 쓰는 모양으로 — 빈 칸을 채워 두면 화면에 `?.` 가 줄어든다. */
export function asConditions(raw: unknown): Conditions {
  const empty = emptyConditions()
  if (!raw || typeof raw !== 'object') return empty
  return { ...empty, ...(raw as Partial<Conditions>) }
}

/** 3D 에서 찍은 자리 하나에 대한 **셀렉터 후보**. */
export interface SelectorCandidate {
  label: string
  select: Record<string, unknown>
  /** 지금 몇 개에 맞나 — 1 이면 이것 하나, 여럿이면 그 부류 전부. */
  matches: number
}

/** 도면의 바디 하나 — 물성이 붙는 자리. 내보낼 때의 `topology.bodies` 와 같은 줄이다. */
export interface Body {
  name: string
  /** STEP 안에서의 이름(`body_1`) — 해석 쪽이 짝지을 때 쓴다. */
  step_product?: string
  volume?: number
  centroid?: number[]
  bbox?: number[][]
}

export const conditionsApi = {
  /**
   * 이 도면의 **바디 목록** — 물성이 「어디에」 붙는지 고를 손잡이.
   *
   * 메시의 면에서 지어내지 않는 까닭: 내보낼 때 쓰는 이름은 `topology.bodies` 가 정한다.
   * 화면이 따로 지으면 두 곳이 어긋나는 날 **사람이 고른 이름이 폴더에 없는 이름**이 된다.
   */
  bodies: (recipe: Recipe) => api.post<{ items: Body[] }>('/cad/recipe/bodies', { recipe }),
  schema: () => api.get<ConditionsSchema>('/cad/conditions/schema'),

  /** 찍은 자리를 말로 되돌려 받는다. `what` 은 faces · edges · vertices. */
  selectors: (recipe: Recipe, what: string, point: number[]) =>
    api.post<{ picked: Record<string, unknown> | null; candidates: SelectorCandidate[] }>(
      '/cad/recipe/selectors',
      { recipe, pick: { what, point } },
    ),

  /** 버전에 붙인다 — **새 버전을 만들지 않는다**(도면이 안 바뀌었으니까). */
  save: (workId: string, number: number, conditions: Conditions) =>
    api.put<{ conditions: Conditions }>(`/works/${workId}/versions/${number}/conditions`, {
      conditions,
    }),
}
