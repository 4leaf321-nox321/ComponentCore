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
      // 부서 스코프 항목은 slug 가 런타임 값이라 자리표로 본다.
      const to = item.to ?? item.resolve?.(':slug')
      expect(paths, `${item.label} (${to})`).toContain(to)
    }
  }
})

test('온톨로지의 두 번째 사이드바와 동적 화면이 제 자리를 갖는다', () => {
  const paths = collectPaths(router.routes as never)
  for (const path of ['/o/:typeSlug', '/o/:typeSlug/:objectId', '/w/:slug', '/w/:slug/members']) {
    expect(paths).toContain(path)
  }
  for (const tab of ['groups', 'types', 'interfaces', 'relations', 'import', 'core']) {
    expect(paths).toContain(`/admin/ontology/${tab}`)
  }
})
