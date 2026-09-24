/**
 * 요소가 **스크롤 영역의 아래 끝까지** 차게 높이를 잰다 — 3D 뷰가 화면을 채우되 페이지 스크롤은
 * 안 생기게. `calc(100vh - N rem)` 로 어림하면 머리 높이가 조금만 달라도 넘치거나 모자란다.
 *
 * 스크롤 영역(AppShell 의 <main>) 안에서 요소의 자리(스크롤과 무관한 콘텐츠 좌표)를 재고,
 * 영역 높이에서 그 자리와 아래 여백을 뺀 만큼을 높이로 준다. 위쪽이 바뀌면(모드 줄이 늘거나
 * 안내가 생기면) 다시 잰다.
 *
 * ## `min` 은 **그 자리가 원래 쓰던 높이**로 준다
 *
 * 이 계산은 요소가 스크롤 영역 위쪽에서 시작할 때만 이득이다. 위에 쌓인 것이 많은 화면
 * (내 작업: 머리 · 꼬리표 · 탭 · 카드 머리 · 리본 · 안내)에서는 화면 아래까지 재도 남는
 * 것이 얼마 없어 **바닥값으로 떨어진다.**
 *
 * 그때 바닥값이 원래 높이보다 낮으면 **「채우기」 가 오히려 줄인다** — 실제로 겪었다
 * (2026-09-24: 도면 편집기를 `h-[600px]` 에서 바꾸며 바닥값을 360 으로 줘서, 내 작업에서
 * 3D 가 눈에 띄게 작아졌다). 바닥값을 원래 높이로 두면 **여유가 있을 때만 이득이고 없을
 * 때도 손해는 아니다.**
 */

import { useLayoutEffect, useRef, useState } from 'react'

const DEFAULT_MIN = 320

export function useFillHeight<T extends HTMLElement>(options: { min?: number; gap?: number; deps?: unknown[] } = {}) {
  const { min = DEFAULT_MIN, gap = 0, deps = [] } = options
  const ref = useRef<T | null>(null)
  const [height, setHeight] = useState<number | null>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const scroller = (el.closest('main') as HTMLElement | null) ?? document.documentElement
    function measure() {
      if (!el) return
      const outer = scroller.getBoundingClientRect()
      const top = el.getBoundingClientRect().top - outer.top + scroller.scrollTop
      const paddingBottom = parseFloat(getComputedStyle(scroller).paddingBottom) || 0
      const avail = scroller.clientHeight - top - paddingBottom - gap
      setHeight(Math.max(min, Math.floor(avail)))
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(scroller)
    if (scroller.firstElementChild) observer.observe(scroller.firstElementChild)
    window.addEventListener('resize', measure)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { ref, height, style: height === null ? undefined : { height } }
}
