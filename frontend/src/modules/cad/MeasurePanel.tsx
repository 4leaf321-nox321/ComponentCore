/**
 * 측정 — 3D 에서 누른 것으로 거리 · 길이 · 넓이 · 각도를 잰다.
 *
 * 점(꼭짓점에 스냅)을 둘 누르면 거리(와 ΔX ΔY ΔZ), 셋이면 가운데 점의 각도. 엣지를 누르면 길이 ·
 * 중점, 면을 누르면 넓이 · 중심 · 법선. 두 엣지의 중점 사이, 점과 면 중심 사이도 같은 규칙으로
 * 잰다 — 고른 것에서 **대표 점**을 뽑아 점처럼 다룬다.
 */

import type { MeasurePick } from '@/shared/viewer/PickViewer'
import { Button } from '@/shared/components/ui/button'

export function representative(pick: MeasurePick): number[] {
  if (pick.kind === 'point') return pick.at
  if (pick.kind === 'edge') return pick.edge.midpoint
  return pick.face.center
}

function fmt(v: number): string {
  return (Math.round(v * 100) / 100).toString()
}

function vec(p: number[]): string {
  return `(${p.map(fmt).join(', ')})`
}

export function measureMarks(picks: MeasurePick[]): { points: number[][]; segments: number[][][] } {
  const points = picks.map(representative)
  const segments: number[][][] = []
  for (let i = 1; i < points.length; i += 1) segments.push([points[i - 1], points[i]])
  return { points, segments }
}

export function MeasurePanel({ picks, onClear, onUndo }: { picks: MeasurePick[]; onClear: () => void; onUndo: () => void }) {
  const points = picks.map(representative)
  const lines: string[] = []
  picks.forEach((pick, i) => {
    if (pick.kind === 'point') lines.push(`점 ${i + 1} ${vec(pick.at)}`)
    if (pick.kind === 'edge') lines.push(`엣지 ${i + 1} — 길이 ${fmt(pick.edge.length)} mm · ${pick.edge.kind} · 중점 ${vec(pick.edge.midpoint)}`)
    if (pick.kind === 'face') lines.push(`면 ${i + 1} — 넓이 ${fmt(pick.face.area)} mm² · ${pick.face.kind} · 법선 ${vec(pick.face.normal)}`)
  })
  if (points.length >= 2) {
    const [a, b] = points.slice(-2)
    const d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]
    lines.push(`거리 ${fmt(Math.hypot(...d))} mm  (ΔX ${fmt(d[0])} · ΔY ${fmt(d[1])} · ΔZ ${fmt(d[2])})`)
  }
  if (points.length >= 3) {
    const [a, b, c] = points.slice(-3)
    const u = [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
    const v = [c[0] - b[0], c[1] - b[1], c[2] - b[2]]
    const dot = u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    const cos = dot / ((Math.hypot(...u) * Math.hypot(...v)) || 1)
    lines.push(`각도 ${fmt((Math.acos(Math.max(-1, Math.min(1, cos))) * 180) / Math.PI)}° (가운데 점 기준)`)
  }
  return (
    <div className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs">
      <div className="mb-1 flex items-center gap-2">
        <span className="font-medium">측정</span>
        <span className="text-muted-foreground">점(꼭짓점 근처) · 엣지 · 면을 누르세요. 둘이면 거리, 셋이면 각도.</span>
        <div className="flex-1" />
        <Button size="sm" variant="ghost" className="h-6 px-2" onClick={onUndo} disabled={picks.length === 0}>
          하나 빼기
        </Button>
        <Button size="sm" variant="ghost" className="h-6 px-2" onClick={onClear} disabled={picks.length === 0}>
          지우기
        </Button>
      </div>
      {lines.length === 0 ? <p className="text-muted-foreground">아직 고른 것이 없습니다.</p> : (
        <ul className="space-y-0.5 font-mono">
          {lines.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
