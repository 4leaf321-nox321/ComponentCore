/**
 * 사이드바 메뉴 정의 — **화면 목록의 정본이다.**
 *
 * 라우터(`routes/router.tsx`)에 같은 경로가 있어야 한다. `router.test.tsx` 가 검사한다.
 */

import { Boxes, DraftingCompass, Server, UserCog, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export type NavAudience = 'everyone' | 'system_admin'

export interface NavItem {
  label: string
  icon: LucideIcon
  to: string
  end?: boolean
  audience?: NavAudience
  summary?: string
}

export interface NavGroup {
  /** 없으면 제목 없이 항목만 선다. 한 항목짜리 그룹에는 제목을 안 단다. */
  title?: string
  items: NavItem[]
  audience?: NavAudience
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: '지그',
    items: [
      {
        label: '지그 프로젝트',
        icon: Boxes,
        to: '/jigs',
        summary: '제품 STEP 을 올리고 지그를 만든다.',
      },
      {
        label: 'CAD 작업대',
        icon: DraftingCompass,
        to: '/cad',
        summary: '제품 파일 없이 기본 도형을 그려 STEP 으로 받는다.',
      },
    ],
  },
  {
    items: [{ label: '내 정보', icon: UserCog, to: '/me' }],
  },
  {
    title: '관리',
    audience: 'system_admin',
    items: [
      { label: '계정', icon: Users, to: '/admin/accounts', audience: 'system_admin' },
      { label: '서버', icon: Server, to: '/admin/server', audience: 'system_admin' },
    ],
  },
]

export function canSee(audience: NavAudience | undefined, viewer: { isSystemAdmin: boolean }) {
  if (audience === 'system_admin') return viewer.isSystemAdmin
  return true
}

/** 볼 수 있는 것만 남긴 메뉴. **빈 그룹은 제목까지 지운다.** */
export function visibleGroups(viewer: { isSystemAdmin: boolean }): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => canSee(item.audience, viewer)),
  })).filter((group) => canSee(group.audience, viewer) && group.items.length > 0)
}
