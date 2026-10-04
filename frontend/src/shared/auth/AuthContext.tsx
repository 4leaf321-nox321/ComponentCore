/**
 * 인증 상태.
 *
 * 새로고침하면 메모리의 access 토큰이 사라지므로, 앱이 뜰 때 refresh 쿠키로 한 번
 * 갱신을 시도한다. 성공하면 로그인 상태가 유지되고 실패하면 익명이다 — 사용자
 * 눈에는 "로그인이 유지되는" 것으로 보인다.
 *
 * 쿠키가 없어도 **HWAX 포털 안이면** 포털 세션으로 한 번 들어와 본다(`portal.ts`) — 채팅의
 * 화면 링크를 눌러 처음 온 사람이 로그인 화면을 보지 않게.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, refreshSession, session } from '@/shared/api/client'
import { markPortalOptOut, portalLogin, shouldAutoHandoff } from '@/shared/auth/portal'
import type { CurrentUser, LoginResponse } from '@/shared/auth/types'

type Status = 'loading' | 'authenticated' | 'anonymous'

interface AuthContextValue {
  status: Status
  user: CurrentUser | null
  login: (email: string, password: string) => Promise<CurrentUser>
  /** HWAX 포털 세션으로 들어온다. 포털에서 토큰을 못 받으면 null. */
  loginWithPortal: () => Promise<CurrentUser | null>
  logout: () => Promise<void>
  /** 비밀번호 변경 등으로 사용자 정보가 바뀐 뒤 다시 읽는다. */
  reload: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<CurrentUser | null>(null)

  const clear = useCallback(() => {
    session.setToken(null)
    setUser(null)
    setStatus('anonymous')
  }, [])

  const accept = useCallback((body: LoginResponse) => {
    session.setToken(body.access_token)
    setUser(body.user)
    setStatus('authenticated')
    return body.user
  }, [])

  // 앱 기동 시 1회 — 쿠키가 살아 있으면 세션을 되살린다.
  //
  // **api.post 가 아니라 refreshSession 이다.** StrictMode 가 이 effect 를 두 번
  // 돌리므로 api.post 면 refresh 가 같은 쿠키로 둘 나가고, 서버가 둘째를 탈취로
  // 봐 세션을 전부 끊는다. refreshSession 은 진행 중인 요청을 같이 기다린다.
  useEffect(() => {
    let cancelled = false
    session.onLost(clear)

    refreshSession<LoginResponse>()
      .then((body) => {
        if (!cancelled) accept(body)
      })
      .catch(async () => {
        if (cancelled) return
        // 취소 확인 뒤에 부른다 — StrictMode 의 첫 effect 는 취소되므로 launch 가 한 번만 나간다.
        const viaPortal = shouldAutoHandoff() ? await portalLogin({ auto: true }).catch(() => null) : null
        if (cancelled) return
        if (viaPortal) accept(viaPortal)
        else clear()
      })

    return () => {
      cancelled = true
      session.onLost(null)
    }
  }, [clear, accept])

  const login = useCallback(
    async (email: string, password: string) => accept(await api.post<LoginResponse>('/auth/login', { email, password })),
    [accept],
  )

  const loginWithPortal = useCallback(async () => {
    const body = await portalLogin()
    return body ? accept(body) : null
  }, [accept])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      markPortalOptOut()
      clear()
    }
  }, [clear])

  const reload = useCallback(async () => {
    const me = await api.get<CurrentUser>('/auth/me')
    setUser(me)
  }, [])

  const value = useMemo(
    () => ({ status, user, login, loginWithPortal, logout, reload }),
    [status, user, login, loginWithPortal, logout, reload],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth는 AuthProvider 안에서만 사용할 수 있습니다.')
  return value
}
