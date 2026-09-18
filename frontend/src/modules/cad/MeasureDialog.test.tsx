import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import { keptLabel, MeasureDialog } from '@/modules/cad/MeasureDialog'
import type { KeptMeasure, PickKind } from '@/modules/cad/MeasureDialog'
import type { Pick } from '@/modules/cad/measure'

const HOLE_A: Pick = {
  kind: 'edge',
  edge: { index: 0, kind: 'circle', midpoint: [3, 0, 10], length: 18.85, vertical: false, points: [3, 0, 10, 0, 3, 10, -3, 0, 10], radius: 3, center: [0, 0, 10] },
}
const HOLE_B: Pick = { ...HOLE_A, edge: { ...HOLE_A.kind === 'edge' ? HOLE_A.edge : ({} as never), center: [40, 0, 10], midpoint: [43, 0, 10] } }

function Host({ picks, kept = [] }: { picks: Pick[]; kept?: KeptMeasure[] }) {
  const [kinds, setKinds] = useState<Set<PickKind>>(new Set<PickKind>(['point', 'edge', 'face']))
  return (
    <MeasureDialog
      open
      picks={picks}
      kept={kept}
      kinds={kinds}
      onKinds={setKinds}
      onUndo={() => {}}
      onClear={() => {}}
      onKeep={() => {}}
      onDropKept={() => {}}
      onClose={() => {}}
    />
  )
}

test('하나만 골라도 지름이 나오고, 둘이면 중심 사이 거리까지 한꺼번에 나온다', () => {
  const { rerender } = render(<Host picks={[HOLE_A]} />)
  expect(screen.getByText('⌀6 mm')).toBeInTheDocument()
  expect(screen.getByText(/하나 더 고르면/)).toBeInTheDocument()

  rerender(<Host picks={[HOLE_A, HOLE_B]} />)
  expect(screen.getByText('40 mm')).toBeInTheDocument() // 중심 사이
  expect(screen.getByText('담기 — 3D 에 남깁니다')).toBeInTheDocument()
})

test('고를 종류를 켜고 끄되, 마지막 하나는 꺼지지 않는다', () => {
  render(<Host picks={[]} />)
  const face = screen.getByRole('button', { name: '면' })
  expect(face).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(face)
  expect(face).toHaveAttribute('aria-pressed', 'false')
  fireEvent.click(screen.getByRole('button', { name: '선' }))
  const point = screen.getByRole('button', { name: '점' })
  expect(point).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(point) // 마지막 하나 — 꺼지지 않는다
  expect(point).toHaveAttribute('aria-pressed', 'true')
})

test('담아 둔 측정은 무엇을 어떻게 쟀는지 한 줄로 남는다', () => {
  expect(keptLabel([HOLE_A, HOLE_B])).toBe('원 1 ↔ 원 2 : 40 mm')
  render(<Host picks={[]} kept={[{ id: 'k1', picks: [HOLE_A, HOLE_B], label: '원 1 ↔ 원 2 : 40 mm' }]} />)
  expect(screen.getByText('원 1 ↔ 원 2 : 40 mm')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /지우기/ })).toBeInTheDocument()
})
