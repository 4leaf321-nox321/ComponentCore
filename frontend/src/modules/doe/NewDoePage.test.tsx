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
    const body = url.endsWith('/works/w2') ? WORK2 : url.includes('/doe/preview') ? { count: 3, max: 200, max_samples: 500, too_many: false, points: [], varying: ['지그_높이'] } : WORKS
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
})

test('DOE 는 대상을 먼저 고른다 — 부품 · 지그 · 조립 중에서, 저장된 것만', async () => {
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
  await waitFor(() => expect(screen.getByText(/DOE — 브래킷 \+ 지그/)).toBeInTheDocument())
  // 그 조립의 변수(지그_높이)가 인자 표에 뜬다.
  expect(await screen.findByText('지그_높이')).toBeInTheDocument()
})

test('지난 DOE 에서 「설정 바꿔 다시 만들기」 로 오면 대상과 인자가 채워져 있다', async () => {
  const STUDY = {
    id: 's1',
    name: '높이 훑기',
    description: '',
    work_id: 'w2',
    method: 'lhs',
    samples: 12,
    seed: 7,
    recipe: WORK2.current.recipe,
    factors: [{ name: '지그_높이', mode: 'range', start: 20, end: 30, steps: 3 }],
    points: [],
    done: 0,
    failed: 0,
    job: null,
    export_dir_windows: '',
    exported_at: null,
    point_count: 3,
    created_at: '2026-09-19T00:00:00Z',
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.endsWith('/doe/s1') ? STUDY : url.endsWith('/works/w2') ? WORK2 : url.includes('/doe/preview') ? { count: 12, max: 200, max_samples: 500, too_many: false, points: [], varying: ['지그_높이'] } : WORKS
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter initialEntries={['/doe/new?from=s1']}>
      <Routes>
        <Route path="/doe/new" element={<NewDoePage />} />
      </Routes>
    </MemoryRouter>,
  )
  // 대상을 다시 고르지 않고 바로 그 조립의 폼이다. 이름 · 방식 · 구간이 지난 값이다.
  expect(await screen.findByText(/DOE — 브래킷 \+ 지그 \(다시\)/)).toBeInTheDocument()
  expect(await screen.findByLabelText('이름')).toHaveValue('높이 훑기')
  expect(screen.getByLabelText('지그_높이 시작')).toHaveValue(20)
  expect(screen.getByLabelText('지그_높이 끝')).toHaveValue(30)
  expect(screen.getByLabelText(/^표본 수/)).toHaveValue(12)
})
