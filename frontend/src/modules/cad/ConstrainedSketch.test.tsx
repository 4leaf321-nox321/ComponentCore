import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'

import { ConstrainedForm, constrainedPath, defaultConstrained } from '@/modules/cad/ConstrainedSketch'
import type { ConstrainedSpec, Solved } from '@/modules/cad/ConstrainedSketch'
import { SketchCanvas } from '@/modules/cad/SketchCanvas'
import type { SketchShape } from '@/modules/cad/SketchCanvas'

const BOX: ConstrainedSpec = { type: 'constrained', ...defaultConstrained() }

test('윤곽 경로 — 직선은 L, 호는 A(반시계면 sweep 1, 반 바퀴 넘으면 큰 호)', () => {
  const shape: ConstrainedSpec = {
    type: 'constrained',
    points: { a: [0, 0], b: [20, 0], o: [10, 0] },
    segments: [
      { from: 'a', to: 'b' },
      { from: 'b', to: 'a', center: 'o', ccw: true },
    ],
    constraints: [],
  }
  expect(constrainedPath(shape, { a: [0, 0], b: [20, 0], o: [10, 0] })).toBe('M 0 0 L 20 0 A 10 10 0 0 1 0 0 Z')
  // 반시계로 270° — 큰 호.
  const wide: ConstrainedSpec = {
    type: 'constrained',
    points: {},
    segments: [
      { from: 'p', to: 'q', center: 'o', ccw: true },
      { from: 'q', to: 'p' },
    ],
    constraints: [],
  }
  expect(constrainedPath(wide, { p: [10, 0], q: [0, -10], o: [0, 0] })).toBe('M 10 0 A 10 10 0 1 1 0 -10 L 10 0 Z')
})

function Host({ solved, onShape }: { solved?: Solved; onShape: (next: ConstrainedSpec) => void }) {
  const [shape, setShape] = useState<ConstrainedSpec>(BOX)
  return (
    <ConstrainedForm
      shape={shape}
      solved={solved}
      params={{}}
      onChange={(patch) => {
        const next = { ...shape, ...patch }
        setShape(next)
        onShape(next)
      }}
    />
  )
}

test('구속을 더하고, 구간을 나누면 뒤 구간을 가리키던 구속의 번호가 따라 밀린다', () => {
  const onShape = vi.fn()
  render(<Host solved={{ points: {}, free: 1 }} onShape={onShape} />)
  expect(screen.getByRole('status')).toHaveTextContent('남은 자유도: 1')
  fireEvent.change(screen.getByLabelText('추가할 구속'), { target: { value: 'perpendicular' } })
  fireEvent.click(screen.getByRole('button', { name: '+ 구속' }))
  let last = onShape.mock.calls.at(-1)![0] as ConstrainedSpec
  expect(last.constraints.at(-1)).toEqual({ type: 'perpendicular', segments: [0, 1] })

  // 구간 0 을 나누면 새 점 e 가 생기고, 구간 1 · 2 · 3 을 가리키던 구속이 2 · 3 · 4 로.
  fireEvent.click(screen.getAllByRole('button', { name: '분할' })[0])
  last = onShape.mock.calls.at(-1)![0] as ConstrainedSpec
  expect(last.points.e).toEqual([20, 0])
  expect(last.segments.slice(0, 2)).toEqual([
    { from: 'a', to: 'e' },
    { from: 'e', to: 'b' },
  ])
  expect(last.constraints.find((one) => one.type === 'vertical')!.segments).toEqual([2])
  expect(last.constraints.at(-1)!.segments).toEqual([0, 2])
})

test('직선을 호로 바꾸면 중심점이 새로 생긴다 — 반지름은 구속으로', () => {
  const onShape = vi.fn()
  render(<Host onShape={onShape} />)
  expect(screen.getByRole('status')).toHaveTextContent('계산 중')
  fireEvent.click(screen.getAllByRole('button', { name: '호로 변경' })[1])
  const last = onShape.mock.calls.at(-1)![0] as ConstrainedSpec
  expect(last.segments[1]).toEqual({ from: 'b', to: 'c', center: 'e', ccw: false })
  expect(Object.keys(last.points)).toContain('e')
})

test('캔버스는 서버가 푼 모양을 그리고, 못 풀면 까닭을 보인다', async () => {
  let answer: Response = new Response(JSON.stringify({ points: { a: [0, 0], b: [40, 0], c: [40, 30], d: [0, 30] }, free: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  const fetched = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => answer.clone())
  const shapes = [{ ...BOX, at: [0, 0], mode: 'add' } as SketchShape]
  const { container, rerender } = render(<SketchCanvas shapes={shapes} onChange={() => {}} />)
  await waitFor(() => expect(container.querySelector('[data-solved="yes"]')).not.toBeNull())
  expect(fetched.mock.calls[0][0]).toContain('/cad/recipe/sketch-solve')
  expect(screen.getByRole('status')).toHaveTextContent('완전히 구속되었습니다')

  answer = new Response(JSON.stringify({ error: { code: 'CCR-CAD-0021', message: '구속 8(길이) — 앞의 구속과 맞지 않습니다, 10 어긋남' } }), { status: 400, headers: { 'Content-Type': 'application/json' } })
  rerender(<SketchCanvas shapes={[{ ...shapes[0], constraints: [...BOX.constraints, { type: 'length', segments: [2], value: 50 }] } as SketchShape]} onChange={() => {}} />)
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('구속 8(길이)'))
})
