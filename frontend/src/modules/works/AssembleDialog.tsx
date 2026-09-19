/**
 * 「부품 + 지그로 조립」 — 부품 하나와 지그 작업 하나를 고르면 서버가 **맞는 자리에** 놓은 조립
 * 작업을 만든다. 좌표 계산(생성기 좌표계 · 받침 높이)을 사람이 하지 않는다.
 */

import { useState } from 'react'

import { partsApi } from '@/modules/parts/api'
import { worksApi } from '@/modules/works/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/components/ui/select'
import { useResource } from '@/shared/hooks/useResource'

export function AssembleDialog({ open, onClose, onMade }: { open: boolean; onClose: () => void; onMade: (workId: string, mode: string) => void }) {
  const works = useResource(() => worksApi.list(0, 100), [open])
  const parts = useResource(() => partsApi.list(0, 100), [open])
  const [partSource, setPartSource] = useState('')
  const [jigId, setJigId] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)

  const partOptions = [
    ...(works.data?.items ?? []).filter((one) => one.kind === 'part' && one.current_version > 0).map((one) => ({ value: `work:${one.id}`, label: `${one.name} (내 작업 v${one.current_version})` })),
    ...(parts.data?.items ?? []).map((one) => ({ value: `part:${one.id}`, label: `${one.name} (공용 v${one.current_version})` })),
  ]
  const jigOptions = (works.data?.items ?? []).filter((one) => one.kind === 'jig' && one.current_version > 0).map((one) => ({ value: one.id, label: `${one.name} (v${one.current_version})` }))

  async function make() {
    setBusy(true)
    setError(null)
    try {
      const got = await worksApi.assemble({ part_source: partSource, jig_work_id: jigId, name: name.trim() || undefined })
      onMade(got.work.id, got.placement.mode)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void make()
          }}
          className="space-y-4"
        >
          <DialogHeader>
            <DialogTitle>부품 + 지그로 조립</DialogTitle>
            <DialogDescription>
              부품과 지그를 고르면 맞는 자리에 놓은 조립이 생깁니다. 「부품에서 지그 생성」 으로 만든 지그는 그 좌표계로 정확히, 직접 그린 지그는 윗면에 얹어 어림합니다(만든 뒤 자리를 확인하세요). 부품 높이는 변수라 DOE 로 훑을 수 있습니다.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="asm-part">부품</Label>
              <Select value={partSource} onValueChange={setPartSource}>
                <SelectTrigger id="asm-part" aria-label="부품">
                  <SelectValue placeholder="부품을 고르세요" />
                </SelectTrigger>
                <SelectContent>
                  {partOptions.map((one) => (
                    <SelectItem key={one.value} value={one.value}>
                      {one.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="asm-jig">지그 작업</Label>
              <Select value={jigId} onValueChange={setJigId}>
                <SelectTrigger id="asm-jig" aria-label="지그 작업">
                  <SelectValue placeholder="지그를 고르세요" />
                </SelectTrigger>
                <SelectContent>
                  {jigOptions.map((one) => (
                    <SelectItem key={one.value} value={one.value}>
                      {one.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {jigOptions.length === 0 && <p className="text-muted-foreground text-xs">저장된 지그 작업이 없습니다 — 「부품에서 지그 생성」 이나 「새 부품/지그」 로 먼저 만드세요.</p>}
            </div>
            <div className="space-y-1">
              <Label htmlFor="asm-name">이름 (비우면 「부품 + 지그」)</Label>
              <Input id="asm-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <ErrorNotice error={error ?? works.error ?? parts.error} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              취소
            </Button>
            <Button type="submit" disabled={busy || !partSource || !jigId}>
              {busy ? '만드는 중…' : '조립 만들기'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
