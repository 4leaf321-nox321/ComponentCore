import { api, fetchBlob } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'

/** 서버 `modules/jigs/schemas.py` 와 짝. `npm run api:types` 뒤에는 생성 타입으로 갈아탄다. */
export interface JigProject {
  id: string
  name: string
  description: string
  owner_id: string
  owner_name: string
  product_filename: string | null
  product_size_bytes: number | null
  product_spec: Record<string, unknown> | null
  has_product_file: boolean
  run_count: number
  last_run_status: string | null
  created_at: string
  updated_at: string
}

export interface StageLog {
  name: string
  millis: number
  detail: string
}

export interface InterferenceItem {
  a: string
  b: string
  volume: number
  ok: boolean
}

export interface RunSummary {
  geometry: {
    bbox: { min: number[]; max: number[]; size: number[] }
    volume: number
    surface_area: number
    solid_count: number
    face_count: number
    edge_count: number
  }
  feature_counts: Record<string, number>
  plan: {
    base_plate: { length: number; width: number; thickness: number }
    supports: { label: string; position: number[]; diameter: number }[]
    locators: { label: string; kind: string; position: number[]; diameter: number | null }[]
    clamps: { label: string; pad_position: number[]; post_position: number[] }[]
    product_lift: number
    notes: string[]
  }
  interference: { ok: boolean; tolerance: number; total_volume: number; items: InterferenceItem[] }
  files: Record<string, string>
  stages: StageLog[]
}

export interface JigRun {
  id: string
  project_id: string
  status: string
  options: Record<string, unknown>
  summary: RunSummary | null
  error: string | null
  files: string[]
  started_at: string
  finished_at: string | null
}

export interface JigOptionsOut {
  defaults: Record<string, unknown>
  primitive_kinds: string[]
}

export const jigsApi = {
  options: () => api.get<JigOptionsOut>('/jigs/options'),
  list: (offset = 0, limit = 50) =>
    api.get<Page<JigProject>>(`/jigs/projects?offset=${offset}&limit=${limit}`),
  get: (id: string) => api.get<JigProject>(`/jigs/projects/${id}`),
  create: (body: { name: string; description: string; product_spec: Record<string, unknown> | null }) =>
    api.post<JigProject>('/jigs/projects', body),
  update: (id: string, body: Partial<Pick<JigProject, 'name' | 'description' | 'product_spec'>>) =>
    api.patch<JigProject>(`/jigs/projects/${id}`, body),
  remove: (id: string) => api.delete<void>(`/jigs/projects/${id}`),
  uploadProduct: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<JigProject>(`/jigs/projects/${id}/product`, form)
  },
  removeProduct: (id: string) => api.delete<JigProject>(`/jigs/projects/${id}/product`),
  runs: (id: string) => api.get<JigRun[]>(`/jigs/projects/${id}/runs`),
  run: (id: string, options: Record<string, unknown>) =>
    api.post<JigRun>(`/jigs/projects/${id}/runs`, { options }),
  filePath: (projectId: string, runId: string, key: string) =>
    `/jigs/projects/${projectId}/runs/${runId}/files/${key}`,
  fileBlob: (projectId: string, runId: string, key: string) =>
    fetchBlob(`/jigs/projects/${projectId}/runs/${runId}/files/${key}`),
}
