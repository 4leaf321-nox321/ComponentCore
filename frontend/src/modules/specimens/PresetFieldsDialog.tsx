/**
 * 굽힘을 뺀 시험의 **사내 규격** 편집 — 공개 규격을 복사해 고치거나 사내 규격을 고친다. 칸은
 * 종류의 정의(`kinds.ts`)에서 읽는다. 시스템 관리자만 열린다(판정은 서버 — 값의 검사도 서버가
 * 한다). 굽힘은 칸이 많아 `PresetDialog` 가 따로 맡는다.
 */

import { useState } from 'react'

import { fieldsFor, kindOf } from '@/modules/specimens/kinds'
import type { Field } from '@/modules/specimens/kinds'
import { specimensApi } from '@/modules/specimens/api'
import type { AnyPreset, NewPreset, PresetRow } from '@/modules/specimens/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Textarea } from '@/shared/components/ui/textarea'

type Values = Record<string, string>
type Groups = Record<string, Record<string, unknown>>

const SELECT = 'bg-background h-9 w-full rounded-md border px-2 text-sm'
const id = (one: Field) => `preset-${one.group}-${one.key}`
const slot = (one: Field) => `${one.group}.${one.key}`

function read(preset: AnyPreset, one: Field): string {
  const group = (preset as unknown as Groups)[one.group] ?? {}
  const value = group[one.key]
  return value === null || value === undefined ? '' : String(value)
}

function parsed(one: Field, text: string): unknown {
  if (one.type === 'bool') return text === 'true'
  if (one.type === 'select') return text
  if (!text.trim()) return one.optional ? null : Number.NaN
  return Number(text)
}

/** 원래 프리셋을 바탕으로 칸의 값을 덮는다 — 정의에 없는 칸(계열 · 해석 기본값)은 그대로 간다. */
export function presetOf(preset: AnyPreset, fields: Field[], values: Values, common: { standard: string; name: string; source: string; note: string; verified: boolean }): NewPreset {
  const { id: _id, ...rest } = structuredClone(preset)
  const made = rest as unknown as Groups & Record<string, unknown>
  for (const one of fields) {
    made[one.group] = { ...made[one.group], [one.key]: parsed(one, values[slot(one)] ?? '') }
  }
  return { ...made, standard: common.standard.trim(), name: common.name.trim(), source: common.source.trim(), note: common.note.trim(), verified: common.verified } as unknown as NewPreset
}

export function PresetFieldsDialog({ row, mode, onClose, onSaved }: { row: PresetRow; mode: 'copy' | 'edit'; onClose: () => void; onSaved: () => void }) {
  const preset = row.preset
  const spec = kindOf(preset.test)
  const fields = spec ? fieldsFor(spec, preset) : []
  const [values, setValues] = useState<Values>(() => Object.fromEntries(fields.map((one) => [slot(one), read(preset, one)])))
  const [common, setCommon] = useState({
    standard: preset.standard,
    name: mode === 'copy' ? `${preset.name} (사내)` : preset.name,
    source: preset.source,
    note: preset.note,
    verified: mode === 'edit' ? preset.verified : false,
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const problems = error instanceof ApiError ? ((error.details.problems as string[] | undefined) ?? []) : []
  const set = (one: Field, value: string) => setValues({ ...values, [slot(one)]: value })

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const made = presetOf(preset, fields, values, common)
      if (mode === 'edit') await specimensApi.update(row.id, made)
      else await specimensApi.create(made)
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const inputs = fields.filter((one) => one.type !== 'bool')
  const checks = fields.filter((one) => one.type === 'bool')
  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
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
              {spec ? `${spec.label} · ` : ''}
              {mode === 'edit' ? '사내 규격의 값을 수정합니다.' : `‘${row.name}’의 값을 복사하여 사내 규격으로 등록합니다.`} 저장하기 전에 서버가 값을 검사합니다.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="product-standard">규격 번호</Label>
              <Input id="product-standard" value={common.standard} onChange={(event) => setCommon({ ...common, standard: event.target.value })} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="product-name">이름</Label>
              <Input id="product-name" value={common.name} onChange={(event) => setCommon({ ...common, name: event.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {inputs.map((one) => (
              <div key={slot(one)} className="space-y-1">
                <Label htmlFor={id(one)}>
                  {one.label}
                  {one.optional && <span className="text-muted-foreground"> (선택)</span>}
                </Label>
                {one.type === 'select' ? (
                  <select id={id(one)} className={SELECT} value={values[slot(one)] ?? ''} onChange={(event) => set(one, event.target.value)}>
                    {(one.options ?? []).map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input id={id(one)} type="number" step={one.type === 'int' ? 1 : 'any'} value={values[slot(one)] ?? ''} onChange={(event) => set(one, event.target.value)} />
                )}
              </div>
            ))}
          </div>
          {checks.map((one) => (
            <label key={slot(one)} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={values[slot(one)] === 'true'} onChange={(event) => set(one, String(event.target.checked))} />
              {one.label}
            </label>
          ))}
          <div className="space-y-1">
            <Label htmlFor="product-source">출처</Label>
            <Textarea id="product-source" rows={2} value={common.source} onChange={(event) => setCommon({ ...common, source: event.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="product-note">메모</Label>
            <Textarea id="product-note" rows={2} value={common.note} onChange={(event) => setCommon({ ...common, note: event.target.value })} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={common.verified} onChange={(event) => setCommon({ ...common, verified: event.target.checked })} />
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
