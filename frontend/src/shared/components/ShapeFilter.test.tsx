import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import { addShapeParams, describeShape, ShapeFilter, shapeConditionCount } from '@/shared/components/ShapeFilter'
import type { ShapeQuery } from '@/shared/components/ShapeFilter'

test('조건을 목록 API 의 쿼리로 — 부피는 cm³ 를 mm³ 로', () => {
  const query = new URLSearchParams()
  addShapeParams(query, { has: ['hole', 'sheet_metal'], thread: 'M6', fits: '100x60', volumeMax: 25, hole: 6.6, holes: 4 })
  expect(query.getAll('has')).toEqual(['hole', 'sheet_metal'])
  expect(Object.fromEntries([...query].filter(([key]) => key !== 'has'))).toEqual({ thread: 'M6', fits: '100x60', volume_max: '25000', hole: '6.6', holes: '4' })
  expect(shapeConditionCount({ has: ['hole'], thread: 'M6', hole: 6.6 })).toBe(3)
  expect(shapeConditionCount({})).toBe(0)
})

test('목록 한 줄의 형상 — 크기와 구멍 몇 가지', () => {
  const shape = {
    size: [120, 40, 8],
    dims: [8, 40, 120],
    volume: 1,
    solids: 1,
    holes: [
      { d: 5, n: 1, through: 0 },
      { d: 6.6, n: 2, through: 2 },
      { d: 11, n: 2, through: 0 },
      { d: 20, n: 1, through: 1 },
    ],
    hole_count: 6,
    ops: [],
    threads: [],
    params: [],
  }
  expect(describeShape(shape)).toBe('120 × 40 × 8 · 구멍 Ø5 Ø6.6×2 Ø11×2 …')
  expect(describeShape({ ...shape, holes: [] })).toBe('120 × 40 × 8')
})

test('고른 뒤 「적용」 을 눌러야 거른다', () => {
  const onChange = vi.fn()
  function Host() {
    const [value, setValue] = useState<ShapeQuery>({})
    return (
      <ShapeFilter
        value={value}
        onChange={(next) => {
          setValue(next)
          onChange(next)
        }}
      />
    )
  }
  render(<Host />)
  fireEvent.click(screen.getByRole('button', { name: /형상/ }))
  fireEvent.click(screen.getByRole('button', { name: '판금' }))
  fireEvent.change(screen.getByLabelText('나사 호칭'), { target: { value: 'M6' } })
  fireEvent.change(screen.getByLabelText('상자 크기'), { target: { value: '100x60x30' } })
  expect(onChange).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '적용' }))
  expect(onChange).toHaveBeenLastCalledWith({ has: ['sheet_metal'], thread: 'M6', fits: '100x60x30' })
  expect(screen.getByRole('button', { name: /형상 3/ })).toHaveAttribute('aria-pressed', 'true')
})
