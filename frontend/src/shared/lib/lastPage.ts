/**
 * 직전에 본 화면 — 의견(VOC)을 쓸 때 「어느 화면에서」 를 함께 담는다. 「그 화면에서 안 된다」 를
 * 재현하는 실마리다.
 *
 * `document.referrer` 는 SPA 에서 앱을 처음 연 주소일 뿐이라 쓸 수 없다. 앱 껍데기(`AppShell`)가
 * 화면이 바뀔 때마다 적고, 건너뛸 경로(VOC 화면 자신)는 적지 않는다.
 */

let last: string | null = null

const SKIP = ['/voc']

export function rememberPage(path: string): void {
  if (!SKIP.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))) last = path
}

export function previousPage(): string | null {
  return last
}
