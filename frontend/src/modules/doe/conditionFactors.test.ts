import type { ConditionsSchema } from '@/modules/conditions/api'
import { choiceTargets, factorName, propertyNames } from '@/modules/doe/conditionFactors'

const SPEC = {
  unit_systems: [],
  entities: [],
  analysis: {
    properties: {
      type: { enum: ['modal', 'static'], labels: { modal: '모달', static: '정적' } },
      prestressed: { title: '선응력 반영', type: 'boolean', only_for: ['modal'] },
      modes: { title: '모드 수', anyOf: [{ type: 'integer' }, { type: 'string' }] },
    },
  },
  groups: {
    contacts: {
      label: '접촉',
      types: ['bonded', 'frictional'],
      fields: {
        name: {},
        type: { enum: ['bonded', 'frictional'], labels: { bonded: '본딩', frictional: '마찰' } },
        source: { title: '접촉면' },
        target: { title: '대상면' },
        friction: { title: '마찰계수', anyOf: [{ type: 'number' }], only_for: ['frictional'] },
        formulation: { title: '정식화', enum: ['program_controlled', 'mpc'], labels: { program_controlled: '프로그램이 정함', mpc: 'MPC' } },
      },
      required: [],
      accepts: { bonded: [{ entity: 'face' }], frictional: [{ entity: 'face' }] },
    },
    constraints: {
      label: '구속',
      types: ['displacement'],
      fields: { name: {}, type: { enum: ['displacement'] }, on: {}, x: { title: 'X', component: true, dimension: 'length', only_for: ['displacement'] } },
      required: [],
    },
  },
} as unknown as ConditionsSchema

const CONDITIONS = {
  named_selections: [
    { name: '윗판', entity: 'face', select: {} },
    { name: '아랫판', entity: 'face', select: {} },
    { name: '모서리', entity: 'edge', select: {} },
  ],
  contacts: [{ name: '블록-판', type: 'bonded', source: '윗판', target: '아랫판' }],
  constraints: [{ name: '밀기', type: 'displacement', on: '윗판', x: 0 }],
  analysis: { type: 'modal' },
}

test('조건에서 **고를 수 있는 칸**을 사양표로 뽑는다 — 종류 · 선택 그룹 · 정식화 · 자유/고정 · 해석', () => {
  const targets = choiceTargets(CONDITIONS, SPEC)
  const byLabel = Object.fromEntries(targets.map((one) => [one.label, one]))
  expect(byLabel['접촉 「블록-판」 · 종류'].options.map((o) => o.label)).toEqual(['본딩', '마찰'])
  expect(byLabel['접촉 「블록-판」 · 종류'].target).toEqual({ group: 'contacts', item: '블록-판', field: 'type' })
  // 선택 그룹은 **받는 종류만**(면) — 모서리는 없다.
  expect(byLabel['접촉 「블록-판」 · 접촉면'].options.map((o) => o.value)).toEqual(['윗판', '아랫판'])
  expect(byLabel['접촉 「블록-판」 · 정식화'].options.map((o) => o.label)).toEqual(['프로그램이 정함', 'MPC'])
  // 본딩에는 마찰계수 칸이 없다(숫자 칸은 어차피 `=식` 으로 훑는다).
  expect(targets.some((one) => one.label.includes('마찰계수'))).toBe(false)
  expect(byLabel['구속 「밀기」 · X'].options).toEqual([
    { value: null, label: '자유' },
    { value: 0, label: '고정' },
  ])
  expect(byLabel['해석 설정 · 종류'].target).toEqual({ group: 'analysis', field: 'type' })
  expect(byLabel['해석 설정 · 선응력 반영'].options.map((o) => o.value)).toEqual([false, true])
  // 사양표가 없으면 고를 칸도 없다.
  expect(choiceTargets(CONDITIONS, null)).toEqual([])
})

test('인자 이름은 겹치지 않게 번호를 붙이고, 물성 이름은 담아 둔 재료에서 모은다', () => {
  const taken = new Set(['두께'])
  expect(factorName('접촉 종류', taken)).toBe('접촉 종류')
  expect(factorName('접촉 종류', taken)).toBe('접촉 종류 2')
  expect(propertyNames([{ payload: { declared_properties: [{ item: '탄성계수' }] } }])).toEqual(['밀도', '푸아송비', '탄성계수'])
})
