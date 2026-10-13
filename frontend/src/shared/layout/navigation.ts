/**
 * 사이드바 메뉴 정의 — **화면 목록의 정본이다.** `router.test.tsx` 가 라우터와 맞는지 검사한다.
 *
 * 순서가 곧 동선이다: 내 활동(새 작업 → 내 작업 → 실행 기록) → 공용 공간(템플릿 · 시험 규격 ·
 * 부품 · 지그) → 온톨로지가 만든 묶음 → 기준정보(검색 · 타입 · 그래프 · 지표) → 내 부서 → 지원(VOC)
 * → 관리. 템플릿 · 시험 규격은 시작점, 부품 · 지그는 승격된 결과다.
 *
 * 온톨로지 · 부서 쪽 항목과 동적 묶음(`mergeDynamic`)은 StandardPlatform 의 것을 그대로
 * 들였다(ADR 0008). 정적 화면의 정본은 여전히 이 파일이다 — 동적 화면은 `/o/:typeSlug` 둘로 받는다.
 */

import {
  Bell,
  Boxes,
  Building2,
  ChartColumn,
  ChartLine,
  DatabaseZap,
  DraftingCompass,
  FileStack,
  FlaskConical,
  FolderPen,
  FolderSearch,
  Home,
  Inbox,
  LayoutGrid,
  Layers,
  ListChecks,
  ListTodo,
  MessagesSquare,
  Ruler,
  ScrollText,
  Search,
  Server,
  ShieldCheck,
  UserCog,
  Users,
  Waypoints,
  Webhook,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { NavBadgeKey } from '@/shared/api/navBadges'
import { iconOf } from '@/shared/icons'

/**
 * 누구에게 보이는가 — **표시일 뿐 권한이 아니다.** 권한은 서버가 판정한다. `manager` 는 어느
 * 부서에서든 관리자인 사람(과 시스템 관리자).
 */
export type NavAudience = 'everyone' | 'manager' | 'system_admin'

export interface NavItem {
  label: string
  icon: LucideIcon
  /** 고정 경로 */
  to?: string
  /** 부서 스코프 경로 — 지금 보는 부서의 slug 로 만든다. 소속 부서가 없으면 항목이 안 선다. */
  resolve?: (slug: string) => string
  end?: boolean
  audience?: NavAudience
  summary?: string
  /** 메뉴 옆에 셀 것 — 이 사용자가 손댈 차례인 건(`shared/api/navBadges`). */
  badge?: NavBadgeKey
  /** 이름 옆의 작은 표 — 기록 타입이면 「기록」(SP ADR 0011). 세는 `badge` 와 다르다. */
  tag?: string
}

/** 서버가 주는 동적 묶음(`modules/ontology/api` 의 NavGroupNode 와 짝). */
export interface DynamicGroup {
  slug: string
  label: string
  icon: string
  audience: string
  /** 상위 묶음의 slug — 없으면 맨 위. 평평하게 와서 `mergeDynamic` 이 두 단계로 세운다. */
  parent?: string | null
  /** 서버가 묶음 안에서 **축을 먼저, 기록을 뒤에** 세워 보낸다(`usage`). */
  items: { label: string; icon: string; to: string; slug: string; usage?: string }[]
}

export interface NavGroup {
  title?: string
  items: NavItem[]
  audience?: NavAudience
  /** 하위 묶음 — **한 단계까지다**(상위 묶음 › 묶음 › 타입). */
  children?: NavGroup[]
  /** 접힘을 기억할 열쇠. 없으면 제목 — 동적 묶음은 이름이 겹칠 수 있어 slug 를 준다. */
  foldKey?: string
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: '내 활동',
    items: [
      { label: '새 작업', icon: DraftingCompass, to: '/draw', summary: '빈 화면, 템플릿 또는 STEP 파일에서 부품이나 지그를 모델링하여 새 작업으로 저장합니다.' },
      { label: '내 작업', icon: FolderPen, to: '/works', summary: '작성 중인 작업입니다. 본인만 조회할 수 있으며, 다른 사용자에게 공개하려면 부품 또는 지그로 등록하십시오.' },
      {
        label: 'DOE',
        icon: FlaskConical,
        to: '/doe',
        summary: '변수 범위에 따라 여러 형상을 서버에서 생성하고, ‘내보내기’로 해석용 공유 폴더에 저장합니다.',
      },
      { label: '실행 기록', icon: ListChecks, to: '/jobs', summary: '본인이 요청한 작업(부품 평가, 지그 생성)과 그 산출물을 조회합니다.' },
      {
        // **형상 작업과 다른 큐다**(ADR 0008) — 일괄 입력 · 가져오기 · 지표 계산처럼 DB 를 들고
        // 도는 일. 대화상자를 닫아도 계속되므로 그 진행과 실패 이유를 볼 자리가 있어야 한다.
        label: '데이터 작업',
        icon: ListTodo,
        to: '/tasks',
        summary: '일괄 입력, 가져오기, 지표 계산처럼 기준정보를 다루는 작업의 진행과 결과를 조회합니다.',
      },
      { label: '알림', icon: Bell, to: '/notifications' },
      { label: '내 정보', icon: UserCog, to: '/me' },
    ],
  },
  {
    title: '공용 공간',
    items: [
      {
        label: '템플릿',
        icon: FileStack,
        to: '/templates',
        summary: '모델링의 시작점입니다. 내 템플릿과 공용 템플릿으로 구분됩니다.',
      },
      {
        label: '시험 규격',
        icon: Ruler,
        to: '/specimens',
        summary: 'ASTM·ISO 공개 규격과 사내 규격으로 시편, 시험 지그, 해석 조건이 포함된 작업을 생성합니다.',
      },
      { label: '부품', icon: Layers, to: '/parts', summary: '등록된 부품입니다. 모든 사용자가 조회할 수 있으며, 내 작업 공간으로 복사하여 사용할 수 있습니다.' },
      { label: '지그', icon: Boxes, to: '/jigs', summary: '등록된 지그입니다. 대상 부품과 그 버전을 함께 표시합니다.' },
    ],
  },
  {
    // 온톨로지의 공통 화면 — 동적 묶음(타입별 목록)은 이 바로 앞에 선다(`mergeDynamic`).
    title: '기준정보',
    items: [
      { label: '검색', icon: Search, to: '/search' },
      // **타입이 백 개가 되면 사이드바는 색인이 못 된다** — 색인은 이 화면이 진다. 묶음에 안 걸린
      // 타입도 여기서만 보인다.
      { label: '객체 타입 전부', icon: LayoutGrid, to: '/o', end: true },
      { label: '지식 그래프', icon: Waypoints, to: '/graph' },
      { label: '지표', icon: ChartLine, to: '/metrics' },
    ],
  },
  {
    // **사슬이 아닌 둘.** 부서 사람과 그 부서에서 무엇이 바뀌었나.
    title: '내 부서',
    audience: 'manager',
    items: [
      { label: '부서 홈', icon: Home, resolve: (slug) => `/w/${slug}`, end: true, audience: 'manager' },
      { label: '부서 멤버', icon: Users, resolve: (slug) => `/w/${slug}/members`, audience: 'manager' },
      // 고칠 수 있으면 감사가 아니다 — 여기에는 생성 · 수정 · 삭제가 없다.
      { label: '변경 이력', icon: ScrollText, to: '/audit', audience: 'manager' },
      { label: '데이터 품질', icon: ShieldCheck, to: '/quality', audience: 'manager' },
      // 사람이 판단할 일을 한 곳에서(SP ADR 0027) — 권한은 줄마다 원래 화면의 것이다.
      { label: '검토함', icon: Inbox, to: '/review', audience: 'manager' },
    ],
  },
  {
    title: '지원',
    items: [
      {
        label: 'VOC',
        icon: MessagesSquare,
        to: '/voc',
        badge: 'voc',
        summary: '불편한 점이나 필요한 기능을 등록합니다. 모든 사용자가 조회할 수 있으며, 처리 과정이 이력으로 남습니다.',
      },
    ],
  },
  {
    title: '관리',
    audience: 'system_admin',
    items: [
      {
        label: '모든 작업',
        icon: FolderSearch,
        to: '/admin/works',
        audience: 'system_admin',
        summary: '모든 사용자의 작업을 검색하고 조회합니다. 수정하면 해당 사용자의 작업에 새 버전이 생성됩니다.',
      },
      { label: '계정', icon: Users, to: '/admin/accounts', audience: 'system_admin' },
      // 전사 부서 목록 — 위 「내 부서」 는 내 부서의 일, 이쪽은 부서를 만들고 고치는 자리.
      { label: '부서 정보', icon: Building2, to: '/admin/workspaces', audience: 'system_admin' },
      // **도메인을 정의하는 자리.** 타입을 만들면 위 묶음과 화면이 여기서 생긴다.
      { label: '온톨로지', icon: Boxes, to: '/admin/ontology', audience: 'system_admin' },
      { label: '서버', icon: Server, to: '/admin/server', audience: 'system_admin' },
      { label: '차트 보기', icon: ChartColumn, to: '/admin/charts', audience: 'system_admin' },
      // 바뀐 것을 바깥에 알리는 자리 — 감사 기록에 남는 변경이 곧 이벤트다.
      { label: '웹훅', icon: Webhook, to: '/admin/webhooks', audience: 'system_admin' },
      // 바깥 시스템(OData · REST · 파일)에서 읽어 채우는 자리 — 웹훅의 반대 방향.
      { label: '데이터 소스', icon: DatabaseZap, to: '/admin/datasources', audience: 'system_admin' },
    ],
  },
]

/** 동적 묶음이 서는 자리 — 이 제목의 그룹 **바로 앞**. */
const DYNAMIC_BEFORE = '기준정보'

/**
 * 서버가 준 동적 묶음(`/api/ontology/nav`)을 정적 메뉴와 합친다(SP 그대로, 서는 자리만 다르다 —
 * SP 는 홈 바로 아래, 여기는 공용 공간 다음 · 기준정보 앞).
 */
export function mergeDynamic(groups: NavGroup[], dynamic: DynamicGroup[]): NavGroup[] {
  if (dynamic.length === 0) return groups

  const asGroup = (group: DynamicGroup): NavGroup => ({
    title: group.label,
    foldKey: group.slug,
    audience: (group.audience as NavAudience) ?? 'everyone',
    items: group.items.map((item) => ({
      label: item.label,
      // 아이콘 이름은 데이터에서 온다(타입 정의의 `icon`). **모르는 이름이면 기본으로 떨어진다.**
      icon: iconOf(item.icon),
      to: item.to,
      // 기록은 축과 같은 묶음에 서되 표를 단다.
      tag: item.usage === 'log' ? '기록' : undefined,
    })),
  })

  // **먼저 전부 만들고 그다음 붙인다** — 상위가 목록에서 뒤에 오면 한 바퀴로는 자식이 상위를
  // 못 찾는다(SP 실측).
  const made = new Map<string, NavGroup>()
  for (const group of dynamic) made.set(group.slug, asGroup(group))
  const converted: NavGroup[] = []
  for (const group of dynamic) {
    const node = made.get(group.slug)
    if (!node) continue
    const up = group.parent ? made.get(group.parent) : undefined
    if (up && up !== node) {
      up.children = [...(up.children ?? []), node]
      continue
    }
    converted.push(node)
  }

  const at = groups.findIndex((group) => group.title === DYNAMIC_BEFORE)
  const cut = at < 0 ? groups.length : at
  return [...groups.slice(0, cut), ...converted, ...groups.slice(cut)]
}

/** 항목이 가리키는 곳. 부서 스코프 항목은 부서를 모르면 null — 그 항목은 서지 않는다. */
export function itemHref(item: NavItem, slug: string | null): string | null {
  if (item.to) return item.to
  if (item.resolve) return slug ? item.resolve(slug) : null
  return '/'
}

export interface NavViewer {
  isSystemAdmin: boolean
  isAnyManager: boolean
}

export function canSee(audience: NavAudience | undefined, viewer: NavViewer): boolean {
  if (audience === 'system_admin') return viewer.isSystemAdmin
  if (audience === 'manager') return viewer.isSystemAdmin || viewer.isAnyManager
  return true
}

/**
 * 볼 수 있는 것만 남긴 메뉴. **빈 그룹은 제목까지 지운다** — 자식에도 같은 규칙을 적용한다.
 * `slug` 는 지금 보는 부서 — 없으면 부서 스코프 항목이 빠진다.
 */
export function visibleGroups(
  viewer: NavViewer,
  dynamic: DynamicGroup[] = [],
  slug: string | null = null,
): NavGroup[] {
  const prune = (group: NavGroup): NavGroup | null => {
    if (!canSee(group.audience, viewer)) return null
    const items = group.items.filter(
      (item) => canSee(item.audience, viewer) && itemHref(item, slug) !== null,
    )
    const children = (group.children ?? [])
      .map(prune)
      .filter((one): one is NavGroup => one !== null)
    if (items.length === 0 && children.length === 0) return null
    return children.length > 0 ? { ...group, items, children } : { ...group, items }
  }
  return mergeDynamic(NAV_GROUPS, dynamic)
    .map(prune)
    .filter((one): one is NavGroup => one !== null)
}
