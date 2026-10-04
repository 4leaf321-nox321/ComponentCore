import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import JobsPage from '@/modules/jobs/JobsPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

const job = (id: string, who: string) => ({
  id,
  kind: 'cad',
  status: 'done',
  work_id: null,
  work_name: null,
  requested_by_id: who,
  requested_by_name: who === 'u1' ? '나' : '김',
  progress: [],
  artifacts: [],
  error: null,
  created_at: '2026-10-04T00:00:00Z',
  started_at: null,
  finished_at: null,
})

function serve(admin: boolean) {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    calls.push(url)
    const me = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: admin, must_change_password: false }
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: me }
      : url.includes('/jobs?')
        ? {
            items: url.includes('mine=false') ? [job('j1', 'u1'), job('j2', 'u2')] : [job('j1', 'u1')],
            total: 2,
            limit: 20,
            offset: 0,
          }
        : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <AuthProvider>
      <MemoryRouter>
        <JobsPage />
      </MemoryRouter>
    </AuthProvider>,
  )
  return calls
}

test('시스템 관리자는 전체 사용자의 실행 기록을 요청자와 함께 조회한다', async () => {
  const calls = serve(true)
  fireEvent.click(await screen.findByRole('button', { name: '전체 사용자' }))
  await waitFor(() => expect(calls.some((one) => one.includes('mine=false'))).toBe(true))
  expect(await screen.findByRole('columnheader', { name: '요청자' })).toBeInTheDocument()
  expect(await screen.findByText('김')).toBeInTheDocument()
})

test('일반 사용자에게는 범위 전환이 없다', async () => {
  const calls = serve(false)
  await waitFor(() => expect(calls.some((one) => one.includes('mine=true'))).toBe(true))
  expect(screen.queryByRole('button', { name: '전체 사용자' })).toBeNull()
})
