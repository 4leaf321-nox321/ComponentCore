/**
 * **규격 사양** — 공용 부품에 붙은 종류 · 품번 · 쓰는 버전 · 치수. 지그 생성기가 요구에 맞으면 이
 * 부품을 놓고 부품표에 품번 · 수량을 남긴다. 붙이고 고치고 떼는 일은 **시스템 관리자만** 한다.
 *
 * 형상은 공급사 STEP 을 받아 사내에서 레시피로 다시 그린 것이다. 저장할 때 서버가 그 버전의 형상이
 * 기준(바닥 중심 원점 · 패드 자리)을 지키는지 보고, 어기면 무엇을 고칠지 말한다.
 */

import { useState } from 'react'

import { partsApi, STANDARD_KINDS } from '@/modules/parts/api'
import type { Part, StandardKind, StandardSpec } from '@/modules/parts/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

type Field = { key: keyof StandardSpec; label: string }

/** 종류마다 꼭 있는 치수 — 서버 `STANDARD_FIELDS` 와 같다. */
const FIELDS: Record<StandardKind, Field[]> = {
  support: [
    { key: 'top_diameter', label: '윗면 지름 (mm)' },
    { key: 'height', label: '높이 (mm)' },
  ],
  pin: [
    { key: 'diameter', label: '지름 (mm)' },
    { key: 'length', label: '판 위 길이 (mm)' },
  ],
  clamp: [
    { key: 'reach', label: '도달 거리 (mm)' },
    { key: 'pad_height', label: '누르는 높이 (mm)' },
    { key: 'pad_diameter', label: '패드 지름 (mm)' },
    { key: 'base_length', label: '베이스 길이 (mm)' },
    { key: 'base_width', label: '베이스 폭 (mm)' },
  ],
}

/** 변수로 움직이는 치수 — 서버 `STANDARD_RANGES` 와 같다. */
const RANGES: Partial<Record<StandardKind, { param: keyof StandardSpec; min: keyof StandardSpec; max: keyof StandardSpec; label: string }>> = {
  support: { param: 'height_param', min: 'height_min', max: 'height_max', label: '높이' },
  pin: { param: 'length_param', min: 'length_min', max: 'length_max', label: '길이' },
}

const kindLabel = (kind: StandardKind) => STANDARD_KINDS.find((one) => one.value === kind)?.label ?? kind

function dims(spec: StandardSpec): string {
  const shown = FIELDS[spec.kind].map((one) => `${one.label.replace(' (mm)', '')} ${spec[one.key] ?? '—'}`)
  const range = RANGES[spec.kind]
  if (range && spec[range.param]) shown.push(`${range.label} 변수 ‘${spec[range.param]}’ ${spec[range.min]}~${spec[range.max]}`)
  return shown.join(' · ')
}

export function StandardCard({ part, admin, onChanged }: { part: Part; admin: boolean; onChanged: () => void }) {
  const spec = part.standard ?? null
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  if (!spec && !admin) return null

  async function clear() {
    setBusy(true)
    setError(null)
    try {
      await partsApi.clearStandard(part.id)
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>규격 사양</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {spec ? (
          <>
            <p>
              {kindLabel(spec.kind)} · 품번 <b>{spec.part_no}</b>
              {spec.maker ? ` · ${spec.maker}` : ''} · v{spec.version} 사용
            </p>
            <p className="text-muted-foreground text-xs">{dims(spec)}</p>
            <p className="text-muted-foreground text-xs">지그 생성 시 요구에 맞으면 이 부품을 배치하고 부품표에 품번을 기록합니다.</p>
          </>
        ) : (
          <p className="text-muted-foreground">규격 부품이 아닙니다. 사양을 등록하면 지그 생성기가 받침 · 위치 핀 · 토글 클램프로 사용합니다.</p>
        )}
        <ErrorNotice error={error} />
        {admin && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing(true)}>
              {spec ? '규격 사양 편집' : '규격 사양 등록'}
            </Button>
            {spec && (
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => void clear()}>
                규격 사양 해제
              </Button>
            )}
          </div>
        )}
      </CardContent>
      {editing && (
        <StandardDialog
          part={part}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false)
            onChanged()
          }}
        />
      )}
    </Card>
  )
}

function StandardDialog({ part, onClose, onSaved }: { part: Part; onClose: () => void; onSaved: () => void }) {
  const start = part.standard
  const [kind, setKind] = useState<StandardKind>(start?.kind ?? 'support')
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries({ version: part.current_version, preference: 100, ...start })
        .filter(([, value]) => value !== null && value !== undefined)
        .map(([key, value]) => [key, String(value)]),
    ),
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const problems = error instanceof ApiError ? ((error.details.problems as string[] | undefined) ?? []) : []
  const range = RANGES[kind]
  const set = (key: string, value: string) => setValues((now) => ({ ...now, [key]: value }))
  const number = (key: string) => (values[key]?.trim() ? Number(values[key]) : null)

  async function save() {
    setBusy(true)
    setError(null)
    const spec: StandardSpec = {
      kind,
      part_no: values.part_no?.trim() ?? '',
      maker: values.maker?.trim() ?? '',
      version: number('version') ?? part.current_version,
      preference: number('preference') ?? 100,
      ...Object.fromEntries(FIELDS[kind].map((one) => [one.key, number(one.key)])),
    }
    if (range && values[range.param]?.trim()) {
      Object.assign(spec, { [range.param]: values[range.param].trim(), [range.min]: number(range.min), [range.max]: number(range.max) })
    }
    try {
      await partsApi.setStandard(part.id, spec)
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const input = (key: string, label: string, kindOf: 'text' | 'number' = 'number') => (
    <div className="space-y-1" key={key}>
      <Label htmlFor={`std-${key}`}>{label}</Label>
      <Input id={`std-${key}`} type={kindOf} value={values[key] ?? ''} onChange={(e) => set(key, e.target.value)} />
    </div>
  )

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void save()
          }}
          className="space-y-4"
        >
          <DialogHeader>
            <DialogTitle>규격 사양</DialogTitle>
            <DialogDescription>{STANDARD_KINDS.find((one) => one.value === kind)?.hint}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="std-kind">종류</Label>
              <select id="std-kind" className="bg-background h-9 w-full rounded-md border px-2 text-sm" value={kind} onChange={(e) => setKind(e.target.value as StandardKind)}>
                {STANDARD_KINDS.map((one) => (
                  <option key={one.value} value={one.value}>
                    {one.label}
                  </option>
                ))}
              </select>
            </div>
            {input('part_no', '품번', 'text')}
            {input('maker', '제조사', 'text')}
            {input('version', '사용할 버전')}
            {FIELDS[kind].map((one) => input(one.key, one.label))}
            {input('preference', '선호 (작을수록 먼저)')}
          </div>
          {range && (
            <div className="grid grid-cols-3 gap-3">
              {input(range.param, `${range.label} 변수 (선택)`, 'text')}
              {input(range.min, '최소')}
              {input(range.max, '최대')}
            </div>
          )}
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
