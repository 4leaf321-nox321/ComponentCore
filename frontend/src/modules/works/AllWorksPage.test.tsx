import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import AllWorksPage from '@/modules/works/AllWorksPage'

const row = (id: string, name: string, owner: string, ownerName: string) => ({
  id,
  name,
  description: '',
  kind: 'part',
  owner_id: owner,
  owner_name: ownerName,
  current_version: 1,
  current_status: 'done',
  jig_run_count: 0,
  last_jig_status: null,
  promoted_part_id: null,
  promoted_jig_id: null,
  tags: [],
  folder: '고객A',
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-20T00:00:00Z',
  deleted_at: null,
})

const account = (id: string, name: string) => ({
  id,
  email: `${id}@example.local`,
  display_name: name,
  status: 'active',
  is_system_admin: false,
  must_change_password: false,
  created_at: '2026-01-01T00:00:00Z',
  deleted_at: null,
})

test('모든 사람의 작업을 둘러보고, 사람으로 거른다', async () => {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    calls.push(url)
    const u = new URL(url, 'http://x')
    let body: unknown
    if (u.pathname.endsWith('/accounts')) body = [account('kim', '김'), account('lee', '이')]
    else if (u.pathname.endsWith('/works/tags')) body = []
    else if (u.pathname.endsWith('/works')) {
      const owner = u.searchParams.get('owner')
      const items = [row('w1', '김의 브래킷', 'kim', '김'), row('w2', '이의 받침', 'lee', '이')].filter(
        (one) => owner === 'all' || one.owner_id === owner,
      )
      body = { items, total: items.length, limit: 20, offset: 0 }
    } else body = {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter initialEntries={['/admin/works']}>
      <Routes>
        <Route path="/admin/works" element={<AllWorksPage />} />
      </Routes>
    </MemoryRouter>,
  )
  // 기본은 모두 — 만든 사람이 보이고, 이름은 그 작업을 연다.
  expect(await screen.findByText('김의 브래킷')).toBeInTheDocument()
  expect(screen.getByText('이의 받침')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '김의 브래킷' })).toHaveAttribute('href', '/works/w1')
  expect(calls.some((c) => c.includes('owner=all'))).toBe(true)

  // 사람으로 — 고르개에서.
  await screen.findByRole('option', { name: /이 \(lee@/ })
  fireEvent.change(screen.getByLabelText('작성자'), { target: { value: 'lee' } })
  await waitFor(() => expect(screen.queryByText('김의 브래킷')).toBeNull())
  expect(screen.getByText('이의 받침')).toBeInTheDocument()
  expect(calls.some((c) => c.includes('/works/tags?owner=lee'))).toBe(true)
})

test('계정 화면에서 온 사람은 주소로 걸러져 있다', async () => {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    calls.push(String(input))
    const u = new URL(String(input), 'http://x')
    const body = u.pathname.endsWith('/works')
      ? { items: [row('w1', '김의 브래킷', 'kim', '김')], total: 1, limit: 20, offset: 0 }
      : []
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter initialEntries={['/admin/works?owner=kim']}>
      <Routes>
        <Route path="/admin/works" element={<AllWorksPage />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText('김의 브래킷')).toBeInTheDocument()
  expect(calls.some((c) => c.includes('/works?') && c.includes('owner=kim'))).toBe(true)
  expect(calls.some((c) => c.includes('owner=all'))).toBe(false)
})
