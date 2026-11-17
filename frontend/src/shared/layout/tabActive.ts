/**
 * 화면이 그려진 **화면 탭**과 그 탭이 보이는가 — 뷰어 · 단축키가 숨은 탭에서 쉬려고 본다. 탭 장치(`tabs.tsx`)와
 * 떼어 둔다: 3D 뷰어가 이것을 부르는데 탭 줄 · 메뉴까지 끌고 오지 않게.
 */

import { createContext, useContext } from 'react'

export const PaneContext = createContext<{ id: string; active: boolean } | null>(null)

/** 이 화면이 보이는 탭인가 — 탭 밖(시험 · 단독 화면)이면 늘 참. 숨은 탭은 단축키 · 그리기를 쉰다. */
export function useTabActive(): boolean {
  return useContext(PaneContext)?.active ?? true
}
