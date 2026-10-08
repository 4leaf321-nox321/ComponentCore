import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AuthProvider } from '@/shared/auth/AuthContext'
import { Sidebar } from '@/shared/layout/Sidebar'

function serve(summary: Record<string, unknown>) {
  const asked: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    asked.push(url)
    const me = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: true, must_change_password: false }
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: me }
      : url.endsWith('/voc/summary')
        ? summary
        : { status: 'ok', version: 'v0.13.0', app: 'CompCore' }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <AuthProvider>
      <MemoryRouter>
        <Sidebar collapsed={false} />
      </MemoryRouter>
    </AuthProvider>,
  )
  return asked
}

test('손댈 차례인 VOC 가 없으면 숫자를 그리지 않는다', async () => {
  const asked = serve({ waiting: 0, to_confirm: 0 })
  await waitFor(() => expect(asked.some((one) => one.endsWith('/voc/summary'))).toBe(true))
  expect(screen.getByRole('link', { name: /VOC/ })).toBeInTheDocument()
  expect(screen.queryByLabelText(/대기/)).toBeNull()
})

test('VOC 메뉴 옆에 접수 대기와 확인 대기를 더해 센다', async () => {
  serve({ waiting: 2, to_confirm: 1 })
  const badge = await screen.findByLabelText('접수 대기 2건, 확인 대기 1건')
  expect(badge).toHaveTextContent('3')
  expect(screen.getByRole('link', { name: /VOC/ })).toContainElement(badge)
})
