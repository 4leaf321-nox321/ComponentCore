import { api, fetchBlob } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'

/** 서버 `modules/jobs/schemas.py` 와 짝. */
export interface Artifact {
  id: string
  job_id: string | null
  work_id: string | null
  parent_id: string | null
  kind: string
  filename: string
  content_type: string
  size_bytes: number
  created_at: string
}

export interface Stage {
  name: string
  millis: number
  detail: string
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export interface Job {
  id: string
  kind: string
  status: JobStatus
  requested_by_id: string | null
  requested_by_name: string | null
  work_id: string | null
  work_name: string | null
  options: Record<string, unknown>
  progress: Stage[]
  summary: Record<string, unknown> | null
  error: string | null
  artifacts: Artifact[]
  created_at: string
  started_at: string | null
  finished_at: string | null
  /** 도는 중에 멈추라고 했다 — 워커가 다음 단계에서 멈춘다(화면은 「멈추는 중」). */
  cancel_requested_at?: string | null
}

export const isFinished = (job: Job) => job.status === 'done' || job.status === 'failed' || job.status === 'cancelled'

/** 배지에 보일 상태 — 도는 중에 멈추라고 했으면 「멈추는 중」. */
export const runState = (job: Job) => (job.status === 'running' && job.cancel_requested_at ? 'cancelling' : job.status)

export const jobsApi = {
  list: (params: { mine?: boolean; work_id?: string; kind?: string; status?: string; offset?: number; limit?: number }) => {
    const query = new URLSearchParams()
    if (params.mine !== undefined) query.set('mine', String(params.mine))
    if (params.work_id) query.set('work_id', params.work_id)
    if (params.kind) query.set('kind', params.kind)
    if (params.status) query.set('status', params.status)
    if (params.offset) query.set('offset', String(params.offset))
    if (params.limit) query.set('limit', String(params.limit))
    return api.get<Page<Job>>(`/jobs?${query.toString()}`)
  },
  get: (id: string) => api.get<Job>(`/jobs/${id}`),
  /** 멈춘다 — 대기 중이면 바로 취소, 도는 중이면 다음 단계에서 멈춘다. 건 사람 · 주인 · 관리자만. */
  cancel: (id: string) => api.post<Job>(`/jobs/${id}/cancel`, {}),
  artifactPath: (id: string) => `/artifacts/${id}/download`,
  artifactBlob: (id: string) => fetchBlob(`/artifacts/${id}/download`),
}
