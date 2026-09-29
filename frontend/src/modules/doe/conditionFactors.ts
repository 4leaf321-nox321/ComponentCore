/**
 * DOE 의 **조건 인자** — 시뮬레이션 조건에서 「바꿔 볼 수 있는 칸」 을 뽑는다.
 *
 * - 고르기(`choice`): 고르는 칸 하나(구속 · 하중 · 접촉의 종류, 정식화, 선택 그룹, 해석 종류,
 *   켬 · 끔, 변위의 자유 ↔ 고정 …)를 후보 중에서 설계점마다 하나씩.
 * - 배율(`scale`): 바디에 붙은 재료의 물성 하나에 곱할 수.
 *
 * 칸 목록은 서버의 사양표(`conditions_schema`)에서 나온다 — 종류를 더해도 여기는 안 고친다.
 * 숫자 칸(하중 크기 · 마찰계수 …)은 여기 없다: 그것은 도면 변수를 `=식` 으로 불러 훑는다.
 */

import type { ConditionsSchema, FieldSchema, GroupSchema, MaterialItem, NamedSelection } from '@/modules/conditions/api'
import type { Factor } from '@/modules/doe/api'

export interface ChoiceOption {
  value: unknown
  label: string
}

export interface ChoiceTarget {
  /** 화면의 열쇠 — `묶음|항목|칸`. */
  key: string
  /** 사람이 읽는 이름 — 「접촉 「블록-판」 · 종류」. 인자 이름으로도 쓴다. */
  label: string
  target: { group: string; item?: string | number; field: string }
  options: ChoiceOption[]
}

const GROUPS: [string, string][] = [
  ['constraints', '구속'],
  ['loads', '하중'],
  ['contacts', '접촉'],
  ['initial', '초기조건'],
  ['mesh_hints', '메시 힌트'],
]
/** 이름으로 가리키는 묶음 — 나머지(초기조건 · 메시 힌트)는 번호로. */
const NAMED = new Set(['constraints', 'loads', 'contacts'])
/** 선택 그룹을 가리키는 칸. */
const TARGET_FIELDS = new Set(['on', 'source', 'target'])

function enumOf(field: FieldSchema): string[] | null {
  if (field.enum) return field.enum
  return (field.anyOf ?? []).find((one) => one.enum)?.enum ?? null
}

/** 칸 하나에서 고를 후보들 — 없으면(숫자 칸 등) 빈 목록. */
function optionsOf(key: string, field: FieldSchema, type: string, group: GroupSchema | null, names: NamedSelection[]): ChoiceOption[] {
  if (TARGET_FIELDS.has(key)) {
    const accepts = group?.accepts?.[type] ?? group?.accepts?.['*']
    const ok = accepts ? names.filter((one) => accepts.some((a) => a.entity === one.entity)) : names
    return [...(field.whole ? [{ value: field.whole, label: field.whole }] : []), ...ok.map((one) => ({ value: one.name, label: one.name }))]
  }
  const values = enumOf(field)
  if (values) return values.map((value) => ({ value, label: field.labels?.[value] ?? value }))
  if (field.type === 'boolean') {
    return [
      { value: false, label: '끔' },
      { value: true, label: '켬' },
    ]
  }
  // 변위 성분 — 자유(null) ↔ 고정(0). 변위량(수)은 `=식` 으로 훑는다.
  if (field.component && !values) {
    return [
      { value: null, label: '자유' },
      { value: 0, label: '고정' },
    ]
  }
  return []
}

function fieldsOf(
  spec: { fields: Record<string, FieldSchema>; types?: string[] },
  item: Record<string, unknown>,
  group: GroupSchema | null,
  names: NamedSelection[],
): [string, string, ChoiceOption[]][] {
  const type = String(item.type ?? '')
  const out: [string, string, ChoiceOption[]][] = []
  const typeLabels = spec.fields.type?.labels ?? {}
  if ((spec.types ?? []).length > 1 && 'type' in spec.fields) {
    out.push(['type', '종류', (spec.types ?? []).map((one) => ({ value: one, label: typeLabels[one] ?? one }))])
  }
  for (const [key, field] of Object.entries(spec.fields)) {
    if (key === 'name' || key === 'type' || field.hidden) continue
    if (field.only_for && !field.only_for.includes(type)) continue
    const options = optionsOf(key, field, type, group, names)
    if (options.length >= 2) out.push([key, field.title ?? key, options])
  }
  return out
}

/** 조건에서 **바꿔 볼 수 있는 칸**들. */
export function choiceTargets(conditions: Record<string, unknown> | null | undefined, spec: ConditionsSchema | null | undefined): ChoiceTarget[] {
  // 사양표를 아직 못 받았거나 모양이 다르면 고를 칸이 없는 것으로 — 폼은 그대로 쓴다.
  if (!conditions || !spec?.groups) return []
  const names = (conditions.named_selections ?? []) as NamedSelection[]
  const out: ChoiceTarget[] = []
  for (const [group, groupLabel] of GROUPS) {
    const groupSpec = spec.groups[group]
    if (!groupSpec) continue
    const items = (conditions[group] ?? []) as Record<string, unknown>[]
    items.forEach((item, index) => {
      const named = NAMED.has(group) && typeof item.name === 'string' && item.name
      const ref: string | number = named ? String(item.name) : index + 1
      const itemLabel = named ? `${groupLabel} 「${String(item.name)}」` : `${groupLabel} ${index + 1}`
      for (const [field, title, options] of fieldsOf(groupSpec, item, groupSpec, names)) {
        out.push({ key: `${group}|${ref}|${field}`, label: `${itemLabel} · ${title}`, target: { group, item: ref, field }, options })
      }
    })
  }
  const analysis = (conditions.analysis ?? {}) as Record<string, unknown>
  const analysisSpec = {
    fields: spec.analysis?.properties ?? {},
    types: (spec.analysis?.properties?.type?.enum ?? []) as string[],
  }
  for (const [field, title, options] of fieldsOf(analysisSpec, analysis, null, names)) {
    out.push({ key: `analysis||${field}`, label: `해석 설정 · ${title}`, target: { group: 'analysis', field }, options })
  }
  return out
}

/** 인자 이름 — 40 자까지, 겹치면 번호를 붙인다. */
export function factorName(label: string, taken: Set<string>): string {
  const base = label.slice(0, 36)
  let name = base
  for (let n = 2; taken.has(name); n += 1) name = `${base} ${n}`
  taken.add(name)
  return name
}

/** 고르기 인자 한 줄 → 서버에 보낼 인자. */
export function choiceFactor(target: ChoiceTarget, values: unknown[], name: string): Factor {
  return { name, mode: 'choice', target: target.target, values: values as Factor['values'] }
}

/** 담아 둔 재료들이 가진 물성 이름 — 배율을 걸 수 있는 것들. 밀도 · 푸아송비는 늘 칸이 있다. */
export function propertyNames(materials: MaterialItem[]): string[] {
  const out = new Set<string>(['밀도', '푸아송비'])
  for (const one of materials) {
    const payload = (one.payload ?? {}) as Record<string, unknown>
    for (const row of (payload.declared_properties ?? []) as { item?: string }[]) if (row.item) out.add(row.item)
    for (const row of (payload.values ?? []) as { property_name?: string }[]) if (row.property_name) out.add(row.property_name)
  }
  return [...out]
}
