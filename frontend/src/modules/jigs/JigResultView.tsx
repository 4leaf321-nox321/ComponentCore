/**
 * 지그 생성 작업 하나 — 도는 동안은 단계 진행을, 끝나면 3D · 계획 · 간섭 · 내려받기를.
 *
 * 내 작업의 지그 탭과 지그 카탈로그가 같은 것을 보여 주므로 여기 하나다.
 */

import { lazy, Suspense, useEffect, useState } from 'react'

import type { JigSummary } from '@/modules/jigs/api'
import { isFinished, jobsApi } from '@/modules/jobs/api'
import type { Job } from '@/modules/jobs/api'
import { useJobPolling } from '@/modules/jobs/useJobPolling'
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
import { FullscreenButton, frameClass, useFullscreen } from '@/shared/viewer/FullscreenFrame'

const ModelViewer = lazy(() => import('@/shared/viewer/ModelViewer'))

const STAGES = [
  ['load', '제품 읽기'],
  ['geometry', 'Geometry Understanding'],
  ['features', 'Feature Recognition'],
  ['planning', 'Fixture Planning'],
  ['elements', 'Support · Locator · Clamp'],
  ['assembly', 'Jig 생성'],
  ['interference', '간섭 검사'],
  ['export', 'STEP 내보내기'],
] as const

const STAGE_LABELS: Record<string, string> = Object.fromEntries(STAGES)

const ARTIFACT_LABELS: Record<string, string> = {
  jig_step: '지그 STEP',
  assembly_step: '지그 + 제품 STEP',
  jig_stl: '지그 STL',
}

/**
 * 결과 glTF 를 Blob URL 로 받는다 — 토큰이 있어야 하므로 주소를 바로 뷰어에 줄 수 없다.
 *
 * 지그는 두 길로 생긴다: 생성기가 만든 것(`jig_glb` + `product_glb`)과 **사람이 그린 것**
 * (레시피 평가의 `model_glb` 하나뿐 — 제품이 따로 없다). 둘 다 여기서 그린다.
 */
function useModelUrls(job: Job) {
  const [urls, setUrls] = useState<{ product: string | null; jig: string } | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const product = job.artifacts.find((one) => one.kind === 'product_glb')
  const jig = job.artifacts.find((one) => one.kind === 'jig_glb') ?? job.artifacts.find((one) => one.kind === 'model_glb')
  const productId = product?.id
  const jigId = jig?.id
  useEffect(() => {
    if (!jigId) {
      setUrls(null)
      return
    }
    let cancelled = false
    const made: string[] = []
    Promise.all([productId ? jobsApi.artifactBlob(productId) : Promise.resolve(null), jobsApi.artifactBlob(jigId)])
      .then(([p, j]) => {
        if (cancelled) return
        const pair = { product: p ? URL.createObjectURL(p) : null, jig: URL.createObjectURL(j) }
        made.push(...[pair.product, pair.jig].filter((one): one is string => one !== null))
        setUrls(pair)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof Error ? caught : new Error('3D 를 읽지 못했습니다'))
      })
    return () => {
      cancelled = true
      made.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [productId, jigId])
  return { urls, error }
}

/** 도는 동안 — 끝난 단계는 시간, 지금 단계는 점, 남은 단계는 흐리게. */
function Progress({ job }: { job: Job }) {
  const done = new Map(job.progress.map((one) => [one.name, one]))
  const current = STAGES.find(([name]) => !done.has(name))?.[0]
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {job.status === 'queued' ? '대기 중' : '만드는 중'} <StatusBadge kind="run" value={job.status} />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-1 text-sm">
          {STAGES.map(([name, label]) => {
            const stage = done.get(name)
            const active = name === current && job.status === 'running'
            return (
              <li
                key={name}
                className={
                  stage ? '' : active ? 'font-medium' : 'text-muted-foreground/60'
                }
              >
                <span className="inline-block w-5">{stage ? '✓' : active ? '…' : ''}</span>
                {label}
                {stage && (
                  <span className="text-muted-foreground ml-2 text-xs">
                    {stage.detail} · {stage.millis} ms
                  </span>
                )}
              </li>
            )
          })}
        </ul>
        {job.status === 'queued' && (
          <p className="text-muted-foreground mt-3 text-xs">
            워커가 집어 가기를 기다립니다. 오래 이 상태면 워커(`python -m app.worker`)가 안 떠 있는
            것입니다.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export function JigResultView({
  job: initial,
  onFinished,
  actions,
}: {
  job: Job
  /** 폴링하던 작업이 끝났을 때 — 목록의 상태 배지를 새로 그릴 자리. */
  onFinished?: (job: Job) => void
  /** 결과 위 오른쪽에 둘 단추(승격 같은 것). */
  actions?: React.ReactNode
}) {
  const job = useJobPolling(initial) ?? initial
  const { urls, error } = useModelUrls(job)
  const full = useFullscreen()

  useEffect(() => {
    if (isFinished(job) && !isFinished(initial)) onFinished?.(job)
    // initial 이 바뀌면 새 작업이다 — onFinished 는 그 작업이 끝날 때 한 번이면 된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.status])

  if (!isFinished(job)) return <Progress job={job} />

  if (job.status === 'failed') {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            실행 실패 <StatusBadge kind="run" value="failed" />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-destructive text-sm">{job.error}</p>
        </CardContent>
      </Card>
    )
  }

  const s = job.summary as JigSummary | null
  if (!s) return null

  // 손으로 그린 지그에는 제품이 따로 없다 — 지그 하나만 그린다.
  const models = urls
    ? [
        ...(urls.product ? [{ url: urls.product, color: VIEWER_COLORS.product }] : []),
        { url: urls.jig, color: VIEWER_COLORS.jig, opacity: urls.product ? 0.85 : 1 },
      ]
    : []

  const box = full.active ? 'h-[calc(100vh-5rem)]' : 'h-[480px]'
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge kind="run" value={job.status} />
        <StatusBadge kind="interference" value={s.interference.ok ? 'ok' : 'bad'} />
        <span className="text-muted-foreground text-xs">
          {s.stages.reduce((sum, one) => sum + one.millis, 0)} ms
        </span>
        <div className="flex-1" />
        {actions}
        {job.artifacts
          .filter((one) => one.kind in ARTIFACT_LABELS)
          .map((one) => (
            <Button
              key={one.id}
              size="sm"
              variant="outline"
              onClick={() => downloadFile(jobsApi.artifactPath(one.id), one.filename)}
            >
              {ARTIFACT_LABELS[one.kind]}
            </Button>
          ))}
      </div>

      <div ref={full.frame} className={frameClass(full.active) || 'space-y-1'}>
        <div className="flex items-center gap-2">
          <p className="text-muted-foreground text-xs">
            {urls?.product && (
              <>
                <span style={{ color: VIEWER_COLORS.product }}>■</span> 제품{' '}
              </>
            )}
            <span style={{ color: VIEWER_COLORS.jig }}>■</span> 지그 — 끌어서 돌리고, 굴려서 확대합니다.
          </p>
          <div className="flex-1" />
          {urls && <FullscreenButton active={full.active} onToggle={() => void full.toggle()} />}
        </div>
        {urls && (
          <Suspense fallback={<Skeleton className={`${box} w-full`} />}>
            <ModelViewer models={models} className={`${box} w-full rounded-md border`} />
          </Suspense>
        )}
        <ErrorNotice error={error} />
      </div>

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
