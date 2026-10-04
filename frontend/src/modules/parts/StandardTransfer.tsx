/**
 * **규격 부품 옮기기** — 개발 PC 에서 고른 규격 부품을 묶음 파일(JSON 하나)로 내보내고, 운영
 * 서버에서 가져온다. 둘 다 시스템 관리자만이다(판정은 서버). 가져오기는 늘 **미리 보기 → 확인**:
 * 품번으로 짝지어 새 부품 · 새 버전 · 사양 수정 · 변경 없음 · 건너뜀을 먼저 보여 준다(ADR 0005).
 */

import { useState } from 'react'

import { partsApi, STANDARD_KINDS } from '@/modules/parts/api'
import type { StandardBundle, StandardImportAction, StandardImportResult } from '@/modules/parts/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'

const ACTIONS: Record<StandardImportAction, string> = {
  create: '새 부품',
  version: '새 버전',
  spec: '사양 수정',
  same: '변경 없음',
  skip: '건너뜀',
}

const kindLabel = (kind: string) => STANDARD_KINDS.find((one) => one.value === kind)?.label ?? kind

const asError = (caught: unknown) => (caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))

function stamp(date: Date): string {
  const two = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}${two(date.getMonth() + 1)}${two(date.getDate())}-${two(date.getHours())}${two(date.getMinutes())}`
}

/** 묶음을 파일로 — 브라우저에는 「내려받아라」 가 따로 없어 임시 <a> 를 누른다. */
function saveBundle(bundle: StandardBundle): void {
  const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = `규격부품-${stamp(new Date())}.json`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(href), 10_000)
}

/** 고른 것 중 규격 부품만 묶어 내려받는다 — 부품 목록의 선택 막대에 둔다. */
export function StandardExportButton({ ids }: { ids: string[] }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      saveBundle(await partsApi.exportStandard(ids))
    } catch (caught) {
      setError(asError(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        className="h-7"
        disabled={busy || ids.length === 0}
        title={ids.length === 0 ? '선택한 부품 중 규격 부품이 없습니다.' : '선택한 규격 부품을 묶음 파일(JSON)로 다운로드합니다.'}
        onClick={() => void run()}
      >
        {busy ? '내보내는 중…' : `규격 부품 내보내기 (${ids.length})`}
      </Button>
      <ErrorNotice error={error} className="text-xs" />
    </>
  )
}

/** 묶음 파일을 골라 미리 보고, 확인하면 가져온다. `onDone` — 가져온 뒤 목록을 새로 읽는다. */
export function StandardImportDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [bundle, setBundle] = useState<StandardBundle | null>(null)
  const [result, setResult] = useState<StandardImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const applied = result !== null && !result.dry_run
  const todo = result?.items.filter((one) => one.action !== 'same' && one.action !== 'skip').length ?? 0
  const counts = result
    ? (Object.keys(ACTIONS) as StandardImportAction[])
        .map((action) => [action, result.items.filter((one) => one.action === action).length] as const)
        .filter(([, count]) => count > 0)
        .map(([action, count]) => `${ACTIONS[action]} ${count}`)
        .join(', ')
    : ''

  async function pick(file: File) {
    setError(null)
    setResult(null)
    setBundle(null)
    let parsed: StandardBundle
    try {
      parsed = JSON.parse(await file.text()) as StandardBundle
    } catch {
      setError(new Error('JSON 파일을 읽을 수 없습니다. ‘규격 부품 내보내기’로 만든 파일을 선택하십시오.'))
      return
    }
    setBusy(true)
    try {
      setResult(await partsApi.importStandard(parsed, true))
      setBundle(parsed)
    } catch (caught) {
      setError(asError(caught))
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!bundle) return
    setBusy(true)
    setError(null)
    try {
      setResult(await partsApi.importStandard(bundle, false))
      onDone()
    } catch (caught) {
      setError(asError(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>규격 부품 가져오기</DialogTitle>
          <DialogDescription>
            다른 서버에서 내보낸 규격 부품 묶음(JSON)을 선택하십시오. 품번이 같은 규격 부품이 있으면 형상이 다를 때 새 버전으로, 사양만 다를 때 사양 수정으로 반영합니다.
          </DialogDescription>
        </DialogHeader>
        {!applied && (
          <div className="space-y-1">
            <Label htmlFor="standard-bundle">묶음 파일</Label>
            <Input
              id="standard-bundle"
              type="file"
              accept=".json,application/json"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void pick(file)
              }}
            />
          </div>
        )}
        <ErrorNotice error={error} />
        {result && (
          <div className="space-y-2">
            <p className="text-sm">
              {applied ? '가져오기 결과' : '미리 보기'}: {counts}
            </p>
            <div className="max-h-80 overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>품번</TableHead>
                    <TableHead>이름</TableHead>
                    <TableHead>종류</TableHead>
                    <TableHead>처리</TableHead>
                    <TableHead>버전</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.items.map((one, index) => (
                    <TableRow key={`${index}-${one.part_no}`}>
                      <TableCell className="font-mono text-xs">{one.part_no || '—'}</TableCell>
                      <TableCell>
                        {one.name}
                        {one.problems.length > 0 && (
                          <ul className="text-destructive list-disc pl-4 text-xs">
                            {one.problems.map((problem) => (
                              <li key={problem}>{problem}</li>
                            ))}
                          </ul>
                        )}
                      </TableCell>
                      <TableCell>{kindLabel(one.kind)}</TableCell>
                      <TableCell className={one.action === 'skip' ? 'text-destructive' : undefined}>{ACTIONS[one.action]}</TableCell>
                      <TableCell>{one.version ? `v${one.version}` : '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {applied && <p className="text-muted-foreground text-xs">가져오기를 완료했습니다. 새 버전의 3D 모델은 평가가 끝나면 표시됩니다.</p>}
            {!applied && todo === 0 && <p className="text-muted-foreground text-xs">반영할 항목이 없습니다.</p>}
          </div>
        )}
        <DialogFooter>
          {applied ? (
            <Button onClick={onClose}>닫기</Button>
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={busy}>
                취소
              </Button>
              <Button onClick={() => void apply()} disabled={busy || !bundle || todo === 0}>
                {busy ? '확인 중…' : `가져오기 (${todo})`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
