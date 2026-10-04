/**
 * 변수가 **어디에 쓰였나** — 도면 입력란(`nodes`), 다른 변수의 식(`params`), 해석 조건.
 *
 * 형상에 안 쓰여도 조건이 쓰는 변수(`마찰계수` · `처짐`)가 있고, 다른 변수의 식만 쓰는 변수(`간격비` →
 * `지지_간격 = 간격비 * 두께`)가 있다. 입력란만 세면 그것들이 「미사용」 으로 보이고, 사람이 지우면
 * 조건 · 식이 조용히 깨진다(2026-10-04 사용자 지적).
 *
 * 이름의 경계는 **유니코드 글자**로 본다 — `\w` 는 한글을 글자로 안 봐서 「길이」 가 「판길이」 안에서
 * 걸렸다.
 */

import type { Recipe } from '@/modules/cad/api'

export interface ParamUse {
  /** 도면 입력란에서 쓴 횟수. */
  fields: number
  /** 이 변수를 식에 쓰는 다른 변수들. */
  params: string[]
  /** 해석 조건에서 쓴 횟수. */
  conditions: number
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** 식 안의 이름 — 앞뒤가 글자 · 숫자 · `_` 가 아니어야 한다. */
export function namePattern(name: string, flags = 'gu'): RegExp {
  return new RegExp(`(?<![\\p{L}\\p{N}_])${escape(name)}(?![\\p{L}\\p{N}_])`, flags)
}

/** JSON 안의 `"=식"` 들에서 이 이름이 나온 횟수. */
function countIn(json: string, name: string): number {
  const pattern = namePattern(name)
  let found = 0
  for (const expression of json.match(/"=[^"]*"/g) ?? []) found += (expression.match(pattern) ?? []).length
  return found
}

export function paramUses(recipe: Recipe, conditions?: unknown): Record<string, ParamUse> {
  const params = (recipe.params ?? {}) as Record<string, number | string>
  const nodes = JSON.stringify(recipe.nodes ?? [])
  const rules = conditions ? JSON.stringify(conditions) : ''
  const out: Record<string, ParamUse> = {}
  for (const name of Object.keys(params)) {
    const users = Object.entries(params)
      .filter(([other, value]) => other !== name && typeof value === 'string' && value.startsWith('=') && namePattern(name, 'u').test(value))
      .map(([other]) => other)
    out[name] = { fields: countIn(nodes, name), params: users, conditions: rules ? countIn(rules, name) : 0 }
  }
  return out
}

/** 사람이 읽는 한 줄 — `입력란 2 · 변수 · 조건`, 아무 데도 없으면 `미사용`. */
export function useLabel(use: ParamUse): string {
  const parts = [use.fields ? `입력란 ${use.fields}` : '', use.params.length ? '변수' : '', use.conditions ? '조건' : ''].filter(Boolean)
  return parts.length ? parts.join(' · ') : '미사용'
}

/** 툴팁 — 어디서 쓰는지 문장으로. */
export function useTitle(use: ParamUse): string {
  const lines = [
    use.fields ? `${use.fields}개 입력란에서 사용합니다.` : '',
    use.params.length ? `변수 ${use.params.join(', ')}의 식에서 사용합니다.` : '',
    use.conditions ? `해석 조건 ${use.conditions}곳에서 사용합니다. DOE로 변경하면 설계점마다 조건이 함께 바뀝니다.` : '',
  ].filter(Boolean)
  return lines.length ? lines.join(' ') : '입력란, 다른 변수, 해석 조건 어디에서도 사용하지 않습니다. 입력란의 fx를 눌러 =이름을 입력하십시오.'
}
