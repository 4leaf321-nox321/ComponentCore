/**
 * 스케치 캔버스 — 스케치 피처의 도형을 SVG 로 그리고 마우스로 놓고 끈다.
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
      Number(s.x_radius ?? 0) * 2,
      s.type === 'triangle' ? Math.max(Number(s.a ?? 0), Number(s.b ?? 0), Number(s.c ?? 0)) * 2 : 0,
      Number(s.y_radius ?? 0) * 2,
      s.type === 'text' ? String(s.text ?? '').length * Number(s.size ?? 0) * 0.7 : 0,
      ...(((s.points as number[][]) ?? []).flat().map((v) => Math.abs(v) * 2)),
      ...polylinePoints(s).flat().map((v) => Math.abs(v) * 2),
    )
    r = Math.max(r, Math.abs(x) + size / 2 + 10, Math.abs(y) + size / 2 + 10)
  }
  return r
}

type Segment = { to: number[]; via?: number[] | null; radius?: number | null; tangent?: boolean }

/**
 * 변 · 각 셋으로 삼각형을 푼다 — 캔버스에 그리려고. 서버(build123d Triangle)와 같은 규칙:
 * 변 a 의 맞은편이 각 A 이고, 무게중심이 원점에 온다. 못 풀면 null(3D 미리보기로 확인).
 */
function solveTriangle(shape: SketchShape): number[][] | null {
  const v: Record<string, number | null> = {}
  for (const key of ['a', 'b', 'c', 'A', 'B', 'C']) {
    const raw = shape[key]
    v[key] = raw === null || raw === undefined || raw === '' ? null : Number(raw)
  }
  const rad = (deg: number) => (deg * Math.PI) / 180
  for (let round = 0; round < 4; round += 1) {
    const angles = (['A', 'B', 'C'] as const).filter((k) => v[k] != null)
    if (angles.length === 2) {
      const missing = (['A', 'B', 'C'] as const).find((k) => v[k] == null)!
      v[missing] = 180 - angles.reduce((sum, k) => sum + (v[k] as number), 0)
    }
    // 사인 법칙 — 마주 보는 변 · 각 한 쌍을 알면 나머지를 뽑는다.
    const pair = (['a', 'b', 'c'] as const).find((side, i) => v[side] != null && v[['A', 'B', 'C'][i]] != null)
    if (pair) {
      const angleKey = { a: 'A', b: 'B', c: 'C' }[pair]
      const k = (v[pair] as number) / Math.sin(rad(v[angleKey] as number))
      for (const [side, angle] of [['a', 'A'], ['b', 'B'], ['c', 'C']]) {
        if (v[side] == null && v[angle] != null) v[side] = k * Math.sin(rad(v[angle] as number))
        if (v[angle] == null && v[side] != null) v[angle] = (Math.asin(Math.min(1, (v[side] as number) / k)) * 180) / Math.PI
      }
    }
    // 코사인 법칙 — 두 변과 낀각, 또는 세 변.
    if (v.a != null && v.b != null && v.C != null && v.c == null) {
      v.c = Math.sqrt(v.a ** 2 + v.b ** 2 - 2 * v.a * v.b * Math.cos(rad(v.C)))
    }
    if (v.a != null && v.b != null && v.c != null && v.C == null) {
      v.C = (Math.acos((v.a ** 2 + v.b ** 2 - v.c ** 2) / (2 * v.a * v.b)) * 180) / Math.PI
    }
    if (v.a != null && v.b != null && v.C != null) break
  }
  const { a, b, C } = v
  if (a == null || b == null || C == null || !Number.isFinite(a + b + C)) return null
  // v0 →(a)→ v1 →(b, 낀각 C)→ v2. 무게중심을 원점으로 옮긴다.
  const points = [
    [0, 0],
    [a, 0],
    [a + b * Math.cos(Math.PI - rad(C)), b * Math.sin(Math.PI - rad(C))],
  ]
  const cx = (points[0][0] + points[1][0] + points[2][0]) / 3
  const cy = (points[0][1] + points[1][1] + points[2][1]) / 3
  return points.map(([x, y]) => [x - cx, y - cy])
}

/** 구간의 「지나는 점」 — 서버와 같은 호를 그리려고 반지름 · 접선을 via 로 바꿔 계산한다. */
function viaOf(from: number[], segment: Segment, direction: number[] | null): number[] | null {
  if (segment.via) return segment.via
  const [dx, dy] = [segment.to[0] - from[0], segment.to[1] - from[1]]
  const span = Math.hypot(dx, dy)
  if (span < 1e-6) return null
  const mid = [(from[0] + segment.to[0]) / 2, (from[1] + segment.to[1]) / 2]
  if (segment.radius) {
    const r = Math.abs(segment.radius)
    if (r < span / 2) return null
    // 현의 왼쪽(진행 방향 기준)이 양수 반지름 — build123d 의 RadiusArc 와 같다.
    const sagitta = r - Math.sqrt(Math.max(r * r - (span / 2) * (span / 2), 0))
    const left = [-dy / span, dx / span]
    const sign = segment.radius > 0 ? 1 : -1
    return [mid[0] + left[0] * sagitta * sign, mid[1] + left[1] * sagitta * sign]
  }
  if (segment.tangent && direction) {
    // 시작에서 direction 에 접하고 to 를 지나는 원 — 중심은 시작점의 법선 위에 있다.
    const len = Math.hypot(direction[0], direction[1]) || 1
    const t = [direction[0] / len, direction[1] / len]
    const n = [-t[1], t[0]]
    const denominator = 2 * (dx * n[0] + dy * n[1])
    if (Math.abs(denominator) < 1e-9) return null // 직선과 다름없다
    const r = (dx * dx + dy * dy) / denominator
    const center = [from[0] + n[0] * r, from[1] + n[1] * r]
    const toMid = [mid[0] - center[0], mid[1] - center[1]]
    const toMidLen = Math.hypot(toMid[0], toMid[1]) || 1
    return [center[0] + (toMid[0] / toMidLen) * Math.abs(r), center[1] + (toMid[1] / toMidLen) * Math.abs(r)]
  }
  return null
}

/** 구간이 끝나는 방향 — 다음 접선 호가 쓴다. */
function directionAt(from: number[], segment: Segment, via: number[] | null): number[] {
  if (!via) return [segment.to[0] - from[0], segment.to[1] - from[1]]
  return [segment.to[0] - via[0], segment.to[1] - via[1]]
}

function polylinePoints(s: SketchShape): number[][] {
  if (s.type !== 'polyline' && s.type !== 'path') return []
  const start = (s.start as number[]) ?? [0, 0]
  const segs = (s.segments as Segment[]) ?? []
  const out = [start]
  let cursor = start
  let direction: number[] | null = null
  for (const g of segs) {
    const via = viaOf(cursor, g, direction)
    if (via) out.push(via)
    out.push(g.to)
    direction = directionAt(cursor, g, via)
    cursor = g.to
  }
  return out
}

/** 세 점을 지나는 호의 SVG path 조각. 세 점이 한 직선이면 그냥 선. */
function arcTo(from: number[], via: number[], to: number[]): string {
  const [ax, ay] = from, [bx, by] = via, [cx, cy] = to
  const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
  if (Math.abs(d) < 1e-9) return `L ${cx} ${cy}`
  const ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
  const uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
  const r = Math.hypot(ax - ux, ay - uy)
  // via 가 현의 어느 쪽에 있나 → sweep. 호가 반원보다 큰가 → large-arc.
  const cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
  const sweep = cross < 0 ? 1 : 0
  const crossC = (cx - ax) * (uy - ay) - (cy - ay) * (ux - ax)
  const large = (crossC < 0) === (cross < 0) ? 0 : 1
  return `A ${r} ${r} 0 ${large} ${sweep} ${cx} ${cy}`
}

function polylinePath(s: SketchShape, close = true): string {
  const start = (s.start as number[]) ?? [0, 0]
  const segs = (s.segments as Segment[]) ?? []
  let cursor = start
  let direction: number[] | null = null
  let d = `M ${start[0]} ${start[1]}`
  for (const g of segs) {
    const via = viaOf(cursor, g, direction)
    d += via ? ' ' + arcTo(cursor, via, g.to) : ` L ${g.to[0]} ${g.to[1]}`
    direction = directionAt(cursor, g, via)
    cursor = g.to
  }
  return close ? d + ' Z' : d
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
      const w = Number(shape.width)
      // 중심 사이 기준이면 양 끝 반원이 더 붙는다 — 서버(SlotCenterToCenter)와 같게.
      const l = Number(shape.length) + (shape.measure === 'centers' ? w : 0)
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
    case 'polyline':
      return <path d={polylinePath(shape)} transform={transform} {...common} />
    case 'path':
      // 중심선을 폭만큼 굵게 — 끝은 둥글고 모서리는 고른 대로. 서버가 만드는 면과 같은 모양.
      return (
        <path
          d={polylinePath(shape, false)}
          transform={transform}
          {...common}
          fill="none"
          stroke={common.fill}
          strokeWidth={Number(shape.width)}
          strokeLinecap="round"
          strokeLinejoin={shape.corners === 'sharp' ? 'miter' : 'round'}
          vectorEffect={undefined}
          style={{ cursor: 'move', outline: selected ? '1px solid #f59e0b' : undefined }}
        />
      )
    case 'ellipse':
      return <ellipse rx={Number(shape.x_radius)} ry={Number(shape.y_radius)} transform={transform} {...common} />
    case 'rounded_rect': {
      const w = Number(shape.width), h = Number(shape.height)
      return <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={Number(shape.radius)} transform={transform} {...common} />
    }
    case 'triangle': {
      const pts = solveTriangle(shape)
      if (!pts) return null
      return <polygon points={pts.map(([px, py]) => `${px},${py}`).join(' ')} transform={transform} {...common} />
    }
    case 'trapezoid': {
      // 밑변이 width, 빗변 각도만큼 윗변이 좁아진다 — 서버(Trapezoid)와 같은 규칙.
      const w = Number(shape.width), h = Number(shape.height)
      const left = (Number(shape.left_angle ?? 75) * Math.PI) / 180
      const right = ((Number(shape.right_angle ?? shape.left_angle ?? 75)) * Math.PI) / 180
      const dl = h / Math.tan(left), dr = h / Math.tan(right)
      const pts = [
        [-w / 2, -h / 2],
        [w / 2, -h / 2],
        [w / 2 - dr, h / 2],
        [-w / 2 + dl, h / 2],
      ]
      return <polygon points={pts.map(([px, py]) => `${px},${py}`).join(' ')} transform={transform} {...common} />
    }
    case 'text': {
      // 바깥 <g> 가 y 를 뒤집으니 글자는 다시 뒤집는다. 실제 글꼴 모양은 서버가 정한다 — 자리만.
      const size = Number(shape.size)
      return (
        <text
          transform={`${transform} scale(1 -1)`}
          fontSize={size}
          textAnchor="middle"
          dominantBaseline="middle"
          fontWeight={shape.bold ? 700 : 400}
          fontFamily="sans-serif"
          {...common}
          fill={cut ? 'rgba(239,68,68,0.5)' : 'rgba(59,130,246,0.6)'}
        >
          {String(shape.text ?? '')}
        </text>
      )
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
  /** 임의 윤곽을 찍는 중 — 찍은 점들(스케치 좌표). 두 번 누르거나 「닫기」 로 끝난다. */
  const [drafting, setDrafting] = useState<number[][] | null>(null)
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

  function finishPolyline() {
    const need = tool === 'path' ? 2 : 3
    if (drafting && drafting.length >= need) {
      const [sx, sy] = drafting[0]
      const made = {
        ...defaultShape(tool),
        type: tool,
        at: [0, 0],
        start: [sx, sy],
        segments: drafting.slice(1).map((pt) => ({ to: pt })),
      } as SketchShape
      onChange([...shapes, made])
      setSelected(shapes.length)
    }
    setDrafting(null)
    setTool('select')
  }

  function onCanvasDown(event: PointerEvent) {
    if (tool === 'select') {
      setSelected(null)
      return
    }
    if (tool === 'polyline' || tool === 'path') {
      const [px, py] = toWorld(event)
      const point = [snap(px, !event.shiftKey), snap(py, !event.shiftKey)]
      const last = drafting?.[drafting.length - 1]
      if (last && last[0] === point[0] && last[1] === point[1]) {
        finishPolyline() // 같은 자리를 두 번 → 끝
        return
      }
      setDrafting([...(drafting ?? []), point])
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
          {tool === 'polyline' && drafting && drafting.length >= 3 && (
            <Button size="sm" variant="secondary" onClick={finishPolyline}>
              윤곽 닫기 ({drafting.length}점)
            </Button>
          )}
          {tool === 'path' && drafting && drafting.length >= 2 && (
            <Button size="sm" variant="secondary" onClick={finishPolyline}>
              선 끝내기 ({drafting.length}점)
            </Button>
          )}
          <span className="text-muted-foreground ml-2 text-xs">
            {tool === 'select'
              ? '도형을 끌어 옮깁니다. 격자 1mm, Shift 로 5mm.'
              : tool === 'polyline' || tool === 'path'
                ? '점을 차례로 누릅니다. 같은 자리를 다시 누르거나 단추로 끝. 호는 폼에서.'
                : '캔버스를 눌러 놓습니다.'}
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
            {drafting && (
              <g>
                <polyline points={drafting.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="#f59e0b" strokeWidth={0.6} vectorEffect="non-scaling-stroke" strokeDasharray="2 1" />
                {drafting.map(([x, y], i) => (
                  <circle key={i} cx={x} cy={y} r={1.2 / scale} fill="#f59e0b" />
                ))}
              </g>
            )}
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
            {numberField('length', shape.measure === 'centers' ? '중심 사이 거리' : '전체 길이')}
            {numberField('width', '폭')}
            <div className="space-y-1">
              <Label className="text-xs">길이 기준</Label>
              <Select value={String(shape.measure ?? 'overall')} onValueChange={(v) => onChange({ measure: v })}>
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="overall">전체 길이</SelectItem>
                  <SelectItem value="centers">중심 사이</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </>
        )}
        {shape.type === 'triangle' && (
          <>
            {numberField('a', '변 a (A 의 맞은편)')}
            {numberField('b', '변 b')}
            {numberField('c', '변 c')}
            {numberField('A', '각 A (°)', 1)}
            {numberField('B', '각 B (°)', 1)}
            {numberField('C', '각 C (°)', 1)}
            <p className="text-muted-foreground col-span-2 text-[11px]">셋을 주면 정해집니다. 비운 칸은 빈 채로 두세요 — 변은 하나 이상.</p>
          </>
        )}
        {shape.type === 'regular_polygon' && (
          <>
            {numberField('radius', '외접 반지름')}
            {numberField('sides', '변 수', 1)}
          </>
        )}
        {shape.type === 'rounded_rect' && (
          <>
            {numberField('width', '너비')}
            {numberField('height', '높이')}
            {numberField('radius', '모서리 반지름')}
          </>
        )}
        {shape.type === 'trapezoid' && (
          <>
            {numberField('width', '밑변 너비')}
            {numberField('height', '높이')}
            {numberField('left_angle', '왼쪽 각 (°)', 1)}
            {numberField('right_angle', '오른쪽 각 (°, 비우면 대칭)', 1)}
          </>
        )}
        {shape.type === 'ellipse' && (
          <>
            {numberField('x_radius', 'X 반지름')}
            {numberField('y_radius', 'Y 반지름')}
          </>
        )}
        {shape.type === 'text' && (
          <>
            <div className="col-span-2 space-y-1">
              <Label htmlFor="shape-text" className="text-xs">
                글자
              </Label>
              <Input id="shape-text" value={String(shape.text ?? '')} onChange={(e) => onChange({ text: e.target.value })} className="h-8" />
            </div>
            {numberField('size', '글자 높이 (mm)')}
            <label className="flex items-end gap-1 pb-2 text-xs">
              <input type="checkbox" checked={Boolean(shape.bold)} onChange={(e) => onChange({ bold: e.target.checked })} />
              굵게
            </label>
          </>
        )}
        {shape.type === 'polyline' && numberField('corner_radius', '모서리 둥글리기 (mm, 0 = 각지게)')}
        {shape.type === 'path' && (
          <>
            {numberField('width', '폭 (mm)')}
            <div className="space-y-1">
              <Label className="text-xs">모서리</Label>
              <Select value={String(shape.corners ?? 'round')} onValueChange={(v) => onChange({ corners: v })}>
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="round">둥글게</SelectItem>
                  <SelectItem value="sharp">뾰족하게</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </>
        )}
        {shape.type !== 'circle' && numberField('rotation', '회전 (°)', 1)}
      </div>
      {(shape.type === 'polyline' || shape.type === 'path') && (
        <div className="space-y-1">
          <Label className="text-xs">
            구간 (시작 {((shape.start as number[]) ?? [0, 0]).join(', ')}) — 호는 **반지름** 이나 **접선** 으로 주는 것이 쉽습니다
          </Label>
          {((shape.segments as Segment[]) ?? []).map((g, i) => {
            const segs = shape.segments as Segment[]
            const prev = i === 0 ? ((shape.start as number[]) ?? [0, 0]) : segs[i - 1].to
            const update = (patch: Partial<Segment>) => onChange({ segments: segs.map((q, j) => (j === i ? { ...q, ...patch } : q)) })
            const kind = g.tangent ? 'tangent' : g.radius ? 'radius' : g.via ? 'via' : 'line'
            function setKind(next: string) {
              if (next === 'line') return update({ via: null, radius: null, tangent: false })
              if (next === 'tangent') return update({ via: null, radius: null, tangent: true })
              if (next === 'radius') {
                // 두 점 사이 거리의 0.8 배 — 너무 작으면 호가 닿지 않는다.
                const span = Math.hypot(g.to[0] - prev[0], g.to[1] - prev[1]) || 10
                return update({ via: null, tangent: false, radius: Math.round(span * 0.8 * 10) / 10 })
              }
              // 현의 중점에서 수직으로 20% 띄운 점 — 그 뒤 손으로 고친다.
              const mx = (prev[0] + g.to[0]) / 2, my = (prev[1] + g.to[1]) / 2
              const dx = g.to[0] - prev[0], dy = g.to[1] - prev[1]
              const len = Math.hypot(dx, dy) || 1
              update({ radius: null, tangent: false, via: [Math.round((mx - (dy / len) * len * 0.2) * 10) / 10, Math.round((my + (dx / len) * len * 0.2) * 10) / 10] })
            }
            return (
              <div key={i} className="flex items-center gap-1">
                <span className="text-muted-foreground w-4 text-[10px]">{i + 1}</span>
                <Input type="number" step={0.5} value={String(g.to[0])} onChange={(e) => update({ to: [Number(e.target.value), g.to[1]] })} className="h-7" />
                <Input type="number" step={0.5} value={String(g.to[1])} onChange={(e) => update({ to: [g.to[0], Number(e.target.value)] })} className="h-7" />
                <Select value={kind} onValueChange={setKind}>
                  <SelectTrigger className="h-7 w-24 text-[11px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="line">직선</SelectItem>
                    <SelectItem value="radius">호 · 반지름</SelectItem>
                    <SelectItem value="tangent">호 · 접선</SelectItem>
                    <SelectItem value="via">호 · 지나는 점</SelectItem>
                  </SelectContent>
                </Select>
                {kind === 'radius' && (
                  <Input
                    type="number"
                    step={0.5}
                    value={String(g.radius ?? 0)}
                    onChange={(e) => update({ radius: Number(e.target.value) })}
                    className="h-7 w-20"
                    aria-label={`구간 ${i + 1} 반지름`}
                    title="부호가 휘는 쪽 — 양수는 가는 방향의 왼쪽"
                  />
                )}
                {kind === 'via' && g.via && (
                  <>
                    <Input type="number" step={0.5} value={String(g.via[0])} onChange={(e) => update({ via: [Number(e.target.value), g.via![1]] })} className="h-7 w-16" />
                    <Input type="number" step={0.5} value={String(g.via[1])} onChange={(e) => update({ via: [g.via![0], Number(e.target.value)] })} className="h-7 w-16" />
                  </>
                )}
                <button type="button" className="text-muted-foreground px-1 text-xs" onClick={() => onChange({ segments: segs.filter((_, j) => j !== i) })}>
                  ×
                </button>
              </div>
            )
          })}
          <button
            type="button"
            className="text-muted-foreground text-xs hover:underline"
            onClick={() => {
              const segs = (shape.segments as Segment[]) ?? []
              const last = segs.length ? segs[segs.length - 1].to : ((shape.start as number[]) ?? [0, 0])
              onChange({ segments: [...segs, { to: [last[0] + 10, last[1]] }] })
            }}
          >
            + 구간
          </button>
        </div>
      )}
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
