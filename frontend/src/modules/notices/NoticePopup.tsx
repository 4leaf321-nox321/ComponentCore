/**
 * 로그인 후 한 번 뜨는 공지(MatNexus 와 같다).
 *
 * 폐쇄망에서 배포 없이 안내를 전하는 수단인데, **사람이 공지 화면에 들어가야만 보인다면 전달이
 * 되지 않는다.** 그래서 읽지 않은 팝업 공지는 스스로 나타난다. 닫으면 읽음으로 기록되어 다시
 * 뜨지 않는다(`notice_reads`). 여러 건이면 하나씩 차례로 — 한 번에 쌓아 보여 주면 아무도 안 읽는다.
 */

import { useEffect, useState } from 'react'
import { Megaphone } from 'lucide-react'

import { NoticeBody } from '@/modules/notices/NoticeBody'
import { noticesApi } from '@/modules/notices/api'
import type { Notice } from '@/modules/notices/api'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { shownDate } from '@/shared/lib/datetime'

export function NoticePopup() {
  const [queue, setQueue] = useState<Notice[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    noticesApi
      .popup()
      .then((items) => {
        if (!cancelled) setQueue(items)
      })
      .catch(() => {
        // 팝업은 부가 기능이다. 실패해도 화면을 막지 않는다.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const current = queue[0]
  if (!current) return null

  async function dismiss() {
    if (!current) return
    setBusy(true)
    try {
      await noticesApi.read(current.id)
    } catch {
      // 읽음 기록에 실패하면 다음 로그인에 다시 뜬다. 그 편이 안전하다.
    } finally {
      setBusy(false)
      setQueue((rest) => rest.slice(1))
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && void dismiss()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Megaphone className="size-4" />
            {current.title}
          </DialogTitle>
          <DialogDescription>
            {shownDate(current.published_at ?? current.created_at)}
            {queue.length > 1 && ` · ${queue.length}건 중 1`}
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-auto">
          <NoticeBody text={current.body} />
        </div>
        <DialogFooter>
          <Button onClick={() => void dismiss()} disabled={busy}>
            확인
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
