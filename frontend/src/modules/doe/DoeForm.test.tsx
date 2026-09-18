import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { Recipe } from '@/modules/cad/api'
import { DoeForm } from '@/modules/doe/DoeForm'

const RECIPE: Recipe = {
  params: { 두께: 6, 길이: 90 },
  nodes: [{ id: 'b', op: 'box', length: '=길이', width: 40, height: '=두께' }],
}

function mockApi(count = 10) {
  const calls: { url: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : null
    calls.push({ url, body })
    const payload = url.endsWith('/doe/preview')
      ? { count, max: 200, too_many: count > 200, points: [], varying: ['두께'] }
      : { id: 'study-1' }
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return calls
}

test('변수에 범위를 주면 설계점 개수를 먼저 보여 준다', async () => {
  const calls = mockApi(10)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  // 처음에는 모두 고정 — 바꿀 변수를 고르라고 한다.
  expect(screen.getByText(/바꿀 변수를 하나는 고르세요/)).toBeInTheDocument()

  // [0] 재료 · [1] 두께 행의 방식 · [2] 길이 행 · [3] 방법
  fireEvent.click(screen.getAllByRole('combobox')[1])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '4, 8, 12' } })

  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe/preview'))).toBe(true))
  await waitFor(() => expect(screen.getByText('10')).toBeInTheDocument())
})

test('설계점이 너무 많으면 만들지 못하게 막는다', async () => {
  mockApi(625)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[1])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '1,2,3' } })
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '훑기' } })
  await waitFor(() => expect(screen.getByText(/200 개까지만 만듭니다/)).toBeInTheDocument())
  expect(screen.getByRole('button', { name: '만들기' })).toBeDisabled()
})

test('변수가 없으면 어디서 어떻게 만드는지 알려 주고, 편집기로 보내 준다', () => {
  const onEditRecipe = vi.fn()
  render(<DoeForm recipe={{ nodes: [] }} onCreated={() => {}} onEditRecipe={onEditRecipe} />)
  expect(screen.getByText(/먼저 레시피에 「변수」 를 만들어야 합니다/)).toBeInTheDocument()
  expect(screen.getByText(/fx/)).toBeInTheDocument() // 어느 단추를 누르는지까지
  fireEvent.click(screen.getByRole('button', { name: '레시피 고치러 가기' }))
  expect(onEditRecipe).toHaveBeenCalled()
})
