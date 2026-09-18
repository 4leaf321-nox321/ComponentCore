/**
 * 맞서는 목표 고르기 — **파레토**.
 *
 * 지그에서 목표는 늘 맞선다: 두께를 키우면 공진은 목표에 가까워지지만 질량이 는다. 이럴 때
 * 가중치를 물어 한 점을 고르게 하지 않는다 — 그 답은 가중치의 것이지 사람의 것이 아니다.
 * 대신 **아무한테도 지지 않는 점**만 남겨 보여 주고, 고르는 일은 사람에게 맡긴다.
 */

import { useCallback, useEffect, useState } from 'react'

import { doeApi } from '@/modules/doe/api'
import type { DoeStudy, Objective, TradeoffPoint } from '@/modules/doe/api'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/components/ui/select'

const KEYS: { key: string; label: string }[] = [
  { key: 'mass_g', label: '질량 g' },
  { key: 'volume_mm3', label: '부피 mm³' },
  { key: 'size_x', label: '크기 X' },
  { key: 'size_y', label: '크기 Y' },
  { key: 'size_z', label: '크기 Z' },
  { key: 'izz', label: 'Izz' },
  { key: 'ixx', label: 'Ixx' },
  { key: 'iyy', label: 'Iyy' },
]

const label = (key: string) => KEYS.find((one) => one.key === key)?.label ?? key

/** 두 목표를 축으로 흩뿌려 그린다 — 지지 않는 점은 채운 점, 지는 점은 옅게. */
function Scatter({ points, x, y }: { points: TradeoffPoint[]; x: string; y: string }) {
  const usable = points.filter((one) => one.comparable && Number.isFinite(Number(one[x])) && Number.isFinite(Number(one[y])))
  if (usable.length < 2) return null
  const xs = usable.map((one) => Number(one[x]))
  const ys = usable.map((one) => Number(one[y]))
  const [minX, maxX] = [Math.min(...xs), Math.max(...xs)]
  const [minY, maxY] = [Math.min(...ys), Math.max(...ys)]
  const at = (value: number, low: number, high: number) => (high === low ? 0.5 : (value - low) / (high - low))
  const W = 520
  const H = 240
  const PAD = 34
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="bg-muted/30 w-full rounded-md border" role="img" aria-label={`${label(x)} 대 ${label(y)} 흩뿌림`}>
      <line x1={PAD} y1={H - PAD} x2={W - 8} y2={H - PAD} stroke="currentColor" strokeWidth={0.5} opacity={0.4} />
      <line x1={PAD} y1={8} x2={PAD} y2={H - PAD} stroke="currentColor" strokeWidth={0.5} opacity={0.4} />
      <text x={W - 8} y={H - PAD + 14} textAnchor="end" fontSize={10} fill="currentColor" opacity={0.6}>
        {label(x)}
      </text>
      <text x={PAD} y={14} fontSize={10} fill="currentColor" opacity={0.6}>
        {label(y)}
      </text>
      {usable.map((one) => {
        const cx = PAD + at(Number(one[x]), minX, maxX) * (W - PAD - 16)
        const cy = H - PAD - at(Number(one[y]), minY, maxY) * (H - PAD - 16)
        return (
          <g key={one.number}>
            <circle
              cx={cx}
              cy={cy}
              r={one.pareto ? 5 : 3.5}
              className={one.pareto ? 'fill-primary' : 'fill-muted-foreground'}
              opacity={one.pareto ? 1 : 0.35}
            />
            {one.pareto && (
              <text x={cx + 7} y={cy + 3} fontSize={9} fill="currentColor" opacity={0.75}>
                p{one.number}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

export function TradeoffPanel({ study }: { study: DoeStudy }) {
  const [objectives, setObjectives] = useState<Objective[]>([
    { key: 'mass_g', goal: 'min' },
    { key: 'size_z', goal: 'max' },
  ])
  const [points, setPoints] = useState<TradeoffPoint[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (next: Objective[]) => {
    setError(null)
    try {
      const got = await doeApi.tradeoff(study.id, next)
      setPoints(got.points)
    } catch (caught) {
      setPoints(null)
      setError(caught instanceof Error ? caught.message : '알 수 없는 오류')
    }
  }, [study.id])

  useEffect(() => {
    void load(objectives)
  }, [load, objectives])

  const kept = (points ?? []).filter((one) => one.pareto)

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">맞서는 목표</span>
        <span className="text-muted-foreground text-xs">
          아무한테도 지지 않는 점만 채워 보여 줍니다. **한 값으로 합치지 않습니다** — 고르는 것은 사람의 몫입니다.
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {objectives.map((objective, index) => (
          <div key={index} className="flex items-center gap-1">
            <Select
              value={objective.key}
              onValueChange={(key) => setObjectives(objectives.map((one, i) => (i === index ? { ...one, key } : one)))}
            >
              <SelectTrigger className="h-8 w-28 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KEYS.map((one) => (
                  <SelectItem key={one.key} value={one.key}>
                    {one.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={objective.goal}
              onValueChange={(goal) =>
                setObjectives(
                  objectives.map((one, i) =>
                    i === index ? { ...one, goal: goal as Objective['goal'], target: goal === 'target' ? (one.target ?? 0) : undefined } : one,
                  ),
                )
              }
            >
              <SelectTrigger className="h-8 w-32 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="min">작을수록 좋음</SelectItem>
                <SelectItem value="max">클수록 좋음</SelectItem>
                <SelectItem value="target">목표값에 가깝게</SelectItem>
              </SelectContent>
            </Select>
            {objective.goal === 'target' && (
              <Input
                type="number"
                value={String(objective.target ?? 0)}
                onChange={(e) => setObjectives(objectives.map((one, i) => (i === index ? { ...one, target: Number(e.target.value) } : one)))}
                className="h-8 w-24"
                aria-label={`목표 ${index + 1} 목표값`}
              />
            )}
            {objectives.length > 1 && (
              <button type="button" className="text-muted-foreground px-1 text-xs" onClick={() => setObjectives(objectives.filter((_, i) => i !== index))}>
                ×
              </button>
            )}
          </div>
        ))}
        {objectives.length < 4 && (
          <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setObjectives([...objectives, { key: 'volume_mm3', goal: 'min' }])}>
            + 목표
          </Button>
        )}
      </div>

      {error && <p className="text-destructive text-xs">{error}</p>}

      {points && (
        <>
          <p className="text-xs">
            지지 않는 점 <b>{kept.length}</b> / {points.filter((one) => one.comparable).length} —{' '}
            {kept.map((one) => `p${one.number}`).join(', ') || '없음'}
          </p>
          {objectives.length >= 2 && <Scatter points={points} x={objectives[0].key} y={objectives[1].key} />}
          <ul className="space-y-0.5 text-xs">
            {kept.slice(0, 8).map((one) => (
              <li key={one.number} className="flex flex-wrap items-center gap-2">
                <span className="font-mono">p{String(one.number).padStart(4, '0')}</span>
                <span className="text-muted-foreground font-mono">
                  {Object.entries(one.params as Record<string, number>)
                    .map(([key, value]) => `${key} ${value}`)
                    .join(' · ')}
                </span>
                <span className="ml-auto font-mono">
                  {objectives.map((objective) => `${label(objective.key)} ${Number(one[objective.key]).toLocaleString(undefined, { maximumFractionDigits: 1 })}`).join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
