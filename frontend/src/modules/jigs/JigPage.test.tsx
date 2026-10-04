import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import JigPage from '@/modules/jigs/JigPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

vi.mock('@/modules/jigs/JigResultView', () => ({ JigResultView: () => <div data-testid="result" /> }))

const ME = { id: 'u2', email: 'lee@x', display_name: '이', status: 'active', is_system_admin: false, must_change_password: false }

const VERSION = {
  id: 'jv1',
  jig_id: 'j1',
  number: 1,
  job: null,
  options: {},
  summary: null,
  recipe: { nodes: [] },
  conditions: { named_selections: [{ name: '바닥' }], constraints: [{ name: '고정' }, { name: '옆 고정' }] },
  part_id: null,
  part_name: null,
  part_version: null,
  note: '',
  promoted_by_name: '김',
  created_at: '2026-10-04T00:00:00Z',
}

const JIG = {
  id: 'j1',
  name: '받침 지그',
  tags: [],
  description: '',
  owner_id: 'u1',
  owner_name: '김',
  work_id: 'w1',
  part_id: null,
  part_name: null,
  current_version: 1,
  version_count: 1,
  current: VERSION,
  folder: '',
  created_at: '2026-10-04T00:00:00Z',
  updated_at: '2026-10-04T00:00:00Z',
}

function serve(version: Record<string, unknown>) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: ME }
      : url.endsWith('/jigs/j1/copy-to-work')
        ? { id: 'w9' }
        : url.endsWith('/jigs/j1/versions')
          ? [version]
          : url.endsWith('/jigs/j1')
            ? { ...JIG, current: version }
            : { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/jigs/j1']}>
        <Routes>
          <Route path="/jigs/:id" element={<JigPage />} />
          <Route path="/works/:id" element={<p>복사한 작업</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

test('남의 공용 지그를 해석 조건과 함께 내 작업 공간으로 복사한다', async () => {
  serve(VERSION)
  expect(await screen.findByText('선택 그룹 1 · 구속 2')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '내 작업 공간으로 복사' }))
  expect(await screen.findByText('복사한 작업')).toBeInTheDocument()
  const calls = vi.mocked(globalThis.fetch).mock.calls
  await waitFor(() => expect(calls.some(([url]) => String(url).endsWith('/jigs/j1/copy-to-work'))).toBe(true))
})

test('레시피가 없는 이전 버전은 복사할 수 없다고 말한다', async () => {
  serve({ ...VERSION, recipe: null, conditions: {} })
  const button = await screen.findByRole('button', { name: '내 작업 공간으로 복사' })
  await waitFor(() => expect(button).toBeDisabled())
  expect(button).toHaveAttribute('title', '생성기로 만든 이전 버전이라 레시피가 없어 복사할 수 없습니다.')
})
