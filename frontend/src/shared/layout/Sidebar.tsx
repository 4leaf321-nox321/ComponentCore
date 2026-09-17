/** 사이드바 — 접으면 폭 0 으로 줄어들고 본문이 전체 폭을 쓴다. */

import { NavLink } from 'react-router-dom'

import { UNKNOWN_VERSION, systemApi } from '@/shared/api/system'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { APP_NAME, APP_TAGLINE } from '@/shared/branding'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/shared/components/ui/sheet'
import { useResource } from '@/shared/hooks/useResource'
import { visibleGroups } from '@/shared/layout/navigation'
import { cn } from '@/shared/lib/utils'

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth()
  // **서버가 정본이다.** 번들에 박힌 버전은 빌드된 버전이지 지금 도는 서버가 아니다.
  const health = useResource(() => systemApi.health(), [])
  const release = health.data?.version
  const stale =
    import.meta.env.DEV && !!release && release !== UNKNOWN_VERSION && release !== __APP_VERSION__

  const groups = visibleGroups({ isSystemAdmin: isSystemAdmin(user) })

  return (
    <div className="flex h-full w-60 flex-col">
      <div className="flex h-14 shrink-0 flex-col justify-center border-b px-4">
        <span className="text-base leading-tight font-semibold tracking-tight">{APP_NAME}</span>
        <span className="text-muted-foreground text-xs leading-tight">
          {APP_TAGLINE}
          {release && release !== UNKNOWN_VERSION && (
            <span
              className={cn('ml-1.5 font-mono', stale && 'font-semibold text-amber-600')}
              title={
                stale
                  ? `이 화면은 ${__APP_VERSION__} 인데 서버는 ${release} 입니다.`
                  : '지금 도는 서버의 버전입니다'
              }
            >
              {release}
            </span>
          )}
        </span>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-2 py-4">
        {groups.map((group) => (
          <div key={group.title ?? group.items[0]?.label}>
            {group.title && (
              <p className="text-muted-foreground px-2 pb-1 text-xs font-medium">{group.title}</p>
            )}
            <ul className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.label}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
                        isActive
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                          : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground',
                      )
                    }
                  >
                    <item.icon className="size-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </div>
  )
}

/** 좁은 화면의 메뉴 — 서랍으로 연다. 고르면 닫는다. */
export function SidebarDrawer({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="bg-sidebar w-72 p-0 md:hidden">
        <SheetHeader className="sr-only">
          <SheetTitle>메뉴</SheetTitle>
        </SheetHeader>
        <SidebarBody onNavigate={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
  )
}

export function Sidebar({ collapsed }: { collapsed: boolean }) {
  return (
    <aside
      data-collapsed={collapsed}
      aria-hidden={collapsed}
      className={cn(
        'bg-sidebar hidden h-full shrink-0 flex-col overflow-hidden md:flex',
        'transition-[width] duration-200 ease-in-out',
        collapsed ? 'w-0 border-r-0' : 'w-60 border-r',
      )}
    >
      <SidebarBody />
    </aside>
  )
}
