import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import JigFromPartPage from '@/modules/works/JigFromPartPage'

// 시험 환경에는 WebGL 이 없다 — 뷰어는 빈 자리로 둔다. 미리보기가 **왔는지**는 계획 글로 본다.
vi.mock('@/shared/viewer/PickViewer', () => ({ default: () => <div data-testid="viewer" /> }))

const WORKS = {
  items: [
    { id: 'w1', name: '센서 브래킷', kind: 'part', current_version: 2 },
    { id: 'w2', name: '옛 지그', kind: 'jig', current_version: 1 },
    { id: 'w3', name: '빈 부품', kind: 'part', current_version: 0 },
  ],
  total: 3,
  limit: 100,
  offset: 0,
}
const PARTS = { items: [{ id: 'p1', name: '공용 브래킷', current_version: 3 }], total: 1, limit: 100, offset: 0 }
const JOB = {
  id: 'job1',
  kind: 'jig',
  status: 'done',
  work_id: 'j1',
  summary: { plan: { supports: [], locators: [], clamps: [], notes: [] }, interference: { ok: true, items: [] }, stages: [], geometry: { bbox: { size: [1, 1, 1] } } },
  artifacts: [],
  progress: [],
  error: null,
}

const PREVIEW = {
  plan: { kind: 'clamped', base_plate: {}, supports: [{}, {}, {}], locators: [{ kind: 'pin' }, { kind: 'pin' }], clamps: [{}, {}], bolts: [], rollers: [], nose: null, impactor: null, product_lift: 25, notes: ['받침은 구멍을 피해 놓았다'] },
  interference: { ok: true, items: [] },
  geometry: {},
  mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [{ index: 0, kind: 'plane', center: [0, 0, 0], normal: [0, 0, 1], area: 1, vertices: [], triangles: [], part: '받침 1' }], edges: [] },
}

test('부품을 고르고 만들면 지그 작업이 생기고, 끝난 결과가 첫 버전이 되어 그 화면으로 간다', async () => {
  const calls: { url: string; method: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push({ url, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : null })
    const body = url.endsWith('/works/jig-from-part/preview')
      ? PREVIEW
      : url.endsWith('/works/jig-from-part')
      ? { work: { id: 'j1', name: '센서 브래킷 지그', kind: 'jig' }, job: JOB }
      : url.endsWith('/adopt')
        ? { number: 1 }
        : url.includes('/works/jig-options')
          ? { support_count: 4 }
          : url.includes('/parts')
            ? PARTS
            : url.includes('/jobs/')
              ? JOB
              : WORKS
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter initialEntries={['/draw/jig-from-part']}>
      <Routes>
        <Route path="/draw/jig-from-part" element={<JigFromPartPage />} />
        <Route path="/works/:id" element={<div>작업 화면</div>} />
      </Routes>
    </MemoryRouter>,
  )
  // 내 작업의 부품(도면 있는 것만)과 공용 부품이 고를 것으로 뜬다. 지그 · 빈 부품은 안 뜬다.
  expect(await screen.findByRole('button', { name: /센서 브래킷/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /공용 브래킷/ })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /옛 지그/ })).toBeNull()
  expect(screen.queryByRole('button', { name: /빈 부품/ })).toBeNull()
  expect(screen.getByRole('button', { name: '이대로 지그 만들기' })).toBeDisabled()

  fireEvent.click(screen.getByRole('button', { name: /센서 브래킷/ }))
  // 고르면 미리보기가 돈다 — 만들기와 같은 옵션으로. 계획이 글로도 보인다.
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/jig-from-part/preview'))).toBe(true), { timeout: 3000 })
  expect(await screen.findByText('받침은 구멍을 피해 놓았다')).toBeInTheDocument()
  expect(calls.find((c) => c.url.endsWith('/jig-from-part/preview'))!.body).toMatchObject({ source: 'work:w1', options: { support_count: 4, kind: 'clamped' } })
  expect(screen.getByText(/받침 3 · 위치 핀 2 · 클램프 2/)).toBeInTheDocument()

  // 형식을 바꾸면 옵션에 kind 가 실려 미리보기가 다시 돈다 — 그 형식의 칸만 편다.
  fireEvent.click(screen.getByRole('button', { name: /볼트 고정/ }))
  await waitFor(() => expect(calls.filter((c) => c.url.endsWith('/jig-from-part/preview')).at(-1)!.body).toMatchObject({ options: { kind: 'bolted' } }), { timeout: 3000 })
  fireEvent.click(screen.getByRole('button', { name: '세부 옵션 펴기' }))
  expect(screen.getByLabelText('볼트 수 (최대)')).toBeInTheDocument()
  expect(screen.queryByLabelText('클램프 수')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '세부 옵션 접기' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '이대로 지그 만들기' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: '이대로 지그 만들기' }))

  await waitFor(() => expect(screen.getByText('작업 화면')).toBeInTheDocument())
  const made = calls.find((c) => c.url.endsWith('/works/jig-from-part'))!
  expect(made.body).toMatchObject({ source: 'work:w1', options: { support_count: 4, kind: 'bolted' } })
  expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/works/j1/jig-runs/job1/adopt'))).toBe(true)
})
