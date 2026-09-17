/** 사이드바와 라우터가 어긋나지 않는지 — 메뉴는 있는데 화면이 없으면 눌러야 안다. */

import { NAV_GROUPS } from '@/shared/layout/navigation'
import { router } from '@/routes/router'

function collectPaths(routes: { path?: string; index?: boolean; children?: unknown[] }[], base = ''): string[] {
  const out: string[] = []
  for (const route of routes) {
    const path = route.path ? (route.path.startsWith('/') ? route.path : `${base}/${route.path}`) : base
    if (route.path) out.push(path.replace(/\/+/g, '/'))
    if (route.children) out.push(...collectPaths(route.children as typeof routes, path))
  }
  return out
}

test('사이드바의 모든 항목에 라우트가 있다', () => {
  const paths = collectPaths(router.routes as never)
  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      expect(paths, `${item.label} (${item.to})`).toContain(item.to)
    }
  }
})
