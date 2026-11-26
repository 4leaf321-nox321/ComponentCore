/**
 * 해석 케이스(v2, `schema_version: 2`) — 공유 모델 위에 해석을 여럿. 서버 `conditions/cases.py` 와 같은 모양.
 *
 * 한 벌은 **공유**(단위 · 선택 그룹 · 재료 · 파트 설정 · 접촉 · 메시 힌트 · 좌표계 · 곡선)와 **케이스**
 * (해석 설정 · 구속 · 하중 · 초기조건 — `CASE_FIELDS`, 그리고 앞 케이스 · 대상 솔버)로 나뉜다.
 *
 * 화면은 케이스 하나를 **v1 모양**(`caseView` — 공유 칸 + 그 케이스 칸)으로 그리고 고친다 — 서버의 「케이스
 * 보기」 와 같은 생각이다. 편집기는 케이스를 몰라도 되고, 고친 것은 `putCaseView` 가 공유 칸은 맨 위로, 케이스
 * 칸은 그 케이스로 되돌린다. 저장할 때는 맨 위의 케이스 칸을 뺀다(`saved`) — 섞이면 서버가 막는다(어느 쪽이 그
 * 케이스인지 모른다).
 */

import type { ConditionItem, Conditions } from '@/modules/conditions/api'

/** 케이스마다 적는 칸 — 나머지는 공유다. */
export const CASE_FIELDS = ['analysis', 'constraints', 'loads', 'initial'] as const

export interface CaseItem {
  name: string
  /** 앞 케이스 — 그 끝 상태에서 시작한다(하중은 이어지지 않는다, 조인 볼트는 잠긴다). 비면 처음 상태. */
  depends_on?: string
  /** 풀 솔버 — 받는 쪽 능력표의 이름(`calculix` · `ansys`). 비면 받는 쪽 작업의 솔버. */
  target?: { solver?: string }
  analysis?: Record<string, unknown>
  constraints?: ConditionItem[]
  loads?: ConditionItem[]
  initial?: ConditionItem[]
}

/** 저장된 조건의 해석 케이스 — v1 이면 빈 목록. */
export function casesOf(value: unknown): CaseItem[] {
  const cases = value && typeof value === 'object' ? (value as { cases?: unknown }).cases : undefined
  return Array.isArray(cases) ? (cases as CaseItem[]) : []
}

/** 케이스 하나의 v1 모양 — 공유 칸 + 그 케이스 칸. 케이스가 없으면 그 자체. */
export function caseView(whole: Conditions, index: number): Conditions {
  const cases = casesOf(whole)
  const one = cases[Math.min(Math.max(index, 0), cases.length - 1)]
  if (!one) return whole
  const { cases: _cases, ...shared } = whole as Conditions & { cases?: unknown }
  return {
    ...shared,
    schema_version: 1,
    analysis: one.analysis ?? { type: 'modal' },
    constraints: one.constraints ?? [],
    loads: one.loads ?? [],
    initial: one.initial ?? [],
  }
}

/** 고친 v1 모양을 한 벌로 되돌린다 — 공유 칸은 맨 위로, 케이스 칸은 그 케이스로. */
export function putCaseView(whole: Conditions, index: number, view: Conditions): Conditions {
  const cases = casesOf(whole)
  if (cases.length === 0) return view
  const next = cases.map((one, i) =>
    i === index
      ? { ...one, analysis: view.analysis, constraints: view.constraints, loads: view.loads, initial: view.initial }
      : one,
  )
  return { ...view, schema_version: whole.schema_version ?? 2, cases: next } as Conditions
}

/** 케이스 목록을 바꾼 한 벌(추가 · 삭제 · 이름 · 앞 케이스 · 대상 솔버). */
export function withCases(whole: Conditions, cases: CaseItem[]): Conditions {
  return { ...whole, cases } as Conditions
}

/** 저장할 모양 — 케이스가 있으면 맨 위의 케이스 칸을 뺀다(화면이 채운 빈 칸 · 마지막에 본 케이스의 사본). */
export function saved(whole: Conditions): Conditions {
  if (casesOf(whole).length === 0) return whole
  const out: Record<string, unknown> = { ...whole }
  for (const key of CASE_FIELDS) delete out[key]
  return out as unknown as Conditions
}

/** 같은 이름이 없는 새 케이스 이름 — 「케이스 3」. */
export function nextCaseName(cases: CaseItem[]): string {
  const taken = new Set(cases.map((one) => one.name))
  let n = cases.length + 1
  while (taken.has(`케이스 ${n}`)) n += 1
  return `케이스 ${n}`
}

/**
 * `index` 의 케이스 뒤에 **이어지는 케이스** — 받는 쪽의 사슬 규칙을 처음부터 지키는 사본(서버 `_check_follows`):
 * 해석 설정 · 구속은 그대로(사슬 안의 구속은 같다), 하중은 **중력만** 옮긴다(하중은 이어지지 않고 중력은 케이스마다
 * 같아야 한다 — 조인 볼트는 잠기므로 예압을 다시 적지 않는다). 초기조건은 비운다(앞 케이스의 끝 상태에서 시작한다).
 */
export function followingCase(cases: CaseItem[], index: number): CaseItem {
  const before = cases[index]
  return {
    name: nextCaseName(cases),
    depends_on: before.name,
    target: { ...before.target },
    analysis: structuredClone(before.analysis ?? { type: 'modal' }),
    constraints: structuredClone(before.constraints ?? []),
    loads: structuredClone((before.loads ?? []).filter((one) => one.type === 'standard_earth_gravity')),
    initial: [],
  }
}

/** 케이스 이름을 바꾼다 — 그 케이스를 앞 케이스로 가리키던 것도 함께. */
export function renamed(cases: CaseItem[], index: number, name: string): CaseItem[] {
  const old = cases[index]?.name
  return cases.map((one, i) =>
    i === index ? { ...one, name } : old && one.depends_on === old ? { ...one, depends_on: name } : one,
  )
}

/** 이 케이스 뒤에 오는 케이스 — 사슬만이라 하나이거나 없다. */
export function followerOf(cases: CaseItem[], index: number): CaseItem | undefined {
  const name = cases[index]?.name
  return name ? cases.find((one) => one.depends_on === name) : undefined
}
