/**
 * 공지 — **게시판이다.** 읽기는 모두, 쓰기는 시스템 관리자. MatNexus 의 공지를 옮겼다(2026-11-16).
 *
 * 폐쇄망에서 **배포 없이 안내를 갱신하는 수단**이고, **판마다 무엇이 바뀌었나**가 여기 선다 —
 * 업데이트 안내는 배포에 실려 와(`backend/seeds/notices`) 초안으로 들어오고, 관리자가 읽고
 * 발행한다. 첫 배포에는 지난 판의 안내가 수십 건이라 **「초안 모두 발행」** 을 둔다(CompCore).
 *
 * VOC 와 같은 짜임이다(번호 · 찾기 · 쪽 넘기기 · 한 건 상세). **안 읽은 글이 보인다** — 굵게 적고
 * 「새 글」 을 붙인다. 사이드바에도 그 수가 선다(`navBadges`). **「모두 읽음」** — 처음 들어온
 * 사람에게는 쌓인 공지가 전부 새 글이다. **「내용 전체 복사」** — 거른 것 그대로 글 하나로.
 */

import { useState } from 'react'
import { CheckCheck, Copy, Plus, Send } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { NoticeCopyDialog } from '@/modules/notices/NoticeCopyDialog'
import { NoticeDialog } from '@/modules/notices/NoticeDialog'
import { noticesApi, writerOf } from '@/modules/notices/api'
import { useDisplay } from '@/shared/api/display'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { SearchBox } from '@/shared/components/SearchBox'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { shownDate } from '@/shared/lib/datetime'

export default function NoticesPage() {
  const { user } = useAuth()
  const admin = isSystemAdmin(user)
  const navigate = useNavigate()
  const PAGE = useDisplay().list_page_size
  const [q, setQ] = useState('')
  const [unread, setUnread] = useState(false)
  const [offset, setOffset] = useState(0)
  const [writing, setWriting] = useState(false)
  const [copying, setCopying] = useState(false)
  const [publishing, setPublishing] = useState(false)

  const page = useResource(() => noticesApi.list({ q: q || undefined, unread, limit: PAGE, offset }), [q, unread, offset, PAGE])
  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0
  // 이 쪽에 안 보이는 안 읽은 글도 센다 — 목록은 쪽으로 잘려 있다.
  const unreadCount = useResource(() => noticesApi.unreadCount(), [])
  const unreadTotal = unreadCount.data?.unread ?? 0
  // 초안 수 — 관리자에게만. 찾기와 상관없이 **전부** 센다(「모두 발행」 은 전부를 낸다).
  const drafts = useResource(async () => (admin ? (await noticesApi.list({ draft: true, limit: 1 })).total : 0), [admin])
  const draftCount = drafts.data ?? 0
  const [marking, setMarking] = useState(false)
  const [markError, setMarkError] = useState<Error | null>(null)
  const narrowed = Boolean(q) || unread

  async function readAll() {
    setMarking(true)
    setMarkError(null)
    try {
      await noticesApi.readAll()
      page.reload()
      unreadCount.reload()
    } catch (caught) {
      setMarkError(caught instanceof Error ? caught : new Error('읽음으로 바꾸지 못했습니다.'))
    } finally {
      setMarking(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="공지"
        description="판마다 바뀐 내용과 운영 안내를 알립니다. 업데이트 안내는 배포와 함께 올라옵니다."
        actions={
          admin && (
            <>
              {draftCount > 0 && (
                <Button variant="outline" onClick={() => setPublishing(true)}>
                  <Send className="size-4" />
                  초안 모두 발행 ({draftCount})
                </Button>
              )}
              <Button onClick={() => setWriting(true)}>
                <Plus className="size-4" />
                공지 작성
              </Button>
            </>
          )
        }
      />

      <ErrorNotice error={page.error ?? markError} className="mb-4" />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={unread}
            onChange={(event) => {
              setOffset(0)
              setUnread(event.target.checked)
            }}
          />
          안 읽은 것만
        </label>
        {unreadTotal > 0 && (
          <Button size="sm" variant="outline" disabled={marking} onClick={() => void readAll()}>
            <CheckCheck className="size-4" />
            모두 읽음 ({unreadTotal})
          </Button>
        )}
        {total > 0 && (
          <Button size="sm" variant="outline" onClick={() => setCopying(true)}>
            <Copy className="size-4" />
            {/* 걸렀으면 「전체」 가 아니다 — 무엇을 복사하는지 단추가 말한다. */}
            {narrowed ? `찾은 ${total}건 복사` : '내용 전체 복사'}
          </Button>
        )}
        <SearchBox
          value={q}
          onChange={(next) => {
            setOffset(0)
            setQ(next.trim())
          }}
          placeholder="제목·내용으로 찾기"
          className="ml-auto w-full sm:w-64"
        />
      </div>

      {!page.loading && rows.length === 0 && (
        <EmptyState
          title={narrowed ? '거른 조건에 맞는 공지가 없습니다.' : '공지가 없습니다.'}
          hint={narrowed ? '검색어나 「안 읽은 것만」 을 바꾸십시오.' : undefined}
        />
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16 text-right">번호</TableHead>
                <TableHead>제목</TableHead>
                <TableHead className="w-32">올린 사람</TableHead>
                <TableHead className="w-32">올린 날짜</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((notice, at) => (
                // 줄 어디를 눌러도 연다. 키보드는 제목 링크가 받는다.
                <TableRow key={notice.id} className="cursor-pointer" onClick={() => navigate(`/notices/${notice.id}`)}>
                  {/* **번호는 게시판의 차례다** — 가장 오래된 것이 1. 저장된 값이 아니라 지우면 당겨진다. */}
                  <TableCell className="text-right tabular-nums">{total - offset - at}</TableCell>
                  <TableCell>
                    <Link
                      to={`/notices/${notice.id}`}
                      // 굵게는 **알릴 글**에만 — 초안은 아직 아무에게도 안 알렸다.
                      className={`hover:underline ${notice.is_read || !notice.is_published ? '' : 'font-semibold'}`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      {notice.title}
                    </Link>
                    {!notice.is_read && notice.is_published && <Badge className="ml-2">새 글</Badge>}
                    {!notice.is_published && (
                      <Badge variant="outline" className="text-muted-foreground ml-2">
                        초안
                      </Badge>
                    )}
                    {notice.is_popup && (
                      <Badge variant="outline" className="ml-2">
                        팝업
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>{writerOf(notice)}</TableCell>
                  <TableCell className="text-sm tabular-nums">{shownDate(notice.published_at ?? notice.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {page.data && (
        <div className="mt-3">
          <Pagination total={page.data.total} limit={page.data.limit} offset={offset} onChange={setOffset} />
        </div>
      )}

      <NoticeCopyDialog open={copying} q={q} unread={unread} onClose={() => setCopying(false)} />

      <NoticeDialog
        open={writing}
        notice={null}
        onClose={() => setWriting(false)}
        onDone={(saved) => {
          setWriting(false)
          navigate(`/notices/${saved.id}`)
        }}
      />

      <ConfirmDialog
        open={publishing}
        title="초안을 모두 발행합니다"
        confirmLabel="모두 발행"
        description={
          <>
            초안 {draftCount}건이 모든 사용자에게 보입니다. 배포에 실려 온 업데이트 안내는 그 판의 날짜로 섭니다.
            <p className="text-muted-foreground mt-2">팝업은 켜지 않습니다. 내보내기 전에 고칠 글이 있으면 먼저 열어 고치십시오.</p>
          </>
        }
        onClose={() => setPublishing(false)}
        onConfirm={async () => {
          await noticesApi.publishDrafts()
          page.reload()
          unreadCount.reload()
          drafts.reload()
        }}
      />
    </div>
  )
}
