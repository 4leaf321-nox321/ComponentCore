/**
 * 설계점 분포 — 점들이 변수 공간을 어떻게 채우는지 두 변수씩 흩뿌림으로.
 *
 * LHS · Sobol 이 한쪽으로 몰렸는지, 제약식이 어디를 잘랐는지(걸러진 후보는 옅은 ×), 더한 묶음이
 * 빈 곳을 메웠는지(묶음마다 색), 실패한 점이 범위의 어느 구석에 모였는지(빨간 ×)를 눈으로 본다.
 * 변수가 넷까지면 모든 짝을, 그보다 많으면 고른 두 변수를 그린다. 점을 누르면 그 점을 고른다.
 *
 * 라이브러리 없이 SVG 로 — 설계점은 많아야 수백 개다.
 */

import { useState } from 'react'
import type { ReactNode } from 'react'

type Value = number | string | boolean | null | undefined

export interface ScatterPoint {
  number?: number
  values: Record<string, Value>
  /** ok · failed · pending · rejected(제약에 걸린 후보). */
  status?: 'ok' | 'failed' | 'pending' | 'rejected'
  /** 몇째 묶음(더한 점) — 색을 가른다. */
  batch?: number
}

/** 묶음마다 색 — 첫 묶음은 기본색. */
const BATCH_COLORS = ['#2563eb', '#f59e0b', '#10b981', '#8b5cf6', '#ec4899', '#0ea5e9']
const SIZE = 150
const PAD = 18

/** 축 하나 — 수면 최소 · 최대, 글자(재료 · 고르기)면 차례. */
function axisOf(points: ScatterPoint[], name: string) {
  const raw = points.map((one) => one.values[name])
  const numbers = raw.filter((one): one is number => typeof one === 'number' && Number.isFinite(one))
  if (numbers.length === raw.filter((one) => one !== null && one !== undefined).length && numbers.length > 0) {
    const low = Math.min(...numbers)
    const high = Math.max(...numbers)
    const span = high - low || 1
    return {
      at: (value: Value) => (typeof value === 'number' ? (value - low) / span : null),
      ticks: [String(+low.toPrecision(4)), String(+high.toPrecision(4))],
    }
  }
  const labels = [...new Set(raw.filter((one) => one !== null && one !== undefined).map(String))]
  return {
    at: (value: Value) => (value === null || value === undefined ? null : (labels.indexOf(String(value)) + 0.5) / Math.max(1, labels.length)),
    ticks: labels.length ? [labels[0], labels[labels.length - 1]] : ['', ''],
  }
}

function Plot({
  points,
  x,
  y,
  focus,
  onPick,
}: {
  points: ScatterPoint[]
  x: string
  y: string | null
  focus?: number | null
  onPick?: (number: number) => void
}) {
  const ax = axisOf(points, x)
  const ay = y ? axisOf(points, y) : null
  const inner = SIZE - 2 * PAD
  // 걸러진 후보를 먼저(아래에), 고른 점을 마지막에(위에) 그린다.
  const order = [...points].sort((a, b) => (a.status === 'rejected' ? -1 : 0) - (b.status === 'rejected' ? -1 : 0) || (a.number === focus ? 1 : 0) - (b.number === focus ? 1 : 0))
  return (
    <svg width={SIZE} height={y ? SIZE : 56} className="text-muted-foreground shrink-0 overflow-visible" role="img" aria-label={y ? `${x} 대 ${y}` : x}>
      <rect x={PAD} y={y ? PAD : 14} width={inner} height={y ? inner : 20} fill="none" stroke="currentColor" strokeOpacity={0.25} />
      {order.map((point, index) => {
        const px = ax.at(point.values[x])
        const py = ay && y ? ay.at(point.values[y]) : 0.5
        if (px === null || py === null) return null
        const cx = PAD + px * inner
        const cy = y ? PAD + (1 - py) * inner : 24
        const chosen = point.number !== undefined && point.number === focus
        if (point.status === 'rejected' || point.status === 'failed') {
          const color = point.status === 'failed' ? '#dc2626' : 'currentColor'
          return (
            <g key={index} stroke={color} strokeOpacity={point.status === 'rejected' ? 0.35 : 0.9} strokeWidth={1.2} data-status={point.status}>
              <line x1={cx - 2.5} y1={cy - 2.5} x2={cx + 2.5} y2={cy + 2.5} />
              <line x1={cx - 2.5} y1={cy + 2.5} x2={cx + 2.5} y2={cy - 2.5} />
            </g>
          )
        }
        const color = point.status === 'pending' ? '#9ca3af' : BATCH_COLORS[((point.batch ?? 1) - 1) % BATCH_COLORS.length]
        return (
          <circle
            key={index}
            cx={cx}
            cy={cy}
            r={chosen ? 4.5 : 2.8}
            fill={color}
            stroke={chosen ? '#111827' : 'none'}
            strokeWidth={1.5}
            className={onPick && point.number !== undefined ? 'cursor-pointer' : undefined}
            onClick={() => point.number !== undefined && onPick?.(point.number)}
            data-status={point.status ?? 'ok'}
          >
            {point.number !== undefined && <title>{`p${String(point.number).padStart(4, '0')}`}</title>}
          </circle>
        )
      })}
      <text x={PAD} y={y ? SIZE - 4 : 52} fontSize={9} fill="currentColor">
        {ax.ticks[0]}
      </text>
      <text x={SIZE - PAD} y={y ? SIZE - 4 : 52} fontSize={9} fill="currentColor" textAnchor="end">
        {ax.ticks[1]}
      </text>
      <text x={SIZE / 2} y={y ? SIZE - 4 : 10} fontSize={10} fill="currentColor" textAnchor="middle" className="font-mono">
        {x}
      </text>
      {y && ay && (
        <>
          <text x={4} y={SIZE - PAD} fontSize={9} fill="currentColor">
            {ay.ticks[0]}
          </text>
          <text x={4} y={PAD + 8} fontSize={9} fill="currentColor">
            {ay.ticks[1]}
          </text>
          <text x={10} y={SIZE / 2} fontSize={10} fill="currentColor" textAnchor="middle" transform={`rotate(-90 10 ${SIZE / 2})`} className="font-mono">
            {y}
          </text>
        </>
      )}
    </svg>
  )
}

export function PointsScatter({
  points,
  names,
  focus,
  onPick,
  batches = 1,
}: {
  points: ScatterPoint[]
  /** 그릴 변수(바꾼 것) — 고정은 빼고 준다. */
  names: string[]
  focus?: number | null
  onPick?: (number: number) => void
  /** 묶음 수 — 둘 이상이면 색의 뜻을 적는다. */
  batches?: number
}) {
  const [x, setX] = useState(names[0] ?? '')
  const [y, setY] = useState(names[1] ?? '')
  if (names.length === 0 || points.length === 0) return null
  const pairs: [string, string][] = []
  if (names.length <= 4) for (let i = 0; i < names.length; i += 1) for (let j = i + 1; j < names.length; j += 1) pairs.push([names[i], names[j]])
  const rejected = points.some((one) => one.status === 'rejected')
  const failed = points.some((one) => one.status === 'failed')
  return (
    <div className="space-y-2" aria-label="설계점 분포">
      {names.length > 4 && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">가로</span>
          <select aria-label="가로 변수" className="bg-background rounded border px-1 py-0.5" value={x} onChange={(e) => setX(e.target.value)}>
            {names.map((one) => (
              <option key={one}>{one}</option>
            ))}
          </select>
          <span className="text-muted-foreground">세로</span>
          <select aria-label="세로 변수" className="bg-background rounded border px-1 py-0.5" value={y} onChange={(e) => setY(e.target.value)}>
            {names.map((one) => (
              <option key={one}>{one}</option>
            ))}
          </select>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        {names.length === 1 ? (
          <Plot points={points} x={names[0]} y={null} focus={focus} onPick={onPick} />
        ) : names.length > 4 ? (
          <Plot points={points} x={x} y={y} focus={focus} onPick={onPick} />
        ) : (
          pairs.map(([a, b]) => <Plot key={`${a}|${b}`} points={points} x={a} y={b} focus={focus} onPick={onPick} />)
        )}
      </div>
      <p className="text-muted-foreground flex flex-wrap gap-x-3 text-[11px]">
        {batches > 1 &&
          Array.from({ length: batches }, (_, i) => (
            <span key={i}>
              <span style={{ color: BATCH_COLORS[i % BATCH_COLORS.length] }}>●</span> 묶음 {i + 1}
            </span>
          ))}
        {failed && (
          <span>
            <span className="text-red-600">×</span> 실패
          </span>
        )}
        {rejected && <span>× 제약에 걸린 후보</span>}
      </p>
    </div>
  )
}

/** 접어 둔 칸 — **펼칠 때만** 그린다(설계점이 수백이면 접힌 채 그릴 까닭이 없다). */
export function ScatterDetails({ summary, children }: { summary: string; children: () => ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <details className="rounded-md border px-3 py-2" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer text-xs font-medium">{summary}</summary>
      {open && <div className="pt-2">{children()}</div>}
    </details>
  )
}
