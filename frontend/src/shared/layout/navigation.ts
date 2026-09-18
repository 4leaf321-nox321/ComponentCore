/**
 * 사이드바 메뉴 정의 — **화면 목록의 정본이다.** `router.test.tsx` 가 라우터와 맞는지 검사한다.
 *
 * 순서가 곧 동선이다: 내 활동(그리기 → 내 작업 → 실행 기록) → 모아 둔 것(템플릿 · 부품 · 지그)
 * → 관리. 템플릿은 시작점, 부품 · 지그는 승격된 결과다.
 */

import {
  Boxes,
  DraftingCompass,
  FileStack,
  FlaskConical,
  FolderPen,
  Layers,
  ListChecks,
  Server,
  UserCog,
  Users,
} from 'lucide-react'
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
  title?: string
  items: NavItem[]
  audience?: NavAudience
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: '내 활동',
    items: [
      { label: '그리기', icon: DraftingCompass, to: '/draw', summary: '템플릿이나 STEP 에서 새 작업을 시작한다.' },
      { label: '내 작업', icon: FolderPen, to: '/works', summary: '그리고 있는 것. 나만 본다. 여기서 부품 · 지그로 승격한다.' },
      {
        label: '실험계획',
        icon: FlaskConical,
        to: '/doe',
        summary: '치수를 훑어 형상 여러 벌 — 해석으로 넘길 STEP 을 공유 폴더에 쏟는다.',
      },
      { label: '실행 기록', icon: ListChecks, to: '/jobs', summary: '내가 건 작업(부품 평가 · 지그 생성)과 산출물.' },
      { label: '내 정보', icon: UserCog, to: '/me' },
    ],
  },
  {
    title: '모아 둔 것',
    items: [
      {
        label: '템플릿',
        icon: FileStack,
        to: '/templates',
        summary: '그리기의 출발점. 내 것과 공용 두 자리가 있다.',
      },
      { label: '부품', icon: Layers, to: '/parts', summary: '승격된 부품. 누구나 보고 내 공간으로 복사한다.' },
      { label: '지그', icon: Boxes, to: '/jigs', summary: '승격된 지그. 어느 부품 버전의 지그인지 함께.' },
    ],
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
