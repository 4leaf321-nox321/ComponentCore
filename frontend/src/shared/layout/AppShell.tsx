/** 앱 껍데기 — 사이드바 + 헤더 + 본문. **본문만 스크롤한다.** */

import { Suspense, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { ErrorBoundary } from '@/shared/components/ErrorBoundary'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Header } from '@/shared/layout/Header'
import { Sidebar, SidebarDrawer } from '@/shared/layout/Sidebar'

function PageSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-4 w-80" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const { pathname } = useLocation()

  return (
    <div className="flex h-svh overflow-hidden">
      <Sidebar collapsed={collapsed} />
      <SidebarDrawer open={drawer} onOpenChange={setDrawer} />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          onToggleSidebar={() => {
            if (window.matchMedia('(min-width: 768px)').matches) setCollapsed((v) => !v)
            else setDrawer(true)
          }}
        />
        <main className="flex-1 overflow-auto p-6">
          {/* 경계는 본문에만 — 사이드바와 헤더는 살아 있어야 나갈 길이 남는다. */}
          <ErrorBoundary resetKey={pathname}>
            <Suspense fallback={<PageSkeleton />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}
