/**
 * 사이드바 메뉴 정의 — **화면 목록의 정본이다.** `router.test.tsx` 가 라우터와 맞는지 검사한다.
 *
 * 순서가 곧 동선이다: 내 활동(새 작업 → 내 작업 → 실행 기록) → 공용 공간(템플릿 · 시험 규격 ·
 * 부품 · 지그) → 관리. 템플릿 · 시험 규격은 시작점, 부품 · 지그는 승격된 결과다.
 */

import {
  Boxes,
  DraftingCompass,
  FileStack,
  FlaskConical,
  FolderPen,
  FolderSearch,
  Layers,
  ListChecks,
  Ruler,
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
      { label: '새 작업', icon: DraftingCompass, to: '/draw', summary: '빈 화면, 템플릿 또는 STEP 파일에서 부품이나 지그를 모델링하여 새 작업으로 저장합니다.' },
      { label: '내 작업', icon: FolderPen, to: '/works', summary: '작성 중인 작업입니다. 본인만 조회할 수 있으며, 다른 사용자에게 공개하려면 부품 또는 지그로 등록하십시오.' },
      {
        label: 'DOE',
        icon: FlaskConical,
        to: '/doe',
        summary: '변수 범위에 따라 여러 형상을 서버에서 생성하고, ‘내보내기’로 해석용 공유 폴더에 저장합니다.',
      },
      { label: '실행 기록', icon: ListChecks, to: '/jobs', summary: '본인이 요청한 작업(부품 평가, 지그 생성)과 그 산출물을 조회합니다.' },
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
