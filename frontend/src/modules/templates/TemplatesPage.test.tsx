import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import TemplatesPage from '@/modules/templates/TemplatesPage'

const MINE = {
  id: 'a',
  name: '내 브래킷',
  description: 'L 자',
  owner_id: 'u1',
  owner_name: '나',
  is_shared: false,
  mine: true,
  node_count: 3,
  updated_at: '2026-09-19T00:00:00Z',
}
const SHARED = { ...MINE, id: 'b', name: '공용 지그판', is_shared: true, mine: false, owner_name: '동료' }

function mockFetch(items: unknown[]) {
  const calls: { url: string; method: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push({ url, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : null })
    const body = url.includes('/templates?') ? { items, total: items.length, limit: 20, offset: 0 } : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return calls
}

test('자리(내 것 · 공용)로 나눠 보고, 내 것은 공용으로 내놓고 남의 것은 복사한다', async () => {
  const calls = mockFetch([MINE, SHARED])
  render(
    <MemoryRouter>
      <TemplatesPage />
    </MemoryRouter>,
  )
  await waitFor(() => expect(screen.getByText('내 브래킷')).toBeInTheDocument())

  // 내 것에는 「공용으로 내놓기」, 남의 것에는 「내 것으로 복사」 가 뜬다.
  fireEvent.click(screen.getByRole('button', { name: '공용으로 내놓기' }))
  await waitFor(() => expect(calls.some((c) => c.method === 'PATCH' && c.url.endsWith('/templates/a'))).toBe(true))
  expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ is_shared: true })

  fireEvent.click(screen.getByRole('button', { name: '내 것으로 복사' }))
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/templates/b/copy'))).toBe(true))

  // 자리 탭은 scope 로 물어본다.
  fireEvent.mouseDown(screen.getByRole('tab', { name: '공용' }))
  await waitFor(() => expect(calls.some((c) => c.url.includes('scope=shared'))).toBe(true))
})
