/** 로그인. **원래 가려던 곳으로 되돌려 보낸다.** */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { APP_NAME, APP_TAGLINE } from '@/shared/branding'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

export default function LoginPage() {
  const { status, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  const wanted = (location.state as { from?: { pathname: string } } | null)?.from?.pathname
  const from = wanted && !['/login', '/force-password-change'].includes(wanted) ? wanted : undefined

  if (status === 'authenticated') return <Navigate to={from ?? '/'} replace />

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const user = await login(email, password)
      navigate(user.must_change_password ? '/force-password-change' : (from ?? '/'), {
        replace: true,
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{APP_NAME}</h1>
          {APP_TAGLINE && <p className="text-muted-foreground mt-1 text-sm">{APP_TAGLINE}</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="email">아이디</Label>
          <Input
            id="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">비밀번호</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        <ErrorNotice error={error} />

        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? '확인 중…' : '로그인'}
        </Button>
        <p className="text-muted-foreground text-center text-xs">
          계정은 시스템 관리자가 만듭니다.
        </p>
      </form>
    </div>
  )
}
