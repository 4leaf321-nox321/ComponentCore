import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

import { AuthProvider } from '@/shared/auth/AuthContext'
import { Header } from '@/shared/layout/Header'
import { ThemeProvider } from '@/shared/theme/ThemeProvider'

function Where() {
  const { pathname, search } = useLocation()
  return <p>지금: {pathname + search}</p>
}

function serve(extra: Record<string, unknown> = {}) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const me = {
      id: 'u1',
      email: 'me@x',
      display_name: '나',
      status: 'active',
      is_system_admin: false,
      must_change_password: false,
      memberships: [],
      home_workspace_slug: null,
      ...extra,
    }
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: me }
      : url.includes('/notifications')
        ? { unread: 0 }
        : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <ThemeProvider>
      <AuthProvider>
        <MemoryRouter initialEntries={['/works']}>
          <Routes>
            <Route
              path="*"
              element={
                <>
                  <Header onToggleSidebar={() => {}} workspaceSlug={(extra.home_workspace_slug as string | null) ?? null} />
                  <Where />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </ThemeProvider>,
  )
}

test('검색 칸은 결과를 그리지 않고 검색 화면으로 넘긴다', async () => {
  serve()
  const box = await screen.findByLabelText('기준정보 객체에서 검색')
  fireEvent.change(box, { target: { value: '브래킷 A' } })
  fireEvent.submit(box.closest('form')!)
  expect(await screen.findByText(`지금: /search?q=${encodeURIComponent('브래킷 A')}`)).toBeInTheDocument()
  expect(box).toHaveValue('')
})

test('소속 부서가 없으면 부서 선택기를 그리지 않는다', async () => {
  serve()
  await screen.findByLabelText('기준정보 객체에서 검색')
  expect(screen.queryByLabelText('부서 선택')).toBeNull()
})

test('소속 부서가 있으면 선택기가 서고, 관리자면 그렇다고 적는다', async () => {
  serve({
    home_workspace_slug: 'cae',
    memberships: [{ workspace_id: 'w1', slug: 'cae', name: 'CAE', path: '설계 › CAE', role: 'manager' }],
  })
  expect(await screen.findByLabelText('부서 선택')).toHaveTextContent('설계 › CAE')
  expect(screen.getByText('부서 관리자')).toBeInTheDocument()
})
