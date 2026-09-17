/** 실행 결과 — 단계별 시간 · 계획 · 간섭 · 3D · 내려받기. */

import { lazy, Suspense, useEffect, useState } from 'react'

import { jigsApi } from '@/modules/jigs/api'
import type { JigRun } from '@/modules/jigs/api'
import { downloadFile } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Skeleton } from '@/shared/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { VIEWER_COLORS } from '@/shared/viewer/colors'

const ModelViewer = lazy(() => import('@/shared/viewer/ModelViewer'))

const STAGE_LABELS: Record<string, string> = {
  load: '제품 읽기',
  geometry: 'Geometry Understanding',
  features: 'Feature Recognition',
  planning: 'Fixture Planning',
  elements: 'Support · Locator · Clamp',
  assembly: 'Jig 생성',
  interference: '간섭 검사',
  export: 'STEP 내보내기',
}

const FILE_LABELS: Record<string, string> = {
  jig_step: '지그 STEP',
  assembly_step: '지그 + 제품 STEP',
  jig_stl: '지그 STL',
}

/** 결과 glTF 를 Blob URL 로 받는다 — 토큰이 있어야 하므로 주소를 바로 뷰어에 줄 수 없다. */
function useModelUrls(run: JigRun) {
  const [urls, setUrls] = useState<{ product: string; jig: string } | null>(null)
  const [error, setError] = useState<Error | null>(null)
  useEffect(() => {
    let cancelled = false
    const made: string[] = []
    if (!run.files.includes('jig_glb') || !run.files.includes('product_glb')) {
      setUrls(null)
      return
    }
    Promise.all([
      jigsApi.fileBlob(run.project_id, run.id, 'product_glb'),
      jigsApi.fileBlob(run.project_id, run.id, 'jig_glb'),
    ])
      .then(([product, jig]) => {
        if (cancelled) return
        const pair = { product: URL.createObjectURL(product), jig: URL.createObjectURL(jig) }
        made.push(pair.product, pair.jig)
        setUrls(pair)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof Error ? caught : new Error('3D 를 읽지 못했습니다'))
      })
    return () => {
      cancelled = true
      made.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [run])
  return { urls, error }
}

export function RunResult({ run }: { run: JigRun }) {
  const { urls, error } = useModelUrls(run)
  const s = run.summary

  if (run.status === 'failed') {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            실행 실패 <StatusBadge kind="run" value="failed" />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-destructive text-sm">{run.error}</p>
        </CardContent>
      </Card>
    )
  }
  if (!s) return null

  const models = urls
    ? [
        { url: urls.product, color: VIEWER_COLORS.product },
        { url: urls.jig, color: VIEWER_COLORS.jig, opacity: 0.85 },
      ]
    : []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge kind="run" value={run.status} />
        <StatusBadge kind="interference" value={s.interference.ok ? 'ok' : 'bad'} />
        <span className="text-muted-foreground text-xs">
          {s.stages.reduce((sum, one) => sum + one.millis, 0)} ms
        </span>
        <div className="flex-1" />
        {run.files
          .filter((key) => key in FILE_LABELS)
          .map((key) => (
            <Button
              key={key}
              size="sm"
              variant="outline"
              onClick={() =>
                downloadFile(jigsApi.filePath(run.project_id, run.id, key), `${key}.step`)
              }
            >
              {FILE_LABELS[key]}
            </Button>
          ))}
      </div>

      {urls && (
        <Suspense fallback={<Skeleton className="h-[480px] w-full" />}>
          <ModelViewer models={models} />
        </Suspense>
      )}
      <ErrorNotice error={error} />
      <p className="text-muted-foreground text-xs">
        <span style={{ color: VIEWER_COLORS.product }}>■</span> 제품{' '}
        <span style={{ color: VIEWER_COLORS.jig }}>■</span> 지그 — 끌어서 돌리고, 굴려서 확대합니다.
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>단계</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableBody>
                {s.stages.map((stage) => (
                  <TableRow key={stage.name}>
                    <TableCell className="whitespace-nowrap">{STAGE_LABELS[stage.name] ?? stage.name}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">{stage.detail}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{stage.millis} ms</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>제품과 계획</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              크기 {s.geometry.bbox.size.map((v) => v.toFixed(1)).join(' × ')} mm · 부피{' '}
              {s.geometry.volume.toLocaleString()} mm³ · 면 {s.geometry.face_count}
            </p>
            <p className="text-muted-foreground text-xs">
              특징:{' '}
              {Object.entries(s.feature_counts)
                .map(([key, count]) => `${key} ${count}`)
                .join(', ')}
            </p>
            <p>
              베이스 플레이트 {s.plan.base_plate.length} × {s.plan.base_plate.width} ×{' '}
              {s.plan.base_plate.thickness} mm · 받침 {s.plan.supports.length} · 로케이터{' '}
              {s.plan.locators.length} ({s.plan.locators.map((l) => l.kind).join(', ') || '없음'}) ·
              클램프 {s.plan.clamps.length}
            </p>
            {s.plan.notes.length > 0 && (
              <ul className="text-muted-foreground list-inside list-disc text-xs">
                {s.plan.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {!s.interference.ok && (
        <Card>
          <CardHeader>
            <CardTitle>간섭</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>부품</TableHead>
                  <TableHead>상대</TableHead>
                  <TableHead className="text-right">겹침 부피 (mm³)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {s.interference.items
                  .filter((item) => !item.ok)
                  .map((item) => (
                    <TableRow key={`${item.a}-${item.b}`}>
                      <TableCell>{item.a}</TableCell>
                      <TableCell>{item.b}</TableCell>
                      <TableCell className="text-right font-mono">{item.volume}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
