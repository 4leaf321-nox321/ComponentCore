import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import WorksPage from '@/modules/works/WorksPage'

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

test('찾기 · 꼬리표 · 휴지통은 서버가 거르고, 되살리기가 된다', async () => {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push(`${init?.method ?? 'GET'} ${url}`)
    const u = new URL(url, 'http://x')
    let body: unknown
    // 쓰인 태그 객체(타입별) — 거르개는 이름이 아니라 객체로 거른다(ADR 0011).
    if (u.pathname.endsWith('/tags/used/work'))
      body = [
        { object_id: 't1', label: '진동', type_slug: 'cc_tag', type_label: '일반 태그', uses: 1 },
        { object_id: 't2', label: 'P1', type_slug: 'customer', type_label: '고객사', uses: 1 },
      ]
    else if (u.pathname.endsWith('/works/folders') || u.pathname.endsWith('/works/years')) body = []
    else if (u.pathname.endsWith('/restore')) body = row('w2', '모터 브래킷')
    else if (u.pathname.endsWith('/works')) {
      const items = u.searchParams.get('trashed')
        ? [row('w2', '모터 브래킷', { deleted_at: '2026-09-19T00:00:00Z' })]
        : u.searchParams.get('q') === '모터' || u.searchParams.get('tag_id') === 't1'
          ? [row('w2', '모터 브래킷', { tags: ['진동'] })]
          : [row('w1', '센서 브래킷'), row('w2', '모터 브래킷', { tags: ['진동'] })]
      body = { items, total: items.length, limit: 20, offset: 0 }
    } else body = { items: [], total: 0, limit: 20, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter initialEntries={['/works']}>
      <Routes>
        <Route path="/works" element={<WorksPage />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText('센서 브래킷')).toBeInTheDocument()

  // 찾기 — 조금 쉬었다 서버에 q 로 묻는다.
  fireEvent.change(screen.getByLabelText('검색'), { target: { value: '모터' } })
  await waitFor(() => expect(calls.some((c) => c.includes('q=%EB%AA%A8%ED%84%B0'))).toBe(true))
  await waitFor(() => expect(screen.queryByText('센서 브래킷')).toBeNull())
  fireEvent.click(screen.getByLabelText('검색어 초기화'))
  await waitFor(() => expect(screen.getByText('센서 브래킷')).toBeInTheDocument())

  // 태그 칩 — 타입별로 묶이고(「고객사:」), 서버에는 태그 객체(tag_id)로.
  expect(screen.getByText('고객사:')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /^진동/ }))
  await waitFor(() => expect(calls.some((c) => c.includes('tag_id=t1'))).toBe(true))
  await waitFor(() => expect(screen.queryByText('센서 브래킷')).toBeNull())
  fireEvent.click(screen.getByRole('button', { name: /^진동/ })) // 풀기

  // 휴지통 — 지운 것만, 되살리기.
  fireEvent.click(screen.getByRole('button', { name: '휴지통' }))
  await waitFor(() => expect(calls.some((c) => c.includes('trashed=true'))).toBe(true))
  fireEvent.click(await screen.findByRole('button', { name: '복원' }))
  await waitFor(() => expect(calls.some((c) => c.startsWith('POST') && c.endsWith('/works/w2/restore'))).toBe(true))
})
