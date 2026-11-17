/**
 * 앱 껍데기 — 사이드바 + 헤더 + 본문. **본문만 스크롤한다.** 본문은 **화면 탭**이다(`tabs.tsx`) — 탭마다 화면이
 * 살아 있고 제 스크롤을 가진다. 탭이 하나면 탭 줄은 안 보인다.
 */

import { useEffect, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import type { RouteObject } from 'react-router-dom'

import { NoticePopup } from '@/modules/notices/NoticePopup'
import { useAuth } from '@/shared/auth/AuthContext'

import { Skeleton } from '@/shared/components/ui/skeleton'
import { Header } from '@/shared/layout/Header'
import { Sidebar, SidebarDrawer } from '@/shared/layout/Sidebar'
import { TabBar, TabPanes, TabsProvider } from '@/shared/layout/tabs'
import { rememberPage } from '@/shared/lib/lastPage'

function PageSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-4 w-80" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}

/** `routes` 는 본문의 라우트 표 — 탭마다 그 탭의 주소로 이것을 그린다(라우터의 자식 경로와 같은 표). */
export function AppShell({ routes }: { routes: RouteObject[] }) {
  const [collapsed, setCollapsed] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const { pathname } = useLocation()
  const { slug } = useParams<{ slug?: string }>()
  const { user } = useAuth()
  // 부서 스코프가 아닌 화면에서도 사이드바의 「부서 홈」 · 「부서 멤버」 는 **어느 부서인지**
  // 정해야 한다 — 보던 부서, 없으면 소속 부서. 소속이 없으면 그 항목이 안 선다.
  const workspaceSlug = slug ?? user?.home_workspace_slug ?? user?.memberships?.[0]?.slug ?? null
  // 의견(VOC)에 「보던 화면」 을 담으려고 — 화면이 바뀔 때마다 적는다.
  useEffect(() => rememberPage(pathname), [pathname])

  return (
    <div className="flex h-svh overflow-hidden">
      <Sidebar collapsed={collapsed} workspaceSlug={workspaceSlug} />
      <SidebarDrawer open={drawer} onOpenChange={setDrawer} workspaceSlug={workspaceSlug} />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          workspaceSlug={workspaceSlug}
          onToggleSidebar={() => {
            if (window.matchMedia('(min-width: 768px)').matches) setCollapsed((v) => !v)
            else setDrawer(true)
          }}
        />
        <TabsProvider>
          <TabBar />
          {/* 경계는 탭마다 본문에만 — 사이드바와 헤더는 살아 있어야 나갈 길이 남는다. */}
          <main className="relative min-h-0 flex-1">
            <TabPanes routes={routes} fallback={<PageSkeleton />} />
          </main>
        </TabsProvider>
      </div>
      {/* 읽지 않은 팝업 공지가 있으면 로그인 뒤 한 번 뜬다(닫으면 읽음). */}
      <NoticePopup />
    </div>
  )
}
