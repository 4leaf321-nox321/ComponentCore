import { fireEvent, render, screen } from '@testing-library/react'

import type { ConditionItem, GroupSchema } from '@/modules/conditions/api'
import { ConditionForm } from '@/modules/conditions/ConditionForm'

const axis = (title: string) => ({ title, anyOf: [{ type: 'number' }, { type: 'null' }], component: true, only_for: ['displacement'] })
const GROUP: GroupSchema = {
  label: '구속',
  types: ['fixed_support', 'displacement'],
  fields: { name: {}, type: { enum: ['fixed_support', 'displacement'] }, on: {}, x: axis('X'), y: axis('Y'), z: axis('Z') },
  required: [],
}

test('성분은 **자유 · 고정 · 변위량**을 고른다 — 빈칸 · 0 을 알아서 읽게 두지 않는다', () => {
  let item: ConditionItem = { name: '받침', type: 'displacement', on: '바닥', x: null, y: 0, z: 0.5 }
  const view = () => <ConditionForm group={GROUP} item={item} names={[]} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  const pressed = (axisName: string) =>
    screen.getByRole('group', { name: `${axisName} 구속` }).querySelector('[aria-pressed="true"]')?.textContent
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

test('성분 칸은 변위 구속에만 보인다', () => {
  render(<ConditionForm group={GROUP} item={{ name: '고정', type: 'fixed_support', on: '바닥', x: 0 }} names={[]} onChange={() => {}} />)
  expect(screen.queryByRole('group', { name: 'X 구속' })).toBeNull()
})
