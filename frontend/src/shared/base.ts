/** 주소 접두어. 이 플랫폼은 루트에 뜬다 — 접두어를 쓰게 되면 서버가 meta 로 심어 준다. */
export const PUBLIC_PATH: string =
  typeof document === 'undefined'
    ? ''
    : (document.querySelector('meta[name="app-base"]')?.getAttribute('content') ?? '')

export const ROUTER_BASENAME = PUBLIC_PATH || '/'
