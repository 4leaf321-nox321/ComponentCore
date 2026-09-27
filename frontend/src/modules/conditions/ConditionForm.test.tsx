import { fireEvent, render, screen } from '@testing-library/react'

import type { ConditionItem, GroupSchema } from '@/modules/conditions/api'
import { ConditionForm } from '@/modules/conditions/ConditionForm'

const axis = (title: string, onlyFor = ['displacement', 'remote_displacement']) => ({
  title,
  anyOf: [{ type: 'number' }, { type: 'null' }],
  component: true,
  only_for: onlyFor,
  ...(onlyFor.length === 1 ? { unit: '도' } : { dimension: 'length' }),
})
const cylinder = (title: string, description: string) => ({ title, description, enum: ['fixed', 'free'], default: 'fixed', component: true, only_for: ['cylindrical'] })
const GROUP: GroupSchema = {
  label: '구속',
  types: ['fixed_support', 'displacement', 'remote_displacement', 'frictionless', 'cylindrical', 'elastic_support'],
  fields: {
    name: {},
    type: { enum: ['fixed_support', 'displacement', 'remote_displacement', 'frictionless', 'cylindrical', 'elastic_support'] },
    on: {},
    cs: { type: 'string', default: 'global', only_for: ['displacement', 'remote_displacement'] },
    location: {
      title: '원격점',
      enum: ['centroid', 'cs_origin'],
      default: 'centroid',
      only_for: ['remote_displacement'],
      labels: { centroid: '선택 그룹의 중심', cs_origin: '좌표계의 원점' },
    },
    x: axis('X'),
    y: axis('Y'),
    z: axis('Z'),
    rx: axis('회전 X', ['remote_displacement']),
    ry: axis('회전 Y', ['remote_displacement']),
    rz: axis('회전 Z', ['remote_displacement']),
    stiffness: { title: '기초 강성', anyOf: [{ type: 'number' }, { type: 'null' }], description: '법선으로 단위 길이 눌리는 데 드는 압력', only_for: ['elastic_support'] },
    radial: cylinder('반지름', '원통 중심에서 바깥쪽'),
    axial: cylinder('축', '원통 축을 따라'),
    tangential: cylinder('접선', '원통 축 둘레로 도는 방향'),
  },
  required: [],
  implied: {
    fixed_support: [
      { label: 'X', hold: 'fixed', hint: '모든 이동을 막는다' },
      { label: 'Y', hold: 'fixed', hint: '' },
      { label: 'Z', hold: 'fixed', hint: '' },
    ],
    frictionless: [
      { label: '법선', hold: 'fixed', hint: '면에 수직' },
      { label: '접선', hold: 'free', hint: '면을 따라 미끄러진다' },
    ],
    elastic_support: [
      { label: '법선', hold: 'spring', hint: '기초 강성만큼 버틴다' },
      { label: '접선', hold: 'free', hint: '받치지 않는다' },
    ],
  },
}

const pressed = (axisName: string) =>
  screen.getByRole('group', { name: `${axisName} 구속` }).querySelector('[aria-pressed="true"]')?.textContent

test('성분은 **자유 · 고정 · 변위량**을 고른다 — 빈칸 · 0 을 알아서 읽게 두지 않는다', () => {
  let item: ConditionItem = { name: '받침', type: 'displacement', on: '바닥', x: null, y: 0, z: 0.5 }
  const view = () => <ConditionForm group={GROUP} item={item} names={[]} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect([pressed('X'), pressed('Y'), pressed('Z')]).toEqual(['자유', '고정', '변위량'])
  expect(screen.queryByLabelText('X 변위량')).toBeNull()
  expect(screen.getByLabelText('Z 변위량')).toHaveValue('0.5')

  // 변위량을 고르면 칸이 열리고, 아직 0 이어도 「고정」 으로 돌아가지 않는다.
  fireEvent.click(screen.getAllByRole('button', { name: '변위량' })[0])
  expect(item.x).toBe(0)
  rerender(view())
  expect(pressed('X')).toBe('변위량')
  fireEvent.change(screen.getByLabelText('X 변위량'), { target: { value: '=밀기' } })
  expect(item.x).toBe('=밀기')

  // 고정은 0, 자유는 null.
  rerender(view())
  fireEvent.click(screen.getAllByRole('button', { name: '자유' })[2])
  expect(item.z).toBeNull()
})

test('원통 지지는 **반지름 · 축 · 접선**마다 자유 · 고정을 고른다 — 좌표계 칸은 없다', () => {
  let item: ConditionItem = { name: '핀', type: 'cylindrical', on: '구멍' }
  const view = () => <ConditionForm group={GROUP} item={item} names={[]} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect([pressed('반지름'), pressed('축'), pressed('접선')]).toEqual(['고정', '고정', '고정'])
  expect(screen.queryByRole('group', { name: 'X 구속' })).toBeNull()
  expect(screen.queryByLabelText('좌표계')).toBeNull()
  expect(screen.getByText('원통 축 둘레로 도는 방향')).toBeInTheDocument()

  const turn = screen.getByRole('group', { name: '접선 구속' })
  fireEvent.click(turn.querySelector('button')!)
  expect(item.tangential).toBe('free')
  rerender(view())
  expect(pressed('접선')).toBe('자유')
})

test('종류가 정하는 방향은 **잠긴 단추**로 보인다 — 어느 방향이 어떻게 잡히는지', () => {
  const { rerender } = render(<ConditionForm group={GROUP} item={{ name: '고정', type: 'fixed_support', on: '바닥' }} names={[]} onChange={() => {}} />)
  expect([pressed('X'), pressed('Y'), pressed('Z')]).toEqual(['고정', '고정', '고정'])
  for (const button of screen.getByRole('group', { name: 'X 구속' }).querySelectorAll('button')) expect(button).toBeDisabled()
  expect(screen.queryByLabelText('X 변위량')).toBeNull()

  rerender(<ConditionForm group={GROUP} item={{ name: '미끄럼', type: 'frictionless', on: '바닥' }} names={[]} onChange={() => {}} />)
  expect([pressed('법선'), pressed('접선')]).toEqual(['고정', '자유'])
  expect(screen.getByText('면을 따라 미끄러진다')).toBeInTheDocument()
  expect(screen.getByText(/바꿀 수 없습니다/)).toBeInTheDocument()
})

test('원격 변위는 이동 X · Y · Z 와 **회전 X · Y · Z** 를 고르고, 원격점을 사람 말로 고른다', () => {
  let item: ConditionItem = { name: '핀', type: 'remote_displacement', on: '구멍', x: 0, rz: null }
  const view = () => <ConditionForm group={GROUP} item={item} names={[]} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect([pressed('X'), pressed('회전 X'), pressed('회전 Z')]).toEqual(['고정', '자유', '자유'])
  expect(screen.getByLabelText('좌표계')).toBeInTheDocument()
  expect(screen.getByLabelText('원격점')).toHaveTextContent('선택 그룹의 중심')

  fireEvent.click(screen.getByRole('group', { name: '회전 Y 구속' }).querySelectorAll('button')[1])
  expect(item.ry).toBe(0)
  rerender(view())
  expect(pressed('회전 Y')).toBe('고정')
})

test('탄성 지지는 법선이 **스프링**으로 잠겨 보이고, 기초 강성을 적는다', () => {
  let item: ConditionItem = { name: '패드', type: 'elastic_support', on: '바닥' }
  render(<ConditionForm group={GROUP} item={item} names={[]} onChange={(next) => (item = next)} />)
  expect([pressed('법선'), pressed('접선')]).toEqual(['스프링', '자유'])
  expect(screen.queryByLabelText('좌표계')).toBeNull()
  fireEvent.change(screen.getByLabelText('기초 강성'), { target: { value: '0.2' } })
  expect(item.stiffness).toBe(0.2)
  expect(screen.getByText('법선으로 단위 길이 눌리는 데 드는 압력')).toBeInTheDocument()
})

const DIRECTED = ['pressure', 'force', 'standard_earth_gravity']
const LOADS: GroupSchema = {
  label: '하중',
  types: ['pressure', 'force', 'bolt_pretension', 'standard_earth_gravity'],
  fields: {
    name: {},
    type: { enum: ['pressure', 'force', 'bolt_pretension', 'standard_earth_gravity'], labels: { pressure: '압력', force: '힘' } },
    on: { only_for: ['pressure', 'force', 'bolt_pretension'] },
    cs: { type: 'string', default: 'global', only_for: DIRECTED },
    magnitude: { title: '크기', anyOf: [{ type: 'number' }, { type: 'null' }], only_for: ['pressure', 'force'], unit_by_type: true },
    unit: { type: 'string', default: '', hidden: true },
    direction: { title: '방향', direction: true, only_for: DIRECTED, normal_for: ['pressure'] },
    preload: { title: '예압', anyOf: [{ type: 'number' }, { type: 'null' }], only_for: ['bolt_pretension'], bolt: true },
  },
  required: [],
  notes: { force: '합계 힘 — 여러 면에 걸면 나눠 가집니다.' },
  dimensions: { pressure: 'stress', force: 'force' },
}
const MM = { force: 'N', stress: 'MPa', length: 'mm' }

test('하중의 크기에는 **단위계의 단위**가 붙고, 방향은 성분마다 적거나 빠른 단추로 고른다', () => {
  let item: ConditionItem = { name: '밀기', type: 'force', on: '윗면' }
  const view = () => <ConditionForm group={LOADS} item={item} names={[]} units={MM} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.getByLabelText('크기 (N)')).toBeInTheDocument()
  expect(screen.getByText('합계 힘 — 여러 면에 걸면 나눠 가집니다.')).toBeInTheDocument()
  expect(screen.queryByLabelText('unit')).toBeNull()
  // 힘은 법선을 고를 수 없다 — 성분 칸만.
  expect(screen.queryByRole('group', { name: '방향 방식' })).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: '−Z' }))
  expect(item.direction).toEqual([0, 0, -1])
  rerender(view())
  fireEvent.change(screen.getByLabelText('방향 X'), { target: { value: '=기울기' } })
  expect(item.direction).toEqual(['=기울기', 0, -1])
})

test('압력은 **면의 법선**이 기본이고 성분으로 바꿀 수 있다', () => {
  let item: ConditionItem = { name: '누름', type: 'pressure', on: '윗면' }
  const view = () => <ConditionForm group={LOADS} item={item} names={[]} units={MM} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.getByLabelText('크기 (MPa)')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '면의 법선' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByLabelText('방향 X')).toBeNull()
  expect(screen.queryByLabelText('좌표계')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'X · Y · Z 성분' }))
  expect(item.direction).toEqual([0, 0, -1])
  rerender(view())
  expect(screen.getByLabelText('방향 Z')).toHaveValue('-1')
  expect(screen.getByLabelText('좌표계')).toBeInTheDocument()
})

test('볼트는 **예압(N) · 조임량(mm)** 을 고르고, 중력은 선택 그룹 없이 -Z 를 보인다', () => {
  let item: ConditionItem = { name: '조임', type: 'bolt_pretension', on: '볼트' }
  const view = () => <ConditionForm group={LOADS} item={item} names={[]} units={MM} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.getByRole('button', { name: '예압 (N)' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: '조임량 (mm)' }))
  expect(item.unit).toBe('mm')
  rerender(view())
  fireEvent.change(screen.getByLabelText('조임량'), { target: { value: '0.1' } })
  expect(item).toMatchObject({ preload: 0.1, unit: 'mm' })

  rerender(<ConditionForm group={LOADS} item={{ name: '자중', type: 'standard_earth_gravity' }} names={[]} units={MM} onChange={() => {}} />)
  expect(screen.queryByText('선택 그룹')).toBeNull()
  expect(screen.getByLabelText('방향 Z')).toHaveValue('-1')
  expect(screen.queryByLabelText(/크기/)).toBeNull()
})

test('변위량에는 **단위계의 길이**가, 회전에는 도가 칸마다 붙는다 — SI 면 m', () => {
  const item: ConditionItem = { name: '핀', type: 'remote_displacement', on: '구멍', x: 0.001, rx: 2 }
  const { rerender } = render(<ConditionForm group={GROUP} item={item} names={[]} units={{ length: 'm' }} onChange={() => {}} />)
  expect(pressed('X')).toBe('변위량 (m)')
  expect(screen.getByLabelText('X 변위량')).toHaveAttribute('placeholder', '수 또는 =식 · m')
  expect(pressed('회전 X')).toBe('변위량 (도)')
  rerender(<ConditionForm group={GROUP} item={item} names={[]} units={{ length: 'mm' }} onChange={() => {}} />)
  expect(pressed('X')).toBe('변위량 (mm)')
})
