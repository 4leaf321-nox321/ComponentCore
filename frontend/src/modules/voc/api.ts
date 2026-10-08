/** VOC API — 게시판이고 절차다. 서버 `modules/voc/schemas.py` 와 짝. */

import { api, downloadFile, postForBlob } from '@/shared/api/client'
import type { Page } from '@/shared/api/types'

/** 상태의 차례 — 필터 칩이 이 순서로 선다. 말과 색은 `StatusBadge`(kind="voc")가 정한다. */
export const VOC_STATUSES = ['open', 'accepted', 'in_progress', 'resolved', 'closed', 'rejected'] as const

export interface VocItem {
  id: string
  seq: number
  title: string
  status: string
  status_label: string
  page_path: string | null
  created_at: string
  created_by: string | null
  status_at: string
  status_by: string | null
  /** 본인이 등록한 것인가 — 이름으로 짐작하지 않는다(동명이인). */
  is_mine: boolean
  /** 수정 · 삭제할 수 있는가 — 서버가 정한다. */
  can_edit: boolean
  /** 등록을 뺀 이력 수 — 「말이 오간 건」. */
  event_count: number
  attachment_count: number
}

export interface VocEvent {
  id: string
  at: string
  by: string | null
  /** 비면 등록 줄이다. `to_status` 와 같으면 댓글. */
  from_status: string | null
  to_status: string
  to_status_label: string
  note: string | null
}

export interface VocAttachment {
  id: string
  filename: string
  content_type: string
  size: number
  created_at: string
  created_by: string | null
  url: string
}

export interface VocDetail extends VocItem {
  body: string
  events: VocEvent[]
  attachments: VocAttachment[]
  can_attach: boolean
  /** **이 사용자가 지금 옮길 수 있는 상태.** 화면이 규칙을 외우지 않는다. */
  allowed: string[]
  allowed_labels: Record<string, string>
  /** `allowed` 가운데 내용이 꼭 필요한 것. */
  note_required: string[]
  can_delete_events: boolean
}

/** 파일 크기 — 1 KB 아래는 바이트로(캡처 한 장이 「0 KB」 로 보이면 빈 파일로 읽힌다). */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export interface VocListParams {
  status?: string
  q?: string
  mine?: boolean
  limit?: number
  offset?: number
}

export const vocApi = {
  list: (params: VocListParams = {}) => {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.q) query.set('q', params.q)
    if (params.mine) query.set('mine', 'true')
    if (params.limit) query.set('limit', String(params.limit))
    if (params.offset) query.set('offset', String(params.offset))
    const suffix = query.toString()
    return api.get<Page<VocItem>>(`/voc${suffix ? `?${suffix}` : ''}`)
  },
  get: (id: string) => api.get<VocDetail>(`/voc/${id}`),
  create: (payload: { title: string; body: string; page_path: string | null }) => api.post<VocDetail>('/voc', payload),
  /** 작성자는 다른 사용자가 말을 남기기 전까지, 관리자는 언제나 — 서버가 같은 것을 막는다. */
  update: (id: string, payload: { title?: string; body?: string }) => api.patch<VocDetail>(`/voc/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/voc/${id}`),
  /** 상태를 옮기거나(`status`) 말만 보탠다(`status` 없이). */
  event: (id: string, payload: { status: string | null; note: string | null }) => api.post<VocDetail>(`/voc/${id}/events`, payload),
  /** 이력 한 줄의 말을 고친다 — 시스템 관리자만. */
  updateEvent: (id: string, eventId: string, note: string) => api.patch<VocDetail>(`/voc/${id}/events/${eventId}`, { note }),
  /** 이력 한 줄을 지운다 — 시스템 관리자만. 상태는 남은 이력에서 다시 정해진다. */
  removeEvent: (id: string, eventId: string) => api.delete<VocDetail>(`/voc/${id}/events/${eventId}`),
  /** 파일 하나를 붙인다. 여럿이면 차례로 — 하나가 커서 막혀도 나머지는 붙는다. */
  attach: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return api.postForm<VocDetail>(`/voc/${id}/attachments`, form)
  },
  detach: (id: string, attachmentId: string) => api.delete<VocDetail>(`/voc/${id}/attachments/${attachmentId}`),
  /** 토큰이 있어야 열리므로 `<a href>` 가 아니라 받아서 넘긴다. */
  download: (attachment: VocAttachment) => downloadFile(attachment.url.replace(/^\/api/, ''), attachment.filename),
  /** 고른 건들을 zip 하나로 — 건마다 폴더, `item.json` + `attachments/`. */
  exportZip: async (ids: string[]) => {
    const blob = await postForBlob('/voc/export', { ids })
    const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-')
    const href = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = href
    anchor.download = `voc-export-${stamp}.zip`
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(href), 10_000)
  },
}
