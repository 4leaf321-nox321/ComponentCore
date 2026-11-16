/**
 * 사이드바 메뉴 옆의 숫자 — **이 사용자가 손댈 차례인 것.**
 *
 * VOC 에는 알림이 없어(폐쇄망, 알림 모듈 없음) 게시판을 열어 보지 않으면 새 의견이 묻힌다. 그래서
 * 메뉴 옆에 센다: 관리자는 접수 대기, 작성자는 확인 대기(본인 건이 「해결」 된 것). 값은 모듈에
 * 들고 있고, 화면을 옮길 때 · 2분마다 · VOC 화면이 무엇을 바꿨을 때(`refreshNavBadges`) 다시 묻는다.
 * 못 받으면 숫자를 안 그린다 — 틀린 숫자보다 없는 숫자가 낫다.
 *
 * **공지는 안 읽은 수**(2026-11-16, MatNexus 와 같다) — 팝업은 중요한 것에만 켜므로, 판마다 실려
 * 오는 업데이트 안내는 이 수가 아니면 게시판에 들어가 봐야 안다. 공지를 읽으면 그 자리에서 다시
 * 묻는다(`notices/api` 의 `read` · `readAll`).
 */

import { useEffect, useState } from 'react'

import { api } from '@/shared/api/client'

export type NavBadgeKey = 'voc' | 'notices'

export interface NavBadge {
  count: number
  /** 숫자가 무엇을 세는지 — 메뉴의 툴팁. */
  title: string
}

export type NavBadges = Partial<Record<NavBadgeKey, NavBadge>>

/** 다시 묻는 간격. 사람이 한 화면에 머물러도 새 의견을 놓치지 않을 만큼만. */
const EVERY_MS = 120_000

let current: NavBadges = {}
const listeners = new Set<(value: NavBadges) => void>()

const count = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.floor(value) : 0)

function voc(raw: { waiting?: unknown; to_confirm?: unknown } | null): NavBadge | undefined {
  const waiting = count(raw?.waiting)
  const toConfirm = count(raw?.to_confirm)
  if (waiting + toConfirm === 0) return undefined
  const parts = [waiting > 0 && `접수 대기 ${waiting}건`, toConfirm > 0 && `확인 대기 ${toConfirm}건`].filter(Boolean)
  return { count: waiting + toConfirm, title: parts.join(', ') }
}

function notices(raw: { unread?: unknown } | null): NavBadge | undefined {
  const unread = count(raw?.unread)
  return unread > 0 ? { count: unread, title: `안 읽은 공지 ${unread}건` } : undefined
}

function publish(value: NavBadges) {
  current = value
  for (const listener of listeners) listener(value)
}

/** 다시 묻는다 — VOC 를 등록하거나 상태를 바꾼 화면, 공지를 읽은 자리가 부른다. **하나가 실패해도
 *  다른 하나는 갱신한다** — 못 받은 쪽은 지난 값을 둔다(잠깐 끊긴 것으로 숫자가 깜빡이지 않게). */
export function refreshNavBadges(): void {
  void Promise.allSettled([
    api.get<{ waiting?: unknown; to_confirm?: unknown }>('/voc/summary'),
    api.get<{ unread?: unknown }>('/notices/unread-count'),
  ]).then(([summary, unread]) => {
    if (summary.status === 'rejected' && unread.status === 'rejected') return
    publish({
      voc: summary.status === 'fulfilled' ? voc(summary.value) : current.voc,
      notices: unread.status === 'fulfilled' ? notices(unread.value) : current.notices,
    })
  })
}

/** `key` 가 바뀔 때(화면 이동)마다 다시 묻는다. */
export function useNavBadges(key: string): NavBadges {
  const [value, setValue] = useState(current)
  useEffect(() => {
    listeners.add(setValue)
    return () => {
      listeners.delete(setValue)
    }
  }, [])
  useEffect(() => {
    refreshNavBadges()
    const timer = setInterval(refreshNavBadges, EVERY_MS)
    return () => clearInterval(timer)
  }, [key])
  return value
}
