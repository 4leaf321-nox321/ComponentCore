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
  /**
   * 어느 **부서**의 재료인가(MatNexus 의 `owner_workspace_name`).
   *
   * MatNexus 는 부서 트리로 권한을 나눈다 — 두 부서에 같은 이름의 재료가 있을 수 있어서,
   * 이것이 안 보이면 고르는 사람이 그 둘을 구별할 수 없다. 올려 둔 카탈로그에는 없을 수
   * 있으므로 빈 문자열이 올 수 있다.
   */
  workspace: string
  density: number | null
  density_unit: string
  poisson_ratio: number | null
  declared_count: number
  /** `matnexus`(살아 있는 API) · `catalog`(올려 둔 사본). */
  source: string
  /** MatNexus 응답 그대로 — 조건에 실리는 것은 이것이다. */
  payload: Record<string, unknown>
  /**
   * 고른 **단위계로 환산한 값**(`?system=` 을 줬을 때만). 원본은 `payload` 에 그대로 있다.
   *
   * 화면은 이것만 보고 그린다 — 환산표를 프런트에도 두면 두 벌이 어긋나고, 그때 **화면이
   * 보여 준 값과 내보낸 값이 달라진다.** 서버는 여기 줄 때와 조건으로 내보낼 때 같은
   * 함수를 쓴다.
   */
  converted?: {
    system: string
    density?: number
    density_unit?: string
    properties?: { item: string; unit: string; points: { temperature_C?: number | null; value: number }[] }[]
    /** 표에 없는 단위라 **못 바꾼** 항목 이름. 값은 원래 단위 그대로다. */
    unconverted?: string[]
  }
}

export const materialsApi = {
  /**
   * 물성 찾기 — **서버가 중계한다**(그쪽 CORS 는 자기 주소만 허용하고, 토큰이 화면에
   * 나가면 안 된다). 못 닿으면 `fallback` 이 참이고 `detail` 에 까닭이 온다.
   */
  search: (options: { q?: string; family?: string; category?: string; limit?: number; system?: string } = {}) => {
    const query = new URLSearchParams({ limit: String(options.limit ?? 30) })
    if (options.q) query.set('q', options.q)
    if (options.family) query.set('family', options.family)
    if (options.category) query.set('category', options.category)
    if (options.system) query.set('system', options.system)
    return api.get<{ items: MaterialRow[]; fallback: boolean; detail?: string }>(`/materials?${query}`)
  },
  /**
   * 쪽(族) · 갈래와 그 **개수** — 탐색기의 첫 두 칸이 여기서 나온다.
   *
   * 검색 결과에서 뽑아 만들지 않는 까닭: 목록은 상한만큼만 오므로 「앞 서른 줄에 있는 쪽」
   * 만 보이고, 사람은 나머지가 없는 줄 안다. 개수가 함께 오니 빈 갈래를 눌러 보게 하지도
   * 않는다.
   */
  classifications: () =>
    api.get<{ items: { family: string; category: string; count: number }[]; fallback: boolean; detail?: string }>(
      '/materials/classifications',
    ),
  status: () =>
    api.get<{
      configured: boolean
      ok: boolean
      detail: string
      /** 어느 계정으로 붙었나 — MatNexus 의 권한은 계정으로 정해진다. */
      account?: string
      /** 시스템 관리자 토큰이면 참 — 읽기만 하는 연동에는 과하다. 관리자에게 알린다. */
      system_admin?: boolean
      /** `.env` 로 좁힌 부서 slug. 비면 그 계정이 보는 전부. */
      workspace?: string
      /** 그 계정에게 보이는 재료 수. */
      materials?: number | null
      catalog_count: number
      catalog_fetched_at: string | null
    }>('/materials/status'),
}
