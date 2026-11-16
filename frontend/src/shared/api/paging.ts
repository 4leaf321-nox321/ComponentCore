/** 목록 응답 봉투 (app/shared/pagination.py 의 Page 와 짝). */
export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

/** 서버가 한 쪽에 주는 최대(`shared/pagination.py` 의 `MAX_LIMIT`). */
export const PAGE_MAX = 200
/** 모아 받기의 천장 — 이보다 많으면 찾기로 좁혀 나눠 받는다. */
export const ALL_MAX = 2000

/**
 * 쪽을 이어 받아 모은다(MatNexus 의 것을 옮겼다 — 공지 「내용 전체 복사」 가 쓴다).
 *
 * `total` 을 첫 응답에서 받으므로 몇 번 더 부를지 바로 안다. **천장에 걸렸는지는
 * `items.length < total` 로 드러난다** — 따로 깃발을 두면 화면이 그것을 안 볼 수 있다.
 */
export async function fetchAll<T>(fetchPage: (limit: number, offset: number) => Promise<Page<T>>): Promise<Page<T>> {
  const first = await fetchPage(PAGE_MAX, 0)
  const items = [...first.items]
  const wanted = Math.min(first.total, ALL_MAX)
  while (items.length < wanted) {
    const next = await fetchPage(PAGE_MAX, items.length)
    if (next.items.length === 0) break // 서버가 더 줄 것이 없다 — 무한 반복을 막는다
    items.push(...next.items)
  }
  const collected = items.slice(0, ALL_MAX)
  return { items: collected, total: first.total, limit: collected.length, offset: 0 }
}
