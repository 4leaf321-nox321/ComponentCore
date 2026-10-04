/**
 * 주소의 `:id` 가 바뀌면 **화면을 새로 짓는다.** 같은 경로 안에서 다른 작업으로 가면(유사 형상 카드의
 * 링크) React 가 화면을 그대로 두어, 고른 버전 같은 상태가 앞 작업의 것으로 남았다 — 그대로 「수정 →
 * 저장」 하면 앞 작업의 도면이 다른 작업의 새 버전이 됐다(2026-10-04 점검).
 */

import { Fragment } from 'react'
import type { ReactElement } from 'react'
import { useParams } from 'react-router-dom'

export function ById({ children }: { children: ReactElement }) {
  const { id = '' } = useParams<{ id: string }>()
  return <Fragment key={id}>{children}</Fragment>
}
