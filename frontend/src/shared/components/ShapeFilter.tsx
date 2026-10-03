/**
 * 형상으로 거르기 — **한 벌만 둔다**(내 작업 · 부품 · 지그가 같은 물음에 답한다).
 *
 * 이름이 아니라 형상으로: 「구멍이 있는 것」 · 「M6」 · 「100 x 60 x 30 안에 드는 것」 ·
 * 「Ø6.6 구멍 4 개 이상」 · 「판금」. 서버가 최신 버전의 형상 색인으로 거른다
 * (`shared/shape_search.py`) — 형상을 다시 만들지 않는다.
 */

import { Shapes } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

/** 목록 한 줄에 붙는 형상 색인 — 서버 `core/shape_index.py`. */
export interface ShapeIndex {
  size: number[]
  dims: number[]
  volume: number
  solids: number
  holes: { d: number; n: number; through: number }[]
  hole_count: number
  ops: string[]
  threads: string[]
  params: string[]
}

/** 형상 조건 — 비운 칸은 안 거른다. */
export interface ShapeQuery {
  has?: string[]
  thread?: string
  param?: string
  /** 「이 상자 안에」 — `100x60x30` · `100x60`. */
  fits?: string
  /** 부피 범위(cm³) — 사람이 읽기 쉬운 단위로 받고 서버에는 mm³ 로. */
  volumeMin?: number | null
  volumeMax?: number | null
  hole?: number | null
  holes?: number | null
}

/** 들어 있는 것 — 서버 `shape_index.FEATURES` 의 낱말. */
export const FEATURE_LABELS: { value: string; label: string }[] = [
  { value: 'hole', label: '구멍' },
  { value: 'sheet_metal', label: '판금' },
  { value: 'frame', label: '프레임' },
  { value: 'fillet', label: '필렛' },
  { value: 'chamfer', label: '모따기' },
  { value: 'pattern', label: '패턴' },
  { value: 'fastener', label: '체결품' },
  { value: 'assembly', label: '조립' },
  { value: 'step', label: 'STEP' },
]

const THREADS = ['M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12']

/** 몇 가지 조건을 걸었나 — 단추에 적는다. */
export function shapeConditionCount(shape: ShapeQuery | null | undefined): number {
  if (!shape) return 0
  return (
    (shape.has?.length ?? 0) +
    [shape.thread, shape.param, shape.fits].filter(Boolean).length +
    [shape.volumeMin, shape.volumeMax, shape.hole, shape.holes].filter((one) => one != null).length
  )
}

/** 목록 API 의 쿼리에 형상 조건을 붙인다. */
export function addShapeParams(query: URLSearchParams, shape: ShapeQuery | null | undefined) {
  if (!shape) return
  for (const one of shape.has ?? []) query.append('has', one)
  if (shape.thread) query.set('thread', shape.thread)
  if (shape.param) query.set('param', shape.param)
  if (shape.fits) query.set('fits', shape.fits)
  if (shape.volumeMin != null) query.set('volume_min', String(shape.volumeMin * 1000))
  if (shape.volumeMax != null) query.set('volume_max', String(shape.volumeMax * 1000))
  if (shape.hole != null) query.set('hole', String(shape.hole))
  if (shape.holes != null) query.set('holes', String(shape.holes))
}

const round = (value: number) => String(+value.toFixed(1))

/** 목록 한 줄에 — 「120 × 40 × 8 · 구멍 Ø6.6×2 Ø5」. */
export function describeShape(shape: ShapeIndex | null | undefined): string {
  if (!shape) return ''
  const size = shape.size.map(round).join(' × ')
  const holes = shape.holes
    .slice(0, 3)
    .map((one) => `Ø${round(one.d)}${one.n > 1 ? `×${one.n}` : ''}`)
    .join(' ')
  const more = shape.holes.length > 3 ? ' …' : ''
  return holes ? `${size} · 구멍 ${holes}${more}` : size
}

function numberOrNull(text: string): number | null {
  const value = Number(text)
  return text.trim() === '' || !Number.isFinite(value) ? null : value
}

export function ShapeFilter({ value, onChange }: { value: ShapeQuery; onChange: (next: ShapeQuery) => void }) {
  const [open, setOpen] = useState(false)
  // 고치는 동안은 화면 안에서만 — 「적용」 을 눌러야 목록을 다시 부른다(글자마다 부르지 않게).
  const [draft, setDraft] = useState<ShapeQuery>(value)
  const count = shapeConditionCount(value)
  const set = (patch: Partial<ShapeQuery>) => setDraft((now) => ({ ...now, ...patch }))
  const toggle = (feature: string) => {
    const now = draft.has ?? []
    set({ has: now.includes(feature) ? now.filter((one) => one !== feature) : [...now, feature] })
  }
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) setDraft(value)
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-pressed={count > 0}
          className={`flex items-center gap-1 rounded-md border px-3 py-1 text-sm ${count > 0 ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}
        >
          <Shapes className="size-3.5" /> 형상{count > 0 ? ` ${count}` : ''}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 space-y-3 p-3 text-sm" aria-label="형상 조건">
        <div>
          <p className="text-muted-foreground mb-1 text-xs">들어 있는 것 (모두)</p>
          <div className="flex flex-wrap gap-1">
            {FEATURE_LABELS.map((one) => (
              <button
                key={one.value}
                type="button"
                aria-pressed={draft.has?.includes(one.value) ?? false}
                onClick={() => toggle(one.value)}
                className={`rounded-full border px-2 py-0.5 text-xs ${draft.has?.includes(one.value) ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}
              >
                {one.label}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs">
            <span className="text-muted-foreground">나사</span>
            <select aria-label="나사 호칭" className="bg-background mt-0.5 h-8 w-full rounded-md border px-1" value={draft.thread ?? ''} onChange={(e) => set({ thread: e.target.value })}>
              <option value="">—</option>
              {THREADS.map((one) => (
                <option key={one}>{one}</option>
              ))}
            </select>
          </label>
          <label className="text-xs">
            <span className="text-muted-foreground">변수 이름</span>
            <Input aria-label="변수 이름" className="mt-0.5 h-8" value={draft.param ?? ''} onChange={(e) => set({ param: e.target.value })} placeholder="두께" />
          </label>
        </div>
        <label className="block text-xs">
          <span className="text-muted-foreground">이 상자 안에 (mm, 방향 무관)</span>
          <Input aria-label="상자 크기" className="mt-0.5 h-8" value={draft.fits ?? ''} onChange={(e) => set({ fits: e.target.value })} placeholder="100x60x30 · 판이면 100x60" />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs">
            <span className="text-muted-foreground">부피 최소 (cm³)</span>
            <Input aria-label="부피 최소" type="number" min={0} className="mt-0.5 h-8" value={draft.volumeMin ?? ''} onChange={(e) => set({ volumeMin: numberOrNull(e.target.value) })} />
          </label>
          <label className="text-xs">
            <span className="text-muted-foreground">부피 최대 (cm³)</span>
            <Input aria-label="부피 최대" type="number" min={0} className="mt-0.5 h-8" value={draft.volumeMax ?? ''} onChange={(e) => set({ volumeMax: numberOrNull(e.target.value) })} />
          </label>
          <label className="text-xs">
            <span className="text-muted-foreground">구멍 지름 (±0.1)</span>
            <Input aria-label="구멍 지름" type="number" min={0} step={0.1} className="mt-0.5 h-8" value={draft.hole ?? ''} onChange={(e) => set({ hole: numberOrNull(e.target.value) })} />
          </label>
          <label className="text-xs">
            <span className="text-muted-foreground">구멍 개수 이상</span>
            <Input aria-label="구멍 개수" type="number" min={1} step={1} className="mt-0.5 h-8" value={draft.holes ?? ''} onChange={(e) => set({ holes: numberOrNull(e.target.value) })} />
          </label>
        </div>
        <p className="text-muted-foreground text-[11px]">최신 버전의 형상으로 거릅니다. 오래전에 만든 것이 안 보이면 관리자가 서버 화면에서 「형상 색인 채우기」 를 누릅니다.</p>
        <div className="flex justify-between gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              onChange({})
              setOpen(false)
            }}
          >
            모두 풀기
          </Button>
          <Button
            size="sm"
            onClick={() => {
              onChange(draft)
              setOpen(false)
            }}
          >
            적용
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
