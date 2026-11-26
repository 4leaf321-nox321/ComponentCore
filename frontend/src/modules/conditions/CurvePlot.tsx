/**
 * **곡선 그래프** — 가진 프로파일 · 곡선의 점을 보간 그대로 그린다(해석 확장 설계 4장 「표 칸을 넓혀 그래프를 단다」).
 *
 * - 로그-로그(가속도 PSD)는 두 축 모두 로그 눈금이다 — 규격의 dB/oct 기울기가 직선으로 보여 표의 잘못 친 행이
 *   꺾임으로 드러난다. 선형은 0 을 포함한 세로축, 계단은 다음 점까지 값을 유지한다.
 * - 계열이 하나라 범례 없이 제목이 이름을 대신한다. 값의 정본은 바로 옆의 표다 — 그래프는 모양을 본다.
 * - 가리키면(또는 초점을 두고 ← →) 가장 가까운 점에 십자선과 값이 뜬다.
 * - 식이 든 점은 설계점마다 풀리므로 그리지 않고 몇 개 뺐는지 말한다. 로그 축에 0 이하 점도 그렇다.
 */

import { useId, useState } from 'react'

import { plotPoints } from '@/modules/conditions/curves'

const W = 360
const H = 168
const PAD = { left: 48, right: 20, top: 10, bottom: 32 }

/** 사람이 읽는 수 — 유효숫자 넷. */
function fmt(value: number): string {
  if (value === 0) return '0'
  const abs = Math.abs(value)
  if (abs >= 1e5 || abs < 1e-4) return value.toExponential(1).replace('e+', 'e')
  return String(Number(value.toPrecision(4)))
}

interface Axis {
  log: boolean
  min: number
  max: number
  ticks: number[]
}

/** 선형 축 — 1 · 2 · 5 × 10ⁿ 간격으로 넷쯤. */
function linearAxis(lo: number, hi: number): Axis {
  if (lo === hi) {
    const pad = Math.abs(lo) || 1
    lo -= pad
    hi += pad
  }
  const raw = (hi - lo) / 4
  const base = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * base).find((one) => one >= raw) ?? raw
  const min = Math.floor(lo / step) * step
  const max = Math.ceil(hi / step) * step
  const ticks: number[] = []
  for (let at = min; at <= max + step / 2; at += step) ticks.push(Number(at.toPrecision(12)))
  return { log: false, min, max, ticks }
}

/** 로그 축 — 십진 눈금(10ⁿ). 한 자리 안에 들면 위아래로 한 자리씩 넓힌다. */
function logAxis(lo: number, hi: number): Axis {
  let a = Math.floor(Math.log10(lo))
  let b = Math.ceil(Math.log10(hi))
  if (a === b) {
    a -= 1
    b += 1
  }
  const ticks: number[] = []
  for (let n = a; n <= b; n++) ticks.push(10 ** n)
  // 자리가 많으면(PSD 가 다섯 자리에 걸치면) 눈금이 붙는다 — 하나 걸러.
  const shown = ticks.length > 6 ? ticks.filter((_, i) => i % 2 === 0) : ticks
  return { log: true, min: 10 ** a, max: 10 ** b, ticks: shown }
}

function place(axis: Axis, value: number, from: number, to: number): number {
  const t = axis.log
    ? (Math.log10(value) - Math.log10(axis.min)) / (Math.log10(axis.max) - Math.log10(axis.min))
    : (value - axis.min) / (axis.max - axis.min)
  return from + t * (to - from)
}

export function CurvePlot({
  title,
  points,
  scale = 1,
  interpolation = 'linear',
  xLabel,
  yLabel,
}: {
  /** 그래프의 이름 — 화면 읽기 프로그램에 「가속도 PSD 그래프」 로. */
  title: string
  points: unknown
  /** 모든 값에 곱한다(곡선의 배율). 식이면 모양만 그린다. */
  scale?: unknown
  interpolation?: string
  /** 축 이름표 — 「주파수 (Hz)」. */
  xLabel: string
  yLabel: string
}) {
  const [active, setActive] = useState<number | null>(null)
  const clip = useId()
  const log = interpolation === 'loglog'
  const got = plotPoints(points, scale)
  // 로그 축은 0 이하를 그릴 수 없다 — 빼고 센다.
  const drawable = log ? got.points.filter(([x, y]) => x > 0 && y > 0) : got.points
  const dropped = got.skipped + (got.points.length - drawable.length)
  const notes = [
    dropped > 0 ? `${dropped}개 점은 ${log ? '식이거나 0 이하라' : '식이라'} 그리지 않았습니다.` : '',
    got.scaled ? '' : '배율이 식이라 모양만 표시합니다.',
  ].filter(Boolean)

  if (drawable.length < 2) {
    return <p className="text-muted-foreground text-xs">점이 두 개 이상 있으면 그래프가 표시됩니다.{notes.length > 0 ? ` ${notes.join(' ')}` : ''}</p>
  }

  const xs = drawable.map(([x]) => x)
  const ys = drawable.map(([, y]) => y)
  const xAxis = log ? logAxis(Math.min(...xs), Math.max(...xs)) : linearAxis(Math.min(...xs), Math.max(...xs))
  // 선형 세로축은 0 을 품는다 — 배율 곡선이 0 에서 얼마나 떨어졌는지가 뜻이다.
  const yAxis = log ? logAxis(Math.min(...ys), Math.max(...ys)) : linearAxis(Math.min(0, ...ys), Math.max(0, ...ys))
  const left = PAD.left
  const right = W - PAD.right
  const top = PAD.top
  const bottom = H - PAD.bottom
  const px = (x: number) => place(xAxis, x, left, right)
  const py = (y: number) => place(yAxis, y, bottom, top)
  const screen = drawable.map(([x, y]) => [px(x), py(y)] as const)
  const path =
    interpolation === 'step'
      ? screen.map(([x, y], i) => (i === 0 ? `M${x},${y}` : `H${x}V${y}`)).join('')
      : screen.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join('')
  const pick = active !== null && active < drawable.length ? active : null

  /** 가리킨 자리에서 가장 가까운 점 — 가로로만 잰다(십자선이 X 를 찾는다). */
  function nearest(event: React.PointerEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect()
    if (box.width === 0) return
    const at = ((event.clientX - box.left) / box.width) * W
    let best = 0
    for (let i = 1; i < screen.length; i++) if (Math.abs(screen[i][0] - at) < Math.abs(screen[best][0] - at)) best = i
    setActive(best)
  }

  const summary = `${title} 그래프 — ${drawable.length}점, 가로 ${fmt(Math.min(...xs))} ~ ${fmt(Math.max(...xs))}, 값 ${fmt(Math.min(...ys))} ~ ${fmt(Math.max(...ys))}${log ? ', 로그-로그 눈금' : ''}`

  return (
    <figure className="space-y-1">
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full touch-none select-none"
          role="img"
          aria-label={summary}
          tabIndex={0}
          onPointerMove={nearest}
          onPointerLeave={() => setActive(null)}
          onBlur={() => setActive(null)}
          onKeyDown={(event) => {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
            event.preventDefault()
            const step = event.key === 'ArrowLeft' ? -1 : 1
            setActive((now) => Math.min(Math.max((now ?? (step > 0 ? -1 : drawable.length)) + step, 0), drawable.length - 1))
          }}
        >
          <defs>
            <clipPath id={clip}>
              <rect x={left} y={top - 4} width={right - left} height={bottom - top + 8} />
            </clipPath>
          </defs>
          {/* 격자 — 옅은 실선. 눈금 글자는 낮은 먹. */}
          {yAxis.ticks.map((tick) => (
            <g key={`y${tick}`}>
              <line x1={left} x2={right} y1={py(tick)} y2={py(tick)} className="stroke-border" strokeWidth={1} />
              <text x={left - 6} y={py(tick)} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-[10px]">
                {fmt(tick)}
              </text>
            </g>
          ))}
          {xAxis.ticks.map((tick) => (
            <g key={`x${tick}`}>
              <line x1={px(tick)} x2={px(tick)} y1={top} y2={bottom} className="stroke-border" strokeWidth={1} />
              <text x={px(tick)} y={bottom + 14} textAnchor="middle" className="fill-muted-foreground text-[10px]">
                {fmt(tick)}
              </text>
            </g>
          ))}
          <text x={(left + right) / 2} y={H - 3} textAnchor="middle" className="fill-muted-foreground text-[10px]">
            {xLabel}
          </text>
          <text x={10} y={(top + bottom) / 2} textAnchor="middle" transform={`rotate(-90 10 ${(top + bottom) / 2})`} className="fill-muted-foreground text-[10px]">
            {yLabel}
          </text>
          <g clipPath={`url(#${clip})`}>
            <path d={path} fill="none" className="stroke-primary" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {screen.map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r={pick === i ? 5 : 4} className="fill-primary stroke-background" strokeWidth={2} />
            ))}
          </g>
          {pick !== null && <line x1={screen[pick][0]} x2={screen[pick][0]} y1={top} y2={bottom} className="stroke-foreground/40" strokeWidth={1} />}
        </svg>
        {pick !== null && (
          <div
            role="status"
            className="bg-popover text-popover-foreground pointer-events-none absolute top-1 rounded border px-1.5 py-0.5 text-xs shadow-sm"
            style={screen[pick][0] > W / 2 ? { right: `${((W - screen[pick][0]) / W) * 100 + 2}%` } : { left: `${(screen[pick][0] / W) * 100 + 2}%` }}
          >
            <span className="font-medium tabular-nums">{fmt(drawable[pick][1])}</span>
            <span className="text-muted-foreground"> {yLabel}</span>
            <span className="text-muted-foreground"> · </span>
            <span className="tabular-nums">{fmt(drawable[pick][0])}</span>
            <span className="text-muted-foreground"> {xLabel}</span>
          </div>
        )}
      </div>
      {notes.length > 0 && <figcaption className="text-muted-foreground text-xs">{notes.join(' ')}</figcaption>}
    </figure>
  )
}
