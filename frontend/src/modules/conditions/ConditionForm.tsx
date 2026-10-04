/**
 * 조건 하나의 칸들 — **서버가 준 사양표로 그린다.**
 *
 * 종류가 열 몇이고 칸이 제각각이다(고정 지지에는 값이 없고, 압력에는 크기와 방향이, 볼트에는
 * 예압이). 화면에 `if` 를 늘어놓으면 종류를 더할 때마다 여기를 고쳐야 한다 — 칸 목록은 서버가
 * 들고 있고(`core/conditions.py`) 여기는 그것을 그린다. CAD 의 `NodeForm` 과 같은 방식이다.
 */

import { useEffect, useState } from 'react'

import { acceptsLabel } from '@/modules/conditions/api'
import type { ConditionItem, FieldSchema, GroupSchema, NamedSelection } from '@/modules/conditions/api'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'

/** 화면이 스스로 다루는 칸 — 폼에 두 번 그리지 않는다. */
const HANDLED = new Set(['name', 'type', 'on', 'source', 'target', 'cs'])

/** 숫자 칸인가 — `"=식"` 도 받으므로 글자 칸으로 두고 뜻만 가린다. */
function isNumeric(field: FieldSchema): boolean {
  const kinds = [field.type, ...(field.anyOf ?? []).map((one) => one.type)]
  return kinds.includes('number') || kinds.includes('integer')
}

function choices(field: FieldSchema): string[] | null {
  if (field.enum) return field.enum
  const fromAny = (field.anyOf ?? []).find((one) => one.enum)?.enum
  return fromAny ?? null
}

type Hold = 'free' | 'fixed' | 'amount' | 'spring'

const HOLD_LABEL: Record<Hold, string> = { free: '자유', fixed: '고정', amount: '변위량', spring: '스프링' }

/** 저장된 값의 뜻 — `null` 은 자유, 0 은 고정, 그 밖(수 · `=식`)은 변위량. */
function holdOf(value: unknown): Hold {
  if (value === null || value === undefined || value === '') return 'free'
  return value === 0 ? 'fixed' : 'amount'
}

/**
 * 방향 한 줄 — 이름, 자유 · 고정(· 변위량) 단추, 그 방향이 무엇인지. `onChoose` 가 없으면
 * **잠긴 줄**이다: 종류가 정한 것을 보여만 준다(어느 방향이 어떻게 잡히는지 알고 고르게).
 */
function HoldRow({
  label,
  hint,
  options,
  pressed,
  onChoose,
  amountLabel,
  children,
}: {
  label: string
  hint?: string
  options: Hold[]
  pressed: Hold
  onChoose?: (next: Hold) => void
  /** 「변위량」 단추의 이름 — 단위를 붙인다(`변위량 (mm)`). */
  amountLabel?: string
  children?: React.ReactNode
}) {
  const locked = !onChoose
  return (
    <div className="grid grid-cols-[4.5rem_1fr] items-center gap-x-2 gap-y-0.5">
      <span className="text-sm font-medium">{label}</span>
      <div className="flex gap-1" role="group" aria-label={`${label} 구속`} aria-disabled={locked || undefined}>
        {options.map((key) => (
          <button
            key={key}
            type="button"
            disabled={locked}
            aria-pressed={pressed === key}
            className={`flex-1 rounded border px-2 py-1 text-xs disabled:cursor-not-allowed ${
              pressed === key ? 'border-primary bg-accent font-medium' : 'text-muted-foreground'
            } ${locked && pressed !== key ? 'opacity-40' : ''}`}
            onClick={() => onChoose?.(key)}
          >
            {key === 'amount' && amountLabel ? amountLabel : HOLD_LABEL[key]}
          </button>
        ))}
      </div>
      {children}
      {hint && <p className="text-muted-foreground col-start-2 text-xs">{hint}</p>}
    </div>
  )
}

/**
 * 변위 성분 하나(X · Y · Z) — **자유 · 고정 · 변위량을 고른다.** 빈칸 = 자유, 0 = 고정을 알아서
 * 읽게 두면 헷갈리고, 헷갈리면 구속이 통째로 바뀐다. 변위량을 고르면 수 또는 `=식` 을 적는다.
 */
function AmountField({
  name,
  label,
  hint,
  unit,
  value,
  onChange,
}: {
  name: string
  label: string
  hint?: string
  /** 변위량의 단위 — 칸마다 보인다. 같은 화면의 좌표계 원점은 mm 라, 안 보이면 섞어 적는다. */
  unit?: string
  value: unknown
  onChange: (next: unknown) => void
}) {
  // 변위량을 골랐는데 아직 0 이면 저장값만으로는 「고정」 과 같아 보인다 — 고른 것을 들고 있는다.
  const [hold, setHold] = useState<Hold>(holdOf(value))
  useEffect(() => {
    setHold((now) => (now === 'amount' && value === 0 ? now : holdOf(value)))
  }, [value])
  const choose = (next: Hold) => {
    setHold(next)
    if (next === 'free') onChange(null)
    else if (next === 'fixed') onChange(0)
    else if (holdOf(value) !== 'amount') onChange(0)
  }
  return (
    <HoldRow
      label={label}
      hint={hint}
      options={['free', 'fixed', 'amount']}
      pressed={hold}
      onChoose={choose}
      amountLabel={unit ? `변위량 (${unit})` : undefined}
    >
      {hold === 'amount' && (
        <Input
          id={`cond-${name}`}
          aria-label={`${label} 변위량`}
          className="col-start-2"
          value={value === null || value === undefined ? '' : String(value)}
          placeholder={unit ? `수 또는 =식 (${unit})` : '수 또는 =식'}
          onChange={(e) => {
            const text = e.target.value
            // 비우면 0 — 자유로 바꾸려면 「자유」 를 누른다(빈칸이 자유를 뜻하지 않게).
            if (text === '') return onChange(0)
            if (text.startsWith('=')) return onChange(text)
            const num = Number(text)
            onChange(Number.isFinite(num) ? num : text)
          }}
        />
      )}
    </HoldRow>
  )
}

/** 성분 칸 하나 — 고를 것이 정해진 칸(`fixed` · `free`, 원통 지지)이면 단추만, 아니면 변위량까지. */
function ComponentField({
  name,
  field,
  units,
  value,
  onChange,
}: {
  name: string
  field: FieldSchema
  units: Record<string, string>
  value: unknown
  onChange: (next: unknown) => void
}) {
  const label = field.title ?? name
  const options = choices(field)
  const unit = field.unit ?? (field.dimension ? units[field.dimension] : undefined)
  if (!options) return <AmountField name={name} label={label} hint={field.description} unit={unit} value={value} onChange={onChange} />
  const pressed = String(value ?? field.default ?? 'fixed') as Hold
  return (
    <HoldRow
      label={label}
      hint={field.description}
      options={options.filter((one): one is Hold => one in HOLD_LABEL).sort((a, b) => (a === 'free' ? -1 : b === 'free' ? 1 : 0))}
      pressed={pressed}
      onChoose={onChange}
    />
  )
}

/** `12` → 12, `=식` → 그대로, 빈칸 → 0. */
function numberOrExpr(text: string): number | string {
  if (text.trim() === '') return 0
  if (text.startsWith('=')) return text
  const num = Number(text)
  return Number.isFinite(num) ? num : text
}

const QUICK: [string, number[]][] = [
  ['+X', [1, 0, 0]],
  ['−X', [-1, 0, 0]],
  ['+Y', [0, 1, 0]],
  ['−Y', [0, -1, 0]],
  ['+Z', [0, 0, 1]],
  ['−Z', [0, 0, -1]],
]

/**
 * 하중의 방향 — **좌표계의 X · Y · Z 성분**(길이는 상관없다), 압력이면 **면의 법선**도. 글자
 * 칸 하나에 `0,0,-1` 을 적게 하면 글자로 저장돼 서버가 거절한다 — 성분마다 칸을 둔다.
 */
function DirectionField({
  value,
  canNormal,
  fallback,
  onChange,
}: {
  value: unknown
  canNormal: boolean
  /** 비었을 때 서버가 쓰는 방향(중력은 -Z) — 그것을 보여 준다. */
  fallback: number[] | null
  onChange: (next: unknown) => void
}) {
  const normal = canNormal && (value === 'normal' || value === null || value === undefined)
  const vector = Array.isArray(value) ? (value as (number | string)[]) : (fallback ?? ['', '', ''])
  return (
    <div className="space-y-1">
      <Label>방향</Label>
      {canNormal && (
        <div className="flex gap-1" role="group" aria-label="방향 방식">
          {(
            [
              [true, '면의 법선'],
              [false, 'X·Y·Z 성분'],
            ] as const
          ).map(([isNormal, label]) => (
            <button
              key={label}
              type="button"
              aria-pressed={normal === isNormal}
              className={`flex-1 rounded border px-2 py-1 text-xs ${normal === isNormal ? 'border-primary bg-accent font-medium' : 'text-muted-foreground'}`}
              onClick={() => onChange(isNormal ? 'normal' : [0, 0, -1])}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      {normal ? (
        <p className="text-muted-foreground text-xs">각 면의 법선 방향으로 적용됩니다. 양수 값은 면을 누르는 방향입니다.</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-1">
            {(['X', 'Y', 'Z'] as const).map((axisName, index) => (
              <Input
                key={axisName}
                aria-label={`방향 ${axisName}`}
                placeholder={axisName}
                value={String(vector[index] ?? '')}
                onChange={(e) => {
                  const next = [0, 1, 2].map((i) => (typeof vector[i] === 'string' && vector[i] === '' ? 0 : vector[i]))
                  next[index] = numberOrExpr(e.target.value)
                  onChange(next)
                }}
              />
            ))}
          </div>
          <div className="flex gap-1" role="group" aria-label="빠른 방향">
            {QUICK.map(([label, v]) => (
              <button key={label} type="button" className="hover:bg-accent flex-1 rounded border px-1 py-0.5 text-xs" onClick={() => onChange(v)}>
                {label}
              </button>
            ))}
          </div>
          <p className="text-muted-foreground text-xs">위 ‘좌표계’의 축 성분입니다. 벡터의 크기와 관계없이 방향만 사용됩니다.</p>
        </>
      )}
    </div>
  )
}

/** 볼트 예압 — **예압(힘)** 으로 조일지 **조임량(길이)** 으로 조일지 고르고 값을 적는다. */
function BoltField({
  value,
  unit,
  units,
  onChange,
}: {
  value: unknown
  unit: string
  units: Record<string, string>
  onChange: (next: unknown, unit: string) => void
}) {
  const force = units.force ?? 'N'
  const length = units.length ?? 'mm'
  const byLength = unit === length
  return (
    <div className="space-y-1">
      <Label>체결 방식</Label>
      <div className="flex gap-1" role="group" aria-label="체결 방식">
        {(
          [
            [false, `예압 (${force})`],
            [true, `조임량 (${length})`],
          ] as const
        ).map(([isLength, label]) => (
          <button
            key={label}
            type="button"
            aria-pressed={byLength === isLength}
            className={`flex-1 rounded border px-2 py-1 text-xs ${byLength === isLength ? 'border-primary bg-accent font-medium' : 'text-muted-foreground'}`}
            onClick={() => onChange(value ?? null, isLength ? length : force)}
          >
            {label}
          </button>
        ))}
      </div>
      <Input
        aria-label={byLength ? '조임량' : '예압'}
        value={value === null || value === undefined ? '' : String(value)}
        placeholder="수 또는 =식"
        onChange={(e) => onChange(e.target.value === '' ? null : numberOrExpr(e.target.value), byLength ? length : force)}
      />
      <p className="text-muted-foreground text-xs">
        {byLength ? '볼트를 이 길이만큼 단축하여 체결합니다.' : '볼트 축 방향으로 이 힘만큼 인장하여 체결합니다.'} 볼트 축은 원통면으로부터 결정됩니다.
      </p>
    </div>
  )
}

/** 방향마다 무엇을 적는가 — 종류별 안내. */
const FOOTNOTE: Record<string, string> = {
  displacement: '방향은 위 ‘좌표계’의 축을 따릅니다. 변위량은 도면과 같은 mm 단위로 입력합니다.',
  remote_displacement:
    '선택한 면을 하나의 원격점에 연결하고 그 점을 구속합니다. 방향은 위 ‘좌표계’의 축을 따르며, 이동은 mm, 회전은 도(°) 단위입니다.',
  elastic_support: '방향은 종류에 따라 정해집니다. 스프링 강성은 아래 ‘기초 강성’에 입력합니다.',
  cylindrical: '방향은 선택한 원통면의 축을 기준으로 합니다. 좌표계는 선택하지 않습니다.',
}

export function ConditionForm({
  group,
  item,
  names,
  frames = [],
  units = {},
  onChange,
}: {
  group: GroupSchema
  item: ConditionItem
  /** 있는 선택 그룹 — 조건은 **선택 그룹만** 가리킨다(좌표를 박으면 설계점이 바뀔 때 어긋난다). */
  names: NamedSelection[]
  /** 고를 수 있는 좌표계 이름 — 도면의 것과 조건의 것. 「전역」 은 늘 있다. */
  frames?: string[]
  /** 입력 단위계의 이름표(`{force: 'N', stress: 'MPa', …}`) — 크기 칸에 단위를 붙인다. */
  units?: Record<string, string>
  onChange: (next: ConditionItem) => void
}) {
  const set = (key: string, value: unknown) => onChange({ ...item, [key]: value })
  const type = String(item.type ?? '')
  /** 대상이 「전체」 인가 — 국부 메시의 요소 형상 · 차수는 그때만 뜻이 있다. */
  const whole = group.fields.on?.whole
  const onWhole = whole !== undefined && String(item.on ?? group.fields.on?.default ?? whole) === whole
  const shown = ([, field]: [string, FieldSchema]) =>
    (!field.only_for || field.only_for.includes(type)) &&
    (!field.whole_only || onWhole) &&
    // 다른 칸의 값에 따라 — 비어 있으면 그 칸의 기본값으로 본다(서버가 그렇게 읽는다).
    Object.entries(field.when?.[type] ?? {}).every(([other, wanted]) => (item[other] ?? group.fields[other]?.default) === wanted)
  const implied = group.implied?.[type] ?? []
  const fields = Object.entries(group.fields)
    .filter(([key, field]) => !HANDLED.has(key) && !field.hidden)
    .filter(shown)
  const components = fields.filter(([, field]) => field.component)
  const others = fields.filter(([, field]) => !field.component)
  /** 종류를 바꾸면 그 종류가 안 쓰는 칸은 기본값으로 — 안 보이는 값이 남아 실려 가지 않게. */
  const setType = (nextType: string) => {
    const next: ConditionItem = { ...item, type: nextType }
    for (const [key, field] of Object.entries(group.fields)) {
      // 서버가 채우는 칸(단위)도 — 볼트의 「mm」 가 압력에 남으면 단위계와 어긋난다.
      if (field.hidden || (field.only_for && !field.only_for.includes(nextType))) next[key] = field.default ?? null
    }
    onChange(next)
  }
  const targets = ('source' in group.fields ? ['source', 'target'] : 'on' in group.fields ? ['on'] : []).filter((key) =>
    shown([key, group.fields[key]]),
  )
  /** 압력을 면의 법선으로 걸면 좌표계가 쓰이지 않는다 — 칸을 감춘다. */
  const alongNormal =
    !!group.fields.direction?.normal_for?.includes(type) && (item.direction == null || item.direction === 'normal')
  const typeLabels = group.fields.type?.labels ?? {}
  const note = group.notes?.[type]

  return (
    <div className="space-y-3">
      {group.intro && <p className="text-muted-foreground bg-muted/40 rounded px-2 py-1.5 text-xs">{group.intro}</p>}
      {'name' in group.fields && (
        <div className="space-y-1">
          <Label htmlFor="cond-name">이름</Label>
          <Input
            id="cond-name"
            value={String(item.name ?? '')}
            onChange={(e) => set('name', e.target.value)}
          />
        </div>
      )}

      {'type' in group.fields && (
        <div className="space-y-1">
          <Label>종류</Label>
          <Select value={String(item.type ?? '')} onValueChange={setType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {group.types.map((one) => (
                <SelectItem key={one} value={one}>
                  {typeLabels[one] ? `${typeLabels[one]} (${one})` : one}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {note && <p className="text-muted-foreground text-xs">{note}</p>}
        </div>
      )}

      {targets.map((key) => {
        const field = group.fields[key] ?? {}
        const label = field.title ?? (key === 'target' ? '상대 선택 그룹' : '선택 그룹')
        // **받는 종류만** 고르게 — 압력에 엣지 그룹을 고를 수 없다. 모양(원통면)은 서버가
        // 저장할 때 규칙을 보고 말한다(여기서는 규칙을 풀 수 없다).
        // 종류가 없는 묶음(국부 메시)은 `*` 가 모든 경우다.
        const accepts = group.accepts?.[type] ?? group.accepts?.['*']
        const choosable = accepts ? names.filter((one) => accepts.some((ok) => ok.entity === one.entity)) : names
        return (
        <div key={key} className="space-y-1">
          <Label>{label}</Label>
          <Select value={String(item[key] ?? field.whole ?? '')} onValueChange={(v) => set(key, v)}>
            <SelectTrigger aria-label={label}>
              <SelectValue placeholder="선택" />
            </SelectTrigger>
            <SelectContent>
              {field.whole && (
                <SelectItem value={field.whole}>
                  {field.whole} (모든 바디)
                </SelectItem>
              )}
              {choosable.map((one) => (
                <SelectItem key={one.name} value={one.name}>
                  {one.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {field.description && <p className="text-muted-foreground text-xs">{field.description}</p>}
          {accepts && <p className="text-muted-foreground text-xs">적용 가능 대상: {acceptsLabel(accepts)} 선택 그룹</p>}
          {names.length > 0 && choosable.length === 0 && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              사용할 수 있는 선택 그룹이 없습니다. 3D에서 대상 형상({acceptsLabel(accepts ?? [])})을 선택하여 생성하십시오.
            </p>
          )}
          {names.length === 0 && !field.whole && (
            <p className="text-muted-foreground text-xs">
              선택 그룹이 없습니다. 3D에서 형상을 선택하면 생성됩니다.
            </p>
          )}
        </div>
        )
      })}

      {/*
        **좌표계** — 성분(x · y · z)이 어느 방향인가. 「전역」 이 기본이고, 도면 · 해석 조건에서
        이름 붙인 좌표계를 고른다(리본의 「좌표계」).
      */}
      {'cs' in group.fields && shown(['cs', group.fields.cs]) && !alongNormal && (
        <div className="space-y-1">
          <Label htmlFor="cond-cs">좌표계</Label>
          <select
            id="cond-cs"
            className="bg-background w-full rounded border px-2 py-1 text-sm"
            value={String(item.cs ?? 'global')}
            onChange={(e) => set('cs', e.target.value)}
          >
            <option value="global">전역</option>
            {frames.map((one) => (
              <option key={one} value={one}>
                {one}
              </option>
            ))}
          </select>
        </div>
      )}

      {/*
        **방향마다** — 고르는 종류(변위 · 원통)는 단추를, 종류가 정하는 것(고정 · 마찰 없는 ·
        압축 전용)은 잠긴 단추를 보인다. 어느 방향이 어떻게 잡히는지 모르고 고르면 풀리지 않는
        모델이나 과구속을 만든다.
      */}
      {(components.length > 0 || implied.length > 0) && (
        <div className="space-y-2">
          <Label>방향별 구속</Label>
          {components.map(([key, field]) => (
            <ComponentField key={key} name={key} field={field} units={units} value={item[key]} onChange={(v) => set(key, v)} />
          ))}
          {implied.map((one) => (
            <HoldRow
              key={one.label}
              label={one.label}
              hint={one.hint}
              options={one.hold === 'spring' ? ['free', 'spring'] : ['free', 'fixed']}
              pressed={one.hold}
            />
          ))}
          <p className="text-muted-foreground text-xs">
            {FOOTNOTE[type] ?? '이 종류에서 정해진 값이므로 변경할 수 없습니다. 방향별로 지정하려면 displacement 또는 cylindrical을 선택하십시오.'}
          </p>
        </div>
      )}

      {others.map(([key, field]) => {
        const options = choices(field)
        const value = item[key]
        if (field.direction) {
          return (
            <DirectionField
              key={key}
              value={value}
              canNormal={!!field.normal_for?.includes(type)}
              fallback={type === 'standard_earth_gravity' ? [0, 0, -1] : null}
              onChange={(v) => set(key, v)}
            />
          )
        }
        // 켬 · 끔 — 글자 칸에 true 를 적게 두면 「true」 라는 글자가 저장된다.
        if (field.type === 'boolean') {
          const on = value === true
          return (
            <div key={key} className="space-y-1">
              <Label>{field.title ?? key}</Label>
              <div className="flex gap-1" role="group" aria-label={field.title ?? key}>
                {(
                  [
                    [false, '끔'],
                    [true, '켬'],
                  ] as const
                ).map(([next, label]) => (
                  <button
                    key={label}
                    type="button"
                    aria-pressed={on === next}
                    className={`flex-1 rounded border px-2 py-1 text-xs ${on === next ? 'border-primary bg-accent font-medium' : 'text-muted-foreground'}`}
                    onClick={() => set(key, next)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {field.description && <p className="text-muted-foreground text-xs">{field.description}</p>}
            </div>
          )
        }
        // 최소 ~ 최대 — 글자 칸 하나에 「10, 500」 을 적게 두면 목록이 아니라 글자로 저장된다.
        if (field.range) {
          const span = Array.isArray(value) ? (value as (number | string)[]) : null
          const title = `${field.title ?? key}${field.unit ? ` (${field.unit})` : ''}`
          const put = (index: number, text: string) => {
            const next: (number | string)[] = span ? [...span] : ['', '']
            next[index] = text === '' ? '' : numberOrExpr(text)
            // 둘 다 비우면 범위가 없다(null) — 한쪽만 적은 것은 서버가 알린다.
            set(key, next.every((one) => one === '') ? null : next.map((one) => (one === '' ? 0 : one)))
          }
          return (
            <div key={key} className="space-y-1">
              <Label>{title}</Label>
              <div className="flex items-center gap-1">
                <Input aria-label={`${field.title ?? key} 최소`} placeholder="최소" value={span ? String(span[0] ?? '') : ''} onChange={(e) => put(0, e.target.value)} />
                <span className="text-muted-foreground text-xs">~</span>
                <Input aria-label={`${field.title ?? key} 최대`} placeholder="최대" value={span ? String(span[1] ?? '') : ''} onChange={(e) => put(1, e.target.value)} />
              </div>
              {field.description && <p className="text-muted-foreground text-xs">{field.description}</p>}
            </div>
          )
        }
        if (field.components) {
          const vector = Array.isArray(value) ? (value as (number | string)[]) : ['', '', '']
          const title = `${field.title ?? key}${field.unit ? ` (${field.unit})` : ''}`
          return (
            <div key={key} className="space-y-1">
              <Label>{title}</Label>
              <div className="grid grid-cols-3 gap-1">
                {(['X', 'Y', 'Z'] as const).map((axisName, index) => (
                  <Input
                    key={axisName}
                    aria-label={`${field.title ?? key} ${axisName}`}
                    placeholder={axisName}
                    value={String(vector[index] ?? '')}
                    onChange={(e) => {
                      const next = [0, 1, 2].map((i) => (vector[i] === '' || vector[i] === undefined ? 0 : vector[i]))
                      next[index] = numberOrExpr(e.target.value)
                      set(key, next)
                    }}
                  />
                ))}
              </div>
              {field.description && <p className="text-muted-foreground text-xs">{field.description}</p>}
            </div>
          )
        }
        if (field.bolt) {
          return (
            <BoltField
              key={key}
              value={value}
              unit={String(item.unit ?? '')}
              units={units}
              onChange={(v, unit) => onChange({ ...item, [key]: v, unit })}
            />
          )
        }
        const unitName = field.unit ?? (field.unit_by_type ? units[group.dimensions?.[type] ?? ''] : undefined)
        const title = `${field.title ?? key}${unitName ? ` (${unitName})` : ''}`
        if (options) {
          return (
            <div key={key} className="space-y-1">
              <Label>{title}</Label>
              {/* 비어 있으면 서버의 기본값이 쓰인다 — 그것을 보여 준다. */}
              <Select value={String(value ?? field.default ?? '')} onValueChange={(v) => set(key, v)}>
                <SelectTrigger aria-label={field.title ?? key}>
                  <SelectValue placeholder="(없음)" />
                </SelectTrigger>
                <SelectContent>
                  {options.map((one) => (
                    <SelectItem key={one} value={one}>
                      {field.labels?.[one] ?? one}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {field.description && <p className="text-muted-foreground text-xs">{field.description}</p>}
            </div>
          )
        }
        return (
          <div key={key} className="space-y-1">
            <Label htmlFor={`cond-${key}`}>{title}</Label>
            <Input
              id={`cond-${key}`}
              value={value === null || value === undefined ? '' : String(value)}
              placeholder={
                // 비우면 서버가 기본값을 쓴다 — 그것을 보여 준다(빈칸이 「안 보낸다」 로 읽히지 않게).
                field.default !== undefined && field.default !== null && field.default !== ''
                  ? `기본값 ${String(field.default)}`
                  : field.integer
                    ? '정수 또는 =식'
                    : isNumeric(field)
                      ? '수 또는 =식'
                      : ''
              }
              onChange={(e) => {
                const text = e.target.value
                if (text === '') return set(key, null)
                // **식을 그대로 둔다.** `"=압력"` 은 설계점마다 풀린다 — 여기서 숫자로 바꾸면
                // 그 뜻이 사라진다.
                if (isNumeric(field) && !text.startsWith('=')) {
                  const num = Number(text)
                  return set(key, Number.isFinite(num) ? num : text)
                }
                set(key, text)
              }}
            />
            {field.description && <p className="text-muted-foreground text-xs">{field.description}</p>}
          </div>
        )
      })}
    </div>
  )
}
