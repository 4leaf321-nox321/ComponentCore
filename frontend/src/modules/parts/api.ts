import type { Recipe } from '@/modules/cad/api'
import type { Job } from '@/modules/jobs/api'
import type { Work } from '@/modules/works/api'
import { api } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'

export interface PartVersion {
  id: string
  part_id: string
  number: number
  recipe: Recipe
  job: Job | null
  note: string
  promoted_by_id: string | null
  promoted_by_name: string | null
  work_version_id: string | null
  created_at: string
}

export interface Part {
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  work_id: string | null
  current_version: number
  version_count: number
  current: PartVersion | null
  jig_count: number
  created_at: string
  updated_at: string
}

export interface PartSummary {
  id: string
  name: string
  description: string
  owner_name: string
  current_version: number
  jig_count: number
  updated_at: string
}

export const partsApi = {
  list: (offset = 0, limit = 50, q = '') => api.get<Page<PartSummary>>(`/parts?offset=${offset}&limit=${limit}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  get: (id: string) => api.get<Part>(`/parts/${id}`),
  versions: (id: string) => api.get<PartVersion[]>(`/parts/${id}/versions`),
  update: (id: string, body: { name?: string; description?: string }) => api.patch<Part>(`/parts/${id}`, body),
  remove: (id: string) => api.delete<void>(`/parts/${id}`),
  copyToWork: (id: string, body: { name?: string; number?: number }) =>
    api.post<Work>(`/parts/${id}/copy-to-work`, body),
}
