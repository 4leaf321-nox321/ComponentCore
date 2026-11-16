/**
 * 공지 API — **게시판이다**: 목록은 쪽으로 나가고, 한 건은 주소로 연다. MatNexus 의 공지를
 * 옮겼다(2026-11-16). CompCore 는 판마다 업데이트 안내가 배포에 실려 와 초안으로 들어온다.
 */

import { api } from '@/shared/api/client'
import { refreshNavBadges } from '@/shared/api/navBadges'
import type { Page } from '@/shared/api/types'

/*
 * 서버의 `notices/schemas.py` 와 같은 모양을 **손으로** 적는다. 생성 타입(`@/shared/api/schema`)은
 * 커밋하지 않는 생성물이라 릴리스 번들 빌드에는 없다 — MatNexus 에서 옮긴 첫 판이 그것을 가져와
 * v0.27.0 CI 의 번들 빌드가 떨어졌다(2026-11-17, `objects/api.ts` 의 v0.4.50 과 같은 일). 이 PC
 * 에는 파일이 있어 로컬 검사가 못 봤다.
 */

/** 공지 한 건 — `NoticeOut`. */
export interface Notice {
  id: string
  title: string
  body: string
  is_published: boolean
  is_popup: boolean
  created_at: string
  published_at: string | null
  /** 이 사용자가 읽었나. */
  is_read: boolean
  created_by?: string | null
  /** 판마다 배포에 실려 온 업데이트 안내인가(씨앗에서 들어왔다). */
  from_release?: boolean
}
export type NoticePage = Page<Notice>
export interface NoticeUnread {
  unread: number
}
interface CreateRequest {
  title: string
  body: string
  is_popup?: boolean
  is_published?: boolean
}
interface UpdateRequest {
  title?: string | null
  body?: string | null
  is_popup?: boolean | null
  is_published?: boolean | null
}

/**
 * **읽음이 바뀌었다** — 사이드바의 수를 곧바로 다시 센다. 주기만 기다리면 공지를 읽고 나왔는데
 * 수가 2분 동안 그대로다. 읽음을 적는 자리가 여럿이라(상세 · 로그인 팝업 · 「모두 읽음」) 적는
 * 함수가 직접 알린다 — 화면마다 알리게 두면 한 곳은 빠진다.
 */
function announceRead(): void {
  refreshNavBadges()
}

export interface NoticeListParams {
  /** 제목·내용으로 찾는다. */
  q?: string
  /** 안 읽은 것만. */
  unread?: boolean
  /** 초안만(관리자) — 「초안 모두 발행」 의 수. */
  draft?: boolean
  limit?: number
  offset?: number
}

export const noticesApi = {
  list: (params: NoticeListParams = {}) => {
    const query = new URLSearchParams()
    if (params.q) query.set('q', params.q)
    if (params.unread) query.set('unread', 'true')
    if (params.draft) query.set('draft', 'true')
    if (params.limit) query.set('limit', String(params.limit))
    if (params.offset) query.set('offset', String(params.offset))
    const suffix = query.toString()
    return api.get<NoticePage>(`/notices${suffix ? `?${suffix}` : ''}`)
  },
  get: (id: string) => api.get<Notice>(`/notices/${id}`),
  popup: () => api.get<Notice[]>('/notices/popup'),
  create: (payload: CreateRequest) => api.post<Notice>('/notices', payload),
  update: (id: string, payload: UpdateRequest) => api.patch<Notice>(`/notices/${id}`, payload),
  /** **「내리기」 와 다른 일이다.** 잘못 올린 것을 잠깐 감추려면 발행을 끄면 되고
   *  (`update({ is_published: false })`) 그때 내용과 발행 시각은 남는다. 이것은 그 공지가
   *  있었다는 사실까지 없앤다. */
  remove: (id: string) => api.delete<void>(`/notices/${id}`),
  read: (id: string) => api.post<void>(`/notices/${id}/read`).then(announceRead),
  /** 안 읽은 공지 수 — **발행된 것만** 센다(초안은 안 센다). */
  unreadCount: () => api.get<NoticeUnread>('/notices/unread-count'),
  /** 안 읽은 공지를 모두 읽음으로. 처음 들어온 사람에게는 쌓인 공지가 전부 새 글이다. */
  readAll: () =>
    api.post<NoticeUnread>('/notices/read-all').then((result) => {
      announceRead()
      return result
    }),
  /** 초안을 **모두** 발행한다(관리자) — 첫 배포에 지난 판의 안내가 수십 건 초안으로 들어온다. */
  publishDrafts: () =>
    api.post<{ published: number }>('/notices/publish-drafts').then((result) => {
      refreshNavBadges()
      return result
    }),
}

/**
 * 누가 올렸나. **배포에 실려 온 안내**(`seeds/notices`)는 쓴 사람이 없다 — 「알 수 없음」 이라
 * 적으면 누가 몰래 올린 글처럼 읽힌다.
 */
export function writerOf(notice: Pick<Notice, 'created_by' | 'from_release'>): string {
  return notice.created_by ?? (notice.from_release ? '배포 안내' : '알 수 없음')
}
