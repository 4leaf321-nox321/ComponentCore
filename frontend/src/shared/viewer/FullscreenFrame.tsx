/**
 * 전체 화면 틀 — 안의 것을 브라우저 밖 전체 화면(Fullscreen API)으로. 편집기 · 부품 3D · 지그 결과가
 * 같은 단추와 같은 동작을 쓴다. Esc 로 나오면 상태도 따라온다.
 */

import { useEffect, useRef, useState } from 'react'
import { Maximize2, Minimize2 } from 'lucide-react'

import { Button } from '@/shared/components/ui/button'

export function useFullscreen() {
  const frame = useRef<HTMLDivElement | null>(null)
  const [active, setActive] = useState(false)

  useEffect(() => {
    const sync = () => setActive(document.fullscreenElement !== null && document.fullscreenElement === frame.current)
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])

  async function toggle() {
    if (document.fullscreenElement) {
      await document.exitFullscreen()
      return
    }
    try {
      await frame.current?.requestFullscreen()
    } catch {
      setActive((v) => !v) // 브라우저가 막으면 화면 안에서라도 덮는다
    }
  }
  return { frame, active, toggle }
}

export function FullscreenButton({ active, onToggle, className }: { active: boolean; onToggle: () => void; className?: string }) {
  return (
    <Button size="sm" variant={active ? 'default' : 'outline'} className={className} onClick={onToggle} title="브라우저 밖 전체 화면 (Esc 로 나옴)">
      {active ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
      {active ? '전체 화면 끝' : '전체 화면'}
    </Button>
  )
}

/** 전체 화면일 때 덮는 틀의 클래스. 아니면 빈 문자열. */
export function frameClass(active: boolean): string {
  return active ? 'bg-background fixed inset-0 z-50 flex flex-col gap-2 overflow-auto p-3' : ''
}
