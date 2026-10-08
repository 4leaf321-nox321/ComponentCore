/**
 * VOC 한 건 — **본문 · 첨부 · 이력 · 옮기기.**
 *
 * 목록(`VocPage`)은 여는 자리고, 절차는 여기서 돈다. 등록부터 지금까지 누가 언제 무슨 말로 상태를
 * 옮겼는지가 시간순으로 흐르고, 아래에 **이 사용자가 지금 갈 수 있는 곳**만 단추로 선다.
 *
 * 화면이 규칙을 외우지 않는다 — 어느 상태에서 어디로 갈 수 있는지, 그때 말이 필요한지는 서버가
 * `allowed` · `note_required` 로 준다. 여기 적어 두면 서버와 어긋나는 날이 오고, 그날 단추는
 * 눌리는데 422 가 난다.
 */

import { useState } from 'react'
import { Download, Paperclip, Pencil, Trash2, X } from 'lucide-react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { fileSize, vocApi } from '@/modules/voc/api'
import type { VocAttachment, VocDetail, VocEvent } from '@/modules/voc/api'
import type { VocArrival } from '@/modules/voc/VocPage'
import { refreshNavBadges } from '@/shared/api/navBadges'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { StatusBadge, statusLabel } from '@/shared/components/StatusBadge'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Textarea } from '@/shared/components/ui/textarea'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

function failure(caught: unknown, fallback: string): Error {
  return caught instanceof Error ? caught : new Error(fallback)
}

export default function VocDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const arrival = (useLocation().state ?? {}) as VocArrival
  const item = useResource(() => vocApi.get(id), [id])
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [removingEvent, setRemovingEvent] = useState<VocEvent | null>(null)
  const [editingEvent, setEditingEvent] = useState<VocEvent | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const detail = item.data
  const reload = () => {
    setError(null)
    item.reload()
    refreshNavBadges() // 상태가 바뀌면 사이드바의 숫자도 바뀐다
  }

  return (
    <div className="mx-auto max-w-4xl">
      <ErrorNotice error={item.error ?? error} className="mb-4" />
      {(arrival.failedFiles?.length ?? 0) > 0 && (
        <ErrorNotice
          className="mb-4"
          error={new Error(`의견은 등록되었지만 첨부하지 못한 파일이 있습니다: ${arrival.failedFiles?.join(', ')}. 아래 ‘파일 첨부’로 다시 첨부하십시오.`)}
        />
      )}

      {detail && (
        <>
          <PageHeader
            back={{ to: '/voc', label: 'VOC 목록' }}
            title={
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-muted-foreground tabular-nums">#{detail.seq}</span>
                {detail.title}
                <StatusBadge kind="voc" value={detail.status} />
              </span>
            }
            description={
              <>
                {detail.created_by ?? '알 수 없음'} · {shownDateTime(detail.created_at)}
                {detail.page_path && (
                  <>
                    {' '}
                    · 보던 화면 <code className="font-mono">{detail.page_path}</code>
                  </>
                )}
              </>
            }
            actions={
              detail.can_edit && (
                <>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                    <Pencil className="size-3.5" />
                    수정
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setDeleting(true)}>
                    <Trash2 className="size-3.5" />
                    삭제
                  </Button>
                </>
              )
            }
          />

          <section className="mb-6 rounded-md border p-4">
            <p className="text-sm whitespace-pre-wrap">{detail.body}</p>
          </section>

          <Attachments detail={detail} onChanged={reload} onError={setError} />

          <section className="mb-6">
            <h2 className="mb-2 font-medium">이력</h2>
            <Timeline
              events={detail.events}
              onRemove={detail.can_delete_events ? setRemovingEvent : undefined}
              onEdit={detail.can_delete_events ? setEditingEvent : undefined}
            />
          </section>

          <ActionBox detail={detail} onDone={reload} />

          {editing && <EditDialog item={detail} onClose={() => setEditing(false)} onDone={() => { setEditing(false); reload() }} />}
          {editingEvent && (
            <EditEventDialog itemId={detail.id} event={editingEvent} onClose={() => setEditingEvent(null)} onDone={() => { setEditingEvent(null); reload() }} />
          )}

          {/* **잘못 옮긴 줄을 지운다** — 관리자만. 지우면 상태는 남은 이력의 마지막 변경으로 돌아간다. */}
          <ConfirmDialog
            open={removingEvent !== null}
            title="이력 삭제"
            confirmLabel="삭제"
            destructive
            description={
              removingEvent && (
                <>
                  <p>
                    <b>{eventTitle(removingEvent)}</b>
                    {removingEvent.note && <> : {removingEvent.note}</>}
                  </p>
                  <p className="text-muted-foreground mt-2">상태를 변경한 이력이면 이 의견의 상태는 남은 이력의 마지막 변경으로 돌아갑니다.</p>
                </>
              )
            }
            onClose={() => setRemovingEvent(null)}
            onConfirm={async () => {
              if (!removingEvent) return
              await vocApi.removeEvent(detail.id, removingEvent.id)
              reload()
            }}
          />

          {/* **무엇이 사라지는지 말한다.** 기록을 남기려고 있는 게시판이다. */}
          <ConfirmDialog
            open={deleting}
            title="의견 삭제"
            confirmLabel="삭제"
            destructive
            description={
              <>
                <p>
                  <b>
                    #{detail.seq} ‘{detail.title}’
                  </b>
                  이(가) 이력 {detail.events.length}건, 첨부 {detail.attachments.length}개와 함께 목록에서 사라집니다.
                </p>
                <p className="text-muted-foreground mt-2">처리가 끝난 의견이면 삭제하는 대신 종료 상태로 두십시오.</p>
              </>
            }
            onClose={() => setDeleting(false)}
            onConfirm={async () => {
              await vocApi.remove(detail.id)
              refreshNavBadges()
              navigate('/voc')
            }}
          />
        </>
      )}
    </div>
  )
}

function eventTitle(event: VocEvent): string {
  if (event.from_status === null) return '등록'
  if (event.from_status === event.to_status) return '댓글'
  return `상태 변경: ${statusLabel('voc', event.to_status)}`
}

/**
 * 이력 — 등록 · 상태 변경 · 댓글이 시간순으로. **상태가 바뀐 줄이 눈에 띈다** — 댓글 사이에서
 * 「언제 해결로 갔나」 를 찾는 것이 이 목록의 용도다.
 */
function Timeline({ events, onRemove, onEdit }: { events: VocEvent[]; onRemove?: (event: VocEvent) => void; onEdit?: (event: VocEvent) => void }) {
  return (
    <ol className="space-y-2" aria-label="이력">
      {events.map((one) => {
        const registered = one.from_status === null
        const moved = !registered && one.from_status !== one.to_status
        return (
          <li key={one.id} className="flex gap-3 rounded-md border p-3 text-sm">
            <div className="text-muted-foreground w-40 shrink-0">
              <p className="tabular-nums">{shownDateTime(one.at)}</p>
              <p className="mt-0.5 truncate">{one.by ?? '알 수 없음'}</p>
            </div>
            <div className="min-w-0 flex-1">
              {registered ? (
                <StatusBadge kind="voc" value="open" />
              ) : moved ? (
                <span className="inline-flex items-center gap-1.5">
                  <span className="text-muted-foreground text-xs">상태 변경</span>
                  <StatusBadge kind="voc" value={one.to_status} />
                </span>
              ) : (
                <Badge variant="secondary">댓글</Badge>
              )}
              {one.note && <p className="mt-1.5 whitespace-pre-wrap">{one.note}</p>}
            </div>
            {onEdit && !registered && (
              <Button variant="ghost" size="icon" className="size-8 shrink-0" aria-label="이력 수정" title="이 이력의 내용을 수정합니다." onClick={() => onEdit(one)}>
                <Pencil className="size-4" />
              </Button>
            )}
            {onRemove && !registered && (
              <Button variant="ghost" size="icon" className="size-8 shrink-0" aria-label="이력 삭제" title="잘못 변경한 상태를 되돌릴 때 이 이력을 삭제합니다." onClick={() => onRemove(one)}>
                <Trash2 className="size-4" />
              </Button>
            )}
          </li>
        )
      })}
    </ol>
  )
}

/**
 * 옮기거나 말을 보탠다. 단추는 서버가 말한 것만 선다. **말이 필요한 곳은 말 없이는 안 눌린다** —
 * 「해결」 만 찍힌 건은 무엇이 바뀌었는지 아무도 모르고, 이유 없는 「반려」 는 작성자가 다시 낼
 * 수밖에 없다.
 */
function ActionBox({ detail, onDone }: { detail: VocDetail; onDone: () => void }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const trimmed = note.trim()

  async function send(status: string | null) {
    setBusy(true)
    setError(null)
    try {
      await vocApi.event(detail.id, { status, note: trimmed || null })
      setNote('')
      onDone()
    } catch (caught) {
      setError(failure(caught, '등록하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-md border p-4">
      <Label htmlFor="voc-note" className="mb-1.5 block">
        댓글
      </Label>
      <Textarea
        id="voc-note"
        value={note}
        rows={3}
        onChange={(event) => setNote(event.target.value)}
        placeholder={
          detail.allowed.length > 0
            ? '조치 내용이나 사유를 입력하십시오. 상태를 변경하면 함께 기록됩니다.'
            : '덧붙일 내용을 입력하십시오. 상태는 관리자와 작성자가 변경합니다.'
        }
      />
      <ErrorNotice error={error} className="mt-2" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {detail.allowed.map((status) => {
          const needs = detail.note_required.includes(status)
          return (
            <Button
              key={status}
              size="sm"
              variant={status === 'resolved' || status === 'closed' ? 'default' : 'outline'}
              disabled={busy || (needs && !trimmed)}
              title={needs && !trimmed ? '내용을 입력해야 변경할 수 있습니다.' : undefined}
              onClick={() => void send(status)}
            >
              {detail.allowed_labels[status] ?? status}
            </Button>
          )
        })}
        <Button size="sm" variant="ghost" className="ml-auto" disabled={busy || !trimmed} onClick={() => void send(null)}>
          댓글 등록
        </Button>
      </div>
    </section>
  )
}

/** 의견 수정 — **제목과 본문만.** 상태는 절차가 정하고, 보던 화면은 등록 당시의 사실이다. */
function EditDialog({ item, onClose, onDone }: { item: VocDetail; onClose: () => void; onDone: () => void }) {
  const [title, setTitle] = useState(item.title)
  const [body, setBody] = useState(item.body)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await vocApi.update(item.id, { title: title.trim(), body })
      onDone()
    } catch (caught) {
      setError(failure(caught, '수정하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && !busy && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>의견 수정</DialogTitle>
          <DialogDescription>다른 사용자가 댓글을 남기기 전까지만 수정할 수 있습니다.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="voc-edit-title">제목</Label>
            <Input id="voc-edit-title" value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="voc-edit-body">내용</Label>
            <Textarea id="voc-edit-body" value={body} rows={6} onChange={(event) => setBody(event.target.value)} />
          </div>
        </div>
        <ErrorNotice error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button disabled={busy || !title.trim() || !body.trim()} onClick={() => void submit()}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 이력 한 줄의 내용 수정 — 관리자만. **상태 변경은 건드리지 않는다.** 잘못 옮긴 것은 지우고 다시
 * 옮기는 것이지 글자로 바꾸는 것이 아니다 — 이력이 곧 절차의 기록이다.
 */
function EditEventDialog({ itemId, event, onClose, onDone }: { itemId: string; event: VocEvent; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState(event.note ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const moved = event.from_status !== event.to_status

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await vocApi.updateEvent(itemId, event.id, note)
      onDone()
    } catch (caught) {
      setError(failure(caught, '수정하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && !busy && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>이력 수정</DialogTitle>
          <DialogDescription>
            {moved ? `‘${statusLabel('voc', event.to_status)}’ 상태 변경 이력의 내용만 수정합니다.` : '댓글의 내용을 수정합니다.'} 상태 변경은 바뀌지 않습니다. 잘못 변경했으면 이 이력을 삭제하고
            다시 변경하십시오.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="voc-event-note">내용</Label>
          <Textarea id="voc-event-note" value={note} rows={5} onChange={(e) => setNote(e.target.value)} />
        </div>
        <ErrorNotice error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button disabled={busy || !note.trim()} onClick={() => void submit()}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 첨부 — 다운로드는 누구나, 첨부 · 삭제는 작성자와 관리자(`can_attach`). 다운로드는 `<a href>` 가
 * 아니다 — 토큰은 메모리에만 있어 링크에 안 실린다(`downloadFile`).
 */
function Attachments({ detail, onChanged, onError }: { detail: VocDetail; onChanged: () => void; onError: (error: Error) => void }) {
  const [busy, setBusy] = useState(false)
  const [removing, setRemoving] = useState<VocAttachment | null>(null)
  const attachments = detail.attachments

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    try {
      await action()
      onChanged()
    } catch (caught) {
      onError(failure(caught, '처리하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  if (attachments.length === 0 && !detail.can_attach) return null

  return (
    <section className="mb-6">
      <h2 className="mb-2 flex items-center gap-1 font-medium">
        <Paperclip className="size-4" aria-hidden />
        첨부
        {attachments.length > 0 && <span className="text-muted-foreground text-sm tabular-nums">{attachments.length}</span>}
      </h2>
      {attachments.length > 0 && (
        <ul className="divide-y rounded-md border">
          {attachments.map((one) => (
            <li key={one.id} className="flex items-center gap-2 px-3 py-2 text-sm">
              <button type="button" className="inline-flex items-center gap-1 font-medium hover:underline" disabled={busy} onClick={() => void run(() => vocApi.download(one))}>
                <Download className="size-3.5" aria-hidden />
                {one.filename}
              </button>
              <span className="text-muted-foreground tabular-nums">{fileSize(one.size)}</span>
              <span className="text-muted-foreground ml-auto text-xs">
                {one.created_by ?? '알 수 없음'} · {shownDateTime(one.created_at)}
              </span>
              {detail.can_attach && (
                <Button size="sm" variant="ghost" className="h-6 px-1" disabled={busy} aria-label={`‘${one.filename}’ 삭제`} onClick={() => setRemoving(one)}>
                  <X className="size-3.5" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {detail.can_attach && (
        <label className="text-muted-foreground mt-2 inline-flex cursor-pointer items-center gap-1 text-xs hover:underline">
          <Paperclip className="size-3" aria-hidden />
          파일 첨부 (한 파일 25 MB까지)
          <input
            type="file"
            multiple
            className="sr-only"
            aria-label="파일 첨부"
            disabled={busy}
            onChange={(e) => {
              const chosen = Array.from(e.target.files ?? [])
              e.target.value = ''
              if (chosen.length === 0) return
              void run(async () => {
                for (const file of chosen) await vocApi.attach(detail.id, file)
              })
            }}
          />
        </label>
      )}
      <ConfirmDialog
        open={removing !== null}
        title="첨부 파일 삭제"
        confirmLabel="삭제"
        destructive
        description={removing && <p>‘{removing.filename}’을(를) 삭제합니다. 파일은 저장소에서도 지워집니다.</p>}
        onClose={() => setRemoving(null)}
        onConfirm={async () => {
          if (!removing) return
          await vocApi.detach(detail.id, removing.id)
          onChanged()
        }}
      />
    </section>
  )
}
