/**
 * 작업이 끝날 때까지 `GET /jobs/{id}` 를 폴링한다.
 *
 * 끝난 작업은 다시 묻지 않는다. 진행 중이면 1.5초마다 — 단계가 8개고 대개 1초 안에 끝나므로
 * 더 짧게 물을 이유가 없고, 더 길면 사람이 「멈췄나」 하고 본다.
 */

import { useEffect, useState } from 'react'

import { isFinished, jobsApi } from '@/modules/jobs/api'
import type { Job } from '@/modules/jobs/api'

const INTERVAL_MS = 1500

export function useJobPolling(initial: Job | null): Job | null {
  const [job, setJob] = useState<Job | null>(initial)

  useEffect(() => {
    setJob(initial)
  }, [initial])

  useEffect(() => {
    if (!job || isFinished(job)) return
    let cancelled = false
    const timer = setInterval(async () => {
      try {
        const fresh = await jobsApi.get(job.id)
        if (cancelled) return
        setJob(fresh)
        if (isFinished(fresh)) clearInterval(timer)
      } catch {
        // 잠깐 끊긴 것. 다음 틱에 다시.
      }
    }, INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [job])

  return job
}
