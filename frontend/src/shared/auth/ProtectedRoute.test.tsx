import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { AuthProvider } from '@/shared/auth/AuthContext'
import { ProtectedRoute } from '@/shared/auth/ProtectedRoute'

test('익명이면 로그인으로 보낸다', async () => {
  // refresh 가 실패하면 익명이다.
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ error: { code: 'AJG-AUTH-0003', message: '없음' } }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/jigs']}>
        <Routes>
          <Route path="/login" element={<p>로그인 화면</p>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/jigs" element={<p>보호된 화면</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
  expect(await screen.findByText('로그인 화면')).toBeInTheDocument()
})
