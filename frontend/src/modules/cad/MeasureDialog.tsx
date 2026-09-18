/**
 * 측정 창 — 3D 를 **가리지 않는 모달**(막 없음 · 끌어서 옮김). 띄워 둔 채로 계속 누른다.
 *
 * 쉬워 보여야 한다: 무엇을 고를지(점 · 선 · 면)를 칩으로 켜고 끄고, 고른 것이 무엇인지 줄로
 * 보이고, 잴 수 있는 값은 **한꺼번에** 나온다(거리 · 축별 차 · 각도 · 지름 · 나란한지…).
 * 「담기」 로 쌓아 두면 3D 에 남아 여러 곳을 한 화면에서 비교한다.
 */

import { CircleDot, Minus, MousePointerClick, Ruler, Square, Trash2, X } from 'lucide-react'

import { anchor, headline, measurement, title } from '@/modules/cad/measure'
import type { Pick, Row } from '@/modules/cad/measure'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'

/** 3D 에서 무엇을 고를 수 있나 — 끄면 그 종류는 안 잡힌다(빽빽한 형상에서 헛집기를 막는다). */
export type PickKind = 'point' | 'edge' | 'face'

export const PICK_KINDS: { kind: PickKind; label: string; hint: string; icon: typeof Ruler }[] = [
  { kind: 'point', label: '점', hint: '켜면 3D 에 파란 점이 뜬다 — 꼭짓점 · 모서리 중점 · 원 중심', icon: CircleDot },
  { kind: 'edge', label: '선', hint: '모서리 · 원(구멍 지름)', icon: Minus },
  { kind: 'face', label: '면', hint: '평면 · 원통면', icon: Square },
]

/** 담아 둔 측정 하나. */
export interface KeptMeasure {
  id: string
  picks: Pick[]
  label: string
}

function RowLine({ row }: { row: Row }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground text-xs">{row.label}</span>
      <span className={`font-mono text-xs ${row.headline ? 'text-foreground text-sm font-semibold' : ''}`}>
        {row.approx && <span title="곡면 · 곡선은 삼각형으로 근사합니다">≈ </span>}
        {row.text}
      </span>
    </div>
  )
}

export function MeasureDialog({
  open,
  picks,
  kept,
  kinds,
  onKinds,
  onUndo,
  onClear,
  onKeep,
  onDropKept,
  onClose,
}: {
  open: boolean
  picks: Pick[]
  kept: KeptMeasure[]
  kinds: Set<PickKind>
  onKinds: (next: Set<PickKind>) => void
  onUndo: () => void
  onClear: () => void
  onKeep: () => void
  onDropKept: (id: string) => void
  onClose: () => void
}) {
  const { rows } = measurement(picks)
  const full = picks.length >= 2

  return (
    <Dialog open={open} modal={false} onOpenChange={(value) => !value && onClose()}>
      <DialogContent
        overlay={false}
        // 3D 오른쪽에 붙여 세운다 — 가운데면 재려는 자리를 가린다. 끌어서 옮길 수 있다.
        className="top-24 right-6 left-auto max-h-[70vh] w-80 translate-x-0 translate-y-0 sm:max-w-sm"
        onInteractOutside={(event) => event.preventDefault()}
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Ruler className="size-4" /> 측정
          </DialogTitle>
          <DialogDescription>3D 에서 눌러 고릅니다. 둘을 고르면 거리 · 각도가 한꺼번에 나옵니다.</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* 무엇을 고를까 */}
          <div>
            <p className="text-muted-foreground mb-1 text-xs">고를 것</p>
            <div className="flex gap-1">
              {PICK_KINDS.map((one) => {
                const on = kinds.has(one.kind)
                const Icon = one.icon
                return (
                  <button
                    key={one.kind}
                    type="button"
                    title={one.hint}
                    aria-pressed={on}
                    onClick={() => {
                      const next = new Set(kinds)
                      // 하나는 켜져 있어야 한다 — 다 끄면 아무것도 못 고른다.
                      if (on && next.size > 1) next.delete(one.kind)
                      else next.add(one.kind)
                      onKinds(next)
                    }}
                    className={`flex flex-1 items-center justify-center gap-1 rounded-md border px-2 py-1.5 text-xs ${
                      on ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
                    }`}
                  >
                    <Icon className="size-3.5" />
                    {one.label}
                  </button>
                )
              })}
            </div>
          </div>

          {kinds.has('point') && (
            <p className="text-muted-foreground -mt-2 text-[11px]">
              <span className="text-primary">●</span> 파란 점을 누르면 그 자리를 잽니다. 손을 올리면 커집니다.
            </p>
          )}

          {/* 지금 고른 것 */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <p className="text-muted-foreground text-xs">고른 것 {picks.length > 0 && `(${picks.length})`}</p>
              <div className="flex gap-1">
                <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={onUndo} disabled={picks.length === 0}>
                  하나 빼기
                </Button>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={onClear} disabled={picks.length === 0}>
                  비우기
                </Button>
              </div>
            </div>
            {picks.length === 0 ? (
              <p className="text-muted-foreground flex items-center gap-1 rounded-md border border-dashed p-2 text-xs">
                <MousePointerClick className="size-3.5 shrink-0" />
                하나만 골라도 길이 · 넓이 · 지름이 나옵니다.
              </p>
            ) : (
              <ol className="space-y-0.5">
                {picks.map((pick, i) => (
                  <li key={i} className="flex items-center gap-1 text-xs">
                    <Badge variant="outline" className="px-1 py-0 font-mono text-[10px]">
                      {i + 1}
                    </Badge>
                    <span>{title(pick, i + 1)}</span>
                    <span className="text-muted-foreground ml-auto truncate font-mono text-[10px]">
                      {anchor(pick)
                        .map((v) => Math.round(v * 10) / 10)
                        .join(', ')}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>

          {/* 잰 값 */}
          {rows.length > 0 && (
            <div className="bg-muted/40 space-y-1 rounded-md border p-2">
              {rows.map((row) => (
                <RowLine key={row.label} row={row} />
              ))}
              <div className="flex justify-end pt-1">
                <Button size="sm" className="h-7 text-xs" onClick={onKeep} disabled={picks.length === 0}>
                  담기 — 3D 에 남깁니다
                </Button>
              </div>
            </div>
          )}

          {picks.length === 1 && <p className="text-muted-foreground text-xs">하나 더 고르면 거리 · 각도가 나옵니다.</p>}
          {full && <p className="text-muted-foreground text-xs">점을 셋 고르면 가운데 점의 각도를 잽니다.</p>}

          {/* 담아 둔 것 */}
          {kept.length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1 text-xs">담아 둔 측정 ({kept.length})</p>
              <ul className="space-y-0.5">
                {kept.map((one) => (
                  <li key={one.id} className="flex items-center gap-1 text-xs">
                    <span className="truncate">{one.label}</span>
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-destructive ml-auto rounded p-0.5"
                      aria-label={`${one.label} 지우기`}
                      onClick={() => onDropKept(one.id)}
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={onClose}>
            <X className="size-3.5" /> 측정 끝내기
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** 담은 것의 이름 — 목록에 한 줄로 보인다. */
export function keptLabel(picks: Pick[]): string {
  const what = picks.map((pick, i) => title(pick, i + 1)).join(' ↔ ')
  return `${what} : ${headline(measurement(picks).rows)}`
}
