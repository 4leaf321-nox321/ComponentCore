/**
 * 「내 작업」 만의 폴더 일 — 만든 해로 묶기. 경로 · 나무는 공용(`@/shared/folders/paths`).
 */

import type { WorkSummary } from '@/modules/works/api'

/** 만든 해 — 이 브라우저의 시각으로(목록의 날짜 칸과 같다). */
export function yearOf(iso: string): number {
  return new Date(iso).getFullYear()
}

/** 만든 순으로 온 목록을 해마다 묶는다 — 한 쪽 안에서 같은 해가 한데 있다. */
export function groupByYear(rows: WorkSummary[]): { year: number; rows: WorkSummary[] }[] {
  const out: { year: number; rows: WorkSummary[] }[] = []
  for (const row of rows) {
    const year = yearOf(row.created_at)
    const last = out[out.length - 1]
    if (last && last.year === year) last.rows.push(row)
    else out.push({ year, rows: [row] })
  }
  return out
}
