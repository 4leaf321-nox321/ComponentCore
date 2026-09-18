import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import { NumberField } from '@/modules/cad/NumberField'

function Host({ params = {} }: { params?: Record<string, number> }) {
  const [value, setValue] = useState<number | string | null>(12)
  const [all, setAll] = useState(params)
  return (
    <>
      <NumberField
        value={value}
        params={all}
        aria-label="높이"
        onChange={setValue}
        onCreateParam={(name, seed) => setAll((one) => ({ ...one, [name]: seed }))}
      />
      <pre data-testid="state">{JSON.stringify({ value, all })}</pre>
    </>
  )
}
const state = () => JSON.parse(screen.getByTestId('state').textContent!)

test('fx 는 이 값을 그대로 새 변수로 만들어 준다 — 이름만 적으면 된다', () => {
  render(<Host />)
  fireEvent.click(screen.getByRole('button', { name: '높이 변수로' }))
  // 값 칸에 지금 값이 채워져 있다 — 이름만 적으면 형상이 그대로 남는다.
  expect(screen.getByLabelText('새 변수 값')).toHaveValue(12)
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '두께' } })
  fireEvent.click(screen.getByRole('button', { name: /만들기/ }))
  expect(state()).toEqual({ value: '=두께', all: { 두께: 12 } })
})

test('이미 있는 변수는 목록에서 고른다 — 이름을 외워 치지 않는다', () => {
  render(<Host params={{ 판_길이: 80, 두께: 6 }} />)
  fireEvent.click(screen.getByRole('button', { name: '높이 변수로' }))
  fireEvent.click(screen.getByRole('button', { name: /=판_길이/ }))
  expect(state().value).toBe('=판_길이')
})

test('같은 이름은 못 만들게 막고 고르라고 한다', () => {
  render(<Host params={{ 두께: 6 }} />)
  fireEvent.click(screen.getByRole('button', { name: '높이 변수로' }))
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '두께' } })
  expect(screen.getByText(/이미 있는 이름입니다/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /만들기/ })).toBeDisabled()
})

test('식을 직접 쓸 수도 있고, 못 푸는 식은 물음표로 알린다', () => {
  render(<Host params={{ 두께: 6 }} />)
  fireEvent.click(screen.getByRole('button', { name: '높이 변수로' }))
  fireEvent.click(screen.getByRole('button', { name: '식 직접 쓰기' }))
  const field = screen.getByLabelText('높이') as HTMLInputElement
  fireEvent.change(field, { target: { value: '=두께 * 2' } })
  expect(screen.getByTitle('지금 값')).toHaveTextContent('12')
  fireEvent.change(field, { target: { value: '=없는이름' } })
  expect(screen.getByText('?')).toBeInTheDocument()
})

test('못 푸는 식은 **왜인지** 말한다 — 「아직 안 썼다」 는 빨갛게 하지 않는다', () => {
  render(<Host params={{ 두께: 6 }} />)
  fireEvent.click(screen.getByRole('button', { name: '높이 변수로' }))
  fireEvent.click(screen.getByRole('button', { name: '식 직접 쓰기' }))
  // 막 열었을 때(`=`)는 「쓰는 중」 이다 — 오류가 아니다.
  expect(screen.getByText(/식을 쓰세요/)).toBeInTheDocument()
  expect(screen.getByTitle(/식을 쓰세요/)).toHaveTextContent('…')

  const field = screen.getByLabelText('높이') as HTMLInputElement
  fireEvent.change(field, { target: { value: '=두께2' } })
  expect(screen.getByText(/「두께2」 이라는 변수가 없습니다/)).toBeInTheDocument()

  // 그 이름으로 바로 만들 수 있다 — 오타가 아니라 아직 안 만든 것일 때.
  fireEvent.click(screen.getByRole('button', { name: '이 이름으로 만들기' }))
  expect(screen.getByLabelText('새 변수 이름')).toHaveValue('두께2')
  fireEvent.change(screen.getByLabelText('새 변수 값'), { target: { value: '9' } })
  fireEvent.click(screen.getByRole('button', { name: '만들기' })) // 팝오버 안의 것
  expect(state()).toEqual({ value: '=두께2', all: { 두께: 6, 두께2: 9 } })

  // 괄호가 안 닫히면 그렇게 말한다.
  fireEvent.change(screen.getByLabelText('높이'), { target: { value: '=(두께 + 1' } })
  expect(screen.getByText(/식을 읽을 수 없습니다/)).toBeInTheDocument()
})
