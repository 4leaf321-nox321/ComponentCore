/**
 * 포털이 붙을 곳 — **전체 화면 안이면 그 안에.**
 *
 * Radix 는 모달 · 셀렉트 · 메뉴를 `document.body` 에 붙인다. 편집기가 브라우저 전체 화면
 * (Fullscreen API)으로 들어가면 body 는 화면 밖이라 **모달이 안 보인다**(실측). 전체 화면 요소가
 * 있으면 그 안에 붙인다.
 */
export function portalContainer(): HTMLElement | undefined {
  if (typeof document === 'undefined') return undefined
  return (document.fullscreenElement as HTMLElement | null) ?? undefined
}
