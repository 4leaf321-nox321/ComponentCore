/**
 * 화면이 쓰는 수 — 목록 한 쪽의 줄 수, 실험계획 형상 보기에서 한 번에 그리는 수.
 *
 * 관리자가 「서버 › 설정」 에서 바꾸는 값이라 화면마다 상수로 박아 두면 한쪽만 고쳐진다.
 * 한 번만 받아 **모듈에 들고 있고**(화면을 옮길 때마다 다시 묻지 않는다), 관리자가 저장하면
 * `refreshDisplay()` 로 버린다. 아직 못 받았으면 기본값으로 그린다 — 목록이 한 번 더 뜨는
 * 것보다 빈 화면이 나쁘다.
 */

import { useEffect, useState } from 'react'

import { api } from '@/shared/api/client'

export interface Display {
  /** 겹쳐 보기 · 나란히에서 한 번에 화면에 올리는 형상 수. */
  doe_gallery_max: number
  /** 목록 한 쪽에 보이는 줄 수. */
  list_page_size: number
}

const FALLBACK: Display = { doe_gallery_max: 24, list_page_size: 20 }

let current: Display = FALLBACK
let pending: Promise<Display> | null = null
const listeners = new Set<(value: Display) => void>()

const number = (value: unknown, fallback: number) =>
  typeof value === 'number' && Number.isFinite(value) && value >= 1 ? Math.floor(value) : fallback

function load(): Promise<Display> {
  if (!pending) {
    pending = api
      .get<Display>('/server/display')
      .then((raw) => {
        // 숫자가 아니면(낡은 서버 · 엉뚱한 응답) 기본값을 쓴다 — NaN 이 상한으로 새면
        // 목록이 빈 채로 뜨고 그 까닭을 화면에서 알 길이 없다.
        const value = {
          doe_gallery_max: number(raw?.doe_gallery_max, FALLBACK.doe_gallery_max),
          list_page_size: number(raw?.list_page_size, FALLBACK.list_page_size),
        }
        current = value
        for (const listener of listeners) listener(value)
        return value
      })
      .catch(() => {
        // 못 받아도 화면은 떠야 한다 — 기본값으로 둔 채 다음 기회에 다시 묻는다.
        pending = null
        return current
      })
  }
  return pending
}

/** 관리자가 설정을 저장한 뒤 — 다음에 묻는 화면이 새 값을 받는다. */
export function refreshDisplay(): void {
  pending = null
  void load()
}

export function useDisplay(): Display {
  const [value, setValue] = useState(current)
  useEffect(() => {
    listeners.add(setValue)
    void load().then((loaded) => setValue(loaded))
    return () => {
      listeners.delete(setValue)
    }
  }, [])
  return value
}
