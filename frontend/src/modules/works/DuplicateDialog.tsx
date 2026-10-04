/**
 * 작업 복제 — 현재 도면으로 새 작업. **해석 조건도 옮길지** 고른다.
 *
 * 변형을 그릴 때는 같은 조건으로 DOE 를 돌리는 일이 흔하다(조건까지). 다른 부품의 출발점으로
 * 복제할 때는 옛 조건의 선택 그룹이 엉뚱한 면을 가리킨다(도면만). 조건이 없으면 묻지 않는다.
 */

import { useState } from 'react'

import { worksApi } from '@/modules/works/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/** 조건에 무엇이 들어 있나 — 빈 목록 · 빈 설정은 없는 것으로 친다. */
export function hasConditions(conditions: Record<string, unknown> | null | undefined): boolean {
  return Object.values(conditions ?? {}).some((value) =>
    Array.isArray(value) ? value.length > 0 : value !== null && typeof value === 'object' ? Object.keys(value).length > 0 : false,
  )
}

export function DuplicateDialog({
  open,
  workId,
  workName,
  conditions,
  onClose,
  onMade,
}: {
  open: boolean
  workId: string
  workName: string
  /** 현재 버전의 해석 조건 — 있으면 옮길지 묻는다. */
  conditions: Record<string, unknown> | null | undefined
  onClose: () => void
  onMade: (id: string) => void
}) {
  const [name, setName] = useState(`${workName} 사본`)
  const withConditions = hasConditions(conditions)
  const [copyConditions, setCopyConditions] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const made = await worksApi.duplicate(workId, name.trim() || undefined, withConditions && copyConditions)
      onMade(made.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !busy && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>작업 복제</DialogTitle>
          <DialogDescription>현재 도면으로 새 작업을 생성합니다. 종류, 태그, 폴더가 함께 복사되며 버전은 1부터 시작합니다.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="duplicate-name">이름</Label>
          <Input id="duplicate-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </div>
        {withConditions ? (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={copyConditions} onChange={(e) => setCopyConditions(e.target.checked)} />
            <span>
              해석 조건도 복사
              <span className="text-muted-foreground block text-xs">
                같은 조건으로 변형 설계를 검토할 때 선택하십시오. 다른 부품의 시작점으로 사용할 경우에는 해제하십시오. 기존 선택 그룹이 의도하지 않은 면을 가리킬 수 있습니다.
              </span>
            </span>
          </label>
        ) : (
          <p className="text-muted-foreground text-xs">이 버전에는 해석 조건이 없습니다. 도면만 복사합니다.</p>
        )}
        <ErrorNotice error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={() => void submit()} disabled={busy || !name.trim()}>
            {busy ? '복제 중…' : '복제'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
