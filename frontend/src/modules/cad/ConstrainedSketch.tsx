/**
 * 구속 윤곽 — 점을 대충 두고 관계 · 치수를 적으면 서버가 점을 맞춘다(`sketch_solver.py`).
 *
 * 캔버스는 **푼 모양**을 그린다 — 그린 자리 그대로 그리면 「길이 60」 을 적어도 그림이 안 바뀌어
 * 구속이 먹었는지 알 수 없다. 점은 이름과 함께 손잡이로 보이고, 끌면 그린 자리가 바뀌어 다시
 * 푼다(정해진 쪽으로는 되돌아오고, 남은 움직임 쪽으로만 따라온다).
 */

import { useEffect, useState } from 'react'
import type { PointerEvent } from 'react'

import { cadApi } from '@/modules/cad/api'
import { NumberField } from '@/modules/cad/NumberField'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'

type XY = (number | string)[]
export interface SketchSegmentSpec {
  from: string
  to: string
  center?: string | null
  ccw?: boolean
}
export interface SketchConstraintSpec {
  type: string
  points?: string[]
  segments?: number[]
  value?: number | string | null
  at?: XY | null
}
export type ConstrainedSpec = Record<string, unknown> & {
  type: 'constrained'
  points: Record<string, XY>
  segments: SketchSegmentSpec[]
  constraints: SketchConstraintSpec[]
}

/** 푼 결과 — 점의 자리와 남은 움직임, 또는 왜 못 풀었나. */
export type Solved = { points: Record<string, number[]>; free: number } | { error: string }

/** 종류 · 고를 것(점 수 · 구간 수) · 값의 뜻 — 서버 `SKETCH_CONSTRAINTS` 와 같다. */
export const CONSTRAINT_KINDS: { value: string; label: string; points: number; segments: number; unit?: string }[] = [
  { value: 'fix', label: '고정', points: 1, segments: 0 },
  { value: 'horizontal', label: '수평', points: 0, segments: 1 },
  { value: 'vertical', label: '수직', points: 0, segments: 1 },
  { value: 'length', label: '길이', points: 0, segments: 1, unit: 'mm' },
  { value: 'distance', label: '거리', points: 2, segments: 0, unit: 'mm' },
  { value: 'dx', label: '가로 거리', points: 2, segments: 0, unit: 'mm' },
  { value: 'dy', label: '세로 거리', points: 2, segments: 0, unit: 'mm' },
  { value: 'angle', label: '각도', points: 0, segments: 2, unit: '°' },
  { value: 'parallel', label: '평행', points: 0, segments: 2 },
  { value: 'perpendicular', label: '직각', points: 0, segments: 2 },
  { value: 'equal', label: '동일 길이', points: 0, segments: 2 },
  { value: 'radius', label: '반지름', points: 0, segments: 1, unit: 'mm' },
  { value: 'tangent', label: '접선', points: 0, segments: 2 },
  { value: 'coincident', label: '일치', points: 2, segments: 0 },
  { value: 'on', label: '선 위의 점', points: 1, segments: 1 },
  { value: 'midpoint', label: '중점', points: 1, segments: 1 },
  { value: 'symmetric', label: '대칭', points: 2, segments: 1 },
]
const KIND = Object.fromEntries(CONSTRAINT_KINDS.map((one) => [one.value, one]))

export function isConstrained(shape: Record<string, unknown>): shape is ConstrainedSpec {
  return shape.type === 'constrained'
}

/** 처음 놓는 구속 윤곽 — 가로 40 · 세로 30 네모, 왼쪽 아래 고정. */
export function defaultConstrained(): Pick<ConstrainedSpec, 'points' | 'segments' | 'constraints'> {
  return {
    points: { a: [0, 0], b: [40, 0], c: [40, 30], d: [0, 30] },
    segments: [
      { from: 'a', to: 'b' },
      { from: 'b', to: 'c' },
      { from: 'c', to: 'd' },
      { from: 'd', to: 'a' },
    ],
    constraints: [
      { type: 'fix', points: ['a'] },
      { type: 'horizontal', segments: [0] },
      { type: 'vertical', segments: [1] },
      { type: 'horizontal', segments: [2] },
      { type: 'vertical', segments: [3] },
      { type: 'length', segments: [0], value: 40 },
      { type: 'length', segments: [1], value: 30 },
    ],
  }
}

/** 그린 자리 — 식이 섞였으면 0(그림이 사라지는 것보다 낫다; 풀이는 서버가 식을 푼다). */
function drawn(shape: ConstrainedSpec): Record<string, number[]> {
  return Object.fromEntries(Object.entries(shape.points ?? {}).map(([name, xy]) => [name, xy.map((v) => (typeof v === 'number' ? v : 0))]))
}

/** 구속 윤곽을 서버에서 푼다 — 고칠 때마다(잠깐 기다렸다가). 도형 번호 → 결과. */
export function useSolvedSketches(shapes: Record<string, unknown>[], params: Record<string, number>): Record<number, Solved> {
  const [solved, setSolved] = useState<Record<number, Solved>>({})
  const key = JSON.stringify([shapes.map((one) => (isConstrained(one) ? one : null)), params])
  useEffect(() => {
    const targets = shapes.map((one, index) => [index, one] as const).filter(([, one]) => isConstrained(one))
    if (targets.length === 0) return
    let alive = true
    const timer = setTimeout(() => {
      void Promise.all(
        targets.map(([index, one]) =>
          cadApi
            .sketchSolve(one, params)
            .then((got): [number, Solved] => [index, got])
            .catch((failure: unknown): [number, Solved] => [index, { error: failure instanceof Error ? failure.message : '구속을 풀지 못했습니다.' }]),
        ),
      ).then((rows) => alive && setSolved(Object.fromEntries(rows)))
    }, 250)
    return () => {
      alive = false
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key 가 도형 · 변수의 내용이다
  }, [key])
  return solved
}

/** 윤곽의 SVG 경로 — 호는 `A`(바깥 그룹이 Y 를 뒤집으니 반시계가 sweep 1). */
export function constrainedPath(shape: ConstrainedSpec, points: Record<string, number[]>): string {
  const parts: string[] = []
  for (const [index, segment] of (shape.segments ?? []).entries()) {
    const a = points[segment.from]
    const b = points[segment.to]
    if (!a || !b) return ''
    if (index === 0) parts.push(`M ${a[0]} ${a[1]}`)
    const c = segment.center ? points[segment.center] : null
    if (!c) {
      parts.push(`L ${b[0]} ${b[1]}`)
      continue
    }
    const r = Math.hypot(a[0] - c[0], a[1] - c[1])
    const start = Math.atan2(a[1] - c[1], a[0] - c[0])
    const end = Math.atan2(b[1] - c[1], b[0] - c[0])
    const ccw = segment.ccw ?? true
    const sweep = ccw ? (end - start + 4 * Math.PI) % (2 * Math.PI) : (start - end + 4 * Math.PI) % (2 * Math.PI)
    parts.push(`A ${r} ${r} 0 ${sweep > Math.PI ? 1 : 0} ${ccw ? 1 : 0} ${b[0]} ${b[1]}`)
  }
  return parts.length ? `${parts.join(' ')} Z` : ''
}

export function ConstrainedSvg({
  shape,
  solved,
  selected,
  scale,
  onPointerDown,
  onPointDown,
}: {
  shape: ConstrainedSpec
  solved?: Solved
  selected: boolean
  scale: number
  onPointerDown: (event: PointerEvent) => void
  onPointDown: (name: string, event: PointerEvent) => void
}) {
  const at = (shape.at as number[]) ?? [0, 0]
  const rot = Number(shape.rotation ?? 0) || 0
  const ok = solved && 'points' in solved
  const points = ok ? solved.points : drawn(shape)
  const cut = shape.mode === 'cut'
  const stroke = solved && 'error' in solved ? '#dc2626' : selected ? '#f59e0b' : cut ? '#ef4444' : '#3b82f6'
  const loop = new Set((shape.segments ?? []).flatMap((one) => [one.from, one.to]))
  return (
    <g transform={`translate(${at[0]} ${at[1]}) rotate(${rot})`} data-solved={ok ? 'yes' : 'no'}>
      <path
        d={constrainedPath(shape, points)}
        fill={cut ? 'rgba(239,68,68,0.15)' : 'rgba(59,130,246,0.2)'}
        stroke={stroke}
        strokeWidth={selected ? 0.8 : 0.4}
        strokeDasharray={ok ? undefined : '2 1'}
        vectorEffect="non-scaling-stroke"
        style={{ cursor: 'move' }}
        onPointerDown={onPointerDown}
      />
      {selected &&
        Object.entries(points).map(([name, [x, y]]) => (
          <g key={name}>
            <circle
              cx={x}
              cy={y}
              r={2.2 / scale}
              fill={loop.has(name) ? '#f59e0b' : '#a855f7'}
              style={{ cursor: 'grab' }}
              onPointerDown={(event) => onPointDown(name, event)}
              aria-label={`점 ${name}`}
            />
            <text x={x + 3 / scale} y={-(y + 3 / scale)} transform="scale(1 -1)" fontSize={10 / scale} fill="#92400e">
              {name}
            </text>
          </g>
        ))}
    </g>
  )
}

function nextName(taken: Record<string, unknown>): string {
  for (let i = 0; ; i += 1) {
    const name = i < 26 ? String.fromCharCode(97 + i) : `p${i}`
    if (!(name in taken)) return name
  }
}

export function ConstrainedForm({
  shape,
  solved,
  params,
  onCreateParam,
  onChange,
}: {
  shape: ConstrainedSpec
  solved?: Solved
  params: Record<string, number>
  onCreateParam?: (name: string, value: number) => void
  onChange: (patch: Partial<ConstrainedSpec>) => void
}) {
  const points = shape.points ?? {}
  const segments = shape.segments ?? []
  const constraints = shape.constraints ?? []
  const names = Object.keys(points)
  const [kind, setKind] = useState('length')

  const segmentLabel = (index: number) => {
    const one = segments[index]
    return one ? `${index}: ${one.from}→${one.to}${one.center ? ` (호 ${one.center})` : ''}` : String(index)
  }

  function setConstraint(index: number, patch: Partial<SketchConstraintSpec>) {
    onChange({ constraints: constraints.map((one, i) => (i === index ? { ...one, ...patch } : one)) })
  }

  function addConstraint() {
    const spec = KIND[kind]
    const made: SketchConstraintSpec = { type: kind }
    if (spec.points) made.points = names.slice(0, spec.points)
    if (spec.segments) made.segments = Array.from({ length: spec.segments }, (_, i) => Math.min(i, segments.length - 1))
    if (spec.unit) made.value = spec.unit === '°' ? 90 : 10
    onChange({ constraints: [...constraints, made] })
  }

  /** 구간 하나를 둘로 — 가운데에 새 점. 구간 번호가 뒤로 밀리니 구속의 번호도 맞춘다. */
  function split(index: number) {
    const one = segments[index]
    const a = points[one.from].map(Number)
    const b = points[one.to].map(Number)
    const name = nextName(points)
    const nextPoints = { ...points, [name]: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] }
    const nextSegments = [...segments.slice(0, index), { from: one.from, to: name }, { from: name, to: one.to }, ...segments.slice(index + 1)]
    const shifted = constraints.map((c) => ({ ...c, segments: c.segments?.map((s) => (s > index ? s + 1 : s)) }))
    onChange({ points: nextPoints, segments: nextSegments, constraints: shifted })
  }

  /** 직선 구간을 호로(가운데 곁에 중심점을 새로) · 호를 직선으로. */
  function toggleArc(index: number) {
    const one = segments[index]
    if (one.center) {
      onChange({ segments: segments.map((s, i) => (i === index ? { from: s.from, to: s.to } : s)) })
      return
    }
    const a = points[one.from].map(Number)
    const b = points[one.to].map(Number)
    const name = nextName(points)
    const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
    const normal = [-(b[1] - a[1]) / 2, (b[0] - a[0]) / 2]
    onChange({
      points: { ...points, [name]: [mid[0] + normal[0], mid[1] + normal[1]] },
      segments: segments.map((s, i) => (i === index ? { ...s, center: name, ccw: false } : s)),
    })
  }

  function adoptSolved() {
    if (!solved || !('points' in solved)) return
    onChange({ points: Object.fromEntries(Object.entries(solved.points).map(([name, xy]) => [name, xy.map((v) => Math.round(v * 1000) / 1000)])) })
  }

  return (
    <div className="space-y-3 text-xs">
      <p role="status" className={solved && 'error' in solved ? 'text-destructive' : 'text-muted-foreground'}>
        {!solved
          ? '계산 중…'
          : 'error' in solved
            ? solved.error
            : solved.free === 0
              ? '완전히 구속되었습니다.'
              : `남은 자유도: ${solved.free}. 점 하나를 고정하고 한 변을 수평 또는 수직으로 구속하면 대개 0이 됩니다.`}
      </p>
      {solved && 'points' in solved && (
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={adoptSolved} title="작성한 점 위치를 계산된 위치로 변경합니다. 다음 계산은 이 위치에서 시작합니다.">
          계산된 위치 적용
        </Button>
      )}

      <div>
        <p className="mb-1 font-medium">점 (작성 위치, 계산 시 이동됨)</p>
        <div className="space-y-1">
          {names.map((name) => (
            <div key={name} className="flex items-center gap-1">
              <span className="w-6 font-mono">{name}</span>
              {[0, 1].map((axis) => (
                <Input
                  key={axis}
                  type="number"
                  aria-label={`점 ${name} ${axis === 0 ? 'X' : 'Y'}`}
                  className="h-7 w-20 text-xs"
                  value={String(points[name][axis] ?? 0)}
                  onChange={(event) => {
                    const xy = [...points[name]]
                    xy[axis] = Number(event.target.value) || 0
                    onChange({ points: { ...points, [name]: xy } })
                  }}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1 font-medium">구간 (닫힌 윤곽)</p>
        <ul className="space-y-1">
          {segments.map((one, index) => (
            <li key={index} className="flex items-center gap-1">
              <span className="w-28 font-mono">{segmentLabel(index)}</span>
              <Button size="sm" variant="ghost" className="h-6 px-1 text-[11px]" onClick={() => split(index)}>
                분할
              </Button>
              <Button size="sm" variant="ghost" className="h-6 px-1 text-[11px]" onClick={() => toggleArc(index)}>
                {one.center ? '직선으로 변경' : '호로 변경'}
              </Button>
              {one.center && (
                <label className="flex items-center gap-0.5">
                  <input type="checkbox" checked={one.ccw ?? true} onChange={(e) => onChange({ segments: segments.map((s, i) => (i === index ? { ...s, ccw: e.target.checked } : s)) })} />
                  반시계 방향
                </label>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="mb-1 font-medium">구속</p>
        <ul className="space-y-1">
          {constraints.map((one, index) => {
            const spec = KIND[one.type]
            return (
              <li key={index} className="flex flex-wrap items-center gap-1 rounded border px-1 py-0.5">
                <span className="w-16">
                  {index + 1}. {spec?.label ?? one.type}
                </span>
                {(one.points ?? []).map((name, k) => (
                  <select
                    key={`p${k}`}
                    aria-label={`구속 ${index + 1} 점 ${k + 1}`}
                    className="bg-background h-6 rounded border px-0.5"
                    value={name}
                    onChange={(e) => setConstraint(index, { points: (one.points ?? []).map((p, j) => (j === k ? e.target.value : p)) })}
                  >
                    {names.map((option) => (
                      <option key={option}>{option}</option>
                    ))}
                  </select>
                ))}
                {(one.segments ?? []).map((number, k) => (
                  <select
                    key={`s${k}`}
                    aria-label={`구속 ${index + 1} 구간 ${k + 1}`}
                    className="bg-background h-6 rounded border px-0.5"
                    value={number}
                    onChange={(e) => setConstraint(index, { segments: (one.segments ?? []).map((s, j) => (j === k ? Number(e.target.value) : s)) })}
                  >
                    {segments.map((_, option) => (
                      <option key={option} value={option}>
                        {segmentLabel(option)}
                      </option>
                    ))}
                  </select>
                ))}
                {spec?.unit && (
                  <span className="flex items-center gap-0.5">
                    <NumberField params={params} onCreateParam={onCreateParam} aria-label={`구속 ${index + 1} 값`} value={one.value ?? 0} onChange={(next) => setConstraint(index, { value: next ?? 0 })} />
                    {spec.unit}
                  </span>
                )}
                <button
                  type="button"
                  className="text-muted-foreground hover:text-destructive ml-auto px-1"
                  aria-label={`구속 ${index + 1} 삭제`}
                  onClick={() => onChange({ constraints: constraints.filter((_, i) => i !== index) })}
                >
                  ×
                </button>
              </li>
            )
          })}
        </ul>
        <div className="mt-1 flex items-center gap-1">
          <select aria-label="추가할 구속" className="bg-background h-7 rounded border px-1" value={kind} onChange={(e) => setKind(e.target.value)}>
            {CONSTRAINT_KINDS.map((one) => (
              <option key={one.value} value={one.value}>
                {one.label}
              </option>
            ))}
          </select>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={addConstraint}>
            + 구속
          </Button>
        </div>
      </div>
    </div>
  )
}
