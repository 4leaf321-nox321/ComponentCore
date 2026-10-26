/**
 * 태그 API — 작업 · 부품 · 지그에 **온톨로지의 객체**를 붙인다(백엔드 `tagging`, ADR 0011).
 *
 * 타입을 고르고 그 안에서 고르거나, 「늘리기」 타입이면 이름을 쳐서 새로 만든다. 타입을 안
 * 고르면 「일반 태그」 다. 목록의 `tags`(이름 목록) · `?tag=` 거르개는 그대로다.
 */

import { api } from '@/shared/api/client'

/** 타입을 안 고르고 붙인 이름이 가는 곳 — 「일반 태그」(백엔드 `DEFAULT_TAG_TYPE`). */
export const DEFAULT_TAG_TYPE = 'cc_tag'

/** 태그가 붙는 원 표 — API 경로에 그대로 쓴다. */
export type TagTarget = 'work' | 'part' | 'jig' | 'template'

export interface TagItem {
  object_id: string
  label: string
  type_slug: string
  type_label: string
}

export interface TagCandidate extends TagItem {
  /** 이 객체를 태그로 단 작업 · 부품 · 지그 수 — 많이 쓴 것이 앞이다. */
  uses: number
}

export interface TagUse extends TagItem {
  /** 이 태그가 붙은 수(지운 것 빼고) — 거르개의 칩 곁에 적는다. */
  uses: number
}

export interface TagType {
  slug: string
  label: string
  icon: string
  /** pick — 있는 것에서 고르기만, grow — 붙이는 사람 누구나 새로 만든다. */
  mode: 'pick' | 'grow'
  can_create: boolean
  note: string
  is_default: boolean
}

export type TagMode = 'off' | 'pick' | 'grow'

export interface TagSetting {
  slug: string
  label: string
  mode: TagMode
  managed_by: string
  entry_policy: string
  is_default: boolean
  /** 「늘리기」 인데 다른 규칙(입력 정책 · 허브 관리 …)이 만들기를 막을 때 그 까닭. */
  note: string
}

export interface SimilarTag {
  object_id: string
  label: string
  key: string | null
  /** 붙은 행 수 — 합치면 남길 것으로 옮겨 간다. */
  uses: number
  created_at: string
}

/** 이름이 띄어쓰기 · 이음표 · 대소문자만 다른 태그 한 묶음 — 같은 타입 안에서만. */
export interface SimilarGroup {
  type_slug: string
  type_label: string
  /** 남길 것의 추천 — 많이 쓴 것 → 식별자가 있는 것 → 먼저 만든 것. 맨 앞 줄이다. */
  keep: string
  members: SimilarTag[]
}

export interface SimilarTags {
  groups: SimilarGroup[]
  /** 훑지 않은 타입(너무 큼) · 합칠 수 없는 타입(바깥 원천이 관리). */
  notes: string[]
}

export interface MergedTags {
  into: TagItem
  merged: number
  /** 남길 것으로 옮긴 선. */
  moved: number
  /** 버린 선 — 그 행에 남길 것이 이미 붙어 있었다. */
  dropped: number
}

export interface AddTag {
  object_id?: string
  type_slug?: string
  label?: string
}

export const tagsApi = {
  types: () => api.get<TagType[]>('/tags/types'),
  candidates: (slug: string, q: string, limit = 20) => {
    const query = new URLSearchParams({ q, limit: String(limit) })
    return api.get<TagCandidate[]>(`/tags/types/${encodeURIComponent(slug)}/objects?${query}`)
  },
  of: (target: TagTarget, id: string) => api.get<TagItem[]>(`/tags/${target}/${id}`),
  add: (target: TagTarget, id: string, body: AddTag) => api.post<TagItem[]>(`/tags/${target}/${id}`, body),
  remove: (target: TagTarget, id: string, objectId: string) =>
    api.delete<TagItem[]>(`/tags/${target}/${id}/${objectId}`),
  /** 쓰인 태그 객체를 타입별로 — 목록의 거르개(`tag_id`). 작업은 내 것(관리자는 `owner`). */
  used: (target: TagTarget, owner?: string) =>
    api.get<TagUse[]>(owner ? `/tags/used/${target}?${new URLSearchParams({ owner })}` : `/tags/used/${target}`),
  settings: () => api.get<TagSetting[]>('/tags/settings'),
  setMode: (slug: string, mode: TagMode) =>
    api.put<TagSetting[]>(`/tags/settings/${encodeURIComponent(slug)}`, { mode }),
  /** (관리자) 이름이 비슷한 태그 묶음. */
  similar: () => api.get<SimilarTags>('/tags/similar'),
  /** (관리자) `merge` 를 `into` 에 합친다 — 온톨로지의 객체 합치기 그대로. */
  merge: (into: string, merge: string[]) => api.post<MergedTags>('/tags/merge', { into, merge }),
}
