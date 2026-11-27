/**
 * 조건 하나의 칸들 — **서버가 준 사양표로 그린다.**
 *
 * 종류가 열 몇이고 칸이 제각각이다(고정 지지에는 값이 없고, 압력에는 크기와 방향이, 볼트에는
 * 예압이). 화면에 `if` 를 늘어놓으면 종류를 더할 때마다 여기를 고쳐야 한다 — 칸 목록은 서버가
 * 들고 있고(`core/conditions/`) 여기는 그것을 그린다. CAD 의 `NodeForm` 과 같은 방식이다.
 */

import { useEffect, useState } from 'react'

import { acceptsLabel } from '@/modules/conditions/api'
import { CurvePlot } from '@/modules/conditions/CurvePlot'
import { curveMismatch, nextCurveName, tableOfCurve } from '@/modules/conditions/curves'
import { FrequencyTable } from '@/modules/conditions/FrequencyTable'
import type { FrequencyColumn } from '@/modules/conditions/FrequencyTable'
import { stepLabel } from '@/modules/conditions/LoadStepsEditor'
import type { LoadStep } from '@/modules/conditions/LoadStepsEditor'
import { NumberText } from '@/modules/conditions/NumberText'
import type { ConditionItem, CurveItem, CurveUse, FieldSchema, GroupSchema, NamedSelection } from '@/modules/conditions/api'
import { Button } from '@/shared/components/ui/button'
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
        <NumberText
          id={`cond-${name}`}
          aria-label={`${label} 변위량`}
          className="col-start-2"
          value={value}
          placeholder={unit ? `수 또는 =식 (${unit})` : '수 또는 =식'}
          onText={(text) => {
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
              <NumberText
                key={axisName}
                aria-label={`방향 ${axisName}`}
                placeholder={axisName}
                value={vector[index]}
                onText={(text) => {
                  const next = [0, 1, 2].map((i) => (typeof vector[i] === 'string' && vector[i] === '' ? 0 : vector[i]))
                  next[index] = numberOrExpr(text)
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
      <NumberText
        aria-label={byLength ? '조임량' : '예압'}
        value={value}
        placeholder="수 또는 =식"
        onText={(text) => onChange(text === '' ? null : numberOrExpr(text), byLength ? length : force)}
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

const axisLabel = (column: FrequencyColumn | undefined, fallback: string) =>
  column ? `${column.title}${column.unit ? ` (${column.unit})` : ''}` : fallback

/**
 * 표 대신 **곡선**(`curves[]`, 이름)을 가리키는 하중 — 내보낼 때 서버가 곡선의 점(× 배율)을 이 표로 푼다. 표를
 * 그리면 빈 표로 보이고 거기 적으면 서버가 「표와 곡선을 함께 적을 수 없다」 로 막으므로, 무엇을 쓰는지 말하고
 * 곡선의 그래프를 보인다. 곡선은 공유라 트리의 「곡선」 에서 고친다. 표로 적으려면 뗀다 — 점 × 배율이 표로 옮겨진다.
 */
function CurveNotice({
  field,
  name,
  curve,
  known,
  mismatch,
  onDetach,
}: {
  field: FieldSchema
  name: string
  /** 그 이름의 곡선 — 없으면 `undefined`. */
  curve?: CurveItem
  /** 곡선 목록을 받았나 — 옛 서버면 곡선을 고칠 자리가 없다. */
  known: boolean
  /** 이 하중이 이 곡선을 가리킬 수 없는 까닭(서버 규칙). */
  mismatch: string | null
  onDetach: () => void
}) {
  const columns = field.table?.columns
  return (
    <div role="status" className="bg-muted/40 space-y-1 rounded px-2 py-1.5 text-xs">
      <p>
        {field.title ?? '표'}: 곡선 ‘{name}’의 점을 씁니다.{' '}
        {!known
          ? '곡선은 아직 이 화면에서 고칠 수 없습니다.'
          : curve
            ? '곡선은 트리의 ‘곡선’에서 고칩니다 — 이 곡선을 가리키는 모든 하중에 함께 반영됩니다.'
            : '이 이름의 곡선이 없습니다. 곡선을 만들거나 떼십시오.'}
      </p>
      {mismatch && <p className="text-amber-700 dark:text-amber-400">⚠ {mismatch}</p>}
      {curve && (
        <CurvePlot
          title={`곡선 ‘${curve.name}’`}
          points={curve.points}
          scale={curve.scale ?? 1}
          interpolation={curve.interpolation ?? 'linear'}
          xLabel={axisLabel(columns?.[0], '가로축')}
          yLabel={axisLabel(columns?.[1], '값')}
        />
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        title="곡선의 점(× 배율)을 이 표로 옮기고 곡선을 뗍니다. 배율이 식이면 표는 비워 둡니다."
        onClick={onDetach}
      >
        곡선 떼고 표로 입력
      </Button>
    </div>
  )
}

/**
 * 표 아래의 **곡선 고르기** — 표 대신 공유 곡선을 가리킨다(맞지 않는 곡선은 까닭과 함께 막는다), 또는 지금 표를
 * 곡선으로 저장해 다른 하중 · 케이스와 함께 쓴다.
 */
function CurvePick({
  title,
  curves,
  use,
  canMake,
  onPick,
  onMake,
}: {
  title: string
  curves: CurveItem[]
  use: CurveUse
  /** 표에 점이 두 개 이상 있고 곡선을 더할 수 있나. */
  canMake: boolean
  onPick: (name: string) => void
  onMake?: () => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <label className="flex items-center gap-1.5">
        곡선
        <select
          aria-label={`${title} 곡선`}
          className="bg-background max-w-64 rounded border px-1.5 py-0.5 text-xs"
          title="곡선을 고르면 이 표 대신 곡선의 점을 씁니다(표는 비워집니다)."
          value=""
          disabled={curves.length === 0}
          onChange={(event) => event.target.value && onPick(event.target.value)}
        >
          <option value="">{curves.length > 0 ? '표로 입력 — 곡선 고르기' : '곡선 없음'}</option>
          {curves.map((one) => {
            const why = curveMismatch(one, use)
            return (
              <option key={one.name} value={one.name} disabled={!!why}>
                {one.name}
                {why ? ` — ${why}` : ''}
              </option>
            )
          })}
        </select>
      </label>
      {onMake && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 text-xs"
          disabled={!canMake}
          title="이 표를 공유 곡선으로 저장하고, 이 하중이 그 곡선을 가리키게 합니다. 다른 하중 · 케이스도 같은 곡선을 쓸 수 있습니다."
          onClick={onMake}
        >
          표를 곡선으로 저장
        </Button>
      )}
    </div>
  )
}

/** 표 칸 — 가진 프로파일. 사양표의 열 이름 · Grms 여부로 그리고, 그 보간대로 그래프를 단다(`FrequencyTable`). */
function TableField({ field, value, onChange }: { field: FieldSchema; value: unknown; onChange: (next: unknown) => void }) {
  return (
    <FrequencyTable
      title={field.title ?? '표'}
      columns={field.table?.columns}
      grms={Boolean(field.table?.grms)}
      description={field.description}
      // 가속도 PSD 는 로그-로그, 주파수별 배율은 선형 — 서버가 표를 읽는 법과 같다.
      plot={field.table?.grms ? 'loglog' : 'linear'}
      value={value}
      onChange={onChange}
    />
  )
}

export function ConditionForm({
  group,
  item,
  names,
  frames = [],
  units = {},
  analysis,
  curves,
  curveUses,
  timeUse,
  timeLoads = [],
  steps,
  onMakeCurve,
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
  /** 지금 해석 종류 — 주면 `analysis_only` 칸(조화 응답의 주파수별 배율 · 위상)을 그때만 보인다. */
  analysis?: string
  /** 공유 곡선(`curves[]`) — 주면 표 칸 아래에서 곡선을 고른다. 옛 서버면 없다. */
  curves?: CurveItem[]
  /** 하중 종류마다 곡선이 채우는 표 칸 · 보간 · 단위(`schema.curves.uses`). */
  curveUses?: Record<string, CurveUse>
  /** 정적 하중의 시간 · 단계 곡선(`schema.curves.time_use`) — `timeLoads` 의 종류가 정적에서 이것으로 읽는다. */
  timeUse?: CurveUse
  timeLoads?: string[]
  /**
   * 케이스의 정적 해석이면 그 하중 단계(② — 비면 한 단계). 주면 하중마다 거는 단계를 고른다. 케이스가 없는 조건이나 정적이
   * 아니면 비운다.
   */
  steps?: LoadStep[]
  /** 표를 곡선으로 저장한다 — 한 벌의 곡선에 더한다(창을 취소해도 남는다 — 3D 에서 만든 선택 그룹처럼). */
  onMakeCurve?: (curve: CurveItem) => void
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
    (!field.analysis_only || analysis === undefined || field.analysis_only.includes(analysis)) &&
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
          <Select
            value={String(item[key] ?? field.whole ?? '')}
            onValueChange={(v) => {
              // 「전체」 가 아닌 대상으로 바꾸면 「전체」 에만 뜻이 있는 칸(요소 형상 · 차수)은 기본값으로 —
              // 감춘 값이 남아 실려 가지 않게(종류를 바꿀 때와 같은 규칙).
              if (key === 'on' && whole !== undefined && v !== whole) {
                const next: ConditionItem = { ...item, on: v }
                for (const [name, one] of Object.entries(group.fields)) if (one.whole_only) next[name] = one.default ?? null
                return onChange(next)
              }
              set(key, v)
            }}
          >
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
          {type === 'bolt_pretension' && (
            <p className="text-muted-foreground text-xs">
              바디에 건 예압은 단면을 정할 좌표계를 고릅니다 — Z 축이 볼트 축, 원점이 단면 자리입니다. 원통면에 건
              예압은 면이 정하므로 전역으로 둡니다.
            </p>
          )}
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
        const use = analysis === 'static' && timeUse && timeLoads.includes(type) ? timeUse : curveUses?.[type]
        if (field.table && typeof item.curve === 'string' && item.curve !== '') {
          const curve = curves?.find((one) => one.name === item.curve)
          return (
            <CurveNotice
              key={key}
              field={field}
              name={item.curve}
              curve={curve}
              known={curves !== undefined}
              mismatch={curve && use ? curveMismatch(curve, use) : null}
              onDetach={() => onChange({ ...item, curve: '', [key]: tableOfCurve(curve) })}
            />
          )
        }
        if (field.table) {
          const rows = Array.isArray(value) ? value.length : 0
          return (
            <div key={key} className="space-y-1.5">
              <TableField field={field} value={value} onChange={(v) => set(key, v)} />
              {curves && use?.field === key && (
                <CurvePick
                  title={field.title ?? '표'}
                  curves={curves}
                  use={use}
                  canMake={rows >= 2}
                  onPick={(name) => onChange({ ...item, curve: name, [key]: null })}
                  onMake={
                    onMakeCurve &&
                    (() => {
                      const name = nextCurveName(curves, `${String(item.name ?? '') || (field.title ?? '하중')} 곡선`)
                      onMakeCurve({ name, x: use.axes?.[0] ?? 'frequency', interpolation: use.interpolation, unit: use.unit, points: value as CurveItem['points'], scale: 1 })
                      onChange({ ...item, curve: name, [key]: null })
                    })
                  }
                />
              )}
            </div>
          )
        }
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
                <NumberText aria-label={`${field.title ?? key} 최소`} placeholder="최소" value={span ? span[0] : ''} onText={(text) => put(0, text)} />
                <span className="text-muted-foreground text-xs">~</span>
                <NumberText aria-label={`${field.title ?? key} 최대`} placeholder="최대" value={span ? span[1] : ''} onText={(text) => put(1, text)} />
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
                  <NumberText
                    key={axisName}
                    aria-label={`${field.title ?? key} ${axisName}`}
                    placeholder={axisName}
                    value={vector[index]}
                    onText={(text) => {
                      const next = [0, 1, 2].map((i) => (vector[i] === '' || vector[i] === undefined ? 0 : vector[i]))
                      next[index] = numberOrExpr(text)
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
            <NumberText
              id={`cond-${key}`}
              value={value}
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
              onText={(text) => {
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
      {steps !== undefined && 'active_steps' in group.fields && (
        <StepChoice type={type} item={item} steps={steps} timeLoads={timeLoads} onChange={onChange} />
      )}
    </div>
  )
}

/**
 * **하중을 거는 단계**(② — 케이스의 정적 해석, 단계가 둘 이상일 때). 비우면 모든 단계에 건다(서버 `active_steps` — 처음
 * 켜지는 단계 안에서 0 부터 오르고, 꺼지는 단계 안에서 0 으로 내린다). 시간별 배율과 함께 쓰지 않는다. 볼트는 첫 단계에서
 * 조이고 다음 단계부터 잠그며, 중력은 모든 단계에 같게 걸린다 — 고르지 않고 그렇다고 말한다.
 */
function StepChoice({
  type,
  item,
  steps,
  timeLoads,
  onChange,
}: {
  type: string
  item: ConditionItem
  steps: LoadStep[]
  timeLoads: string[]
  onChange: (next: ConditionItem) => void
}) {
  if (steps.length < 2) return null
  if (type === 'bolt_pretension') {
    return <p className="text-muted-foreground text-xs">볼트는 첫 단계에서 조이고, 다음 단계부터 조인 길이로 잠급니다.</p>
  }
  if (type === 'standard_earth_gravity') {
    return <p className="text-muted-foreground text-xs">중력은 모든 하중 단계에 같게 걸립니다.</p>
  }
  if (!timeLoads.includes(type)) return null
  const chosen = Array.isArray(item.active_steps) ? (item.active_steps as number[]) : []
  const all = steps.map((_, index) => index + 1)
  const on = (n: number) => chosen.length === 0 || chosen.includes(n)
  const timed = (Array.isArray(item.time_table) && item.time_table.length > 0) || (typeof item.curve === 'string' && item.curve !== '')
  const toggle = (n: number) => {
    const current = chosen.length === 0 ? all : chosen
    const next = current.includes(n) ? current.filter((one) => one !== n) : [...current, n].sort((a, b) => a - b)
    if (next.length === 0) return
    onChange({ ...item, active_steps: next.length === all.length ? [] : next })
  }
  return (
    <div className="space-y-1">
      <Label>적용 단계</Label>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs" role="group" aria-label="적용 단계">
        {steps.map((step, index) => (
          <label key={index} className="flex items-center gap-1">
            <input type="checkbox" checked={on(index + 1)} disabled={timed} onChange={() => toggle(index + 1)} />
            {stepLabel(step, index)}
          </label>
        ))}
      </div>
      <p className="text-muted-foreground text-xs">
        {timed
          ? '시간별 배율을 쓰는 하중은 단계를 고르지 않습니다. 끄려는 시간의 배율을 0으로 적으십시오.'
          : '처음 거는 단계 안에서 0부터 오르고, 끄는 단계 안에서 0으로 내립니다. 모두 고르면 모든 단계에 겁니다.'}
      </p>
    </div>
  )
}
