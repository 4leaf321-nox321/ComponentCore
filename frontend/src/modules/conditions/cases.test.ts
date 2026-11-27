import { emptyConditions } from '@/modules/conditions/api'
import type { Conditions } from '@/modules/conditions/api'
import { caseView, followingCase, putCaseView, renamed, saved, withoutPrestress } from '@/modules/conditions/cases'
import type { CaseItem } from '@/modules/conditions/cases'

const PRELOAD: CaseItem = {
  name: '예압',
  analysis: { type: 'static' },
  constraints: [{ name: '바닥 고정', type: 'fixed_support', on: '바닥' }],
  loads: [
    { name: '조임', type: 'bolt_pretension', on: '볼트 면', preload: 1000 },
    { name: '무게', type: 'standard_earth_gravity' },
  ],
  initial: [{ type: 'environment_temperature', value: 80 }],
}
/** 화면이 읽은 v2 — `asConditions` 가 맨 위에 빈 케이스 칸을 채운다. */
const WHOLE = { ...emptyConditions(), schema_version: 2, cases: [PRELOAD, { name: '외력', depends_on: '예압' }] } as Conditions

test('케이스 보기는 공유 칸 + 그 케이스 칸의 v1 모양이고, 비운 칸은 서버의 기본값이다', () => {
  const view = caseView(WHOLE, 0)
  expect(view.schema_version).toBe(1)
  expect(view).not.toHaveProperty('cases')
  expect(view.loads).toBe(PRELOAD.loads)
  expect(caseView(WHOLE, 1)).toMatchObject({ analysis: { type: 'modal' }, constraints: [], loads: [], initial: [] })
  const v1 = emptyConditions()
  expect(caseView(v1, 0)).toBe(v1)
})

test('고친 보기는 공유 칸을 맨 위로, 케이스 칸을 그 케이스로 되돌리고 — 저장할 때 맨 위의 케이스 칸을 뺀다', () => {
  const view = caseView(WHOLE, 1)
  const next = putCaseView(WHOLE, 1, { ...view, units: { system: 'si' }, loads: [{ name: '당김', type: 'force' }] })
  const out = saved(next) as unknown as Record<string, unknown> & { cases: CaseItem[] }
  expect(out.units).toEqual({ system: 'si' })
  expect(out.cases[0]).toBe(PRELOAD)
  expect(out.cases[1]).toMatchObject({ name: '외력', depends_on: '예압', loads: [{ name: '당김' }] })
  expect(out.schema_version).toBe(2)
  for (const key of ['analysis', 'constraints', 'loads', 'initial']) expect(out).not.toHaveProperty(key)
  // 케이스가 없으면 그대로.
  const v1 = emptyConditions()
  expect(saved(putCaseView(v1, 0, v1))).toBe(v1)
})

test('이어지는 케이스는 사슬 규칙을 처음부터 지킨다 — 구속 · 중력만 옮기고, 조인 볼트 · 초기조건은 옮기지 않는다', () => {
  const made = followingCase([PRELOAD], 0)
  expect(made).toMatchObject({
    name: '케이스 2',
    depends_on: '예압',
    analysis: { type: 'static' },
    constraints: PRELOAD.constraints,
    loads: [{ name: '무게', type: 'standard_earth_gravity' }],
    initial: [],
  })
  expect(made.constraints).not.toBe(PRELOAD.constraints)
})

test('케이스 이름을 바꾸면 그것을 앞 케이스로 가리키던 것도 바뀐다', () => {
  const cases = renamed([PRELOAD, { name: '외력', depends_on: '예압' }, { name: '따로' }], 0, '조임')
  expect(cases.map((one) => [one.name, one.depends_on ?? ''])).toEqual([
    ['조임', ''],
    ['외력', '조임'],
    ['따로', ''],
  ])
})

test('케이스의 창에서는 v1 의 선응력 칸을 내지 않는다 — 해석 설정의 선응력 반영, 초기조건 선응력', () => {
  const analysis = { label: '해석 설정', types: ['modal'], fields: { modes: {}, prestressed: {} }, required: [] }
  expect(Object.keys(withoutPrestress('analysis', analysis).fields)).toEqual(['modes'])
  const initial = { label: '초기조건', types: ['environment_temperature', 'prestress'], fields: {}, required: [] }
  expect(withoutPrestress('initial', initial).types).toEqual(['environment_temperature'])
  const loads = { label: '하중', types: ['force'], fields: {}, required: [] }
  expect(withoutPrestress('loads', loads)).toBe(loads)
})
