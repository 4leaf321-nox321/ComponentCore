/**
 * 도면의 좌표계 — 이름 붙인 원점 · 축. 형상은 바뀌지 않고, 해석 조건의 「좌표계」 칸이 이름으로
 * 가리킨다(구속의 x · y · z 가 어느 방향인가).
 *
 * 원점 · 회전에 치수 식을 쓰면(`=길이/2`) 실험계획이 치수를 바꿀 때 같이 움직인다. 3D 에는
 * 서버가 푼 축이 그려진다(X 빨강 · Y 초록 · Z 파랑).
 */

import type { RecipeFrame } from '@/modules/cad/api'
import { FrameForm } from '@/modules/cad/FrameForm'
import type { Placing } from '@/modules/cad/FrameForm'
import { FloatingWindow } from '@/shared/components/FloatingWindow'
import { Button } from '@/shared/components/ui/button'

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
  picked,
  onPicked,
  placing = null,
  onPlacing,
}: {
  open: boolean
  frames: RecipeFrame[]
  onChange: (next: RecipeFrame[]) => void
  onClose: () => void
  /** 고치는 좌표계 — 편집기가 들고 있어야 3D 고르기 · 손잡이를 그것에 잇는다. */
  picked: number
  onPicked: (index: number) => void
  placing?: Placing
  onPlacing?: (next: Placing) => void
}) {
  const setPicked = (index: number) => {
    onPicked(index)
    onPlacing?.(null)
  }
  const current = frames[picked]
  const names = frames.map((one) => one.name)
  const clash = current && (names.filter((one) => one === current.name).length > 1 || ['global', '전역'].includes(current.name))

  return (
    // **3D 를 가리지 않는 창** — 띄운 채 점 · 선 · 면을 누르거나 손잡이를 돌린다.
    <FloatingWindow
      open={open}
      title="좌표계"
      description="시뮬레이션 조건의 「좌표계」 칸이 이름으로 가리킵니다. 원점 · 회전에 치수 식(=길이/2)을 쓰면 DOE 로 치수가 바뀔 때 같이 움직입니다."
      onClose={onClose}
      footer={<Button onClick={onClose}>닫기</Button>}
    >
        <div className="grid gap-3 sm:grid-cols-[120px_1fr]">
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
                  placing={placing}
                  onPlacing={onPlacing}
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
    </FloatingWindow>
  )
}
