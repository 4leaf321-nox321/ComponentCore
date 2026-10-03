/**
 * 「멈추기」 — 대기 중이면 바로 취소, 도는 중이면 다음 단계에서 멈춘다.
 *
 * 돌던 계산을 칼로 자르지 않는다(파일이 반쯤 쓰인 채 남는다) — 그래서 누른 뒤에도 지금 단계를
 * 마칠 때까지는 「멈추는 중」 이다. 무엇이 남는지 창에 적는다.
 */

import { useState } from 'react'

import { jobsApi } from '@/modules/jobs/api'
import type { Job } from '@/modules/jobs/api'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { Button } from '@/shared/components/ui/button'

export function CancelJobButton({
  job,
  onCancelled,
  cancel,
  what = '이 작업',
  keeps = '지금 단계까지 한 것은 남고, 산출물은 만들어지지 않습니다.',
}: {
  job: Pick<Job, 'id' | 'status' | 'cancel_requested_at'>
  onCancelled?: () => void
  /** 멈추는 길 — 없으면 일반 작업 취소(`/jobs/{id}/cancel`). DOE 는 제 길을 준다. */
  cancel?: () => Promise<unknown>
  what?: string
  /** 멈춘 뒤 무엇이 남나. */
  keeps?: string
}) {
  const [asking, setAsking] = useState(false)
  if (job.status !== 'queued' && job.status !== 'running') return null
  if (job.cancel_requested_at) {
    return (
      <Button size="sm" variant="outline" disabled>
        멈추는 중…
      </Button>
    )
  }
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setAsking(true)}>
        멈추기
      </Button>
      <ConfirmDialog
        open={asking}
        title={`${what}을 멈춥니다`}
        description={
          job.status === 'queued'
            ? '아직 시작하지 않았습니다 — 바로 취소합니다.'
            : `지금 하는 단계를 마치고 멈춥니다(계산을 중간에 자르지 않습니다). ${keeps}`
        }
        confirmLabel="멈추기"
        onConfirm={async () => {
          await (cancel ? cancel() : jobsApi.cancel(job.id))
          onCancelled?.()
        }}
        onClose={() => setAsking(false)}
      />
    </>
  )
}
