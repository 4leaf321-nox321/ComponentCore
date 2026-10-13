/**
 * 사이드바 — 접으면 폭 0 으로 줄어들고 본문이 전체 폭을 쓴다.
 *
 * **묶음은 하나씩 접는다**(StandardPlatform 그대로). 온톨로지 타입이 늘면 사이드바가 길어지고,
 * 그때 사람은 자기가 쓰는 묶음을 찾으려고 매번 스크롤한다. 접은 것은 브라우저에 기억한다.
 */

import { useCallback, useEffect, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'

import { ontologyApi } from '@/modules/ontology/api'
import { useNavBadges } from '@/shared/api/navBadges'
import type { NavBadges } from '@/shared/api/navBadges'
import { UNKNOWN_VERSION, systemApi } from '@/shared/api/system'
import { useAuth } from '@/shared/auth/AuthContext'
import { isAnyManager, isSystemAdmin } from '@/shared/auth/roles'
import { APP_NAME, APP_TAGLINE, STORAGE_PREFIX } from '@/shared/branding'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/shared/components/ui/sheet'
import { useResource } from '@/shared/hooks/useResource'
import type { NavGroup } from '@/shared/layout/navigation'
import { itemHref, visibleGroups } from '@/shared/layout/navigation'
import { onNavChanged } from '@/shared/layout/navSignal'
import { cn } from '@/shared/lib/utils'

/** 접어 둔 묶음. **한 서버에 두 플랫폼이 있을 수 있어** 키에 slug 를 붙인다. */
const STORAGE_KEY = `${STORAGE_PREFIX}.sidebar.folded`

function readFolded(): string[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed)
      ? parsed.filter((one): one is string => typeof one === 'string')
      : []
  } catch {
    // 저장을 막은 브라우저 — 접힘은 편의일 뿐이라 그냥 다 펼친다.
    return []
  }
}

function useFoldedGroups() {
  const [folded, setFolded] = useState<string[]>(readFolded)
  const toggle = useCallback((key: string) => {
    setFolded((current) => {
      const next = current.includes(key) ? current.filter((one) => one !== key) : [...current, key]
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch {
        // 위와 같다 — 이번 화면에서만 기억한다.
      }
      return next
    })
  }, [])
  return { folded, toggle }
}

/** 이 묶음(또는 그 아래)에 **지금 보는 화면**이 있나 — 접었을 때 점을 찍는 근거. */
function holdsActive(group: NavGroup, pathname: string, slug: string | null): boolean {
  const mine = group.items.some((item) => {
    const href = itemHref(item, slug)
    if (!href) return false
    return item.end ? pathname === href : pathname.startsWith(href)
  })
  return mine || (group.children ?? []).some((one) => holdsActive(one, pathname, slug))
}

interface BlockProps {
  group: NavGroup
  depth: number
  folded: string[]
  toggle: (key: string) => void
  pathname: string
  slug: string | null
  badges: NavBadges
  onNavigate?: () => void
}

/** 묶음 한 덩어리 — 제 항목과 **하위 묶음**(한 단계까지)을 그린다. */
function GroupBlock({ group, depth, folded, toggle, pathname, slug, badges, onNavigate }: BlockProps) {
  const title = group.title
  const key = group.foldKey ?? title
  const isFolded = Boolean(key && folded.includes(key))
  const hasActive = holdsActive(group, pathname, slug)
  const children = group.children ?? []
  return (
    <div className={cn(depth > 0 && 'mt-2 ml-2 border-l pl-2')}>
      {title && key && (
        <button
          type="button"
          aria-expanded={!isFolded}
          onClick={() => toggle(key)}
          className={cn(
            'hover:text-foreground flex w-full items-center gap-1 rounded px-2 pb-1 text-xs',
            depth === 0 && children.length > 0
              ? 'text-foreground/80 font-semibold'
              : 'text-muted-foreground font-medium',
          )}
        >
          <ChevronRight
            className={cn('size-3 shrink-0 transition-transform', !isFolded && 'rotate-90')}
          />
          <span className="truncate">{title}</span>
          {isFolded && hasActive && (
            <span
              className="bg-primary ml-auto size-1.5 shrink-0 rounded-full"
              title="지금 보는 화면이 이 묶음 안에 있습니다"
            />
          )}
        </button>
      )}
      {/* **접으면 그리지 않는다.** CSS 로 숨기면 접힌 링크가 탭 이동에는 그대로 남는다. */}
      {!isFolded && (
        <>
          {group.items.length > 0 && (
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const href = itemHref(item, slug)
                if (!href) return null
                const badge = item.badge ? badges[item.badge] : undefined
                return (
                  <li key={item.label}>
                    <NavLink
                      to={href}
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
                      {item.tag && (
                        <span className="text-muted-foreground/70 ml-auto shrink-0 rounded border px-1 text-[10px] leading-4">
                          {item.tag}
                        </span>
                      )}
                      {badge && (
                        <span
                          className="bg-primary text-primary-foreground ml-auto rounded-full px-1.5 text-xs leading-5 font-medium tabular-nums"
                          title={badge.title}
                          aria-label={badge.title}
                        >
                          {badge.count}
                        </span>
                      )}
                    </NavLink>
                  </li>
                )
              })}
            </ul>
          )}
          {children.map((child) => (
            <GroupBlock
              key={child.foldKey ?? child.title}
              group={child}
              depth={depth + 1}
              folded={folded}
              toggle={toggle}
              pathname={pathname}
              slug={slug}
              badges={badges}
              onNavigate={onNavigate}
            />
          ))}
        </>
      )}
    </div>
  )
}

function SidebarBody({ workspaceSlug, onNavigate }: { workspaceSlug: string | null; onNavigate?: () => void }) {
  const { user } = useAuth()
  // **서버가 정본이다.** 번들에 박힌 버전은 빌드된 버전이지 지금 도는 서버가 아니다.
  const health = useResource(() => systemApi.health(), [])
  const release = health.data?.version
  const stale =
    import.meta.env.DEV && !!release && release !== UNKNOWN_VERSION && release !== __APP_VERSION__

  // **정의가 만든 화면.** 못 불러와도 정적 메뉴는 그대로 선다 — 사이드바가 통째로 비면 나갈
  // 길까지 사라진다. 정의를 고치면 그 자리에서 따라온다(`navSignal`).
  const dynamic = useResource(() => ontologyApi.nav(), [])
  useEffect(() => onNavChanged(dynamic.reload), [dynamic.reload])

  const groups = visibleGroups(
    { isSystemAdmin: isSystemAdmin(user), isAnyManager: isAnyManager(user) },
    dynamic.data ?? [],
    workspaceSlug,
  )
  const { pathname } = useLocation()
  const badges = useNavBadges(pathname)
  const { folded, toggle } = useFoldedGroups()

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
                  ? `화면 버전(${__APP_VERSION__})과 서버 버전(${release})이 다릅니다.`
                  : '현재 실행 중인 서버의 버전입니다.'
              }
            >
              {release}
            </span>
          )}
        </span>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-2 py-4">
        {groups.map((group) => (
          <GroupBlock
            key={group.foldKey ?? group.title ?? group.items[0]?.label}
            group={group}
            depth={0}
            folded={folded}
            toggle={toggle}
            pathname={pathname}
            slug={workspaceSlug}
            badges={badges}
            onNavigate={onNavigate}
          />
        ))}
      </nav>
    </div>
  )
}

/** 좁은 화면의 메뉴 — 서랍으로 연다. 고르면 닫는다. */
export function SidebarDrawer({
  open,
  onOpenChange,
  workspaceSlug = null,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  workspaceSlug?: string | null
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="bg-sidebar w-72 p-0 md:hidden">
        <SheetHeader className="sr-only">
          <SheetTitle>메뉴</SheetTitle>
        </SheetHeader>
        <SidebarBody workspaceSlug={workspaceSlug} onNavigate={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
  )
}

export function Sidebar({
  collapsed,
  workspaceSlug = null,
}: {
  collapsed: boolean
  workspaceSlug?: string | null
}) {
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
      <SidebarBody workspaceSlug={workspaceSlug} />
    </aside>
  )
}
