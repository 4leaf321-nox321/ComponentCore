import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import DoeStudiesPage from '@/modules/doe/DoeStudiesPage'

test('내 것 / 모두 · 찾기 · 대상 작업 꼬리표는 서버가 거른다', async () => {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = decodeURIComponent(String(input))
    calls.push(url)
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    if (url.includes('/doe/tags')) return json(['고객A', 'EMC'])
    if (url.includes('/doe?')) return json({ items: [], total: 0, limit: 25, offset: 0 })
    return json({})
  })
  render(
    <MemoryRouter>
      <DoeStudiesPage />
    </MemoryRouter>,
  )
  await waitFor(() => expect(calls.some((one) => one.includes('/doe?') && one.includes('scope=mine'))).toBe(true))
  expect(calls.some((one) => one.includes('q='))).toBe(false)

  fireEvent.click(screen.getByRole('button', { name: '전체' }))
  await waitFor(() => expect(calls.some((one) => one.includes('/doe?') && one.includes('scope=all'))).toBe(true))

  // 찾기는 잠깐 기다렸다 보낸다(SearchBox) — 이름 · 설명 · 대상 작업 · 만든 사람.
  fireEvent.change(screen.getByLabelText('검색'), { target: { value: '브래킷 EMC' } })
  await waitFor(() => expect(calls.some((one) => one.includes('q=브래킷 EMC') || one.includes('q=브래킷+EMC'))).toBe(true))

  // 꼬리표 칩은 대상 작업의 것 — 서버가 보이는 DOE 에서 모아 준다.
  fireEvent.click(await screen.findByRole('button', { name: '고객A' }))
  await waitFor(() => expect(calls.some((one) => one.includes('tag=고객A'))).toBe(true))
  expect(screen.getByText('조건에 맞는 DOE가 없습니다')).toBeInTheDocument()
})
