import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import WorkPage from '@/modules/works/WorkPage'

const WORK = {
  id: 'w1',
  name: '튜닝 지그',
  description: '',
  kind: 'jig',
  jig_for_part_id: null,
  jig_for_part_name: null,
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

test('지그 작업은 그림 탭이 「지그」 이고, 승격이 지그 카탈로그로 간다', async () => {
  render(
    <MemoryRouter initialEntries={['/works/w1']}>
      <Routes>
        <Route path="/works/:id" element={<WorkPage />} />
      </Routes>
    </MemoryRouter>,
  )
  // 그림 탭의 이름이 「지그」 다 — 부품 작업이면 「부품」.
  await waitFor(() => expect(screen.getByRole('tab', { name: /^지그 v2/ })).toBeInTheDocument())
  expect(await screen.findByRole('button', { name: '지그 카탈로그로 승격' })).toBeInTheDocument()
  // 지그 작업에는 생성기 대신 「잡는 부품」 이 붙는다.
  fireEventMouseDown(screen.getByRole('tab', { name: '잡는 부품' }))
  expect(await screen.findByText('잡는 부품')).toBeInTheDocument()
  expect(screen.queryByText(/지그 생성기/)).toBeNull()
})

function fireEventMouseDown(element: Element) {
  element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
}
