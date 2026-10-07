/**
 * VOC — 앱 안의 의견 게시판. **게시판이고 절차다.**
 *
 * MatNexus 의 VOC 게시판과 같은 형태다(2026-10-08 옮김). 폐쇄망에서는 GitHub 이슈가 창구가 될 수
 * 없고, 여기가 없으면 문제는 구두로만 오가 기록이 남지 않는다. **로그인한 사용자는 다 보고**, 한
 * 건은 번호를 달고 「등록 → 접수 → 처리 중 → 해결 → 종료」 를 거친다. 목록은 그 흐름을 한눈에
 * 보이는 표다 — 누가 언제 냈고, 지금 어디까지 갔고, 마지막으로 누가 손댔나.
 *
 * 상세(`/voc/:id`)에서 본문 · 이력 · 옮기기를 한다. 목록은 여는 자리다. 등록할 때 **직전에 보던
 * 화면 경로**를 함께 담는다(`shared/lib/lastPage`).
 */

import { useState } from 'react'
import type { ReactNode } from 'react'
import { Download, MessageSquare, MessageSquarePlus, Paperclip, X } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { VOC_STATUSES, vocApi } from '@/modules/voc/api'
import type { VocItem } from '@/modules/voc/api'
import { useDisplay } from '@/shared/api/display'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { SearchBox } from '@/shared/components/SearchBox'
import { StatusBadge, statusLabel } from '@/shared/components/StatusBadge'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'
import { Textarea } from '@/shared/components/ui/textarea'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'
import { previousPage } from '@/shared/lib/lastPage'

/** 상세로 넘기는 것 — 글은 등록됐지만 붙이지 못한 파일. 상세가 알린다. */
export interface VocArrival {
  failedFiles?: string[]
}

export default function VocPage() {
  const navigate = useNavigate()
  const PAGE = useDisplay().list_page_size
  const [status, setStatus] = useState('')
  const [mine, setMine] = useState(false)
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const [writing, setWriting] = useState(false)
  // **골라서 내려받는다.** 이슈 트래커 · 보고서로 옮길 때 건마다 열어 복사하지 않게, 고른 만큼
  // zip 하나(건마다 폴더 · item.json · attachments/)로 받는다.
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<Error | null>(null)

  const page = useResource(
    () => vocApi.list({ status: status || undefined, q: q || undefined, mine, limit: PAGE, offset }),
    [status, q, mine, offset, PAGE],
  )
  const rows = page.data?.items ?? []
  const pickedOnPage = rows.filter((item) => picked.has(item.id))
  const allPicked = rows.length > 0 && pickedOnPage.length === rows.length
  const narrowed = Boolean(status || q || mine)

  function narrow(next: { status?: string; mine?: boolean; q?: string }) {
    setOffset(0)
    if (next.status !== undefined) setStatus(next.status)
    if (next.mine !== undefined) setMine(next.mine)
    if (next.q !== undefined) setQ(next.q)
  }

  function togglePick(id: string) {
    setPicked((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function togglePage() {
    setPicked((current) => {
      const next = new Set(current)
      for (const item of rows) {
        if (allPicked) next.delete(item.id)
        else next.add(item.id)
      }
      return next
    })
  }

  async function exportPicked() {
    setExporting(true)
    setExportError(null)
    try {
      await vocApi.exportZip([...picked])
    } catch (caught) {
      setExportError(caught instanceof Error ? caught : new Error('다운로드하지 못했습니다.'))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="VOC"
        description="불편한 점이나 필요한 기능을 등록하십시오. 등록, 접수, 처리 중, 해결, 종료 순서로 처리되며 누가 언제 처리했는지 이력에 남습니다."
        actions={
          <>
            {/* 고른 것이 있을 때만 선다. 늘 서 있으면 무엇을 받는지 알 수 없다. */}
            {picked.size > 0 && (
              <Button variant="outline" disabled={exporting} onClick={() => void exportPicked()}>
                <Download className="size-4" />
                {exporting ? '압축 중…' : `${picked.size}건 다운로드`}
              </Button>
            )}
            <Button onClick={() => setWriting(true)}>
              <MessageSquarePlus className="size-4" />
              의견 등록
            </Button>
          </>
        }
      />

      <ErrorNotice error={page.error ?? exportError} className="mb-4" />

      {/* **상태로 거른다.** 「내가 등록한 것 중 아직 안 된 것」 이 가장 흔한 물음이다. */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1" role="group" aria-label="상태 필터">
          <Chip active={status === ''} onClick={() => narrow({ status: '' })}>
            전체
          </Chip>
          {VOC_STATUSES.map((one) => (
            <Chip key={one} active={status === one} onClick={() => narrow({ status: one })}>
              {statusLabel('voc', one)}
            </Chip>
          ))}
        </div>
        <label className="ml-1 flex items-center gap-1.5 text-sm">
          <input type="checkbox" checked={mine} onChange={(event) => narrow({ mine: event.target.checked })} />
          내가 등록한 의견만
        </label>
        <SearchBox value={q} onChange={(next) => narrow({ q: next.trim() })} placeholder="제목, 내용, 작성자로 검색" className="ml-auto w-full sm:w-64" />
      </div>

      {!page.loading && rows.length === 0 && (
        <EmptyState
          title={narrowed ? '조건에 맞는 의견이 없습니다.' : '등록된 의견이 없습니다.'}
          hint={narrowed ? '필터나 검색어를 바꾸십시오.' : '‘의견 등록’으로 불편한 점이나 필요한 기능을 남기십시오.'}
        />
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <input type="checkbox" aria-label="이 페이지 전체 선택" checked={allPicked} onChange={togglePage} />
                </TableHead>
                <TableHead className="w-16 text-right">번호</TableHead>
                <TableHead>제목</TableHead>
                <TableHead className="w-24">상태</TableHead>
                <TableHead className="w-28">작성자</TableHead>
                <TableHead className="w-40">등록일</TableHead>
                <TableHead className="w-56">최근 처리</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((item) => (
                <Row key={item.id} item={item} picked={picked.has(item.id)} onPick={() => togglePick(item.id)} onOpen={() => navigate(`/voc/${item.id}`)} />
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

      {writing && (
        <WriteDialog
          onClose={() => setWriting(false)}
          onDone={(id, failedFiles) => {
            setWriting(false)
            navigate(`/voc/${id}`, { state: { failedFiles } satisfies VocArrival })
          }}
        />
      )}
    </div>
  )
}

function Row({ item, picked, onPick, onOpen }: { item: VocItem; picked: boolean; onPick: () => void; onOpen: () => void }) {
  return (
    // 행 어디를 눌러도 연다. 키보드는 제목 링크가 받는다.
    <TableRow className="cursor-pointer" onClick={onOpen}>
      <TableCell onClick={(event) => event.stopPropagation()}>
        <input type="checkbox" aria-label={`‘${item.title}’ 선택`} checked={picked} onChange={onPick} />
      </TableCell>
      <TableCell className="text-right tabular-nums">{item.seq}</TableCell>
      <TableCell>
        <Link to={`/voc/${item.id}`} className="font-medium hover:underline" onClick={(event) => event.stopPropagation()}>
          {item.title}
        </Link>
        {/* **말이 오간 건을 보인다.** 등록만 된 것과 진행 중인 것이 같아 보이면 어느 것부터 볼지 모른다. */}
        {item.event_count > 0 && (
          <span className="text-muted-foreground ml-2 inline-flex items-center gap-0.5" title={`이력 ${item.event_count}건`}>
            <MessageSquare className="size-3" aria-hidden />
            <span className="tabular-nums">{item.event_count}</span>
          </span>
        )}
        {item.attachment_count > 0 && (
          <span className="text-muted-foreground ml-2 inline-flex items-center gap-0.5" title={`첨부 ${item.attachment_count}개`}>
            <Paperclip className="size-3" aria-hidden />
            <span className="tabular-nums">{item.attachment_count}</span>
          </span>
        )}
        {item.is_mine && (
          <Badge variant="secondary" className="ml-2">
            본인
          </Badge>
        )}
      </TableCell>
      <TableCell>
        <StatusBadge kind="voc" value={item.status} />
      </TableCell>
      <TableCell>{item.created_by ?? '알 수 없음'}</TableCell>
      <TableCell className="text-sm tabular-nums">{shownDateTime(item.created_at)}</TableCell>
      <TableCell className="text-sm">
        {/* 등록만 된 건은 「최근 처리」 가 등록 그 자체다. 비운다. */}
        {item.status === 'open' && item.event_count === 0 ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <>
            {item.status_by ?? '알 수 없음'} · <span className="tabular-nums">{shownDateTime(item.status_at)}</span>
          </>
        )}
      </TableCell>
    </TableRow>
  )
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-2.5 py-0.5 text-sm transition ${active ? 'border-primary bg-primary/10 text-foreground' : 'hover:bg-muted'}`}
    >
      {children}
    </button>
  )
}

function WriteDialog({ onClose, onDone }: { onClose: () => void; onDone: (id: string, failedFiles: string[]) => void }) {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const from = previousPage()

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const made = await vocApi.create({ title: title.trim(), body, page_path: from })
      // **글이 먼저, 파일은 하나씩.** 하나가 커서 막혀도 글과 나머지 파일은 남는다 — 막힌 것은
      // 상세에서 다시 붙인다.
      const failed: string[] = []
      for (const file of files) {
        try {
          await vocApi.attach(made.id, file)
        } catch {
          failed.push(file.name)
        }
      }
      onDone(made.id, failed)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('의견을 등록하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && !busy && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <DialogHeader>
            <DialogTitle>의견 등록</DialogTitle>
            <DialogDescription>등록하면 번호가 붙고 관리자가 접수하여 처리합니다. 진행 상황은 해당 의견의 이력에 남습니다.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="voc-title">제목</Label>
            <Input id="voc-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="voc-body">내용</Label>
            <Textarea id="voc-body" value={body} rows={6} onChange={(e) => setBody(e.target.value)} />
            {from && (
              <p className="text-muted-foreground text-xs">
                보던 화면 <code className="font-mono">{from}</code>도 함께 기록됩니다.
              </p>
            )}
          </div>
          {/* 캡처 한 장이 글보다 빠르다. 한 파일 25 MB까지 — 큰 형상은 작업으로 올린다. */}
          <div className="space-y-1.5">
            <Label htmlFor="voc-files">첨부 (한 파일 25 MB까지)</Label>
            <Input
              id="voc-files"
              type="file"
              multiple
              onChange={(e) => {
                const chosen = Array.from(e.target.files ?? [])
                setFiles((current) => [...current, ...chosen])
                e.target.value = ''
              }}
            />
            {files.length > 0 && (
              <ul className="space-y-0.5 text-xs">
                {files.map((file, at) => (
                  <li key={`${file.name}-${at}`} className="flex items-center gap-1">
                    <Paperclip className="size-3" aria-hidden />
                    <span className="truncate">{file.name}</span>
                    <span className="text-muted-foreground tabular-nums">{(file.size / 1024).toFixed(0)} KB</span>
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-foreground ml-auto"
                      aria-label={`‘${file.name}’ 제외`}
                      onClick={() => setFiles((current) => current.filter((_, i) => i !== at))}
                    >
                      <X className="size-3" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <ErrorNotice error={error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              취소
            </Button>
            <Button type="submit" disabled={busy || !title.trim() || !body.trim()}>
              {busy ? '등록 중…' : '등록'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
