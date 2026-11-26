/**
 * **곡선**(`curves[]`) — 이름 붙은 표 하나를 여러 하중이 가리킨다(해석 확장 설계 4장, 서버 `conditions/curves.py`).
 *
 * 곡선은 **공유 칸**이다 — 케이스마다 같은 곡선을 쓴다. 그래서 이름을 바꾸거나 지울 때는 고른 케이스만이 아니라
 * **모든 케이스의 하중**을 본다(`curveUsers` · `renameCurve`). 하중이 곡선을 가리킬 수 있는지는 서버의 규칙
 * (`check_uses`)과 같은 말로 미리 보인다(`curveMismatch`) — 저장 때 막히기 전에.
 */

import type { ConditionItem, Conditions, CurveItem, CurveUse } from '@/modules/conditions/api'
import { casesOf } from '@/modules/conditions/cases'
import type { Row } from '@/modules/conditions/excitation'

/** 가로축의 단위 — 시간은 s, 주파수는 Hz, 단계는 단위 없는 번호. */
export const AXIS_UNITS: Record<string, string> = { time: 's', frequency: 'Hz', step: '' }
const AXIS_LABELS: Record<string, string> = { time: '시간', step: '단계', frequency: '주파수' }
const INTERPOLATION_LABELS: Record<string, string> = { linear: '선형', loglog: '로그-로그', step: '계단' }

/** 같은 이름이 없는 새 곡선 이름 — 「곡선 2」, 또는 `base` 를 주면 「가진 곡선」 · 「가진 곡선 2」. */
export function nextCurveName(curves: CurveItem[], base?: string): string {
  const taken = new Set(curves.map((one) => one.name))
  if (base && !taken.has(base)) return base
  const stem = base ?? '곡선'
  let n = base ? 2 : curves.length + 1
  while (taken.has(`${stem} ${n}`)) n += 1
  return `${stem} ${n}`
}

/** 새 곡선 — 주파수 · 선형 · 배율 1, 점은 비어 있다. */
export function emptyCurve(curves: CurveItem[]): CurveItem {
  return { name: nextCurveName(curves), x: 'frequency', unit: '', interpolation: 'linear', points: [], scale: 1 }
}

/**
 * 그래프에 그릴 수 있는 점 — 두 칸이 다 수이고 배율이 수일 때 `값 × 배율`. 식이 든 점은 설계점마다 풀리므로
 * 빼고 몇 개 뺐는지 센다. 배율이 식이면 모양만 그린다(`scaled: false`).
 */
export function plotPoints(points: unknown, scale: unknown = 1): { points: [number, number][]; skipped: number; scaled: boolean } {
  const rows = Array.isArray(points) ? (points as unknown[][]) : []
  const factor = typeof scale === 'number' && Number.isFinite(scale) ? scale : 1
  const out: [number, number][] = []
  let skipped = 0
  for (const row of rows) {
    const [x, y] = Array.isArray(row) ? row : []
    if (typeof x === 'number' && typeof y === 'number' && Number.isFinite(x) && Number.isFinite(y)) out.push([x, y * factor])
    else skipped += 1
  }
  return { points: out, skipped, scaled: typeof scale === 'number' }
}

/**
 * 이 하중 종류가 이 곡선을 가리킬 수 없는 까닭 — 서버 `check_uses` 와 같은 규칙(주파수 곡선 · 그 표의 보간 · 단위).
 * 가리킬 수 있으면 `null`.
 */
export function curveMismatch(curve: CurveItem, use: CurveUse): string | null {
  if (curve.x !== 'frequency') {
    return `주파수 곡선만 쓸 수 있습니다(${AXIS_LABELS[curve.x] ?? curve.x} 곡선 — 시간 · 단계 곡선은 비선형 정적에서 받습니다).`
  }
  const interpolation = curve.interpolation ?? 'linear'
  if (interpolation !== use.interpolation) {
    return `${INTERPOLATION_LABELS[use.interpolation] ?? use.interpolation} 보간이어야 합니다(곡선: ${INTERPOLATION_LABELS[interpolation] ?? interpolation}).`
  }
  const unit = curve.unit ?? ''
  if (unit !== use.unit) return `단위가 ${use.unit || '없음(배율)'}이어야 합니다(곡선: ${unit || '없음'}).`
  return null
}

/** 곡선 한 줄 요약 — 「주파수 · 로그-로그 · 6점」. */
export function curveSummary(curve: CurveItem): string {
  const count = Array.isArray(curve.points) ? curve.points.length : 0
  return [AXIS_LABELS[curve.x] ?? curve.x, INTERPOLATION_LABELS[curve.interpolation ?? 'linear'], `${count}점`].filter(Boolean).join(' · ')
}

const loadName = (load: ConditionItem) => String(load.name ?? '') || String(load.type ?? '')

/**
 * 이 곡선을 가리키는 하중 — **모든 케이스에서**(곡선은 공유다). 케이스가 있으면 「케이스 ‘A’ · 하중 ‘누름’」.
 */
export function curveUsers(whole: Conditions, name: string): string[] {
  const cases = casesOf(whole)
  if (cases.length === 0) {
    return (whole.loads ?? []).filter((one) => one.curve === name).map((one) => `하중 ‘${loadName(one)}’`)
  }
  return cases.flatMap((one) =>
    (one.loads ?? []).filter((load) => load.curve === name).map((load) => `케이스 ‘${one.name}’ · 하중 ‘${loadName(load)}’`),
  )
}

/** 곡선 이름을 바꾼다 — 그 곡선을 가리키던 하중도 함께(맨 위와 모든 케이스). */
export function renameCurve(whole: Conditions, from: string, to: string): Conditions {
  if (from === to) return whole
  const fix = (loads: ConditionItem[] | undefined) => (loads ?? []).map((one) => (one.curve === from ? { ...one, curve: to } : one))
  const next: Conditions = {
    ...whole,
    curves: (whole.curves ?? []).map((one) => (one.name === from ? { ...one, name: to } : one)),
    loads: fix(whole.loads),
  }
  const cases = casesOf(whole)
  if (cases.length === 0) return next
  return { ...next, cases: cases.map((one) => (one.loads ? { ...one, loads: fix(one.loads) } : one)) } as Conditions
}

/**
 * 곡선을 떼고 표로 옮길 행 — 점 × 배율. 배율이 식이면 옮기지 못한다(`null` — 표는 비워 두고 사람이 적는다):
 * 점만 옮기면 크기가 말없이 달라진다.
 */
export function tableOfCurve(curve: CurveItem | undefined): Row[] | null {
  if (!curve || !Array.isArray(curve.points) || curve.points.length === 0) return null
  const scale = curve.scale ?? 1
  if (typeof scale !== 'number') return null
  return curve.points.map(([x, y]): Row => [x ?? '', typeof y === 'number' && scale !== 1 ? Number((y * scale).toPrecision(12)) : (y ?? '')])
}

/**
 * 점 목록의 문제 — 서버가 저장 때 막는 것(두 점 이상 · 가로축이 커지는 순서 · 로그-로그는 0 보다 큰 점)을 미리.
 * 식이 든 칸은 설계점마다 풀리므로 보지 않는다.
 */
export function curveProblems(curve: CurveItem): string[] {
  const points = Array.isArray(curve.points) ? curve.points : []
  const out: string[] = []
  if (points.length < 2) out.push('점이 두 개 이상 필요합니다.')
  const xs = points.map((one) => one[0])
  for (let i = 1; i < xs.length; i++) {
    const [a, b] = [xs[i - 1], xs[i]]
    if (typeof a === 'number' && typeof b === 'number' && b <= a) {
      out.push(`${i + 1}행: 가로축 값이 앞 행보다 커야 합니다.`)
      break
    }
  }
  if ((curve.interpolation ?? 'linear') === 'loglog') {
    if (curve.x !== 'frequency') out.push('로그-로그 보간은 주파수 곡선에만 씁니다.')
    if (points.some((one) => one.some((cell) => typeof cell === 'number' && cell <= 0))) {
      out.push('로그-로그 보간은 0보다 큰 점만 받습니다.')
    }
  }
  return out
}
