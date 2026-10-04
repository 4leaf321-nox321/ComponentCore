/**
 * HWAX 포털 SSO — 포털의 **표준 jwt-handoff**. ReportArchive 등 포털에 붙은 앱과 같은 방식이다.
 *
 * 들어오는 길은 둘이다:
 *
 *   ① **타일 클릭** — 포털이 launch 토큰을 `/api/auth/portal-callback` 으로 폼 POST 한다. 서버가
 *      refresh 쿠키를 심고 화면으로 보내므로, 화면은 평소처럼 쿠키로 세션을 되살린다. 이 파일은
 *      관여하지 않는다.
 *   ② **주소로 바로 들어옴**(북마크 · 채팅의 화면 링크) — 포털 안이면(`hwax_csrf` 쿠키가
 *      보이면 — 같은 오리진이라 읽힌다) 포털의 **표준 launch**(`POST /systems/{id}/launch`, 타일이
 *      쓰는 바로 그것)를 포털 세션으로 불러 토큰을 받고 `/api/auth/portal-exchange` 로 바꾼다.
 *
 * 서버가 포털 SSO 를 켰을 때만 `<meta name="portal-system">` 을 심는다 — 없으면 이 파일은
 * 아무것도 하지 않는다(단독 설치).
 */

import { api } from '@/shared/api/client'
import type { LoginResponse } from '@/shared/auth/types'

const CSRF_COOKIE = 'hwax_csrf'
/** 이번 브라우저 세션에 자동 시도를 이미 했나 — 실패를 되풀이하지 않게. */
const TRIED_KEY = 'compcore:portal_tried'
/** 이 플랫폼에서 로그아웃했다 — 곧바로 다시 들이면 「로그아웃이 안 된다」 가 된다. */
const OPTOUT_KEY = 'compcore:portal_optout'

/** 포털의 타일 id — 서버가 심어 준다. 비면 포털 로그인이 꺼져 있다. */
export function portalSystem(): string {
  if (typeof document === 'undefined') return ''
  return document.querySelector('meta[name="portal-system"]')?.getAttribute('content') ?? ''
}

function readCookie(name: string): string | null {
  try {
    const found = document.cookie.match(new RegExp(`(?:^|;)\\s*${name}\\s*=\\s*([^;]+)`))
    return found ? decodeURIComponent(found[1]) : null
  } catch {
    return null
  }
}

function remember(op: 'get' | 'set' | 'del', key: string): string | null {
  try {
    if (op === 'get') return sessionStorage.getItem(key)
    if (op === 'set') sessionStorage.setItem(key, '1')
    if (op === 'del') sessionStorage.removeItem(key)
  } catch {
    // 사생활 보호 모드 — 자동 로그인만 꺼진다.
  }
  return null
}

/** 지금 HWAX 포털 안에서 열렸나(포털 SSO 가 켜져 있고 포털 로그인 쿠키가 보이나). */
export function isInsidePortal(): boolean {
  return Boolean(portalSystem() && readCookie(CSRF_COOKIE))
}

/** 화면이 뜰 때 자동으로 포털 로그인을 시도해도 되나. */
export function shouldAutoHandoff(): boolean {
  return isInsidePortal() && !remember('get', OPTOUT_KEY) && !remember('get', TRIED_KEY)
}

/** 포털의 표준 launch 응답에서 토큰을 꺼낸다 — auto_post(`fields`) · redirect(`url`) 둘 다. */
function tokenFrom(payload: unknown): string | null {
  const body = (payload ?? {}) as { fields?: Record<string, unknown>; url?: unknown }
  const fields = body.fields ?? {}
  const first = typeof fields.token === 'string' ? fields.token : Object.values(fields)[0]
  if (typeof first === 'string' && first) return first
  if (typeof body.url === 'string') {
    try {
      return new URL(body.url, window.location.origin).searchParams.get('token')
    } catch {
      return null
    }
  }
  return null
}

/**
 * 포털 세션으로 로그인한다. 포털에서 토큰을 못 받으면 null — 포털 로그인이 끝났거나(401), 이
 * 사람에게 타일이 없다(404). 이 플랫폼이 거절하면(403 정지 등) `ApiError` — 까닭을 보여 준다.
 * **포털 API 는 오리진 루트에 있다** — 이 플랫폼의 접두어(`/compcore`)를 붙이지 않는다.
 */
export async function portalLogin({ auto = false } = {}): Promise<LoginResponse | null> {
  if (auto) remember('set', TRIED_KEY)
  const csrf = readCookie(CSRF_COOKIE)
  const system = portalSystem()
  if (!csrf || !system) return null
  let token: string | null
  try {
    const response = await fetch(`/systems/${encodeURIComponent(system)}/launch`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRF-Token': csrf },
    })
    if (!response.ok) return null
    token = tokenFrom(await response.json())
  } catch {
    return null
  }
  if (!token) return null
  return api.post<LoginResponse>('/auth/portal-exchange', { token })
}

/** 이 플랫폼에서 로그아웃했다 — 이번 브라우저 세션엔 자동으로 다시 들이지 않는다. */
export function markPortalOptOut(): void {
  remember('set', OPTOUT_KEY)
}

/** 사람이 직접 포털 로그인을 골랐다 — 막아 둔 것을 푼다. */
export function clearPortalOptOut(): void {
  remember('del', OPTOUT_KEY)
  remember('del', TRIED_KEY)
}
