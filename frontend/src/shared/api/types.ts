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
}

export interface LoginResponse {
  access_token: string
  expires_in: number
  user: CurrentUser
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
