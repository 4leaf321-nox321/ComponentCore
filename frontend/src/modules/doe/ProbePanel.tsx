/**
 * 「끝 점 미리 만들어 보기」 의 결과 — 200점을 다 돌리기 전에 범위의 끝에서 깨지는지, 선택 그룹이
 * 딴 면을 집는지, 부품이 겹치는지, 한 점에 얼마나 걸리는지를 먼저 본다.
 *
 * 만든 점은 그 자리에서 3D 로 볼 수 있다 — 「모두 최대」 가 실제로 어떤 모양인지 눈으로 봐야
 * 범위를 고칠지 안다.
 */

import { lazy, Suspense, useState } from 'react'

import { cadApi } from '@/modules/cad/api'
import type { Recipe } from '@/modules/cad/api'
import type { ProbePoint, ProbeResult } from '@/modules/doe/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import type { MeshData } from '@/shared/viewer/PickViewer'

const PickViewer = lazy(() => import('@/shared/viewer/PickViewer'))

function show(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return value.toLocaleString(undefined, { maximumFractionDigits: 3 })
  if (typeof value === 'boolean') return value ? '켬' : '끔'
  return String(value)
}

/**
 * 만든 점에 붙는 주의 — 못 푼 영역 · 어긋남 · 겹침 · 형상 점검(얇은 벽 · 짧은 모서리 · 좁은 면 ·
 * 바디 수) · 레시피 경고. 점검을 안 받았으면(옛 서버) 바디 수만 가운데 점과 견준다.
 */
export function probeNotes(point: ProbePoint, baseSolids: number | undefined): string[] {
  const notes: string[] = []
  if (point.unresolved?.length) notes.push(`못 찾은 그룹: ${point.unresolved.join(', ')}`)
  for (const one of point.drift ?? []) notes.push(`${one.name} 이 예측 자리에서 ${one.distance.toFixed(2)} mm 벗어남`)
  if (point.interference && !point.interference.ok) notes.push(`부품 겹침 ${point.interference.items.filter((one) => !one.ok).length}건`)
  if (point.quality) notes.push(...point.quality.warnings)
  else if (baseSolids !== undefined && point.solids !== undefined && point.solids !== baseSolids) notes.push(`바디 ${baseSolids} → ${point.solids}`)
  for (const one of point.warnings ?? []) notes.push(one)
  return notes
}

export function ProbePanel({
  result,
  recipe,
  names,
  measures = [],
  count,
}: {
  result: ProbeResult
  recipe: Recipe
  names: string[]
  /** 측정값 열 — 끝 점에서 값이 얼마나 벌어지는지 본다. */
  measures?: string[]
  count: number | null
}) {
  const [viewing, setViewing] = useState<string | null>(null)
  const [mesh, setMesh] = useState<MeshData | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const baseSolids = result.points.find((one) => one.status === 'ok')?.solids
  const bad = result.points.filter((one) => one.status === 'failed' || probeNotes(one, baseSolids).length > 0).length

  async function view(point: ProbePoint) {
    setViewing(point.label)
    setMesh(null)
    setError(null)
    try {
      const values: Record<string, number> = {}
      for (const [key, value] of Object.entries(point.params)) if (typeof value === 'number' && key in (recipe.params ?? {})) values[key] = value
      const got = await cadApi.mesh({ ...recipe, params: { ...recipe.params, ...values } })
      setMesh(got.mesh)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  const minutes = result.mean_ms !== null && count ? (result.mean_ms * count + result.setup_ms) / 60000 : null
  return (
    <div className="space-y-2 rounded-md border p-3" aria-label="미리 만들어 본 점">
      <p className="text-xs">
        끝 점 {result.points.length} 개를 만들어 봤습니다 —{' '}
        {bad === 0 ? <b>문제 없음</b> : <b className="text-destructive">{bad} 개에 문제가 있습니다</b>}
        {result.mean_ms !== null && (
          <span className="text-muted-foreground">
            {' '}
            · 한 점에 약 {(result.mean_ms / 1000).toFixed(1)} 초
            {minutes !== null && ` · 설계점 ${count} 개면 약 ${minutes < 1 ? '1 분 안' : `${Math.ceil(minutes)} 분`}`}
          </span>
        )}
      </p>
      <div className="overflow-auto">
        <table className="w-full min-w-max text-xs">
          <thead className="text-muted-foreground">
            <tr className="border-b text-left">
              <th className="py-1 pr-2 font-medium">점</th>
              {names.map((name) => (
                <th key={name} className="py-1 pr-2 font-mono font-medium">
                  {name}
                </th>
              ))}
              {measures.map((name) => (
                <th key={`m-${name}`} className="py-1 pr-2 font-mono font-medium text-sky-700 dark:text-sky-400">
                  {name}
                </th>
              ))}
              <th className="py-1 pr-2 font-medium">결과</th>
              <th className="py-1 pr-2 font-medium">주의</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {result.points.map((point) => {
              const notes = probeNotes(point, baseSolids)
              return (
                <tr key={point.label} className={`border-b last:border-b-0 ${viewing === point.label ? 'bg-accent' : ''}`}>
                  <td className="py-1 pr-2">{point.label}</td>
                  {names.map((name) => (
                    <td key={name} className="py-1 pr-2 font-mono">
                      {show(point.params[name])}
                    </td>
                  ))}
                  {measures.map((name) => (
                    <td key={`m-${name}`} className="py-1 pr-2 font-mono">
                      {show(point.measures?.[name])}
                    </td>
                  ))}
                  <td className={`py-1 pr-2 ${point.status === 'failed' ? 'text-destructive' : point.status === 'skipped' ? 'text-muted-foreground' : ''}`} title={point.error}>
                    {point.status === 'ok' ? `만듦 ${((point.ms ?? 0) / 1000).toFixed(1)}s` : point.status === 'failed' ? `실패 — ${point.error.slice(0, 80)}` : `건너뜀 — ${point.error}`}
                  </td>
                  <td className="py-1 pr-2">
                    <span className="text-amber-700 dark:text-amber-400">{notes.join(' · ')}</span>
                    {point.quality?.notes?.length ? <span className="text-muted-foreground"> {point.quality.notes.join(' · ')}</span> : null}
                  </td>
                  <td className="py-1">
                    {point.status === 'ok' && (
                      <button type="button" className="text-muted-foreground hover:text-foreground underline" onClick={() => void view(point)}>
                        보기
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <ErrorNotice error={error} />
      {viewing && mesh && (
        <Suspense fallback={null}>
          <p className="text-muted-foreground text-xs">{viewing}</p>
          <PickViewer mesh={mesh} mode="none" className="h-72 w-full rounded-md border" />
        </Suspense>
      )}
    </div>
  )
}
