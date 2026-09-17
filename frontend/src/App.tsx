import { RouterProvider } from 'react-router-dom'

import { router } from '@/routes/router'
import { AuthProvider } from '@/shared/auth/AuthContext'
import { ThemeProvider } from '@/shared/theme/ThemeProvider'

/** AuthProvider 가 라우터 **바깥**에 있다 — 인증 상태는 앱 전체에서 하나여야 한다. */
export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </ThemeProvider>
  )
}
