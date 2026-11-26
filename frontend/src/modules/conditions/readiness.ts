/**
 * **준비 점검** — 조건 화면 곳곳에 흩어져 있던 ⚠ 를 한 자리에(해석 확장 설계 6장). 트리의 ⚠(물성 값 · 좌표 기준
 * 그룹 · 대상 없음), 식 알림, 옮긴 메시 힌트, 도면 문제를 같은 줄 모양으로 모은다. 줄마다 고칠 자리(`open`)가
 * 있으면 화면이 그곳을 연다.
 *
 * **저장을 막는 것이 아니다** — 서버가 저장 · 내보내기 때 같은 것을 다시 본다. 여기는 그 전에, 고치는 중에 보인다.
 * 접촉 검사(`ContactCheck`)는 채우기 단추가 있어 따로 선다.
 */

import { GROUP_KEYS, hasCoordinateOnlyRule, materialsOn, settingOf } from '@/modules/conditions/api'
import type { Body, ConditionItem, Conditions, ConditionsSchema, ExpressionNote } from '@/modules/conditions/api'
import type { MaterialConverted } from '@/modules/materials/api'
import { materialProblems } from '@/modules/materials/MaterialProperties'

/** 줄을 누르면 열 자리 — 트리의 파트 · 물성 · 선택 그룹, 또는 조건 창. */
export type ReadinessOpen =
  | { kind: 'part'; name: string }
  | { kind: 'library'; index: number }
  | { kind: 'selection'; index: number }
  | { kind: 'item'; group: string; index: number }

export interface ReadinessItem {
  level: 'warn' | 'info'
  where: string
  text: string
  open?: ReadinessOpen
}

export interface ReadinessInput {
  draft: Conditions
  schema: ConditionsSchema
  /** `null` 이면 아직 불러오는 중 — 파트의 물성은 보지 않는다. */
  bodies: Body[] | null
  /** `draft.materials` 와 같은 순서의 내보낼 값 — `null` 이면 아직. */
  converted: (MaterialConverted | null)[] | null
  notes: ExpressionNote[]
  /** 도면을 만들지 못한 까닭 — 있으면 3D 도 없다. */
  geometry: string[]
  /** 바디 그룹에 걸었던 국부 메시를 파트별 설정으로 옮긴 것 · 못 옮긴 것(`moveBodyMeshHints`). */
  moved?: string[]
  kept?: string[]
}

const nameOf = (item: ConditionItem, fallback: string) => String(item.name ?? '') || fallback

export function readiness({ draft, schema, bodies, converted, notes, geometry, moved = [], kept = [] }: ReadinessInput): ReadinessItem[] {
  const out: ReadinessItem[] = []
  if (geometry.length > 0) {
    out.push({ level: 'warn', where: '도면', text: '도면에 문제가 있어 3D가 표시되지 않습니다. ‘도면’ 탭에서 수정하십시오.' })
  }

  // 파트마다 물성 — 해석에서 제외한 파트는 보지 않는다.
  for (const body of bodies ?? []) {
    if (settingOf(draft.body_settings, body.name).suppressed) continue
    if (materialsOn(draft.materials, body.name).length === 0) {
      out.push({
        level: 'warn',
        where: bodies?.length === 1 ? '모델' : `파트 ‘${body.name}’`,
        text: '물성이 지정되지 않았습니다.',
        open: { kind: 'part', name: body.name },
      })
    }
  }
  // 물성의 값 — 파트에 지정한 것만(담아만 둔 재료는 내보내지 않는다).
  draft.materials.forEach((material, index) => {
    if ((material.apply_to ?? []).length === 0) return
    const name = String(((material.ref ?? {}) as Record<string, unknown>).name ?? '이름 없음')
    for (const text of materialProblems(converted?.[index])) {
      out.push({ level: 'warn', where: `물성 ‘${name}’`, text, open: { kind: 'library', index } })
    }
  })

  // 조건의 적용 대상 — 그 종류가 쓰는 칸만(중력 · 가속도 PSD 는 대상이 없다).
  const names = new Set(draft.named_selections.map((one) => one.name))
  for (const group of GROUP_KEYS) {
    const spec = schema.groups[group]
    if (!spec) continue
    ;(draft[group] ?? []).forEach((item, index) => {
      const type = String(item.type ?? '')
      const where = `${spec.label} ‘${nameOf(item, spec.fields.type?.labels?.[type] ?? type)}’`
      const open: ReadinessOpen = { kind: 'item', group, index }
      const keys = 'source' in spec.fields ? ['source', 'target'] : 'on' in spec.fields ? ['on'] : []
      for (const key of keys) {
        const field = spec.fields[key]
        if (field?.only_for && !field.only_for.includes(type)) continue
        const value = String(item[key] ?? '')
        if (!value) {
          const what = key === 'source' ? '접촉면' : key === 'target' ? '대상면' : '적용 대상'
          out.push({ level: 'warn', where, text: `${what}(선택 그룹)이 지정되지 않았습니다.`, open })
        } else if (value !== field?.whole && !names.has(value)) {
          out.push({ level: 'warn', where, text: `선택 그룹 ‘${value}’이(가) 없습니다.`, open })
        }
      }
    })
  }

  // 좌표만 쓰는 선택 규칙 — DOE 가 치수를 바꾸면 딴 형상을 집는다.
  draft.named_selections.forEach((one, index) => {
    if (hasCoordinateOnlyRule(one.select ?? {})) {
      out.push({
        level: 'warn',
        where: `선택 그룹 ‘${one.name}’`,
        text: '좌표만 사용하는 규칙이 포함되어 있습니다. DOE로 치수가 변경되면 다른 형상이 선택될 수 있습니다.',
        open: { kind: 'selection', index },
      })
    }
  })

  for (const note of notes) out.push({ level: note.level, where: note.where, text: note.text })

  if (moved.length > 0) {
    out.push({
      level: 'info',
      where: '국부 메시',
      text: `바디 선택 그룹(${moved.map((one) => `‘${one}’`).join(', ')})에 지정된 국부 메시를 ‘파트별 설정’의 파트 메시로 옮겼습니다. ‘조건 저장’을 클릭하면 반영됩니다.`,
    })
  }
  if (kept.length > 0) {
    out.push({
      level: 'warn',
      where: '국부 메시',
      text: `바디 선택 그룹(${kept.map((one) => `‘${one}’`).join(', ')})의 국부 메시에는 무시할 형상 크기 또는 경계층이 있어 옮기지 않았습니다. 파트 단위 값은 ‘파트별 설정’에서, 나머지는 ‘전체’ 또는 면·엣지 그룹의 국부 메시로 지정하십시오.`,
    })
  }
  // 경고가 먼저.
  return out.sort((a, b) => (a.level === b.level ? 0 : a.level === 'warn' ? -1 : 1))
}
