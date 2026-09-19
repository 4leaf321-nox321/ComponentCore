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
  // 그림 탭 이름은 종류와 상관없이 「도면」 — 지그 작업에는 생성기 탭이 아예 없다.
  await waitFor(() => expect(screen.getByRole('tab', { name: /^도면 v2/ })).toBeInTheDocument())
  expect(screen.queryByRole('tab', { name: /지그 만들어 주기/ })).toBeNull()
  expect(await screen.findByRole('button', { name: '공용 지그로 승격' })).toBeInTheDocument()
})

function fireEventMouseDown(element: Element) {
  element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
}

test('부품 작업의 지그 탭 — 옵션은 접혀 있고 「지그 만들어 보기」 가 먼저다', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const part = { ...WORK, kind: 'part' }
    const body = url.includes('/works/w1/versions')
      ? [WORK.current]
      : url.includes('/works/w1/jig-runs')
        ? []
        : url.includes('/works/jig-options')
          ? { plate_thickness: 15 }
          : url.includes('/works/w1')
            ? part
            : { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter initialEntries={['/works/w1']}>
      <Routes>
        <Route path="/works/:id" element={<WorkPage />} />
      </Routes>
    </MemoryRouter>,
  )
  await waitFor(() => expect(screen.getByRole('tab', { name: /지그 만들어 주기/ })).toBeInTheDocument())
  fireEventMouseDown(screen.getByRole('tab', { name: /지그 만들어 주기/ }))
  // 큰 단추가 먼저, 옵션은 접혀 있다.
  expect(await screen.findByRole('button', { name: '지그 만들어 보기' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '세부 옵션 펴기' })).toBeInTheDocument()
  expect(screen.getByText(/바닥판 · 받침 · 위치 핀 · 클램프/)).toBeInTheDocument()
})
