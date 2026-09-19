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
  // 그림 탭 이름은 종류와 상관없이 「도면」 — 생성기 탭은 이제 어느 작업에도 없다(새 작업 › 부품에서 지그 생성).
  await waitFor(() => expect(screen.getByRole('tab', { name: /^도면 v2/ })).toBeInTheDocument())
  expect(screen.queryByRole('tab', { name: /지그 만들어 주기/ })).toBeNull()
  expect(await screen.findByRole('button', { name: '공용 지그로 승격' })).toBeInTheDocument()
})

function fireEventMouseDown(element: Element) {
  element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
}
