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

import type { ConditionItem, Conditions, FieldSchema } from '@/modules/conditions/api'

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
 * 같아야 한다 — 조인 볼트는 잠기므로 예압을 다시 적지 않는다). 초기조건은 비운다(앞 케이스의 끝 상태에서 시작한다). 하중
 * 단계는 옮기지 않는다 — 다른 케이스와 이은 케이스에서는 쓰지 않는다(받는 쪽 첫 판, 서버 `cases._check_staged_alone`).
 */
/** 해석 설정의 사본 — 하중 단계(`load_steps`)는 뺀다. */
function withoutLoadSteps(analysis: Record<string, unknown>): Record<string, unknown> {
  const out = structuredClone(analysis)
  delete out.load_steps
  return out
}

export function followingCase(cases: CaseItem[], index: number): CaseItem {
  const before = cases[index]
  return {
    name: nextCaseName(cases),
    depends_on: before.name,
    target: { ...before.target },
    // 하중 단계(②)는 옮기지 않는다 — 다른 케이스와 이은 케이스에서는 쓰지 않는다(받는 쪽 첫 판).
    analysis: withoutLoadSteps(before.analysis ?? { type: 'modal' }),
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

/** 같은 볼트인가를 가르는 열쇠 — 선택 그룹과 단면 좌표계(서버 `cases._bolt`, SimEngBay 와 같다). */
const boltKey = (load: ConditionItem) => JSON.stringify([String(load.on ?? ''), String(load.cs ?? 'global')])
const boltsOf = (one: CaseItem | undefined) => (one?.loads ?? []).filter((load) => load.type === 'bolt_pretension')

/**
 * **뒤 케이스에서 처음 조이는 볼트** — 이 케이스와 그 앞 케이스에서는 아직 조이지 않았는데 사슬의 뒤 케이스가 조이는
 * 볼트. 그 볼트는 이 케이스에서 풀린 볼트로 풀려 힘을 전하지 않는다(Ansys 는 그 단계 앞에서 Open, CalculiX 는 기준점이
 * 자유 — SimEngBay 와 정함, 2026-11-27). 이 케이스의 하중이 그 볼트에 기대면 구조가 기구가 되어 풀리지 않는다. 막지 않고
 * 알린다(`readiness`).
 */
export function looseBolts(cases: CaseItem[], index: number): { on: string; at: string }[] {
  const byName = new Map(cases.map((one) => [one.name, one]))
  const tightened = new Set<string>()
  const walked = new Set<string>()
  for (let one: CaseItem | undefined = cases[index]; one && !walked.has(one.name); one = one.depends_on ? byName.get(one.depends_on) : undefined) {
    walked.add(one.name)
    for (const load of boltsOf(one)) tightened.add(boltKey(load))
  }
  const out: { on: string; at: string }[] = []
  const ahead = new Set<string>()
  for (let at = index, next = followerOf(cases, at); next && !ahead.has(next.name); next = followerOf(cases, at)) {
    ahead.add(next.name)
    for (const load of boltsOf(next)) {
      const key = boltKey(load)
      if (tightened.has(key)) continue
      tightened.add(key)
      out.push({ on: String(load.on ?? ''), at: next.name })
    }
    at = cases.indexOf(next)
  }
  return out
}

/**
 * **케이스의 창에서는 v1 의 선응력 칸을 내지 않는다** — 해석 설정의 `prestressed` 와 초기조건 `prestress`. 케이스의
 * 선응력은 앞 케이스(`depends_on`)가 말하고, 둘을 함께 두면 뜻이 갈려 서버가 저장할 때 막는다(SimEngBay 와 정함,
 * 2026-11-27). 케이스가 없는 조건(v1)은 그대로다.
 */
export function withoutPrestress<T extends { types: string[]; fields: Record<string, unknown> }>(group: string, spec: T): T {
  if (group === 'analysis') {
    const { prestressed: _, ...fields } = spec.fields
    return { ...spec, fields }
  }
  if (group === 'initial') return { ...spec, types: spec.types.filter((one) => one !== 'prestress') }
  return spec
}

/**
 * **해석 케이스로 나누기** — 케이스가 없는 조건(v1)을 케이스 하나로. 해석 설정 · 구속 · 하중 · 초기조건이 그 케이스로
 * 간다(공유 칸은 그대로). 해석은 바뀌지 않는다 — 케이스 하나는 v1 그대로 내보낸다. 하중 단계(②)처럼 케이스에서만 쓰는
 * 칸을 열 때 쓴다. 맨 위의 케이스 칸은 화면이 들고 있다가 저장할 때 뺀다(`saved`).
 */
export function splitIntoCases(whole: Conditions, name = '케이스 1'): Conditions {
  if (casesOf(whole).length > 0) return whole
  const one: CaseItem = {
    name,
    analysis: structuredClone(whole.analysis ?? { type: 'modal' }),
    constraints: structuredClone(whole.constraints ?? []),
    loads: structuredClone(whole.loads ?? []),
    initial: structuredClone(whole.initial ?? []),
  }
  return { ...whole, schema_version: 2, cases: [one] } as Conditions
}

/**
 * **케이스의 ② 칸** — 사양표 폼이 그릴 수 있는 것을 연다(서버 사양표는 감춰 둔다 — 케이스가 없는 조건에는 쓰지 않는다).
 *
 * - 하중: ‘시간별 배율’ 표(`time_table`, 정적에서만 — 칸의 `analysis_only`).
 * - 해석 설정: v1 의 ‘하중 단계 수’ 는 하중 단계 표(`LoadStepsEditor`)가 대신한다 — 기본값(1)이면 감춘다. 하중 단계를
 *   쓰면 ‘초기 부단계 수’ 도 단계마다 적으므로 비어 있으면 감춘다.
 */
export function withStepFields<T extends { fields: Record<string, FieldSchema> }>(group: string, spec: T, item: ConditionItem): T {
  if (group === 'loads' && spec.fields.time_table) {
    return { ...spec, fields: { ...spec.fields, time_table: { ...spec.fields.time_table, hidden: false } } }
  }
  if (group === 'analysis') {
    const fields = { ...spec.fields }
    if (item.steps == null || item.steps === 1) delete fields.steps
    const steps = Array.isArray(item.load_steps) ? item.load_steps : []
    if (steps.length > 0 && item.substeps == null) delete fields.substeps
    return { ...spec, fields }
  }
  return spec
}

/**
 * 케이스에서 하중 단계(②)를 쓰는가 — 하중 단계 · 수렴 제어 · 출력 요청, 하중의 시간별 배율 · 적용 단계 · 볼트 동작, 정적
 * 하중이 가리키는 곡선(시간 곡선), 소성 재료. 해석 쪽이 받기 전에는 DOE 생성이 막힌다(서버 `steps.blocked`).
 */
export function usesSteps(view: Conditions): boolean {
  const analysis = (view.analysis ?? {}) as Record<string, unknown>
  if (Array.isArray(analysis.load_steps) && analysis.load_steps.length > 0) return true
  // 소성 재료(공유 칸) — 받는 쪽이 v2 로만 받는다.
  if ((view.materials ?? []).some((one) => (one.model ?? 'linear_elastic') !== 'linear_elastic')) return true
  if (analysis.convergence != null || analysis.outputs != null) return true
  const statics = analysis.type === 'static'
  return (view.loads ?? []).some(
    (load) =>
      (Array.isArray(load.time_table) && load.time_table.length > 0) ||
      (Array.isArray(load.active_steps) && load.active_steps.length > 0) ||
      (Array.isArray(load.bolt_steps) && load.bolt_steps.length > 0) ||
      (statics && typeof load.curve === 'string' && load.curve !== '' && load.type !== 'psd_acceleration'),
  )
}
