/**
 * **화면 탭** — CompCore 안에서 여러 화면을 탭으로 열어 두고 오간다(2026-11-17).
 *
 * 조립 편집기에서 구성품의 원본 도면을 브라우저 새 탭으로 열었더니 주소 접두어(포털의 `/compcore/`)가
 * 빠져 열리지 않았고, 열리더라도 로그인 · 상태가 따로 놀았다. 이제 앱 안의 탭으로 연다.
 *
 * - **탭마다 화면이 살아 있다.** 안 보이는 탭도 그대로 두고 숨긴다(`hidden`) — 조립에서 고치던 배치를 저장하지
 *   않고 부품 탭에 다녀와도 그대로다. 그래서 탭 수에 상한이 있다(3D 가 탭마다 WebGL 문맥을 하나씩 쥔다).
 * - **보이는 탭이 주소를 따른다.** 사이드바 · 링크로 옮기면 지금 탭이 그 화면이 된다(브라우저 탭과 같다).
 *   탭을 누르면 그 탭의 주소로 간다.
 * - 탭마다 같은 라우트 표를 **그 탭의 주소로** 그린다(`useRoutes` 에 주소를 준다) — 화면은 `useParams` ·
 *   `useLocation` 으로 제 탭의 주소를 본다.
 * - 안 보이는 탭은 키보드 단축키 · 3D 그리기를 쉰다(`useTabActive`). 그러지 않으면 숨은 편집기가 Ctrl+Z 를
 *   받아 되돌린다.
 * - 새로 고침해도 탭 목록은 남는다(sessionStorage). 남은 탭은 눌렀을 때 그린다.
 * - **어느 화면의 링크든 Ctrl(⌘)+클릭 · 가운데 단추(휠) 클릭이면 탭으로 연다**(브라우저 탭과 같은 손버릇).
 *   그냥 누르면 지금 탭에서 옮긴다. 브라우저 새 탭은 오른쪽 단추 메뉴로 — 링크 주소에 접두어가 붙어 있다.
 */

import { createContext, Suspense, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { UNSAFE_RouteContext as RouteContext, useLocation, useNavigate, useRoutes } from 'react-router-dom'
import type { Location, RouteObject } from 'react-router-dom'
import { X } from 'lucide-react'

import { PUBLIC_PATH } from '@/shared/base'
import { STORAGE_PREFIX } from '@/shared/branding'
import { ErrorBoundary } from '@/shared/components/ErrorBoundary'
import { NAV_GROUPS } from '@/shared/layout/navigation'
import { PaneContext } from '@/shared/layout/tabActive'

/** 한 번에 열어 둘 수 있는 탭 — 3D 화면이 탭마다 WebGL 문맥을 쥐고, 브라우저는 수십 개에서 오래된 것을 잃는다. */
export const MAX_TABS = 8
const KEY = `${STORAGE_PREFIX}.tabs`

export interface AppTab {
  id: string
  /** 라우터 기준 주소(접두어 없이) — `/works/<id>?tab=…`. */
  path: string
  /** 화면이 알려 준 이름(작업 이름 …). 없으면 메뉴 이름. */
  title?: string
  /** 그 이름을 준 화면의 경로 — 탭이 다른 화면으로 옮기면 이름은 그 화면의 것이 아니다. */
  titleFor?: string
}

interface TabsState {
  tabs: AppTab[]
  activeId: string
}

interface TabsValue extends TabsState {
  /** 그려 둔 탭 — 한 번 보인 탭만(복원한 탭은 누를 때 그린다). */
  mounted: ReadonlySet<string>
  /** 탭으로 연다 — 같은 주소의 탭이 있으면 그리로 간다. 상한이면 `false`. */
  open: (path: string, title?: string) => boolean
  activate: (id: string) => void
  close: (id: string) => void
  setTitle: (id: string, title: string, pathname: string) => void
}

const TabsContext = createContext<TabsValue | null>(null)

const newId = () => `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

function restore(here: string): TabsState {
  try {
    const raw = JSON.parse(sessionStorage.getItem(KEY) ?? 'null') as TabsState | null
    if (raw && Array.isArray(raw.tabs) && raw.tabs.length > 0 && raw.tabs.every((one) => typeof one.id === 'string' && typeof one.path === 'string')) {
      const tabs = raw.tabs.slice(0, MAX_TABS)
      // 주소가 곧 지금 화면이다 — 같은 주소의 탭이 있으면 그 탭, 없으면 보던 탭이 이 주소가 된다.
      const same = tabs.find((one) => one.path === here)
      if (same) return { tabs, activeId: same.id }
      const active = tabs.find((one) => one.id === raw.activeId) ?? tabs[0]
      return { tabs: tabs.map((one) => (one.id === active.id ? { id: one.id, path: here } : one)), activeId: active.id }
    }
  } catch {
    // 저장소를 못 쓰면 탭 하나로 시작한다.
  }
  const id = newId()
  return { tabs: [{ id, path: here }], activeId: id }
}

const pathOf = (location: Pick<Location, 'pathname' | 'search'>) => `${location.pathname}${location.search}`

export function TabsProvider({ children }: { children: ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const here = pathOf(location)
  const [state, setState] = useState<TabsState>(() => restore(here))
  const [mounted, setMounted] = useState<Set<string>>(() => new Set([state.activeId]))

  // **보이는 탭이 주소를 따른다** — 사이드바 · 링크로 옮기면 지금 탭이 그 화면이 된다. 이름은 그 이름을 준 화면의
  // 경로에 묶여 있어(`titleFor`) 따로 지우지 않는다 — 새 화면의 이름은 새 화면이 준다(자식의 효과가 먼저 돈다).
  useEffect(() => {
    setState((now) => ({ ...now, tabs: now.tabs.map((one) => (one.id !== now.activeId || one.path === here ? one : { ...one, path: here })) }))
  }, [here])

  useEffect(() => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(state))
    } catch {
      // 저장하지 못해도 탭은 이 화면 동안 그대로다.
    }
  }, [state])

  const show = useCallback(
    (tab: AppTab) => {
      setMounted((now) => (now.has(tab.id) ? now : new Set([...now, tab.id])))
      setState((now) => ({ ...now, activeId: tab.id }))
      navigate(tab.path)
    },
    [navigate],
  )

  const open = useCallback(
    (path: string, title?: string) => {
      const same = state.tabs.find((one) => one.path === path)
      if (same) {
        show(same)
        return true
      }
      if (state.tabs.length >= MAX_TABS) return false
      const tab: AppTab = { id: newId(), path, title, titleFor: title ? path.split('?')[0] : undefined }
      setState((now) => ({ tabs: [...now.tabs, tab], activeId: tab.id }))
      setMounted((now) => new Set([...now, tab.id]))
      navigate(path)
      return true
    },
    [navigate, show, state.tabs],
  )

  const activate = useCallback(
    (id: string) => {
      const tab = state.tabs.find((one) => one.id === id)
      if (tab && id !== state.activeId) show(tab)
    },
    [show, state.activeId, state.tabs],
  )

  const close = useCallback(
    (id: string) => {
      const index = state.tabs.findIndex((one) => one.id === id)
      if (index < 0 || state.tabs.length === 1) return
      const rest = state.tabs.filter((one) => one.id !== id)
      setMounted((now) => new Set([...now].filter((one) => one !== id)))
      if (id === state.activeId) {
        const next = rest[Math.min(index, rest.length - 1)]
        setState({ tabs: rest, activeId: next.id })
        setMounted((now) => new Set([...now, next.id]))
        navigate(next.path)
      } else {
        setState((now) => ({ ...now, tabs: now.tabs.filter((one) => one.id !== id) }))
      }
    },
    [navigate, state.activeId, state.tabs],
  )

  // **어느 화면의 링크든 Ctrl · 가운데 단추 클릭이면 탭으로** — 화면마다 단추를 달지 않고 링크 하나하나가 된다.
  // 문서에서 먼저(capture) 받아 브라우저 새 탭을 막는다. 탭이 꽉 차면 브라우저에 맡긴다.
  const openRef = useRef(open)
  openRef.current = open
  useEffect(() => {
    function onClick(event: MouseEvent) {
      const viaModifier = event.type === 'click' && event.button === 0 && (event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey
      const viaMiddle = event.type === 'auxclick' && event.button === 1
      if (event.defaultPrevented || !(viaModifier || viaMiddle)) return
      const found = linkTarget(event.target)
      if (found && openRef.current(found.path, found.title)) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    document.addEventListener('click', onClick, true)
    document.addEventListener('auxclick', onClick, true)
    return () => {
      document.removeEventListener('click', onClick, true)
      document.removeEventListener('auxclick', onClick, true)
    }
  }, [])

  const setTitle = useCallback((id: string, title: string, pathname: string) => {
    setState((now) =>
      now.tabs.some((one) => one.id === id && (one.title !== title || one.titleFor !== pathname))
        ? { ...now, tabs: now.tabs.map((one) => (one.id === id ? { ...one, title, titleFor: pathname } : one)) }
        : now,
    )
  }, [])

  const value = useMemo<TabsValue>(() => ({ ...state, mounted, open, activate, close, setTitle }), [state, mounted, open, activate, close, setTitle])
  return <TabsContext.Provider value={value}>{children}</TabsContext.Provider>
}

/**
 * 누른 것이 **CompCore 안의 화면 링크**면 그 라우터 주소와 임시 이름 — 다른 곳(외부 · API 내려받기 · 파일 받기)이나
 * `data-no-tab` 이 붙은 링크면 `null`.
 */
export function linkTarget(target: EventTarget | null): { path: string; title?: string } | null {
  const anchor = target instanceof Element ? target.closest('a[href]') : null
  if (!(anchor instanceof HTMLAnchorElement) || anchor.hasAttribute('download') || anchor.hasAttribute('data-no-tab')) return null
  const url = new URL(anchor.href, window.location.href)
  if (url.origin !== window.location.origin) return null
  if (PUBLIC_PATH && url.pathname !== PUBLIC_PATH && !url.pathname.startsWith(`${PUBLIC_PATH}/`)) return null
  const path = (PUBLIC_PATH ? url.pathname.slice(PUBLIC_PATH.length) : url.pathname) || '/'
  if (path === '/api' || path.startsWith('/api/')) return null
  const text = (anchor.textContent || anchor.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ')
  return { path: `${path}${url.search}`, title: text ? text.slice(0, 40) : undefined }
}

export function useTabs(): TabsValue | null {
  return useContext(TabsContext)
}

/** 탭 장치의 값을 바꿔 끼운다 — 시험이 `open` 을 엿볼 때. */
export function TabsSpy({ value, children }: { value: TabsValue; children: ReactNode }) {
  return <TabsContext.Provider value={value}>{children}</TabsContext.Provider>
}

/** 탭 이름을 화면이 정한다 — 작업 · 부품 이름. 탭 밖이면 아무것도 안 한다. */
export function useTabTitle(title: string | null | undefined) {
  const pane = useContext(PaneContext)
  const tabs = useContext(TabsContext)
  // 이 화면의 경로 — 탭 안이면 그 탭의 주소다(탭이 `useRoutes` 에 주소를 준다).
  const { pathname } = useLocation()
  const setTitle = tabs?.setTitle
  const id = pane?.id
  useEffect(() => {
    if (id && setTitle && title) setTitle(id, title, pathname)
  }, [id, setTitle, title, pathname])
}

/** 탭에 보일 이름 — 지금 화면이 준 이름, 없으면 메뉴 이름. */
export function tabLabel(tab: AppTab): string {
  return tab.title && tab.titleFor === tab.path.split('?')[0] ? tab.title : menuLabel(tab.path)
}

/** 메뉴 이름 — 주소의 가장 긴 앞부분과 맞는 사이드바 항목. 화면이 이름을 안 주면 이것. */
export function menuLabel(path: string): string {
  const pathname = path.split('?')[0]
  let best: { label: string; length: number } | null = null
  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      const to = item.to
      if (!to) continue
      if ((pathname === to || pathname.startsWith(`${to}/`)) && (!best || to.length > best.length)) best = { label: item.label, length: to.length }
    }
  }
  return best?.label ?? pathname
}

/** 탭 줄 — 탭이 둘 이상일 때만. 가운데 단추(휠)로 누르면 닫는다. */
export function TabBar() {
  const tabs = useTabs()
  if (!tabs || tabs.tabs.length < 2) return null
  return (
    <div role="tablist" aria-label="열린 화면" className="bg-muted/40 flex shrink-0 items-end gap-0.5 overflow-x-auto border-b px-2 pt-1">
      {tabs.tabs.map((tab) => {
        const active = tab.id === tabs.activeId
        const label = tabLabel(tab)
        return (
          <div
            key={tab.id}
            className={`group flex max-w-56 shrink-0 items-center rounded-t-md border border-b-0 text-xs ${active ? 'bg-background text-foreground -mb-px' : 'text-muted-foreground hover:bg-background/60 border-transparent'}`}
          >
            <button
              type="button"
              role="tab"
              aria-selected={active}
              title={`${label} — ${tab.path}`}
              className="min-w-0 truncate py-1.5 pr-1 pl-3"
              onClick={() => tabs.activate(tab.id)}
              onAuxClick={(event) => {
                if (event.button === 1) tabs.close(tab.id)
              }}
            >
              {label}
            </button>
            <button
              type="button"
              aria-label={`${label} 탭 닫기`}
              className="hover:bg-muted mr-1 rounded p-0.5 opacity-60 group-hover:opacity-100"
              onClick={() => tabs.close(tab.id)}
            >
              <X className="size-3" />
            </button>
          </div>
        )
      })}
    </div>
  )
}

/** 탭 밖의 경로 문맥 — 탭마다 라우트 표를 **처음부터** 맞춘다(바깥 `/` 경로 아래의 자손 경로로 보지 않게). */
const ROOT_ROUTE_CONTEXT = { outlet: null, matches: [], isDataRoute: false }

function PaneRoutes({ routes, location }: { routes: RouteObject[]; location: Partial<Location> | string }) {
  return useRoutes(routes, location)
}

/** 탭들의 화면 — 그린 탭은 모두 살려 두고 보이는 것 하나만 드러낸다. 탭마다 제 스크롤을 가진다. */
export function TabPanes({ routes, fallback }: { routes: RouteObject[]; fallback: ReactNode }) {
  const tabs = useTabs()
  const location = useLocation()
  if (!tabs) return null
  return (
    <>
      {tabs.tabs
        .filter((tab) => tabs.mounted.has(tab.id))
        .map((tab) => {
          const active = tab.id === tabs.activeId
          // 라우터의 주소는 **그 탭의 것일 때만** 쓴다. 탭을 누르면 보이는 탭이 먼저 바뀌고 주소는 한 박자 늦게
          // 온다 — 그 사이에 앞 탭의 주소로 그리면 이 탭의 화면이 내려갔다 다시 올라와 고치던 것을 잃는다(시험이
          // 잡았다). 링크로 옮길 때는 탭이 주소를 따라온 다음에 새 화면을 그린다.
          const own = active && pathOf(location) === tab.path
          const at = own ? location : tab.path
          const resetKey = own ? location.pathname : tab.path.split('?')[0]
          return (
            <div key={tab.id} data-scroll-root="" hidden={!active} className="absolute inset-0 overflow-auto p-6">
              <PaneContext.Provider value={{ id: tab.id, active }}>
                <ErrorBoundary resetKey={resetKey}>
                  <Suspense fallback={fallback}>
                    <RouteContext.Provider value={ROOT_ROUTE_CONTEXT}>
                      <PaneRoutes routes={routes} location={at} />
                    </RouteContext.Provider>
                  </Suspense>
                </ErrorBoundary>
              </PaneContext.Provider>
            </div>
          )
        })}
    </>
  )
}
