import type { Recipe } from '@/modules/cad/api'
import type { Job } from '@/modules/jobs/api'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'

export interface WorkVersion {
  id: string
  work_id: string
  number: number
  recipe: Recipe
  source: string
  note: string
  created_by_id: string | null
  created_by_name: string | null
  job: Job | null
  promoted_part_id: string | null
  promoted_part_version: number | null
  created_at: string
}

export interface Work {
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  current_version: number
  version_count: number
  current: WorkVersion | null
  jig_options: Record<string, unknown>
  jig_run_count: number
  last_jig_status: string | null
  promoted_part_id: string | null
  promoted_jig_id: string | null
  created_at: string
  updated_at: string
}

export interface WorkSummary {
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  current_version: number
  current_status: string | null
  jig_run_count: number
  last_jig_status: string | null
  promoted_part_id: string | null
  promoted_jig_id: string | null
  updated_at: string
}

export interface PromoteJigResult {
  jig_id: string
  jig_version: number
  part_id: string | null
  part_version: number | null
  part_promoted_now: boolean
}

export const worksApi = {
  jigOptions: () => api.get<Record<string, unknown>>('/works/jig-options'),
  list: (offset = 0, limit = 50) => api.get<Page<WorkSummary>>(`/works?offset=${offset}&limit=${limit}`),
  get: (id: string) => api.get<Work>(`/works/${id}`),
  create: (body: { name: string; description?: string; recipe: Recipe; source?: string; note?: string }) =>
    api.post<Work>('/works', body),
  update: (id: string, body: { name?: string; description?: string; jig_options?: Record<string, unknown> }) =>
    api.patch<Work>(`/works/${id}`, body),
  remove: (id: string) => api.delete<void>(`/works/${id}`),
  createFromStep: (file: File, name?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (name) form.append('name', name)
    return api.postForm<Work>('/works/from-step', form)
  },
  versions: (id: string) => api.get<WorkVersion[]>(`/works/${id}/versions`),
  addVersion: (id: string, body: { recipe: Recipe; source?: string; note?: string }) =>
    api.post<WorkVersion>(`/works/${id}/versions`, body),
  restore: (id: string, number: number) => api.post<WorkVersion>(`/works/${id}/versions/${number}/restore`),
  importStep: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<WorkVersion>(`/works/${id}/import-step`, form)
  },
  jigRuns: (id: string) => api.get<Job[]>(`/works/${id}/jig-runs`),
  runJig: (id: string, options: Record<string, unknown>) => api.post<Job>(`/works/${id}/jig-runs`, { options }),
  promotePart: (id: string, body: { name?: string; note?: string }) =>
    api.post<{ part_id: string; number: number }>(`/works/${id}/promote/part`, body),
  promoteJig: (id: string, body: { job_id: string; name?: string; note?: string; promote_product?: boolean }) =>
    api.post<PromoteJigResult>(`/works/${id}/promote/jig`, body),
}
