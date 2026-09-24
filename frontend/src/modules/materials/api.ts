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
  /**
   * 어디서 왔나 — `matnexus`(등록 재료) · `literature`(문헌 물성 카탈로그) ·
   * `catalog`(MatNexus 에 못 닿아 올려 둔 사본).
   *
   * **`literature` 는 목록에 값이 안 딸려 온다**(2663건을 값째로 끌면 수십 MB). 고른 뒤
   * `materialsApi.one(id, …)` 으로 그 재료만 값까지 받는다.
   */
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
    /** `physical.density` — **기계가 읽을 이름**. 등록 재료든 문헌이든 같다. */
    density_key?: string
    poisson_ratio?: number
    poisson_key?: string
    properties?: {
      item: string
      unit: string
      points: { temperature_C?: number | null; value: number }[]
      /** 문헌 쪽에만 — `mechanical.youngs_modulus` 처럼 **기계가 읽을 이름**. */
      key?: string
      /**
       * 문헌 쪽에만 — **어떤 조건에서 잰 값인가**(`{test: "85°C/85%RH 168hr"}`).
       * 조건이 값의 일부다: 85°C 흡습률을 상온 값으로 쓰면 틀린다.
       */
      conditions?: Record<string, unknown>
      /** 문헌 쪽에만 — 출처 등급(1 이 가장 좋다). */
      tier?: number
    }[]
    /** 표에 없는 단위라 **못 바꾼** 항목 이름. 값은 원래 단위 그대로다. */
    unconverted?: string[]
    /**
     * **선형 탄성으로 풀려면 빠진 것**(탄성계수 · 푸아송비 · 밀도). 다 있으면 없는 칸이다.
     *
     * 목록 한 줄에는 값이 안 딸려 오므로 **거기서는 아예 안 온다** — 「아직 안 봤다」 와
     * 「없다」 는 다르다. 고른 뒤에야 진짜를 말한다.
     */
    missing_structural?: string[]
  }
}

export const materialsApi = {
  /**
   * 물성 찾기 — **서버가 중계한다**(그쪽 CORS 는 자기 주소만 허용하고, 토큰이 화면에
   * 나가면 안 된다). 못 닿으면 `fallback` 이 참이고 `detail` 에 까닭이 온다.
   */
  search: (options: { q?: string; family?: string; category?: string; limit?: number; system?: string; source?: string } = {}) => {
    const query = new URLSearchParams({ limit: String(options.limit ?? 30) })
    if (options.q) query.set('q', options.q)
    if (options.family) query.set('family', options.family)
    if (options.category) query.set('category', options.category)
    if (options.system) query.set('system', options.system)
    if (options.source) query.set('source', options.source)
    return api.get<{ items: MaterialRow[]; fallback: boolean; detail?: string }>(`/materials?${query}`)
  },
  /** 재료 하나 — **문헌은 여기서 값이 온다**(목록에는 안 딸려 온다). */
  one: (id: string, options: { system?: string; source?: string } = {}) => {
    const query = new URLSearchParams()
    if (options.system) query.set('system', options.system)
    if (options.source) query.set('source', options.source)
    return api.get<MaterialRow>(`/materials/${encodeURIComponent(id)}?${query}`)
  },
  /**
   * 쪽(族) · 갈래와 그 **개수** — 탐색기의 첫 두 칸이 여기서 나온다.
   *
   * 검색 결과에서 뽑아 만들지 않는 까닭: 목록은 상한만큼만 오므로 「앞 서른 줄에 있는 쪽」
   * 만 보이고, 사람은 나머지가 없는 줄 안다. 개수가 함께 오니 빈 갈래를 눌러 보게 하지도
   * 않는다.
   */
  /**
   * 이 재료로 **낼 수 있는 솔버 덱 형식**. 중립 물성 옆에 **덤으로** 실어 보낼 수 있다 —
   * 받는 쪽이 제 덱을 손으로 짜는 대신 그대로 쓴다.
   *
   * 담는 순간 솔버를 고르는 것이라 **기본은 안 담는다**. 사람이나 오케스트레이터가 고른다.
   */
  deckFormats: (materialId: string, source = 'registered') =>
    api.get<{
      items: { key: string; label: string; ready: boolean; missing?: { label?: string }[] }[]
      note?: string
    }>(`/materials/${encodeURIComponent(materialId)}/decks?source=${source}`),
  /** **문헌 카탈로그**의 하위계 · 갈래 — 등록 재료 쪽과 같은 모양이라 화면이 한 벌이면 된다. */
  catalogClassifications: () =>
    api.get<{ items: { family: string; category: string; count: number }[]; fallback: boolean; total?: number }>(
      '/materials/catalog/classifications',
    ),
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
