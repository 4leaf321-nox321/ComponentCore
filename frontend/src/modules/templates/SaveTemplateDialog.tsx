/** 지금 레시피를 템플릿으로 — 「템플릿」 공간의 내 자리에 들어간다. 공용으로 두면 누구나 고른다. */

import { useState } from 'react'
import type { FormEvent } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { templatesApi } from '@/modules/templates/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { normalizePath } from '@/shared/folders/paths'
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
  defaultFolder,
  onClose,
  onSaved,
}: {
  open: boolean
  recipe: Recipe
  defaultName?: string
  /** 처음 칸에 든 폴더 — 작업에서 저장하면 그 작업의 폴더. */
  defaultFolder?: string
  onClose: () => void
  onSaved?: () => void
}) {
  const [name, setName] = useState(defaultName ?? '')
  const [description, setDescription] = useState('')
  const [shared, setShared] = useState(false)
  const [folder, setFolder] = useState(defaultFolder ?? '')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await templatesApi.create({ name, description, recipe, is_shared: shared, folder: normalizePath(folder) })
      onSaved?.()
      onClose()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
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
              현재 도면을 템플릿 라이브러리에 저장합니다. 이후 부품이나 지그를 모델링할 때 시작점으로 선택할 수 있습니다. 템플릿은
              시작점이므로 버전을 관리하지 않으며, 수정한 결과는 작업에 저장됩니다.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="tpl-name">이름</Label>
            <Input id="tpl-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tpl-desc">설명</Label>
            <Input id="tpl-desc" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="템플릿의 용도" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tpl-folder">폴더</Label>
            <Input id="tpl-folder" value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="예: 판금/브래킷 (비워 두면 최상위)" />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            공용으로 공개(로그인한 모든 사용자가 시작점으로 선택 가능)
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
