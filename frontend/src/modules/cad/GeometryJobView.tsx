/**
 * 부품 평가 작업(kind="cad") 하나의 3D — 끝날 때까지 폴링하고 glTF 를 그린다.
 *
 * 내 작업의 버전, 부품 카탈로그의 버전이 같은 것을 보여 주므로 여기 하나다.
 */

import { lazy, Suspense, useEffect, useState } from 'react'

import { isFinished, jobsApi } from '@/modules/jobs/api'
import type { Job } from '@/modules/jobs/api'
import { useJobPolling } from '@/modules/jobs/useJobPolling'
import { downloadFile } from '@/shared/api/client'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { FullscreenButton, frameClass, useFullscreen } from '@/shared/viewer/FullscreenFrame'
import { VIEWER_COLORS } from '@/shared/viewer/colors'

const ModelViewer = lazy(() => import('@/shared/viewer/ModelViewer'))

export function GeometryJobView({
  job: initial,
  title,
  stepName,
  onFinished,
  height = 'h-[420px]',
}: {
  job: Job | null
  title: string
  /** 주면 뷰어 머리에 「STEP 받기」 가 뜬다. 도구줄이 따로 있는 화면은 안 준다 — 받는 단추가 두 군데면 헷갈린다. */
  stepName?: string
  onFinished?: () => void
  height?: string
}) {
  const job = useJobPolling(initial)
  const [url, setUrl] = useState<string | null>(null)
  const full = useFullscreen()
  const glb = job?.artifacts.find((one) => one.kind === 'model_glb')
  const step = job?.artifacts.find((one) => one.kind === 'model_step')

  useEffect(() => {
    if (job && isFinished(job) && initial && !isFinished(initial)) onFinished?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status])

  useEffect(() => {
    if (!glb) return
    let cancelled = false
    let made: string | null = null
    jobsApi
      .artifactBlob(glb.id)
      .then((blob) => {
        if (cancelled) return
        made = URL.createObjectURL(blob)
        setUrl(made)
      })
      .catch(() => setUrl(null))
    return () => {
      cancelled = true
      if (made) URL.revokeObjectURL(made)
    }
  }, [glb?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!job) {
    return (
      <div className={`text-muted-foreground flex ${height} items-center justify-center rounded-md border border-dashed text-sm`}>
        아직 부품이 없습니다.
      </div>
    )
  }
  const summary = job.summary as { volume?: number; bbox?: { size: number[] }; face_count?: number } | null
  const box = full.active ? 'h-[calc(100vh-4rem)]' : height
  return (
    <div ref={full.frame} className={frameClass(full.active) || 'space-y-2'}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{title}</span>
        <StatusBadge kind="run" value={job.status} />
        {summary?.bbox && (
          <span className="text-muted-foreground text-xs">
            {summary.bbox.size.map((v) => v.toFixed(1)).join(' × ')} mm · 부피{' '}
            {summary.volume?.toLocaleString()} mm³ · 면 {summary.face_count}
          </span>
        )}
        <div className="flex-1" />
        <FullscreenButton active={full.active} onToggle={() => void full.toggle()} />
        {step && stepName && (
          <Button size="sm" variant="outline" onClick={() => downloadFile(jobsApi.artifactPath(step.id), stepName)}>
            STEP 받기
          </Button>
        )}
      </div>
      {job.status === 'failed' && <p className="text-destructive text-sm">{job.error}</p>}
      {url ? (
        <Suspense fallback={<Skeleton className={`${box} w-full`} />}>
          <ModelViewer models={[{ url, color: VIEWER_COLORS.product }]} className={`${box} w-full rounded-md border`} />
        </Suspense>
      ) : (
        !isFinished(job) && <Skeleton className={`${box} w-full`} />
      )}
    </div>
  )
}
