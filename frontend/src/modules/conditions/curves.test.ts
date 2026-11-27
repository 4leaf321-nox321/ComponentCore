import { curveUseOf, emptyConditions } from '@/modules/conditions/api'
import type { Conditions, ConditionsSchema, CurveItem } from '@/modules/conditions/api'
import {
  curveMismatch,
  curveProblems,
  curveSummary,
  curveUsers,
  nextCurveName,
  plotPoints,
  renameCurve,
  tableOfCurve,
} from '@/modules/conditions/curves'

const PSD = { field: 'psd_table', interpolation: 'loglog', unit: 'g^2/Hz' }
const FACTOR = { field: 'frequency_table', interpolation: 'linear', unit: '' }
const RANDOM: CurveItem = { name: 'IEC 랜덤', x: 'frequency', unit: 'g^2/Hz', interpolation: 'loglog', points: [[20, 0.04], [2000, 0.04]], scale: 1 }

test('새 곡선 이름은 겹치지 않는다 — 하중 이름에서 지으면 그 이름, 있으면 번호를 붙인다', () => {
  expect(nextCurveName([])).toBe('곡선 1')
  expect(nextCurveName([{ ...RANDOM, name: '곡선 2' }])).toBe('곡선 3')
  expect(nextCurveName([RANDOM], '누름 곡선')).toBe('누름 곡선')
  expect(nextCurveName([{ ...RANDOM, name: '누름 곡선' }, { ...RANDOM, name: '누름 곡선 2' }], '누름 곡선')).toBe('누름 곡선 3')
})

test('그래프의 점 — 값 × 배율, 식이 든 점은 빼고 센다. 배율이 식이면 모양만', () => {
  expect(plotPoints([[10, 1], [100, '=a'], [1000, 2]], 3)).toEqual({ points: [[10, 3], [1000, 6]], skipped: 1, scaled: true })
  expect(plotPoints([[10, 1]], '=k')).toEqual({ points: [[10, 1]], skipped: 0, scaled: false })
  expect(plotPoints(null)).toEqual({ points: [], skipped: 0, scaled: true })
})

test('하중이 곡선을 가리킬 수 있나 — 서버와 같은 규칙(주파수 곡선 · 그 표의 보간 · 단위)', () => {
  expect(curveMismatch(RANDOM, PSD)).toBeNull()
  expect(curveMismatch(RANDOM, FACTOR)).toMatch(/선형 보간이어야 합니다\(곡선: 로그-로그\)/)
  expect(curveMismatch({ ...RANDOM, interpolation: 'linear', unit: '' }, FACTOR)).toBeNull()
  expect(curveMismatch({ ...RANDOM, unit: 'm^2/s^4/Hz' }, PSD)).toMatch(/단위가 g\^2\/Hz이어야/)
  expect(curveMismatch({ ...RANDOM, x: 'time', interpolation: 'linear' }, FACTOR)).toMatch(/주파수 곡선만.*시간 곡선/)
})

/** 곡선은 공유 — 두 케이스의 하중이 같은 곡선을 가리킨다. */
const SHARED: Conditions = {
  ...emptyConditions(),
  schema_version: 2,
  curves: [RANDOM, { ...RANDOM, name: '딴 곡선' }],
  // 화면이 채운 고른 케이스의 사본 — 맨 위에도 있다(`putCaseView`).
  loads: [{ name: 'X', type: 'psd_acceleration', curve: 'IEC 랜덤' }],
  cases: [
    { name: '가', loads: [{ name: 'X', type: 'psd_acceleration', curve: 'IEC 랜덤' }] },
    { name: '나', loads: [{ name: 'Y', type: 'psd_acceleration', curve: 'IEC 랜덤' }, { name: 'Z', type: 'psd_acceleration', curve: '딴 곡선' }] },
  ],
} as Conditions

test('곡선을 쓰는 하중 · 이름 바꾸기는 모든 케이스에서', () => {
  expect(curveUsers(SHARED, 'IEC 랜덤')).toEqual(['케이스 ‘가’ · 하중 ‘X’', '케이스 ‘나’ · 하중 ‘Y’'])
  const next = renameCurve(SHARED, 'IEC 랜덤', '규격 랜덤') as Conditions & { cases: { loads: { curve: string }[] }[] }
  expect(next.curves?.map((one) => one.name)).toEqual(['규격 랜덤', '딴 곡선'])
  expect(next.loads[0].curve).toBe('규격 랜덤')
  expect(next.cases.map((one) => one.loads.map((load) => load.curve))).toEqual([['규격 랜덤'], ['규격 랜덤', '딴 곡선']])
  // 케이스가 없으면 맨 위의 하중만.
  const v1 = { ...emptyConditions(), curves: [RANDOM], loads: [{ name: 'X', curve: 'IEC 랜덤' }, { name: 'W' }] }
  expect(curveUsers(v1, 'IEC 랜덤')).toEqual(['하중 ‘X’'])
  expect(renameCurve(v1, 'IEC 랜덤', '새').loads.map((one) => one.curve)).toEqual(['새', undefined])
})

test('곡선을 떼면 점 × 배율이 표로 — 배율이 식이면 옮기지 않는다(크기가 말없이 달라진다)', () => {
  expect(tableOfCurve({ ...RANDOM, scale: 2 })).toEqual([
    [20, 0.08],
    [2000, 0.08],
  ])
  expect(tableOfCurve({ ...RANDOM, points: [[20, '=p'], [2000, 0.04]] })).toEqual([
    [20, '=p'],
    [2000, 0.04],
  ])
  expect(tableOfCurve({ ...RANDOM, scale: '=k' })).toBeNull()
  expect(tableOfCurve(undefined)).toBeNull()
})

test('점의 문제를 미리 — 두 점 이상 · 가로축 순서 · 로그-로그는 0보다 큰 점, 식은 보지 않는다', () => {
  expect(curveProblems(RANDOM)).toEqual([])
  expect(curveProblems({ ...RANDOM, points: [[20, 0.04]] })).toEqual(['점이 두 개 이상 필요합니다.'])
  expect(curveProblems({ ...RANDOM, points: [[20, 0.04], [10, 0.04], [5, '=a']] })).toEqual(['2행: 가로축 값이 앞 행보다 커야 합니다.'])
  expect(curveProblems({ ...RANDOM, points: [[0, 0.04], [20, 0]] })).toEqual(['로그-로그 보간은 0보다 큰 점만 받습니다.'])
  expect(curveProblems({ ...RANDOM, points: [['=f1', 1], ['=f2', 2]], interpolation: 'linear' })).toEqual([])
  expect(curveSummary(RANDOM)).toBe('주파수 · 로그-로그 · 2점')
})

test('정적 하중은 시간 · 단계 곡선을 읽는다 — 해석 종류로 고른다', () => {
  const schema = {
    groups: {},
    curves: {
      label: '곡선',
      fields: {},
      required: [],
      uses: { force: FACTOR },
      time_use: { field: 'time_table', interpolation: 'linear', unit: '', axes: ['time', 'step'] },
      time_loads: ['force'],
    },
  } as unknown as ConditionsSchema
  const timeUse = curveUseOf(schema, 'force', 'static')
  expect(timeUse?.field).toBe('time_table')
  expect(curveUseOf(schema, 'force', 'harmonic')?.field).toBe('frequency_table')
  const ramp: CurveItem = { name: '램프', x: 'time', interpolation: 'linear', unit: '', points: [[0, 0], [1, 1]] }
  expect(curveMismatch(ramp, timeUse!)).toBeNull()
  expect(curveMismatch({ ...ramp, x: 'step' }, timeUse!)).toBeNull()
  expect(curveMismatch({ ...ramp, x: 'frequency' }, timeUse!)).toBe('시간 곡선이나 단계 곡선만 쓸 수 있습니다(주파수 곡선).')
  expect(curveMismatch(ramp, FACTOR)).toBe('주파수 곡선만 쓸 수 있습니다(시간 곡선). 시간 곡선과 단계 곡선은 정적 해석의 하중에 씁니다.')
})
