import { fireEvent, render, screen } from '@testing-library/react'

import type { ConditionItem, GroupSchema } from '@/modules/conditions/api'
import { ConditionForm } from '@/modules/conditions/ConditionForm'

const axis = (title: string) => ({ title, anyOf: [{ type: 'number' }, { type: 'null' }], component: true, only_for: ['displacement'] })
const cylinder = (title: string, description: string) => ({ title, description, enum: ['fixed', 'free'], default: 'fixed', component: true, only_for: ['cylindrical'] })
const GROUP: GroupSchema = {
  label: '구속',
  types: ['fixed_support', 'displacement', 'frictionless', 'cylindrical'],
  fields: {
    name: {},
    type: { enum: ['fixed_support', 'displacement', 'frictionless', 'cylindrical'] },
    on: {},
    cs: { type: 'string', default: 'global', only_for: ['displacement'] },
    x: axis('X'),
    y: axis('Y'),
    z: axis('Z'),
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
