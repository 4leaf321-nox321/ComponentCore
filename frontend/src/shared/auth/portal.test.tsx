import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import LoginPage from '@/modules/auth/LoginPage'
import { AuthProvider, useAuth } from '@/shared/auth/AuthContext'

const me = { id: 'u1', email: 'kim@x', display_name: '김', status: 'active', is_system_admin: false, must_change_password: false }

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** 포털 SSO 가 켜진 화면(서버가 심는 meta)과, 포털에 로그인한 브라우저(`hwax_csrf`). */
function insidePortal(inside = true) {
  const meta = document.createElement('meta')
  meta.name = 'portal-system'
  meta.content = 'compcore'
  document.head.appendChild(meta)
  if (inside) document.cookie = 'hwax_csrf=c-123'
}

function serve() {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push({ url, init })
    if (url.endsWith('/auth/refresh')) return json({ error: { code: 'CCR-AUTH-0003', message: '세션이 없습니다.' } }, 401)
    if (url === '/systems/compcore/launch') return json({ method: 'auto_post', url: '/compcore/api/auth/portal-callback', fields: { token: 'launch-1' } })
    if (url.endsWith('/auth/portal-exchange')) return json({ access_token: 't', expires_in: 900, user: me })
    if (url.endsWith('/auth/logout')) return new Response(null, { status: 204 })
    return json({})
  })
  return calls
}

function Who() {
  const { status, user, logout } = useAuth()
  return (
    <div>
      <p>{status === 'authenticated' ? `${user?.display_name} 로그인` : status}</p>
      <button onClick={() => void logout()}>로그아웃</button>
    </div>
  )
}

afterEach(() => {
  document.head.querySelectorAll('meta[name="portal-system"]').forEach((one) => one.remove())
  document.cookie = 'hwax_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  sessionStorage.clear()
})

test('포털 안에서 쿠키 없이 열면 포털 세션으로 한 번 들어온다', async () => {
  insidePortal()
  const calls = serve()
  render(
    <AuthProvider>
      <Who />
    </AuthProvider>,
  )
  expect(await screen.findByText('김 로그인')).toBeInTheDocument()
  const launch = calls.filter((one) => one.url === '/systems/compcore/launch')
  expect(launch).toHaveLength(1)
  expect(launch[0].init?.headers).toMatchObject({ 'X-CSRF-Token': 'c-123' })
  const exchange = calls.find((one) => one.url.endsWith('/auth/portal-exchange'))
  expect(JSON.parse(String(exchange?.init?.body))).toEqual({ token: 'launch-1' })

  // 로그아웃하면 이번 브라우저 세션에는 자동으로 다시 들이지 않는다.
  fireEvent.click(screen.getByRole('button', { name: '로그아웃' }))
  expect(await screen.findByText('anonymous')).toBeInTheDocument()
  expect(sessionStorage.getItem('compcore:portal_optout')).toBe('1')
})

test('포털 SSO 가 꺼져 있으면 포털을 부르지 않는다', async () => {
  const calls = serve()
  document.cookie = 'hwax_csrf=c-123'
  render(
    <AuthProvider>
      <Who />
    </AuthProvider>,
  )
  expect(await screen.findByText('anonymous')).toBeInTheDocument()
  expect(calls.some((one) => one.url.includes('/systems/'))).toBe(false)
})

test('로그인 화면은 포털 콜백의 실패 까닭과 포털 로그인 단추를 보인다', async () => {
  insidePortal()
  sessionStorage.setItem('compcore:portal_optout', '1')
  const calls = serve()
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={[`/login?sso_error=${encodeURIComponent('정지되었거나 삭제된 계정입니다.')}`]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<p>첫 화면</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
  expect(await screen.findByText('정지되었거나 삭제된 계정입니다.')).toBeInTheDocument()
  // 로그아웃으로 막아 둔 자동 시도는 하지 않았다.
  expect(calls.some((one) => one.url.includes('/systems/'))).toBe(false)

  fireEvent.click(screen.getByRole('button', { name: 'HWAX 포털 계정으로 계속' }))
  expect(await screen.findByText('첫 화면')).toBeInTheDocument()
  await waitFor(() => expect(sessionStorage.getItem('compcore:portal_optout')).toBeNull())
})
