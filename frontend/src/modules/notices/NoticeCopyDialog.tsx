/**
 * 공지 내용 복사 — **모아서 보여 주고, 「복사」 를 누르면 복사한다** (MatNexus 와 같다).
 *
 * 사내망에서 HTTP 로 열면 복사는 **누른 그 순간**에만 된다(`shared/lib/clipboard`). 단추를 누르고
 * 서버에서 공지를 다 받아 온 뒤에 복사하면 그 순간이 지나 조용히 실패한다. 그래서 먼저 모아
 * 보여 주고, 「복사」 는 다 모인 뒤에 누른다. 글이 보이므로 복사가 막힌 브라우저에서도 직접 고를
 * 수 있다. 찾기 · 「안 읽은 것만」 으로 걸러 두었으면 그것만 모은다(화면과 같은 것이 복사된다).
 */

import { useMemo, useState } from 'react'
import { Check, Copy } from 'lucide-react'

import { noticesApi } from '@/modules/notices/api'
import { noticesAsText } from '@/modules/notices/copyAll'
import { fetchAll } from '@/shared/api/paging'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { useResource } from '@/shared/hooks/useResource'
import { copyText } from '@/shared/lib/clipboard'

export function NoticeCopyDialog({ open, q, unread, onClose }: { open: boolean; q: string; unread: boolean; onClose: () => void }) {
  const collected = useResource(async () => {
    if (!open) return null
    const page = await fetchAll((limit, offset) => noticesApi.list({ q: q || undefined, unread, limit, offset }))
    return { page, at: new Date() }
  }, [open, q, unread])
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)

  const page = collected.data?.page ?? null
  const text = useMemo(
    () => (collected.data ? noticesAsText(collected.data.page.items, { total: collected.data.page.total, q: q || undefined, unread, at: collected.data.at }) : ''),
    [collected.data, q, unread],
  )
  const filtered = Boolean(q) || unread

  /** 닫을 때 지난번 복사 결과를 지운다 — 다시 열었을 때 옛 「막았습니다」 가 남지 않게. */
  function close() {
    setCopied(null)
    onClose()
  }

  async function copy() {
    if (!text) return
    // **기다리지 않고 바로** — 글은 이미 모여 있다. 누른 그 순간에 복사해야 HTTP 에서도 된다.
    // CompCore 의 `copyText` 는 못 하면 던진다(MatNexus 는 false 를 돌려준다).
    try {
      await copyText(text)
    } catch {
      setCopied('no')
      return
    }
    setCopied('yes')
    window.setTimeout(() => setCopied(null), 2000)
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>공지 내용 복사</DialogTitle>
          <DialogDescription>
            게시판의 공지를 최근 것부터 글 하나로 모았습니다 — 번호 · 제목 · 올린 사람 · 날짜 · 본문. 다른 문서나 메신저에 붙여 넣으십시오.
            {filtered && ' 지금 거른 조건(찾기 · 안 읽은 것만)에 맞는 것만입니다.'}
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={collected.error} />

        <textarea
          readOnly
          aria-label="공지 내용"
          rows={16}
          className="border-input bg-muted/40 w-full rounded-md border px-3 py-2 text-sm"
          value={collected.loading && !collected.data ? '모으는 중…' : text}
          // 눌러서 전부 고른다 — 복사가 막힌 브라우저에서 사람이 직접 복사하는 길이다.
          onFocus={(event) => event.currentTarget.select()}
        />

        {page && (
          <p className="text-sm" role="status">
            공지 {page.items.length.toLocaleString('ko-KR')}건 · {text.length.toLocaleString('ko-KR')}자
            {page.items.length < page.total && ` — 전체 ${page.total.toLocaleString('ko-KR')}건 중 일부만 모았습니다. 찾기로 좁혀 나눠 복사하십시오.`}
          </p>
        )}
        {copied === 'no' && (
          <p className="text-destructive text-sm" role="alert">
            브라우저가 복사를 막았습니다 — 위 글을 눌러 전부 고른 뒤 Ctrl+C 로 복사하십시오.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={close}>
            닫기
          </Button>
          <Button onClick={() => void copy()} disabled={!text}>
            {copied === 'yes' ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied === 'yes' ? '복사했습니다' : '복사'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
