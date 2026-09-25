/**
 * 도면의 좌표계 — 이름 붙인 원점 · 축. 형상은 바뀌지 않고, 해석 조건의 「좌표계」 칸이 이름으로
 * 가리킨다(구속의 x · y · z 가 어느 방향인가).
 *
 * 원점 · 회전에 치수 식을 쓰면(`=길이/2`) 실험계획이 치수를 바꿀 때 같이 움직인다. 3D 에는
 * 서버가 푼 축이 그려진다(X 빨강 · Y 초록 · Z 파랑).
 */

import { useState } from 'react'

import type { RecipeFrame } from '@/modules/cad/api'
import { FrameForm } from '@/modules/cad/FrameForm'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'

/** 새 좌표계의 이름 — 겹치지 않게 번호를 붙인다. */
export function nextFrameName(taken: string[]): string {
  let n = taken.length + 1
  while (taken.includes(`좌표계 ${n}`)) n += 1
  return `좌표계 ${n}`
}

export function FramesDialog({
  open,
  frames,
  onChange,
  onClose,
}: {
  open: boolean
  frames: RecipeFrame[]
  onChange: (next: RecipeFrame[]) => void
  onClose: () => void
}) {
  const [picked, setPicked] = useState(0)
  const current = frames[picked]
  const names = frames.map((one) => one.name)
  const clash = current && (names.filter((one) => one === current.name).length > 1 || ['global', '전역'].includes(current.name))

  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>좌표계</DialogTitle>
          <DialogDescription>
            해석 조건의 「좌표계」 칸이 이름으로 가리킵니다. 원점 · 회전에 치수 식(=길이/2)을 쓰면 DOE 로 치수가 바뀔 때 같이
            움직입니다.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-[180px_1fr]">
          <div className="space-y-1">
            <ul className="space-y-0.5">
              {frames.map((one, index) => (
                <li key={index}>
                  <button
                    type="button"
                    aria-current={index === picked ? 'true' : undefined}
                    className={`w-full truncate rounded px-2 py-1 text-left text-sm ${index === picked ? 'bg-accent font-medium' : 'hover:bg-accent/50'}`}
                    onClick={() => setPicked(index)}
                  >
                    {one.name || '(이름 없음)'}
                  </button>
                </li>
              ))}
            </ul>
            <Button
              size="sm"
              variant="outline"
              className="w-full"
              onClick={() => {
                onChange([...frames, { name: nextFrameName(names), origin: [0, 0, 0], rotate: [0, 0, 0] }])
                setPicked(frames.length)
              }}
            >
              좌표계 추가
            </Button>
          </div>
          <div>
            {current ? (
              <div className="space-y-2">
                <FrameForm
                  value={current}
                  onChange={(next) => onChange(frames.map((one, i) => (i === picked ? { name: next.name, origin: next.origin, rotate: next.rotate } : one)))}
                />
                {clash && (
                  <p className="text-destructive text-xs">이름이 겹치거나 전역(global)의 이름입니다 — 다른 이름을 입력하세요.</p>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    onChange(frames.filter((_, i) => i !== picked))
                    setPicked(Math.max(0, picked - 1))
                  }}
                >
                  좌표계 삭제
                </Button>
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">좌표계가 없습니다. 「좌표계 추가」 로 만듭니다.</p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button onClick={onClose}>닫기</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
