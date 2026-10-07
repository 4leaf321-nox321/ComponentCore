/**
 * **사내 규격** 편집 — 공개 규격을 복사해 고치거나(`copy`) 사내 규격을 고친다(`edit`). 시스템
 * 관리자만 열린다(판정은 서버). 저장 전에 서버가 값을 검사하고 실제로 그려 본다 — 틀리면 어느
 * 칸이 왜인지 목록으로 보인다.
 *
 * 반지름은 「하나」 또는 「얇은 시편이면 다른 값」(ISO 178 의 2 mm · 5 mm) 두 가지만 고친다. 줄이
 * 셋 이상인 규칙은 화면에서 첫 줄과 마지막 줄로 줄어든다 — 그런 규격이 나오면 칸을 늘린다.
 */

import { useState } from 'react'

import { specimensApi } from '@/modules/specimens/api'
import type { BendingPreset, PresetRow, Radius } from '@/modules/specimens/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Textarea } from '@/shared/components/ui/textarea'

type RadiusForm = { radius: string; thin: string; upTo: string }

type Form = {
  standard: string
  name: string
  points: '3' | '4'
  length: string
  width: string
  thickness: string
  spanMode: 'ratio' | 'value'
  span: string
  loadMode: 'ratio' | 'value'
  load: string
  support: RadiusForm
  nose: RadiusForm
  overhangRatio: string
  overhangMin: string
  strain: string
  friction: string
  source: string
  note: string
  verified: boolean
}

const text = (value: number | null | undefined) => (value === null || value === undefined ? '' : String(value))

function radiusForm(radius: Radius): RadiusForm {
  if (typeof radius === 'number') return { radius: String(radius), thin: '', upTo: '' }
  const last = radius[radius.length - 1]
  const first = radius.length > 1 ? radius[0] : null
  return { radius: String(last.radius), thin: text(first?.radius), upTo: text(first?.max_thickness) }
}

function radiusOf(form: RadiusForm): Radius {
  const radius = Number(form.radius)
  if (!form.thin.trim() || !form.upTo.trim()) return radius
  return [{ max_thickness: Number(form.upTo), radius: Number(form.thin) }, { radius }]
}

function formOf(row: PresetRow<BendingPreset>, mode: 'copy' | 'edit'): Form {
  const preset = row.preset
  const setup = preset.setup
  return {
    standard: preset.standard,
    name: mode === 'copy' ? `${preset.name} (사내)` : preset.name,
    points: setup.points === 4 ? '4' : '3',
    length: String(preset.specimen.length),
    width: String(preset.specimen.width),
    thickness: String(preset.specimen.thickness),
    spanMode: setup.span.to_thickness ? 'ratio' : 'value',
    span: text(setup.span.to_thickness ?? setup.span.value),
    loadMode: setup.load_span?.value ? 'value' : 'ratio',
    load: text(setup.load_span?.to_span ?? setup.load_span?.value ?? 0.3333),
    support: radiusForm(setup.support_radius),
    nose: radiusForm(setup.nose_radius),
    overhangRatio: text(setup.overhang?.to_span ?? 0),
    overhangMin: text(setup.overhang?.min ?? 0),
    strain: String(preset.analysis.strain),
    friction: String(preset.analysis.friction),
    source: preset.source,
    note: preset.note,
    verified: mode === 'edit' ? preset.verified : false,
  }
}

function presetOf(form: Form): Omit<BendingPreset, 'id'> {
  const four = form.points === '4'
  return {
    test: 'bending',
    family: 'bend_bar',
    standard: form.standard.trim(),
    name: form.name.trim(),
    specimen: { length: Number(form.length), width: Number(form.width), thickness: Number(form.thickness) },
    setup: {
      points: four ? 4 : 3,
      span: form.spanMode === 'ratio' ? { to_thickness: Number(form.span) } : { value: Number(form.span) },
      load_span: four ? (form.loadMode === 'ratio' ? { to_span: Number(form.load) } : { value: Number(form.load) }) : null,
      support_radius: radiusOf(form.support),
      nose_radius: radiusOf(form.nose),
      overhang: { to_span: Number(form.overhangRatio || 0), min: Number(form.overhangMin || 0) },
    },
    analysis: { strain: Number(form.strain), friction: Number(form.friction) },
    source: form.source.trim(),
    note: form.note.trim(),
    verified: form.verified,
  }
}

const SELECT = 'bg-background h-9 w-full rounded-md border px-2 text-sm'

export function PresetDialog({ row, mode, onClose, onSaved }: { row: PresetRow<BendingPreset>; mode: 'copy' | 'edit'; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<Form>(() => formOf(row, mode))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const problems = error instanceof ApiError ? ((error.details.problems as string[] | undefined) ?? []) : []
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((now) => ({ ...now, [key]: value }))

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const preset = presetOf(form)
      if (mode === 'edit') await specimensApi.update(row.id, preset)
      else await specimensApi.create(preset)
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const input = (id: keyof Form, label: string, type = 'number') => (
    <div className="space-y-1">
      <Label htmlFor={`preset-${id}`}>{label}</Label>
      <Input id={`preset-${id}`} type={type} step="any" value={String(form[id])} onChange={(event) => set(id, event.target.value as never)} />
    </div>
  )
  const radius = (key: 'support' | 'nose', label: string) => (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
      {(['radius', 'thin', 'upTo'] as const).map((part) => (
        <div key={part} className="space-y-1">
          <Label htmlFor={`preset-${key}-${part}`}>{part === 'radius' ? `${label} (mm)` : part === 'thin' ? '얇은 시편 반지름 (선택)' : '적용 두께 이하 (mm)'}</Label>
          <Input
            id={`preset-${key}-${part}`}
            type="number"
            step="any"
            value={form[key][part]}
            onChange={(event) => set(key, { ...form[key], [part]: event.target.value })}
          />
        </div>
      ))}
    </div>
  )

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            void save()
          }}
        >
          <DialogHeader>
            <DialogTitle>{mode === 'edit' ? '사내 규격 수정' : '사내 규격으로 복사'}</DialogTitle>
            <DialogDescription>
              {mode === 'edit' ? '사내 규격의 값을 수정합니다.' : `‘${row.name}’의 값을 복사하여 사내 규격으로 등록합니다.`} 저장하기 전에 서버가 값을 검사하고 시편을 생성해 봅니다.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            {input('standard', '규격 번호', 'text')}
            {input('name', '이름', 'text')}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="space-y-1">
              <Label htmlFor="preset-points">방식</Label>
              <select id="preset-points" className={SELECT} value={form.points} onChange={(event) => set('points', event.target.value as '3' | '4')}>
                <option value="3">3점 굽힘</option>
                <option value="4">4점 굽힘</option>
              </select>
            </div>
            {input('length', '시편 길이 (mm)')}
            {input('width', '시편 폭 (mm)')}
            {input('thickness', '시편 두께 (mm)')}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="space-y-1">
              <Label htmlFor="preset-spanMode">지지 간격</Label>
              <select id="preset-spanMode" className={SELECT} value={form.spanMode} onChange={(event) => set('spanMode', event.target.value as 'ratio' | 'value')}>
                <option value="ratio">두께의 배수</option>
                <option value="value">고정 값</option>
              </select>
            </div>
            {input('span', form.spanMode === 'ratio' ? '간격비 (× 두께)' : '지지 간격 (mm)')}
            {form.points === '4' && (
              <>
                <div className="space-y-1">
                  <Label htmlFor="preset-loadMode">하중 간격</Label>
                  <select id="preset-loadMode" className={SELECT} value={form.loadMode} onChange={(event) => set('loadMode', event.target.value as 'ratio' | 'value')}>
                    <option value="ratio">지지 간격의 비</option>
                    <option value="value">고정 값</option>
                  </select>
                </div>
                {input('load', form.loadMode === 'ratio' ? '비 (0~1)' : '하중 간격 (mm)')}
              </>
            )}
          </div>
          {radius('support', '지지 반지름')}
          {radius('nose', '노즈 반지름')}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {input('overhangRatio', '최소 돌출 (지지 간격의 비)')}
            {input('overhangMin', '최소 돌출 (mm)')}
            {input('strain', '해석 변형률')}
            {input('friction', '마찰계수')}
          </div>
          <div className="space-y-1">
            <Label htmlFor="preset-source">출처</Label>
            <Textarea id="preset-source" rows={2} value={form.source} onChange={(event) => set('source', event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="preset-note">메모</Label>
            <Textarea id="preset-note" rows={2} value={form.note} onChange={(event) => set('note', event.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.verified} onChange={(event) => set('verified', event.target.checked)} />
            규격서와 대조 완료
          </label>
          <ErrorNotice error={error} />
          {problems.length > 0 && (
            <ul className="text-destructive list-disc pl-5 text-xs">
              {problems.map((one) => (
                <li key={one}>{one}</li>
              ))}
            </ul>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              취소
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? '확인 중…' : '저장'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
