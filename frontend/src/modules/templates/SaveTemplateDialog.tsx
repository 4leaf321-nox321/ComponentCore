/** 지금 레시피를 템플릿으로 — 「템플릿」 공간의 내 자리에 들어간다. 공용으로 두면 누구나 고른다. */

import { useState } from 'react'
import type { FormEvent } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { templatesApi } from '@/modules/templates/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

export function SaveTemplateDialog({
  open,
  recipe,
  defaultName,
  onClose,
  onSaved,
}: {
  open: boolean
  recipe: Recipe
  defaultName?: string
  onClose: () => void
  onSaved?: () => void
}) {
  const [name, setName] = useState(defaultName ?? '')
  const [description, setDescription] = useState('')
  const [shared, setShared] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await templatesApi.create({ name, description, recipe, is_shared: shared })
      onSaved?.()
      onClose()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(value) => !value && !busy && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>템플릿으로 저장</DialogTitle>
            <DialogDescription>
              지금 레시피가 「그리기」 의 시작 목록에 들어갑니다. 버전은 없습니다 — 시작점일 뿐이고, 고친
              결과는 작업으로 갑니다.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="tpl-name">이름</Label>
            <Input id="tpl-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tpl-desc">설명</Label>
            <Input id="tpl-desc" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="언제 쓰는 시작점인가" />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            공용 — 로그인한 누구나 시작점으로 고를 수 있다
          </label>
          <ErrorNotice error={error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              취소
            </Button>
            <Button type="submit" disabled={busy || !name.trim()}>
              {busy ? '저장 중…' : '저장'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
