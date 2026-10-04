import { fireEvent, render, screen } from '@testing-library/react'

import { PointsScatter } from '@/modules/doe/PointsScatter'

const points = [
  { number: 1, values: { 두께: 4, 길이: 80, 재료: 'SECC' }, status: 'ok' as const, batch: 1 },
  { number: 2, values: { 두께: 8, 길이: 100, 재료: 'AL' }, status: 'failed' as const, batch: 1 },
  { number: 3, values: { 두께: 6, 길이: 90, 재료: 'AL' }, status: 'ok' as const, batch: 2 },
  { values: { 두께: 12, 길이: 80, 재료: 'AL' }, status: 'rejected' as const },
]

test('변수가 넷까지면 모든 짝을 그리고, 실패 · 걸린 후보 · 묶음을 가르며, 점을 누르면 고른다', () => {
  const onPick = vi.fn()
  const { container } = render(<PointsScatter names={['두께', '길이', '재료']} points={points} batches={2} focus={3} onPick={onPick} />)
  // 셋이면 짝이 셋 — 글자 변수(재료)도 차례로 놓는다.
  expect(screen.getByRole('img', { name: '두께 대 길이' })).toBeInTheDocument()
  expect(screen.getByRole('img', { name: '길이 대 재료' })).toBeInTheDocument()
  expect(container.querySelectorAll('[data-status="failed"]')).toHaveLength(3)
  expect(container.querySelectorAll('[data-status="rejected"]')).toHaveLength(3)
  expect(screen.getByText(/배치 2/)).toBeInTheDocument()
  expect(screen.getByText(/제약 조건으로 제외된 후보/)).toBeInTheDocument()

  const first = screen.getByRole('img', { name: '두께 대 길이' })
  fireEvent.click(first.querySelector('circle title')!.parentElement!)
  expect(onPick).toHaveBeenCalledWith(1)
})

test('변수가 다섯 이상이면 두 변수를 골라 그린다', () => {
  const names = ['a', 'b', 'c', 'd', 'e']
  const many = [{ number: 1, values: { a: 1, b: 2, c: 3, d: 4, e: 5 } }, { number: 2, values: { a: 2, b: 1, c: 0, d: 1, e: 2 } }]
  render(<PointsScatter names={names} points={many} />)
  expect(screen.getByRole('img', { name: 'a 대 b' })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('세로축 변수'), { target: { value: 'e' } })
  expect(screen.getByRole('img', { name: 'a 대 e' })).toBeInTheDocument()
})
