import { emptyConditions } from '@/modules/conditions/api'
import type { Conditions, ConditionsSchema } from '@/modules/conditions/api'
import { readiness } from '@/modules/conditions/readiness'
import type { ReadinessInput } from '@/modules/conditions/readiness'

const SCHEMA = {
  schema_version: 1,
  units: { system: 'mm_n_tonne' },
  unit_systems: [],
  analysis: {},
  entities: [],
  groups: {
    constraints: { label: '구속', types: ['fixed_support'], fields: { name: {}, type: {}, on: {} }, required: [] },
    loads: {
      label: '하중',
      types: ['pressure', 'standard_earth_gravity'],
      fields: { name: {}, type: { labels: { pressure: '압력', standard_earth_gravity: '중력' } }, on: { only_for: ['pressure'] } },
      required: [],
    },
    contacts: { label: '접촉', types: ['bonded'], fields: { name: {}, type: {}, source: {}, target: {} }, required: [] },
    initial: { label: '초기조건', types: [], fields: { type: {} }, required: [] },
    mesh_hints: { label: '국부 메시', types: [], fields: { on: { whole: '전체' } }, required: [] },
  },
} as unknown as ConditionsSchema

const base = (draft: Partial<Conditions>): ReadinessInput => ({
  draft: { ...emptyConditions(), ...draft },
  schema: SCHEMA,
  bodies: null,
  converted: null,
  notes: [],
  geometry: [],
})

test('물성이 없는 파트를 짚는다 — 해석에서 제외한 파트는 보지 않는다', () => {
  const items = readiness({
    ...base({
      materials: [{ apply_to: ['바닥판'], ref: { name: '강' }, payload: {} }],
      body_settings: [{ name: '덮개', suppressed: true }],
    }),
    bodies: [{ name: '바닥판' }, { name: '기둥' }, { name: '덮개' }],
  })
  expect(items).toEqual([
    { level: 'warn', where: '파트 ‘기둥’', text: '물성이 지정되지 않았습니다.', open: { kind: 'part', name: '기둥' } },
  ])
})

test('물성 값의 문제는 파트에 지정한 물성만 — 담아만 둔 재료는 내보내지 않는다', () => {
  const missing = { missing_structural: ['탄성계수'] }
  const items = readiness({
    ...base({
      materials: [
        { apply_to: ['전체'], ref: { name: '강' }, payload: {} },
        { apply_to: [], ref: { name: '담아 둔 것' }, payload: {} },
      ],
    }),
    converted: [missing, missing] as unknown as ReadinessInput['converted'],
  })
  expect(items).toEqual([
    { level: 'warn', where: '물성 ‘강’', text: '구조 해석에 필요한 항목 누락: 탄성계수', open: { kind: 'library', index: 0 } },
  ])
})

test('조건의 적용 대상 — 쓰는 종류만 보고, 없는 그룹 이름도 짚는다. 「전체」 는 그룹이 아니어도 된다', () => {
  const items = readiness(
    base({
      named_selections: [{ name: '바닥', entity: 'face', select: { role: 'bottom' } }],
      loads: [
        { name: '누름', type: 'pressure', on: '' },
        { name: '무게', type: 'standard_earth_gravity' },
        { type: 'pressure', on: '지운 그룹' },
      ],
      contacts: [{ name: '본딩', type: 'bonded', source: '바닥', target: '' }],
      mesh_hints: [{ on: '전체' }],
    }),
  )
  expect(items.map((one) => [one.where, one.text, one.open])).toEqual([
    ['하중 ‘누름’', '적용 대상(선택 그룹)이 지정되지 않았습니다.', { kind: 'item', group: 'loads', index: 0 }],
    ['하중 ‘압력’', '선택 그룹 ‘지운 그룹’이(가) 없습니다.', { kind: 'item', group: 'loads', index: 2 }],
    ['접촉 ‘본딩’', '대상면(선택 그룹)이 지정되지 않았습니다.', { kind: 'item', group: 'contacts', index: 0 }],
  ])
})

test('좌표만 쓰는 선택 그룹 · 식 알림 · 옮긴 메시 · 도면 문제를 한 목록에, 경고가 먼저', () => {
  const items = readiness({
    ...base({ named_selections: [{ name: '찍은 면', entity: 'face', select: { what: 'faces', near: [1, 2, 3] } }] }),
    notes: [
      { where: '하중 ‘누름’ 크기', level: 'info', text: '= 3 MPa' },
      { where: '구속 ‘밀기’ X 변위량', level: 'warn', text: "모르는 이름 '없는것'" },
    ],
    geometry: ['스케치가 닫히지 않았습니다'],
    moved: ['볼트 바디'],
  })
  expect(items.map((one) => [one.level, one.where])).toEqual([
    ['warn', '도면'],
    ['warn', '선택 그룹 ‘찍은 면’'],
    ['warn', '구속 ‘밀기’ X 변위량'],
    ['info', '하중 ‘누름’ 크기'],
    ['info', '국부 메시'],
  ])
  expect(items[1].open).toEqual({ kind: 'selection', index: 0 })
})
