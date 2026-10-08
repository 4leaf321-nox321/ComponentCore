/**
 * 규격으로 **시편 작업 만들기** — 치수(비우면 규격 값) · 시험 지그 · 해석 조건을 고르면 서버가
 * 그려 본 값(지지 간격 · 처짐 · 반지름)과 메모를 보이고, 만들면 그 작업으로 간다. 치수는 레시피
 * 변수라 작업에서 DOE 로 그대로 훑는다.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { specimensApi } from '@/modules/specimens/api'
import type { BendingPreset, PresetRow, SpecimenBuild } from '@/modules/specimens/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const asError = (caught: unknown) => (caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))

const number = (text: string) => (text.trim() && Number(text) > 0 ? Number(text) : null)

const shown = (value: number | undefined) => (value === undefined ? '—' : `${Math.round(value * 1000) / 1000} mm`)

export function SpecimenDialog({ row, onClose }: { row: PresetRow<BendingPreset>; onClose: () => void }) {
  const navigate = useNavigate()
  const size = row.preset.specimen
  const [length, setLength] = useState(String(size.length))
  const [width, setWidth] = useState(String(size.width))
  const [thickness, setThickness] = useState(String(size.thickness))
  const [fixture, setFixture] = useState(true)
  const [conditions, setConditions] = useState(true)
  const [name, setName] = useState(row.name)
  const [folder, setFolder] = useState('')
  const [preview, setPreview] = useState<SpecimenBuild | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)
  const four = row.preset.setup.points === 4

  // 칸을 고칠 때마다 서버가 그려 본다 — 식(간격비 x 두께 · 처짐)을 화면이 따로 풀지 않는다.
  useEffect(() => {
    let alive = true
    const timer = setTimeout(() => {
      specimensApi
        .build({
          preset_id: row.id,
          length: number(length),
          width: number(width),
          thickness: number(thickness),
          fixture,
          conditions: fixture && conditions,
        })
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
  }, [row.id, length, width, thickness, fixture, conditions])

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const work = await specimensApi.createWork({
        preset_id: row.id,
        length: number(length),
        width: number(width),
        thickness: number(thickness),
        fixture,
        conditions: fixture && conditions,
        name: name.trim() || undefined,
        folder: folder.trim(),
      })
      navigate(`/works/${work.id}`)
    } catch (caught) {
      setError(asError(caught))
    } finally {
      setBusy(false)
    }
  }

  const values = preview?.values ?? {}
  const field = (id: string, label: string, value: string, set: (next: string) => void, type = 'number') => (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={type} step="any" value={value} onChange={(event) => set(event.target.value)} />
    </div>
  )

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>시편 생성</DialogTitle>
          <DialogDescription>
            ‘{row.name}’으로 내 작업을 생성합니다. 치수는 레시피 변수로 저장되므로 생성 후 DOE로 변경할 수 있습니다.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-3 gap-3">
          {field('spec-length', '길이 (mm)', length, setLength)}
          {field('spec-width', '폭 (mm)', width, setWidth)}
          {field('spec-thickness', '두께 (mm)', thickness, setThickness)}
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={fixture} onChange={(event) => setFixture(event.target.checked)} />
            시험 지그 포함
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={fixture && conditions} disabled={!fixture} onChange={(event) => setConditions(event.target.checked)} />
            해석 조건 포함
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {field('spec-name', '작업 이름', name, setName, 'text')}
          {field('spec-folder', '폴더', folder, setFolder, 'text')}
        </div>
        {preview && (
          <div className="bg-muted/40 space-y-1 rounded-md p-3 text-xs">
            <p>
              지지 간격 {shown(values['지지_간격'])}
              {four && ` · 하중 간격 ${shown(values['하중_간격'])}`}
              {fixture && ` · 지지 반지름 ${shown(values['지지_반지름'])} · 노즈 반지름 ${shown(values['노즈_반지름'])}`}
              {values['처짐'] !== undefined && ` · 노즈 처짐 ${shown(values['처짐'])}`}
            </p>
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
