/**
 * 해석 조건 — 화면이 쓰는 말과 길.
 *
 * **칸 목록을 화면에 박지 않는다.** 조건 종류가 열 몇이고 칸이 제각각이라(고정 지지에는 값이
 * 없고, 압력에는 크기와 방향이, 볼트에는 N 이) 여기 적어 두면 종류를 더할 때마다 화면을
 * 고쳐야 한다. 정본은 서버(`GET /cad/conditions/schema`)이고 화면은 그것으로 폼을 그린다 —
 * CAD 리본이 `OP_SPECS` 로 하는 것과 같다.
 */

import type { Recipe } from '@/modules/cad/api'
import type { FrameDraft } from '@/modules/cad/FrameForm'
import type { FrameRow } from '@/shared/viewer/PickViewer'
import { api } from '@/shared/api/client'

export interface FieldSchema {
  title?: string
  type?: string
  enum?: string[]
  anyOf?: { type?: string; enum?: string[] }[]
  description?: string
  default?: unknown
  /** 성분 칸 — 빈칸 · 0 을 묵시적으로 읽게 두지 않고 「자유 · 고정 · 변위량」 을 고르게 그린다. */
  component?: boolean
  /** 이 칸을 쓰는 종류 — 다른 종류면 그리지 않는다. */
  only_for?: string[]
  /** 고르는 값의 사람 이름(`{rigid: '강체'}`) — 없으면 값 그대로 보인다. */
  labels?: Record<string, string>
  /** 폼에 그리지 않는다 — 서버가 채운다(하중의 `unit`). */
  hidden?: boolean
  /** 방향 칸 — 좌표계의 X · Y · Z 성분, `normal_for` 종류면 「면의 법선」 도. */
  direction?: boolean
  normal_for?: string[]
  /** 볼트 예압 — 예압(힘) · 조임량(길이)을 `unit` 으로 고른다. */
  bolt?: boolean
  /** 크기 — 단위는 종류의 차원(`GroupSchema.dimensions`)과 단위계가 정한다. */
  unit_by_type?: boolean
  /** 값의 단위 — 단위계 이름표의 열쇠(`length` → mm · m). */
  dimension?: string
  /** 칸의 단위(`도` · `mm` · `°C`) — 조건은 늘 mm · N · t 로 적으므로 고정된 이름이다. */
  unit?: string
  /** 「전체」 처럼 선택 그룹 대신 고를 수 있는 값(메시 힌트). */
  whole?: string
  /** 세 성분(X · Y · Z) 칸 — 속도처럼 방향이 아닌 벡터. */
  components?: boolean
  /** 정수만 받는다(경계층 수) — 식을 쓸 수 없다. */
  integer?: boolean
  /** 최소 · 최대 두 값(주파수 범위). */
  range?: boolean
  /** 종류 안에서 다른 칸의 값에 따라 보인다 — `{종류: {칸: 값}}`(열 과도의 시간 칸). */
  when?: Record<string, Record<string, unknown>>
}

export interface GroupSchema {
  label: string
  /** 이 묶음에 더할 수 있는 종류 — 화면의 「+ 조건」 목록. */
  types: string[]
  fields: Record<string, FieldSchema>
  required: string[]
  /** 종류가 스스로 정하는 방향(구속) — 고칠 수 없고, 화면이 잠긴 칸으로 보여 준다. */
  implied?: Record<string, ImpliedHold[]>
  /** 종류마다 한 줄 설명 — 종류 아래에 보인다. */
  notes?: Record<string, string>
  /** 묶음 전체에 대한 한두 줄 — 창 맨 위에 보인다. */
  intro?: string
  /** 종류 → 크기의 차원(단위계 이름표의 열쇠, 예: `stress`). */
  dimensions?: Record<string, string>
  /**
   * 종류 → **받는 선택 그룹** — `[{entity, kind?}]`(압력은 면, 베어링은 원통면 …). 없는 종류는
   * 대상이 없다. `kind` 는 선택 규칙에 적혀 있어야 한다(서버가 저장할 때 본다).
   */
  accepts?: Record<string, TargetKind[]>
}

/** 조건이 받는 선택 그룹 하나 — 종류(면 · 엣지 · 점 · 바디)와, 면이면 모양(원통면). */
export interface TargetKind {
  entity: 'face' | 'edge' | 'vertex' | 'body'
  kind?: string
}

const ENTITY_LABELS: Record<string, string> = { face: '면', edge: '엣지', vertex: '점', body: '바디' }
const KIND_LABELS: Record<string, string> = { cylinder: '원통면' }

/** 「원통면 · 바디」 처럼 — 받는 것을 사람 말로. */
export function acceptsLabel(accepts: TargetKind[]): string {
  return accepts.map((one) => (one.kind ? KIND_LABELS[one.kind] ?? one.kind : ENTITY_LABELS[one.entity])).join(' · ')
}

export interface ImpliedHold {
  label: string
  hold: 'fixed' | 'free' | 'spring'
  hint: string
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
  /** 조건의 값을 적는 계(`mm_n_tonne`) — `units.system` 은 내보내기 계다. */
  input_system?: string
  /** 해석 설정 — 한 벌에 하나라 묶음이 아니지만 같은 폼으로 그린다. */
  analysis: { properties?: Record<string, FieldSchema>; notes?: Record<string, string>; intro?: string }
  groups: Record<string, GroupSchema>
  entities: string[]
}

/**
 * 선택 그룹(`named_selections`) — 조건이 붙는 유일한 창구. 좌표가 아니라 **셀렉터**로 적힌다.
 * 여럿을 묶은 그룹은 `select` 가 `{ any: [셀렉터, …] }` — 고른 것마다의 규칙의 합이다.
 */
export interface NamedSelection {
  name: string
  entity: string
  select: Record<string, unknown>
}

/** 조건 한 벌에 실린 물성 하나. */
export interface MaterialItem extends ConditionItem {
  /**
   * 이 물성이 붙은 **파트(바디)들** — `topology.bodies` 의 이름. 「전체」 면 모든 바디.
   * **비어 있으면 아직 아무 데도 안 붙은 것이다**(담아만 둔 재료). 옛 값은 문자열 하나다 —
   * 읽을 때는 `appliedTo` 를 거친다.
   */
  apply_to?: string[] | string
  ref?: Record<string, unknown>
  payload?: Record<string, unknown>
  /**
   * **함께 내보낼 솔버 덱 형식**(`ansys` · `nastran` …). 비면 안 만든다.
   *
   * 중립 payload 를 대신하지 않고 덤으로 간다 — 글월은 여기 안 담고 **내보낼 때** 뽑는다
   * (재료가 여럿이면 덱 안의 번호가 서로 달라야 하는데, 그건 한 벌이 다 모여야 정해진다).
   */
  deck_formats?: string[]
}

/** 바디 이름 대신 쓰는 말 — **모든 바디.** 단품은 바디가 이것 하나다. 서버와 같은 말. */
export const ALL_BODIES = '전체'

/** `apply_to` 를 목록으로 — 옛 값(문자열 하나)도 읽는다. 서버의 `applied_bodies` 와 같은 규칙. */
export function appliedTo(material: MaterialItem): string[] {
  const value = material.apply_to
  // 칸이 없으면 서버의 기본값(「전체」)과 같게 읽는다 — 둘이 다르면 화면과 내보낸 것이 어긋난다.
  if (value === undefined) return [ALL_BODIES]
  if (typeof value === 'string') return value.trim() ? [value] : []
  return [...new Set(value.filter((one) => one.trim()))]
}

/** 이 파트에 붙은 물성들의 자리(`materials[i]`) — 둘 이상이면 저장이 막힌다(서버 규칙). */
export function materialsOn(materials: MaterialItem[], body: string): number[] {
  return materials.flatMap((one, index) => {
    const where = appliedTo(one)
    return where.includes(body) || where.includes(ALL_BODIES) ? [index] : []
  })
}

/**
 * 파트 하나의 물성을 바꾼 **새 목록** — `index` 가 `null` 이면 그 파트를 비운다.
 *
 * **파트 하나에는 물성 하나**(서버가 막는 규칙과 같다) — 그 파트를 가리키던 다른 재료에서는
 * 뺀다. 「전체」 에 붙은 재료가 있으면 먼저 **파트 이름들로 풀어 쓴다**: 조립에서 한 파트만
 * 다른 재료로 바꾸면 나머지는 그대로여야 한다.
 */
export function assignBody(
  materials: MaterialItem[],
  bodyNames: string[],
  body: string,
  index: number | null,
): MaterialItem[] {
  const single = bodyNames.length === 1 && bodyNames[0] === ALL_BODIES
  return materials.map((one, i) => {
    let where = appliedTo(one)
    if (!single && where.includes(ALL_BODIES)) {
      where = [...new Set([...where.filter((name) => name !== ALL_BODIES), ...bodyNames])]
    }
    where = where.filter((name) => name !== body)
    if (i === index) where = [...where, body]
    return { ...one, apply_to: where }
  })
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
  materials: MaterialItem[]
  constraints: ConditionItem[]
  loads: ConditionItem[]
  contacts: ConditionItem[]
  initial: ConditionItem[]
  analysis: Record<string, unknown>
  mesh_hints: ConditionItem[]
  /**
   * 해석 조건에서 정한 좌표계 — 원점 · 회전(수 또는 식)이거나 선택 그룹의 면에 붙인 것(`on`).
   * 도면의 좌표계와 이름이 겹치면 안 된다. 조건의 「좌표계」(`cs`) 칸이 이름으로 가리킨다.
   */
  coordinate_systems?: FrameDraft[]
}

/** 조건이 담기는 묶음들 — 선택 그룹과 해석 설정은 따로 다룬다. */
export const GROUP_KEYS = [
  'constraints',
  'loads',
  'contacts',
  'initial',
  'mesh_hints',
] as const

/** `system` — 작업의 기본 단위계. 안 주면 mm·t·s(CAD 가 mm 라 해석도 mm — FE 의 사실상 표준). */
export function emptyConditions(system = 'mm_n_tonne'): Conditions {
  return {
    schema_version: 1,
    units: { system },
    named_selections: [],
    materials: [],
    constraints: [],
    loads: [],
    contacts: [],
    initial: [],
    analysis: { type: 'modal', modes: 6 },
    mesh_hints: [],
    coordinate_systems: [],
  }
}

/** 서버가 준 것을 화면이 쓰는 모양으로 — 빈 칸을 채워 두면 화면에 `?.` 가 줄어든다. */
export function asConditions(raw: unknown, defaultSystem?: string): Conditions {
  // 아직 조건이 없으면(또는 계를 안 적었으면) **작업의 기본 단위계로 시작한다.** 적힌 계는 그대로.
  const empty = emptyConditions(defaultSystem)
  if (!raw || typeof raw !== 'object') return empty
  return { ...empty, ...(raw as Partial<Conditions>) }
}

/** 3D 에서 찍은 자리 하나에 대한 **셀렉터 후보**. */
export interface SelectorCandidate {
  label: string
  select: Record<string, unknown>
  /** 지금 몇 개에 맞나 — 1 이면 이것 하나, 여럿이면 그 부류 전부. */
  matches: number
  /**
   * **치수가 바뀌어도 같은 것을 가리키나.** 좌표만 쓰는 규칙은 거짓이다 — DOE 가 치수를 바꾸면
   * 못 찾는 게 아니라 가장 가까운 **딴 것**을 말없이 집는다(판 길이 80 → 130 에서 +X 옆면 대신
   * 구멍, 실측). 없으면 참으로 본다(예전 서버).
   */
  stable?: boolean
}

/**
 * 고른 것 하나의 **기본 규칙** — 그것 하나에 맞고(`matches` 1) 치수에 흔들리지 않는 것을
 * 먼저. 없으면 하나에 맞는 것, 그것도 없으면 첫 후보.
 */
export function defaultRule(candidates: SelectorCandidate[]): number {
  const steady = candidates.findIndex((one) => one.matches === 1 && one.stable !== false)
  if (steady >= 0) return steady
  return Math.max(0, candidates.findIndex((one) => one.matches === 1))
}

/** 이 선택 규칙이 **좌표만** 쓰나 — 종류 · 방향 같은 거르개 없이 「가장 가까운 것」 만. */
function coordinateOnly(rule: Record<string, unknown>): boolean {
  const filters = ['kind', 'normal', 'axis', 'role', 'radius', 'edges', 'tag', 'of_face_role', 'body']
  return rule.near !== undefined && !filters.some((key) => key in rule)
}

/**
 * 선택 그룹에 **좌표만 쓰는 규칙**이 들어 있나 — DOE 로 치수가 바뀌면 딴 형상을 집을 수 있다.
 * 예전에 만든 그룹(「이 자리의 면」)이 이렇다.
 */
export function hasCoordinateOnlyRule(select: Record<string, unknown>): boolean {
  const rules = Array.isArray(select.any) ? (select.any as Record<string, unknown>[]) : [select]
  return rules.some(coordinateOnly)
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

/** 조건의 식 알림 — 풀리지 않는 식. */
export interface ExpressionNote {
  where: string
  level: 'info' | 'warn'
  text: string
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
  /** 값 칸의 식 중 **풀리지 않는 것** — 저장 · 내보내기에서 막히기 전에 알린다. */
  notes: (conditions: Conditions, recipe: Recipe) =>
    api.post<{ items: ExpressionNote[] }>('/cad/conditions/notes', { conditions, recipe }),

  /** 찍은 자리를 말로 되돌려 받는다. `what` 은 faces · edges · vertices. */
  selectors: (recipe: Recipe, what: string, point: number[]) =>
    api.post<{ picked: Record<string, unknown> | null; candidates: SelectorCandidate[] }>(
      '/cad/recipe/selectors',
      { recipe, pick: { what, point } },
    ),
  /**
   * 선택 그룹의 셀렉터를 **지금 형상에서** 푼다 — 트리에서 고른 그룹을 3D 에 비출 때. 합(`any`) ·
   * 면 나누기 태그까지 서버가 푼다(바디 그룹은 부르지 않는다 — 파트 이름이 곧 답이다).
   */
  resolve: (recipe: Recipe, select: Record<string, unknown>) =>
    api.post<{ what: string; total: number; items: { index: number; center?: number[]; midpoint?: number[]; point?: number[] }[] }>(
      '/cad/recipe/find',
      { recipe, query: select },
    ),
  /**
   * 도면과 해석 조건의 **좌표계를 지금 치수로** 푼다 — 3D 에 축을 그린다. 계산은 서버 한 곳이다
   * (화면이 따로 셈하면 보인 방향과 내보낸 방향이 어긋나는 날이 온다). 못 푼 이름은 `missing`.
   */
  frames: (recipe: Recipe, conditions: Conditions) =>
    api.post<{ items: FrameRow[]; missing: string[] }>('/cad/conditions/frames', { recipe, conditions }),
  /**
   * **여럿을 한 번에** — 사각형 선택(Shift + 끌기). 도면을 한 번만 만들고 같은 순서로 돌려준다.
   * 하나씩 부르면 스무 개를 고른 사각형이 도면을 스무 번 만든다.
   */
  selectorsMany: (recipe: Recipe, picks: { what: string; point: number[] }[]) =>
    api.post<{ items: { picked: Record<string, unknown> | null; candidates: SelectorCandidate[] }[] }>(
      '/cad/recipe/selectors',
      { recipe, picks },
    ),

  /** 버전에 붙인다 — **새 버전을 만들지 않는다**(도면이 안 바뀌었으니까). */
  save: (workId: string, number: number, conditions: Conditions) =>
    api.put<{ conditions: Conditions }>(`/works/${workId}/versions/${number}/conditions`, {
      conditions,
    }),
}
