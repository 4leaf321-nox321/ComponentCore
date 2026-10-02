import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import WorksPage from '@/modules/works/WorksPage'
import { groupByYear } from '@/modules/works/folders'
import { buildTree, normalizePath } from '@/shared/folders/paths'

const row = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  name,
  description: '',
  kind: 'part',
  owner_id: 'u',
  owner_name: '나',
  current_version: 1,
  current_status: 'done',
  jig_run_count: 0,
  last_jig_status: null,
  promoted_part_id: null,
  promoted_jig_id: null,
  tags: [],
  folder: '',
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-20T00:00:00Z',
  deleted_at: null,
  ...extra,
})

test('폴더 경로를 나무로 — 위 폴더도 세고, 하위까지 합친다', () => {
  expect(normalizePath(' /고객A//2026/ ')).toBe('고객A/2026')
  const tree = buildTree(
    [
      { path: '', count: 2 },
      { path: '고객A', count: 1 },
      { path: '고객A/2026', count: 3 },
      { path: '고객B', count: 0 },
    ],
    ['고객B/새 폴더'],
  )
  expect(tree.map((one) => [one.name, one.total])).toEqual([
    ['고객A', 4],
    ['고객B', 0],
  ])
  expect(tree[0].children.map((one) => one.path)).toEqual(['고객A/2026'])
  expect(tree[1].children.map((one) => one.path)).toEqual(['고객B/새 폴더'])
})

test('만든 순으로 온 목록을 해마다 묶는다', () => {
  const groups = groupByYear([
    row('a', '가', { created_at: '2026-03-01T00:00:00Z' }),
    row('b', '나', { created_at: '2026-01-05T00:00:00Z' }),
    row('c', '다', { created_at: '2025-12-01T00:00:00Z' }),
  ] as never)
  expect(groups.map((one) => [one.year, one.rows.length])).toEqual([
    [2026, 2],
    [2025, 1],
  ])
})

test('폴더를 누르면 그 폴더로 거르고, 골라서 옮기고, 연도별로 묶는다', async () => {
  const calls: { method: string; url: string; body?: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ method: init?.method ?? 'GET', url, body })
    const u = new URL(url, 'http://x')
    let out: unknown
    if (u.pathname.endsWith('/works/tags')) out = []
    else if (u.pathname.endsWith('/works/folders'))
      out = [
        { path: '', count: 1 },
        { path: '고객A', count: 1 },
        { path: '고객A/2026', count: 1 },
      ]
    else if (u.pathname.endsWith('/works/years'))
      out = [
        { year: 2026, count: 2 },
        { year: 2025, count: 1 },
      ]
    else if (u.pathname.endsWith('/works/move')) out = { moved: 1 }
    else if (u.pathname.endsWith('/works')) {
      const all = [
        row('w1', '센서 지그', { folder: '고객A/2026', created_at: '2026-05-01T00:00:00Z' }),
        row('w2', '모터 지그', { folder: '고객A', created_at: '2026-02-01T00:00:00Z' }),
        row('w3', '옛 받침', { created_at: '2025-11-01T00:00:00Z' }),
      ]
      const folder = u.searchParams.get('folder')
      const items = folder === null ? all : all.filter((one) => one.folder === folder || one.folder.startsWith(`${folder}/`))
      out = { items, total: items.length, limit: 20, offset: 0 }
    } else out = { items: [], total: 0, limit: 20, offset: 0 }
    return new Response(JSON.stringify(out), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter initialEntries={['/works']}>
      <Routes>
        <Route path="/works" element={<WorksPage />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText('옛 받침')).toBeInTheDocument()
  const tree = screen.getByRole('navigation', { name: '폴더' })
  // 나무 — 고객A 는 하위까지 합쳐 2.
  expect(within(tree).getByText('고객A').closest('button')).toHaveTextContent('2')

  // 폴더를 누르면 서버에 folder 로 묻고, 하위 폴더의 작업도 보인다(경로가 줄에 적힌다).
  fireEvent.click(within(tree).getByText('고객A'))
  await waitFor(() => expect(screen.queryByText('옛 받침')).toBeNull())
  expect(calls.some((one) => one.url.includes('folder=%EA%B3%A0%EA%B0%9DA'))).toBe(true)
  expect(screen.getByText(/📁 고객A › 2026/)).toBeInTheDocument()

  // 골라서 옮기기 — 창에 경로를 적는다.
  fireEvent.click(screen.getByLabelText('모터 지그 고르기'))
  fireEvent.click(screen.getByRole('button', { name: '폴더로 옮기기' }))
  fireEvent.change(screen.getByLabelText('폴더 경로'), { target: { value: '보관/ 2026 ' } })
  fireEvent.click(screen.getByRole('button', { name: '옮기기' }))
  await waitFor(() => expect(calls.some((one) => one.url.endsWith('/works/move'))).toBe(true))
  const moved = calls.find((one) => one.url.endsWith('/works/move'))
  expect(moved?.body).toEqual({ ids: ['w2'], folder: '보관/2026' })

  // 연도별로 묶기 — 만든 순으로 다시 묻고 해마다 머리줄이 생긴다.
  fireEvent.click(within(tree).getByText('모든 작업'))
  fireEvent.click(screen.getByRole('button', { name: '연도별로 묶기' }))
  await waitFor(() => expect(calls.some((one) => one.url.includes('order=created'))).toBe(true))
  expect(await screen.findByText(/2026년 · 2개/)).toBeInTheDocument()
  expect(screen.getByText(/2025년 · 1개/)).toBeInTheDocument()
})
