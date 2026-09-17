/**
 * 이 화면이 무슨 플랫폼인가 — 서버가 `<meta name="app-name">` 으로 말해 준다(backend/app/main.py).
 * meta 가 없는 곳(Vite 개발 서버 · 시험)만 아래 기본값. 백엔드 `branding.py` 와 같은 값이다.
 */

function meta(name: string): string | null {
  if (typeof document === 'undefined') return null
  return document.querySelector(`meta[name="${name}"]`)?.getAttribute('content') ?? null
}

export const DEFAULT_APP_NAME = 'AutoJigGenerator'
export const DEFAULT_APP_SLUG = 'autojig'
export const DEFAULT_APP_TAGLINE = '제품 STEP 에서 지그를 자동으로'

export const APP_NAME = meta('app-name') || DEFAULT_APP_NAME
export const APP_SLUG = meta('app-slug') || DEFAULT_APP_SLUG
export const APP_TAGLINE = meta('app-tagline') ?? DEFAULT_APP_TAGLINE

/** localStorage 키의 앞머리. */
export const STORAGE_PREFIX = APP_SLUG

/** 클라이언트가 만드는 오류의 코드 앞머리. 서버의 ERROR_PREFIX 와 같아야 한다. */
export const ERROR_PREFIX = 'AJG'
