import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import WorkPage from '@/modules/works/WorkPage'

const WORK = {
  id: 'w1',
  name: '튜닝 지그',
  description: '',
  current_version: 2,
  jig_run_count: 0,
  current: { number: 2, recipe: { params: { 두께: 6 }, nodes: [] }, job: { status: 'done', artifacts: [], progress: [] } },
  jig_options: {},
  promoted_part_id: null,
  promoted_jig_id: null,
}

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/works/w1/versions')
      ? [WORK.current]
      : url.includes('/works/w1/jig-runs')
        ? []
        : url.includes('/works/jig-options')
          ? {}
          : url.includes('/works/w1')
            ? WORK
            : { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
})

test('지그 탭에서 「그린 지그로 승격」 이 보인다 — 지그 일은 지그 탭에 있다', async () => {
  render(
    <MemoryRouter initialEntries={['/works/w1']}>
      <Routes>
        <Route path="/works/:id" element={<WorkPage />} />
      </Routes>
    </MemoryRouter>,
  )
  await waitFor(() => expect(screen.getByRole('tab', { name: /지그/ })).toBeInTheDocument())
  fireEventMouseDown(screen.getByRole('tab', { name: /^지그/ }))
  expect(await screen.findByRole('button', { name: /그린 지그로 승격/ })).toBeInTheDocument()
  expect(screen.getByText(/생성기가 만들 수 없는 지그/)).toBeInTheDocument()
})

function fireEventMouseDown(element: Element) {
  element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
}
