/**
 * 공통 API 타입 — **정본은 서버다.**
 *
 *     cd backend  ; python scripts/export_openapi.py
 *     cd frontend ; npm run api:types
 *
 * 를 돌리면 `schema.d.ts` 가 생긴다. 여기 손으로 적힌 것은 생성물이 없는 첫 클론에서도
 * 빌드가 되게 하기 위한 것이고, 생성물로 갈아탈 때 이 파일의 타입을 하나씩 바꾼다:
 *
 *     import type { components } from '@/shared/api/schema'
 *     export type CurrentUser = components['schemas']['UserOut']
 */

export interface CurrentUser {
  id: string
  email: string
  display_name: string
  status: string
  is_system_admin: boolean
  must_change_password: boolean
  /** 대표 소속 부서(ADR 0008). */
  home_workspace_slug: string | null
  /** 소속 부서 — 조직도 순서. */
  memberships: WorkspaceMembership[]
}

export interface LoginResponse {
  access_token: string
  expires_in: number
  user: CurrentUser
}

/** 개인 액세스 토큰 — 평문은 만들 때 한 번만 보이고 여기에는 없다. */
export interface Pat {
  id: string
  name: string
  prefix: string
  scopes: string[]
  created_at: string
  expires_at: string | null
  last_used_at: string | null
  revoked_at: string | null
}

export interface Account {
  id: string
  email: string
  display_name: string
  status: string
  is_system_admin: boolean
  must_change_password: boolean
  created_at: string
  deleted_at: string | null
}

export interface TemporaryPassword {
  account: Account
  temporary_password: string
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

/** 관리자가 화면에서 바꾸는 서버 설정 하나 — 지금 값 · .env 기본값 · 허용 범위. */
export interface ServerSetting {
  key: string
  label: string
  description: string
  value: number
  default: number
  overridden: boolean
  minimum: number
  maximum: number
  updated_at: string | null
}

export interface ServerStatus {
  app_name: string
  app_slug: string
  version: string
  app_env: string
  database_url_safe: string
  schema_head: string | null
  schema_current: string | null
  schema_behind: boolean
  disk: { path: string; total_bytes: number; free_bytes: number; used_percent: number } | null
  counts: { label: string; count: number }[]
  build123d_version: string
  started_at: string
}

// --- StandardPlatform 에서 들인 것(ADR 0008) — 부서 · 감사 · 알림 · 남은 일 -------------------

export interface WorkspaceMembership {
  workspace_id: string
  slug: string
  name: string
  /** 개발본부 / 재료시험팀. 같은 이름의 팀이 본부마다 있을 수 있다. */
  path: string
  depth: number
  role: string
}

export interface Workspace {
  id: string
  slug: string
  name: string
  description: string
  parent_slug: string | null
  depth: number
  path: string
  sort_order: number
  is_active: boolean
  restricted: boolean
  created_at: string
  member_count: number
  my_role: string | null
}

export interface WorkspaceOption {
  slug: string
  name: string
  path: string
  depth: number
}

export interface WorkspaceReference {
  table: string
  label: string
  count: number
  /** 지우려면 먼저 정리해야 하는가. */
  blocks_delete: boolean
}

export interface Member {
  user_id: string
  email: string
  display_name: string
  status: string
  role: string
  joined_at: string
}

/** 소속 한 줄 — **이름과 경로를 함께.** slug 만 있으면 화면은 「hq」 라고 쓰게 된다. */
export interface AccountWorkspace {
  slug: string
  name: string
  /** 개발본부 / 재료시험팀 — 같은 이름의 팀이 본부마다 있을 수 있다. */
  path: string
  role: string
  /** 대표 소속인가 — 이 사람이 로그인해서 처음 서는 부서. */
  is_home: boolean
}

export interface Notification {
  id: string
  kind: string
  title: string
  body: string | null
  /** 눌렀을 때 갈 곳. **없으면 알림은 읽고 끝나는 글이 된다.** */
  link: string | null
  read_at: string | null
  created_at: string
}

export interface AuditEntry {
  id: string
  action: string
  /** **그때의 이름이다.** 계정이 지워져도 누가 했는지는 남아야 한다. */
  actor_label: string
  actor_client: string | null
  actor_token: string | null
  target_table: string
  target_id: string | null
  target_label: string
  /** 감사 기록마다 모양이 다르다 — 고치기는 `{before, after}`, 나머지는 수 · 목록 · null 도. */
  changes: Record<string, unknown>
  reason: string | null
  /** 접근 로그·파일 로그와 잇는 끈. */
  request_id: string | null
  created_at: string
}

/** 홈의 「남은 일」 한 줄. 서버의 레지스트리가 채운다. */
export interface MaintenanceItem {
  key: string
  label: string
  count: number
  link: string | null
  /** info · warning. 경고는 색이 붙는다. */
  severity: string
}
