import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import WorkPage from '@/modules/works/WorkPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

const ME = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: true, must_change_password: false }

const WORK = {
  id: 'w1',
  name: '튜닝 지그',
  owner_id: 'u1',
  owner_name: '나',
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
  tags: [],
  deleted_at: null,
}

function serve(work: Record<string, unknown>) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: ME }
      : url.includes('/works/w1/versions')
      ? [WORK.current]
      : url.includes('/works/w1/jig-runs')
        ? []
        : url.includes('/works/jig-options')
          ? {}
          : url.includes('/works/tags') || url.includes('/works/folders')
            ? []
            : url.includes('/works/w1')
              ? work
              : { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
}

function show() {
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/works/w1']}>
        <Routes>
          <Route path="/works/:id" element={<WorkPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

test('지그 작업은 그림 탭이 「지그」 이고, 승격이 지그 카탈로그로 간다', async () => {
  serve(WORK)
  show()
  // 그림 탭 이름은 종류와 상관없이 「도면」 — 생성기 탭은 이제 어느 작업에도 없다(새 작업 › 부품에서 지그 생성).
  await waitFor(() => expect(screen.getByRole('tab', { name: /^도면$/ })).toBeInTheDocument())
  expect(screen.queryByRole('tab', { name: /지그 만들어 주기/ })).toBeNull()
  expect(await screen.findByRole('button', { name: '공용 지그로 승격' })).toBeInTheDocument()
})

test('관리자가 남의 작업을 열면 누구의 것인지 늘 보이고, 꼬리표 제안도 그 사람의 것', async () => {
  serve({ ...WORK, owner_id: 'kim', owner_name: '김' })
  const calls = vi.mocked(globalThis.fetch).mock.calls
  show()
  const note = await screen.findByRole('note')
  expect(note).toHaveTextContent('김 의 작업입니다')
  expect(screen.getByRole('link', { name: /모든 작업/ })).toHaveAttribute('href', '/admin/works?owner=kim')
  await waitFor(() => expect(calls.some(([url]) => String(url).includes('/works/tags?owner=kim'))).toBe(true))
})

test('내 작업이면 알림이 없다', async () => {
  serve(WORK)
  show()
  expect(await screen.findByRole('button', { name: '공용 지그로 승격' })).toBeInTheDocument()
  expect(screen.queryByRole('note')).toBeNull()
})
