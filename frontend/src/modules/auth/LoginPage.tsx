/**
 * 로그인. **원래 가려던 곳으로 되돌려 보낸다.**
 *
 * 포털 SSO 가 켜져 있으면(서버가 `portal-system` 을 심었으면) 「HWAX 포털 계정으로 계속」 을
 * 보인다. 포털 콜백이 실패하면 서버가 까닭을 `?sso_error=` 로 실어 이 화면으로 보낸다.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { clearPortalOptOut, isInsidePortal, portalSystem } from '@/shared/auth/portal'
import { APP_NAME, APP_TAGLINE } from '@/shared/branding'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

export default function LoginPage() {
  const { status, login, loginWithPortal } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<ApiError | Error | null>(() => {
    const said = new URLSearchParams(location.search).get('sso_error')
    return said ? new Error(said) : null
  })
  const [busy, setBusy] = useState(false)
  const portal = portalSystem()

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
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  async function viaPortal() {
    clearPortalOptOut()
    // 포털에 로그인하지 않은 브라우저 — 포털 첫 화면(오리진 루트)에서 로그인하고 타일로 온다.
    if (!isInsidePortal()) {
      window.location.assign('/')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const user = await loginWithPortal()
      if (user) navigate(from ?? '/', { replace: true })
      else setError(new Error('포털 로그인 세션을 확인하지 못했습니다. 포털에서 다시 로그인한 후 시도하십시오.'))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
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
        {portal && (
          <Button type="button" variant="outline" className="w-full" disabled={busy} onClick={() => void viaPortal()}>
            HWAX 포털 계정으로 계속
          </Button>
        )}
        <p className="text-muted-foreground text-center text-xs">
          {portal
            ? 'HWAX 포털 계정 또는 시스템 관리자가 생성한 계정으로 로그인합니다.'
            : '계정은 시스템 관리자가 생성합니다.'}
        </p>
      </form>
    </div>
  )
}
