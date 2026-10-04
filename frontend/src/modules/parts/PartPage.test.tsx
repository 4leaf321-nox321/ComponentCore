import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import PartPage from '@/modules/parts/PartPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

const ME = { id: 'u2', email: 'kim@x', display_name: '김', status: 'active', is_system_admin: false, must_change_password: false }

const VERSION = {
  id: 'pv1',
  part_id: 'p1',
  number: 1,
  recipe: { nodes: [] },
  conditions: {
    named_selections: [{ name: '바닥' }],
    constraints: [{ name: '고정', type: 'fixed_support', on: '바닥' }],
    loads: [],
    analysis: { type: 'modal', modes: 6 },
  },
  job: null,
  note: '',
  promoted_by_id: 'u1',
  promoted_by_name: '나',
  work_version_id: null,
  created_at: '2026-10-04T00:00:00Z',
}

const PART = {
  id: 'p1',
  name: '브래킷',
  tags: [],
  description: '',
  owner_id: 'u1',
  owner_name: '나',
  work_id: null,
  current_version: 1,
  current: VERSION,
  jig_count: 0,
  folder: '',
  created_at: '2026-10-04T00:00:00Z',
  updated_at: '2026-10-04T00:00:00Z',
}

function serve(version: Record<string, unknown>) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: ME }
      : url.endsWith('/parts/p1/copy-to-work')
        ? { id: 'w9' }
        : url.endsWith('/parts/p1/versions')
          ? [version]
          : url.endsWith('/parts/p1')
            ? { ...PART, current: version }
            : { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/parts/p1']}>
        <Routes>
          <Route path="/parts/:id" element={<PartPage />} />
          <Route path="/works/:id" element={<p>복사한 작업</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

test('공용 부품은 함께 올라온 해석 조건을 보이고, 복사하면 조건까지 옮긴다', async () => {
  serve(VERSION)
  expect(await screen.findByText('선택 그룹 1 · 구속 1')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '내 작업 공간으로 복사' }))
  expect(await screen.findByText('복사한 작업')).toBeInTheDocument()
  const calls = vi.mocked(globalThis.fetch).mock.calls
  await waitFor(() => expect(calls.some(([url]) => String(url).endsWith('/copy-to-work'))).toBe(true))
})

test('조건 없이 올린 부품은 없다고 말한다', async () => {
  serve({ ...VERSION, conditions: {} })
  expect(await screen.findByText('이 버전에는 등록된 해석 조건이 없습니다.')).toBeInTheDocument()
})
