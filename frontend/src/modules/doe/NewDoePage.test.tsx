import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import NewDoePage from '@/modules/doe/NewDoePage'

const WORKS = {
  items: [
    { id: 'w1', name: '센서 브래킷', kind: 'part', current_version: 2, description: '' },
    { id: 'w2', name: '브래킷 + 지그', kind: 'assembly', current_version: 1, description: '' },
    { id: 'w3', name: '빈 것', kind: 'jig', current_version: 0, description: '' },
  ],
  total: 3,
  limit: 100,
  offset: 0,
}
const WORK2 = { ...WORKS.items[1], current: { recipe: { params: { 지그_높이: 25 }, nodes: [] } } }

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.endsWith('/works/w2') ? WORK2 : url.includes('/doe/preview') ? { count: 3, max: 200, too_many: false, points: [], varying: ['지그_높이'] } : WORKS
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
})

test('실험계획은 대상을 먼저 고른다 — 부품 · 지그 · 조립 중에서, 저장된 것만', async () => {
  render(
    <MemoryRouter initialEntries={['/doe/new']}>
      <Routes>
        <Route path="/doe/new" element={<NewDoePage />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByRole('button', { name: /센서 브래킷/ })).toBeInTheDocument()
  expect(screen.getByText('조립')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /빈 것/ })).toBeNull() // 저장된 도면이 없으면 못 고른다

  fireEvent.click(screen.getByRole('button', { name: /브래킷 \+ 지그/ }))
  await waitFor(() => expect(screen.getByText(/실험계획 — 브래킷 \+ 지그/)).toBeInTheDocument())
  // 그 조립의 변수(지그_높이)가 인자 표에 뜬다.
  expect(await screen.findByText('지그_높이')).toBeInTheDocument()
})
