/**
 * 스케치 캔버스 — 스케치 노드의 도형을 SVG 로 그리고 마우스로 놓고 끈다.
 *
 * 좌표는 스케치 평면의 2D(mm). 화면은 Y 가 아래로 자라므로 뒤집어 그린다. 격자 스냅은 1mm,
 * Shift 를 누르면 5mm. 치수는 오른쪽 폼에서 — 캔버스는 **어디에**, 폼은 **얼마나**.
 */

import { useMemo, useRef, useState } from 'react'
import type { PointerEvent } from 'react'

import { SHAPE_TYPES, defaultShape } from '@/modules/cad/recipeSpec'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'

export type SketchShape = Record<string, unknown> & { type: string; at?: number[]; mode?: string; rotation?: number }

const W = 560
const H = 400

function extent(shapes: SketchShape[]): number {
  let r = 30
  for (const s of shapes) {
    const [x, y] = (s.at as number[]) ?? [0, 0]
    const size = Math.max(
      Number(s.width ?? 0),
      Number(s.height ?? 0),
      Number(s.length ?? 0),
      Number(s.radius ?? 0) * 2,
      ...(((s.points as number[][]) ?? []).flat().map((v) => Math.abs(v) * 2)),
    )
    r = Math.max(r, Math.abs(x) + size / 2 + 10, Math.abs(y) + size / 2 + 10)
  }
  return r
}

function ShapeSvg({ shape, selected, onPointerDown }: { shape: SketchShape; selected: boolean; onPointerDown: (e: PointerEvent) => void }) {
  const [x, y] = (shape.at as number[]) ?? [0, 0]
  const rot = Number(shape.rotation ?? 0)
  const cut = shape.mode === 'cut'
  const common = {
    fill: cut ? 'rgba(239,68,68,0.15)' : 'rgba(59,130,246,0.2)',
    stroke: selected ? '#f59e0b' : cut ? '#ef4444' : '#3b82f6',
    strokeWidth: selected ? 0.8 : 0.4,
    vectorEffect: 'non-scaling-stroke' as const,
    style: { cursor: 'move' },
    onPointerDown,
  }
  // y 를 뒤집는 변환은 바깥 <g> 가 한다. 회전은 도형 중심 기준.
  const transform = `translate(${x} ${y}) rotate(${rot})`
  switch (shape.type) {
    case 'circle':
      return <circle cx={x} cy={y} r={Number(shape.radius)} {...common} />
    case 'rect': {
      const w = Number(shape.width), h = Number(shape.height)
      return <rect x={-w / 2} y={-h / 2} width={w} height={h} transform={transform} {...common} />
    }
    case 'slot': {
      const l = Number(shape.length), w = Number(shape.width)
      return <rect x={-l / 2} y={-w / 2} width={l} height={w} rx={w / 2} transform={transform} {...common} />
    }
    case 'regular_polygon': {
      const r = Number(shape.radius), n = Number(shape.sides)
      const pts = Array.from({ length: n }, (_, i) => {
        const a = (Math.PI * 2 * i) / n
        return `${(r * Math.cos(a)).toFixed(3)},${(r * Math.sin(a)).toFixed(3)}`
      }).join(' ')
      return <polygon points={pts} transform={transform} {...common} />
    }
    case 'polygon': {
      const pts = ((shape.points as number[][]) ?? []).map(([px, py]) => `${px},${py}`).join(' ')
      return <polygon points={pts} transform={transform} {...common} />
    }
    default:
      return null
  }
}

export function SketchCanvas({
  shapes,
  onChange,
}: {
  shapes: SketchShape[]
  onChange: (next: SketchShape[]) => void
}) {
  const [selected, setSelected] = useState<number | null>(shapes.length ? 0 : null)
  const [tool, setTool] = useState<string>('select')
  const svg = useRef<SVGSVGElement | null>(null)
  const drag = useRef<{ index: number; startX: number; startY: number; atX: number; atY: number } | null>(null)
  const half = useMemo(() => extent(shapes), [shapes])
  const scale = Math.min(W, H) / (half * 2)

  function toWorld(event: PointerEvent): [number, number] {
    const box = svg.current!.getBoundingClientRect()
    const px = ((event.clientX - box.left) / box.width) * W
    const py = ((event.clientY - box.top) / box.height) * H
    return [(px - W / 2) / scale, -(py - H / 2) / scale]
  }
  const snap = (v: number, fine: boolean) => Math.round(v / (fine ? 1 : 5)) * (fine ? 1 : 5)

  function update(index: number, patch: Record<string, unknown>) {
    onChange(shapes.map((s, i) => (i === index ? { ...s, ...patch } : s)))
  }

  function onCanvasDown(event: PointerEvent) {
    if (tool === 'select') {
      setSelected(null)
      return
    }
    const [x, y] = toWorld(event)
    const made = { ...defaultShape(tool), at: [snap(x, !event.shiftKey), snap(y, !event.shiftKey)] } as SketchShape
    onChange([...shapes, made])
    setSelected(shapes.length)
    setTool('select')
  }

  function onShapeDown(index: number, event: PointerEvent) {
    event.stopPropagation()
    setSelected(index)
    const [x, y] = toWorld(event)
    const [ax, ay] = (shapes[index].at as number[]) ?? [0, 0]
    drag.current = { index, startX: x, startY: y, atX: ax, atY: ay }
    ;(event.target as Element).setPointerCapture?.(event.pointerId)
  }

  function onMove(event: PointerEvent) {
    if (!drag.current) return
    const [x, y] = toWorld(event)
    const fine = !event.shiftKey
    update(drag.current.index, {
      at: [snap(drag.current.atX + x - drag.current.startX, fine), snap(drag.current.atY + y - drag.current.startY, fine)],
    })
  }
  function onUp() {
    drag.current = null
  }

  const current = selected !== null ? shapes[selected] : null
  const gridStep = half > 100 ? 20 : half > 40 ? 10 : 5
  const gridLines: number[] = []
  for (let v = -Math.ceil(half / gridStep) * gridStep; v <= half; v += gridStep) gridLines.push(v)

  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <div className="mb-2 flex flex-wrap items-center gap-1">
          <Button size="sm" variant={tool === 'select' ? 'default' : 'outline'} onClick={() => setTool('select')}>
            선택 · 이동
          </Button>
          {SHAPE_TYPES.map((t) => (
            <Button key={t.value} size="sm" variant={tool === t.value ? 'default' : 'outline'} onClick={() => setTool(t.value)}>
              + {t.label}
            </Button>
          ))}
          <span className="text-muted-foreground ml-2 text-xs">
            {tool === 'select' ? '도형을 끌어 옮깁니다. 격자 1mm, Shift 로 5mm.' : '캔버스를 눌러 놓습니다.'}
          </span>
        </div>
        <svg
          ref={svg}
          viewBox={`0 0 ${W} ${H}`}
          className="bg-muted/40 w-full touch-none rounded-md border"
          style={{ aspectRatio: `${W} / ${H}`, cursor: tool === 'select' ? 'default' : 'crosshair' }}
          onPointerDown={onCanvasDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerLeave={onUp}
        >
          {/* 세계 → 화면: 중심을 가운데로, Y 뒤집기 */}
          <g transform={`translate(${W / 2} ${H / 2}) scale(${scale} ${-scale})`}>
            {gridLines.map((v) => (
              <g key={v}>
                <line x1={v} y1={-half} x2={v} y2={half} stroke="#9ca3af" strokeWidth={v === 0 ? 0.6 : 0.2} vectorEffect="non-scaling-stroke" opacity={0.5} />
                <line x1={-half} y1={v} x2={half} y2={v} stroke="#9ca3af" strokeWidth={v === 0 ? 0.6 : 0.2} vectorEffect="non-scaling-stroke" opacity={0.5} />
              </g>
            ))}
            {shapes.map((shape, i) => (
              <ShapeSvg key={i} shape={shape} selected={i === selected} onPointerDown={(e) => onShapeDown(i, e)} />
            ))}
          </g>
          <text x={6} y={H - 6} fontSize={11} fill="#6b7280">
            격자 {gridStep} mm · 보이는 범위 ±{half.toFixed(0)} mm
          </text>
        </svg>
      </div>

      <div className="space-y-2">
        {current ? (
          <ShapeForm
            shape={current}
            onChange={(patch) => update(selected!, patch)}
            onDelete={() => {
              onChange(shapes.filter((_, i) => i !== selected))
              setSelected(null)
            }}
            onMove={(dir) => {
              const j = selected! + dir
              if (j < 0 || j >= shapes.length) return
              const next = [...shapes]
              ;[next[selected!], next[j]] = [next[j], next[selected!]]
              onChange(next)
              setSelected(j)
            }}
          />
        ) : (
          <p className="text-muted-foreground text-sm">도형을 누르면 치수를 고칠 수 있습니다. 순서가 곧 더하고 빼는 순서입니다.</p>
        )}
      </div>
    </div>
  )
}

function ShapeForm({
  shape,
  onChange,
  onDelete,
  onMove,
}: {
  shape: SketchShape
  onChange: (patch: Record<string, unknown>) => void
  onDelete: () => void
  onMove: (dir: -1 | 1) => void
}) {
  const numberField = (key: string, label: string, step = 0.5) => (
    <div key={key} className="space-y-1">
      <Label htmlFor={`shape-${key}`} className="text-xs">
        {label}
      </Label>
      <Input id={`shape-${key}`} type="number" step={step} value={String(shape[key] ?? '')} onChange={(e) => onChange({ [key]: Number(e.target.value) })} className="h-8" />
    </div>
  )
  const at = (shape.at as number[]) ?? [0, 0]
  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{SHAPE_TYPES.find((t) => t.value === shape.type)?.label ?? shape.type}</span>
        <Select value={String(shape.mode ?? 'add')} onValueChange={(v) => onChange({ mode: v })}>
          <SelectTrigger className="h-7 w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="add">더하기</SelectItem>
            <SelectItem value="cut">빼기</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">X</Label>
          <Input type="number" step={0.5} value={String(at[0])} onChange={(e) => onChange({ at: [Number(e.target.value), at[1]] })} className="h-8" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Y</Label>
          <Input type="number" step={0.5} value={String(at[1])} onChange={(e) => onChange({ at: [at[0], Number(e.target.value)] })} className="h-8" />
        </div>
        {shape.type === 'rect' && (
          <>
            {numberField('width', '너비')}
            {numberField('height', '높이')}
          </>
        )}
        {shape.type === 'circle' && numberField('radius', '반지름')}
        {shape.type === 'slot' && (
          <>
            {numberField('length', '전체 길이')}
            {numberField('width', '폭')}
          </>
        )}
        {shape.type === 'regular_polygon' && (
          <>
            {numberField('radius', '외접 반지름')}
            {numberField('sides', '변 수', 1)}
          </>
        )}
        {shape.type !== 'circle' && numberField('rotation', '회전 (°)', 1)}
      </div>
      {shape.type === 'polygon' && (
        <div className="space-y-1">
          <Label className="text-xs">꼭짓점 (중심 기준)</Label>
          {((shape.points as number[][]) ?? []).map((p, i) => (
            <div key={i} className="flex gap-1">
              <Input type="number" step={0.5} value={String(p[0])} onChange={(e) => onChange({ points: (shape.points as number[][]).map((q, j) => (j === i ? [Number(e.target.value), q[1]] : q)) })} className="h-7" />
              <Input type="number" step={0.5} value={String(p[1])} onChange={(e) => onChange({ points: (shape.points as number[][]).map((q, j) => (j === i ? [q[0], Number(e.target.value)] : q)) })} className="h-7" />
              <button type="button" className="text-muted-foreground px-1 text-xs" onClick={() => onChange({ points: (shape.points as number[][]).filter((_, j) => j !== i) })}>
                ×
              </button>
            </div>
          ))}
          <button type="button" className="text-muted-foreground text-xs hover:underline" onClick={() => onChange({ points: [...((shape.points as number[][]) ?? []), [0, 0]] })}>
            + 꼭짓점
          </button>
        </div>
      )}
      <div className="flex gap-1 pt-1">
        <Button size="sm" variant="outline" onClick={() => onMove(-1)}>
          앞으로
        </Button>
        <Button size="sm" variant="outline" onClick={() => onMove(1)}>
          뒤로
        </Button>
        <div className="flex-1" />
        <Button size="sm" variant="ghost" onClick={onDelete}>
          지우기
        </Button>
      </div>
    </div>
  )
}
