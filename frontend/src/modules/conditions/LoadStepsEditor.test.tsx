import { fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'

import type { ConditionItem } from '@/modules/conditions/api'
import { LoadStepsEditor } from '@/modules/conditions/LoadStepsEditor'

/** 마지막으로 알린 해석 설정. */
const last = (seen: ReturnType<typeof vi.fn>) => seen.mock.calls[seen.mock.calls.length - 1][0] as ConditionItem

/** 창이 들고 있는 해석 설정 — 고칠 때마다 바깥으로 알린다. */
function Harness({ start, seen }: { start: ConditionItem; seen: (next: ConditionItem) => void }) {
  const [item, setItem] = useState(start)
  return (
    <LoadStepsEditor
      analysis={item}
      onChange={(next) => {
        setItem(next)
        seen(next)
      }}
    />
  )
}

test('단계를 처음 더하면 v1 의 단계 수 · 초기 부단계 수를 비우고, 초기 부단계 수는 첫 단계로 옮긴다', () => {
  const seen = vi.fn()
  render(<Harness start={{ type: 'static', steps: 1, substeps: 12 }} seen={seen} />)
  fireEvent.click(screen.getByRole('button', { name: '단계 추가' }))
  expect(seen).toHaveBeenLastCalledWith({ type: 'static', steps: 1, substeps: null, load_steps: [{ name: '단계 1', substeps: { initial: 12 } }] })
  fireEvent.click(screen.getByRole('button', { name: '단계 추가' }))
  fireEvent.change(screen.getByLabelText('단계 2 끝 시간'), { target: { value: '=끝' } })
  fireEvent.change(screen.getByLabelText('단계 2 부단계 최대'), { target: { value: '200' } })
  expect(last(seen).load_steps).toEqual([
    { name: '단계 1', substeps: { initial: 12 } },
    { name: '단계 2', end_time: '=끝', substeps: { maximum: 200 } },
  ])
  fireEvent.click(screen.getByRole('button', { name: '단계 1 삭제' }))
  expect(last(seen).load_steps).toEqual([{ name: '단계 2', end_time: '=끝', substeps: { maximum: 200 } }])
})

test('수렴 제어 · 출력 요청은 기본값이면 비운다(받는 쪽 기본)', () => {
  const seen = vi.fn()
  render(<Harness start={{ type: 'static' }} seen={seen} />)
  fireEvent.change(screen.getByLabelText('평형 반복 상한'), { target: { value: '30' } })
  expect(last(seen).convergence).toEqual({ max_iterations: 30 })
  fireEvent.change(screen.getByLabelText('평형 반복 상한'), { target: { value: '' } })
  expect(last(seen).convergence).toBeNull()

  const values = screen.getByRole('group', { name: '저장할 값' })
  fireEvent.click(within(values).getByLabelText('접촉 압력'))
  expect(last(seen).outputs).toEqual({
    quantities: ['displacement', 'stress', 'strain', 'reaction', 'contact_pressure'],
    at: 'step_end',
  })
  fireEvent.change(screen.getByLabelText('저장 시점'), { target: { value: 'count' } })
  expect(last(seen).outputs).toMatchObject({ at: { count: 10 } })
  fireEvent.change(screen.getByLabelText('저장 시점'), { target: { value: 'step_end' } })
  fireEvent.click(within(values).getByLabelText('접촉 압력'))
  expect(last(seen).outputs).toBeNull()
})
