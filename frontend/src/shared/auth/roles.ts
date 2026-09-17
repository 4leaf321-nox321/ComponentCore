/**
 * 이 사람이 무엇을 할 수 있나 — 한 곳에서 판정한다. **표시일 뿐 권한이 아니다.** 권한은
 * 서버가 판정한다 — 여기서 하는 일은 눌러 보고 403 을 알게 하지 않는 것이다.
 */

import type { CurrentUser } from '@/shared/auth/types'

export function isSystemAdmin(user: CurrentUser | null | undefined): boolean {
  return Boolean(user?.is_system_admin)
}

/** 프로젝트를 고칠 수 있나 — 소유자거나 시스템 관리자. 서버의 `require_owner` 와 같은 식. */
export function canEditProject(user: CurrentUser | null | undefined, ownerId: string): boolean {
  return isSystemAdmin(user) || user?.id === ownerId
}
