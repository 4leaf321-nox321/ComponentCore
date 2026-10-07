/**
 * 인장 · 전단 · 접착 이음 규격으로 **시편 작업 만들기** — 시편 치수(종류의 정의 `kinds.ts`)를 고치면
 * 서버가 그려 본 값(전이부 길이 · 당김 …)과 메모를 보이고, 만들면 그 작업으로 간다. 치수가 레시피
 * 변수라 작업에서 DOE 로 그대로 훑는다. 그립은 바디가 아니라 시편 면을 나눈 자리다.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { fieldsFor, kindOf } from '@/modules/specimens/kinds'
import { specimensApi } from '@/modules/specimens/api'
import type { CouponPreset, PresetRow, SpecimenBuild } from '@/modules/specimens/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const asError = (caught: unknown) => (caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))

const shown = (value: number | undefined) => (value === undefined ? '—' : `${Math.round(value * 1000) / 1000} mm`)

export function CouponDialog({ row, onClose }: { row: PresetRow<CouponPreset>; onClose: () => void }) {
  const navigate = useNavigate()
  const spec = kindOf(row.preset.test)
  const dims = spec ? fieldsFor(spec, row.preset).filter((one) => one.group === 'specimen') : []
  const specimen = row.preset.specimen as Record<string, number | null | undefined>
  const [sizes, setSizes] = useState<Record<string, string>>(() => Object.fromEntries(dims.map((one) => [one.key, String(specimen[one.key] ?? '')])))
  const [fixture, setFixture] = useState(true)
  const [conditions, setConditions] = useState(true)
  const [name, setName] = useState(row.name)
  const [folder, setFolder] = useState('')
  const [preview, setPreview] = useState<SpecimenBuild | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)
  // 비운 칸 · 0 이하는 보내지 않는다 — 서버가 프리셋 값을 쓴다.
  const dimensions = Object.fromEntries(
    Object.entries(sizes)
      .filter(([, text]) => text.trim() && Number(text) > 0)
      .map(([key, text]) => [key, Number(text)]),
  )
  const sent = JSON.stringify(dimensions)

  // 칸을 고칠 때마다 서버가 그려 본다 — 식(전이부 · 노치 입구 · 당김)을 화면이 따로 풀지 않는다.
  useEffect(() => {
    let alive = true
    const timer = setTimeout(() => {
      specimensApi
        .build({ preset_id: row.id, dimensions: JSON.parse(sent) as Record<string, number>, fixture, conditions: fixture && conditions })
        .then((made) => {
          if (!alive) return
          setPreview(made)
          setError(null)
        })
        .catch((caught: unknown) => {
          if (!alive) return
          setPreview(null)
          setError(asError(caught))
        })
    }, 250)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [row.id, sent, fixture, conditions])

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const work = await specimensApi.createWork({ preset_id: row.id, dimensions, fixture, conditions: fixture && conditions, name: name.trim() || undefined, folder: folder.trim() })
      navigate(`/works/${work.id}`)
    } catch (caught) {
      setError(asError(caught))
    } finally {
      setBusy(false)
    }
  }

  const values = preview?.values ?? {}
  const known = (spec?.values ?? []).filter((one) => values[one.key] !== undefined)
  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>시편 생성</DialogTitle>
          <DialogDescription>‘{row.name}’으로 내 작업을 생성합니다. 치수는 레시피 변수로 저장되므로 생성 후 DOE로 변경할 수 있습니다.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {dims.map((one) => (
            <div key={one.key} className="space-y-1">
              <Label htmlFor={`coupon-${one.key}`}>{one.label}</Label>
              <Input id={`coupon-${one.key}`} type="number" step="any" value={sizes[one.key] ?? ''} onChange={(event) => setSizes({ ...sizes, [one.key]: event.target.value })} />
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={fixture} onChange={(event) => setFixture(event.target.checked)} />
            그립 자리 포함
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={fixture && conditions} disabled={!fixture} onChange={(event) => setConditions(event.target.checked)} />
            해석 조건 포함
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="coupon-name">작업 이름</Label>
            <Input id="coupon-name" value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="coupon-folder">폴더</Label>
            <Input id="coupon-folder" value={folder} onChange={(event) => setFolder(event.target.value)} />
          </div>
        </div>
        {preview && (
          <div className="bg-muted/40 space-y-1 rounded-md p-3 text-xs">
            {known.length > 0 && <p>{known.map((one) => `${one.label} ${shown(values[one.key])}`).join(' · ')}</p>}
            <ul className="text-muted-foreground list-disc pl-4">
              {preview.notes.map((one) => (
                <li key={one}>{one}</li>
              ))}
            </ul>
          </div>
        )}
        <ErrorNotice error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={() => void create()} disabled={busy || !preview}>
            {busy ? '생성 중…' : '생성'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
