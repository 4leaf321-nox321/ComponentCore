/**
 * 공지 한 건 — **읽고, 관리자는 여기서 고치고 지운다**(MatNexus 와 같다).
 *
 * 목록(`NoticesPage`)은 여는 자리다 — VOC 와 같은 짜임이다. **열면 읽음으로 남긴다**
 * (`POST …/read`). 목록의 「새 글」 과 사이드바의 수가 그때 꺼진다. 읽음을 여는 요청(GET)에 묶지
 * 않은 까닭은 서버 쪽에 적었다 — 미리 불러 두는 화면이 남의 읽음을 대신 찍으면 안 된다. 읽음
 * 기록이 실패해도 읽는 것은 막지 않는다.
 */

import { useEffect, useState } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { NoticeBody } from '@/modules/notices/NoticeBody'
import { NoticeDialog } from '@/modules/notices/NoticeDialog'
import { noticesApi, writerOf } from '@/modules/notices/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'
import { shownDate } from '@/shared/lib/datetime'

export default function NoticeDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const admin = isSystemAdmin(user)
  const notice = useResource(() => noticesApi.get(id), [id])
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const item = notice.data
  // 발행된 것만 — 초안은 읽음을 셀 글이 아니다.
  const unreadId = item && item.is_published && !item.is_read ? item.id : null

  useEffect(() => {
    if (!unreadId) return
    noticesApi.read(unreadId).catch(() => {
      // 읽음 기록이 실패하면 목록에 「새 글」 이 남을 뿐이다 — 읽는 것은 막지 않는다.
    })
  }, [unreadId])

  return (
    // 읽는 화면이라 폭을 좁힌다 — 한 줄이 너무 길면 눈이 다음 줄을 놓친다.
    <div className="mx-auto max-w-4xl">
      <PageHeader
        back={{ to: '/notices', label: '공지 목록' }}
        title={
          item ? (
            <span className="inline-flex flex-wrap items-center gap-2">
              {item.title}
              {!item.is_published && (
                <Badge variant="outline" className="text-muted-foreground">
                  초안
                </Badge>
              )}
              {item.is_popup && <Badge variant="outline">팝업</Badge>}
            </span>
          ) : (
            '공지'
          )
        }
        description={item ? `${writerOf(item)} · ${shownDate(item.published_at ?? item.created_at)}` : undefined}
        actions={
          admin &&
          item && (
            <>
              <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                <Pencil className="size-3.5" />
                편집
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setDeleting(true)}>
                <Trash2 className="size-3.5" />
                삭제
              </Button>
            </>
          )
        }
      />

      <ErrorNotice error={notice.error} className="mb-4" />

      {item && (
        <>
          <section className="mb-6 rounded-md border p-4">
            <NoticeBody text={item.body} />
          </section>

          <NoticeDialog
            open={editing}
            notice={item}
            onClose={() => setEditing(false)}
            onDone={() => {
              setEditing(false)
              notice.reload()
            }}
          />

          {/* **「내리기」 를 함께 말한다.** 잘못 올린 것을 잠깐 감추는 것과 아예 없애는 것은 다른
              일인데, 사람은 그 자리에서 삭제부터 누른다. */}
          <ConfirmDialog
            open={deleting}
            title="공지를 지웁니다"
            confirmLabel="삭제"
            destructive
            description={
              <>
                <b>{item.title}</b> 과 그 읽음 기록이 사라집니다. 배포에 실려 온 안내는 다음 배포에도 다시 들어오지 않습니다.
                <p className="text-muted-foreground mt-2">
                  잠깐 감추려는 것이면 지우지 말고 <b>편집에서 발행을 끄십시오</b> — 내용과 발행 시각이 남습니다.
                </p>
              </>
            }
            onClose={() => setDeleting(false)}
            onConfirm={async () => {
              await noticesApi.remove(item.id)
              navigate('/notices')
            }}
          />
        </>
      )}
    </div>
  )
}
