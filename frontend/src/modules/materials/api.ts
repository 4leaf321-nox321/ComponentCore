/**
 * 물성 — **서버가 중계한다.**
 *
 * 브라우저가 MatNexus 를 직접 못 부른다(그쪽 CORS 는 자기 주소만 허용한다). 토큰이 화면에
 * 나가서도 안 된다. 그래서 이 플랫폼의 서버가 대신 묻고, 못 닿으면 관리자가 올려 둔
 * 카탈로그로 넘어간다 — **넘어갔다는 사실을 답이 말한다**(`fallback`).
 */

import { api } from '@/shared/api/client'
/** 물성 한 줄 — 목록에 그릴 요약과 **payload 통째로**. */
export interface MaterialRow {
  code: string
  id: string
  name: string
  alias: string
  family: string
  category: string
  grade: string
  density: number | null
  density_unit: string
  poisson_ratio: number | null
  declared_count: number
  /** `matnexus`(살아 있는 API) · `catalog`(올려 둔 사본). */
  source: string
  /** MatNexus 응답 그대로 — 조건에 실리는 것은 이것이다. */
  payload: Record<string, unknown>
}

export const materialsApi = {
  /**
   * 물성 찾기 — **서버가 중계한다**(그쪽 CORS 는 자기 주소만 허용하고, 토큰이 화면에
   * 나가면 안 된다). 못 닿으면 `fallback` 이 참이고 `detail` 에 까닭이 온다.
   */
  search: (q = '', limit = 30) =>
    api.get<{ items: MaterialRow[]; fallback: boolean; detail?: string }>(
      `/materials?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  status: () =>
    api.get<{ configured: boolean; ok: boolean; detail: string; catalog_count: number; catalog_fetched_at: string | null }>(
      '/materials/status',
    ),
}
