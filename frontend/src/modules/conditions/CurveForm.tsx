/**
 * **곡선 창의 칸** — 이름 · 가로축 · 보간 · 값의 단위 · 배율 · 점(표 + 그래프). 공유 칸이라 모든 케이스의 하중이
 * 같은 곡선을 본다. 칸의 이름 · 설명은 사양표(`curves.fields`)의 것이다.
 *
 * 하중이 곡선을 가리키려면 그 표의 뜻과 맞아야 한다(가속도 PSD — 주파수 · 로그-로그 · g^2/Hz, 주파수별 배율 —
 * 주파수 · 선형 · 단위 없음). 그래서 **쓰임 단추**가 그 셋을 한 번에 맞춘다(`presets`).
 */

import type { CurveItem, FieldSchema } from '@/modules/conditions/api'
import { AXIS_UNITS, curveProblems } from '@/modules/conditions/curves'
import { FrequencyTable } from '@/modules/conditions/FrequencyTable'
import type { Row } from '@/modules/conditions/excitation'
import { cellOf } from '@/modules/conditions/excitation'
import { NumberText } from '@/modules/conditions/NumberText'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/** 쓰임 하나 — 그 하중 칸이 곡선을 읽는 법(보간 · 단위)과 이름표. */
export interface CurvePreset {
  label: string
  interpolation: string
  unit: string
}

/** 가속도 PSD 의 단위(서버 `PSD_UNIT`) — 표의 열 이름은 g²/Hz 로 보인다. */
const PSD_UNIT = 'g^2/Hz'

function Choices({
  label,
  options,
  value,
  disabled = {},
  onPick,
}: {
  label: string
  options: [string, string][]
  value: string
  /** 고를 수 없는 것과 그 까닭. */
  disabled?: Record<string, string>
  onPick: (next: string) => void
}) {
  return (
    <div className="flex gap-1" role="group" aria-label={label}>
      {options.map(([key, text]) => (
        <button
          key={key}
          type="button"
          aria-pressed={value === key}
          disabled={key in disabled}
          title={disabled[key]}
          className={`flex-1 rounded border px-2 py-1 text-xs disabled:opacity-40 ${value === key ? 'border-primary bg-accent font-medium' : 'text-muted-foreground'}`}
          onClick={() => onPick(key)}
        >
          {text}
        </button>
      ))}
    </div>
  )
}

const labelsOf = (field: FieldSchema | undefined, fallback: Record<string, string>): [string, string][] =>
  Object.entries(field?.labels ?? fallback)

export function CurveForm({
  value,
  onChange,
  fields,
  intro,
  presets,
  users,
}: {
  value: CurveItem
  onChange: (next: CurveItem) => void
  /** 사양표의 칸(`curves.fields`) — 이름표 · 설명. */
  fields: Record<string, FieldSchema>
  intro?: string
  /** 쓰임 단추 — 그 하중 칸이 읽는 보간 · 단위를 한 번에. */
  presets: CurvePreset[]
  /** 이 곡선을 가리키는 하중(모든 케이스). */
  users: string[]
}) {
  const set = (patch: Partial<CurveItem>) => onChange({ ...value, ...patch })
  const x = value.x
  const interpolation = value.interpolation ?? 'linear'
  const unit = value.unit ?? ''
  const rows: Row[] = Array.isArray(value.points) ? (value.points as Row[]) : []
  const problems = curveProblems(value)
  const axisLabels = labelsOf(fields.x, { frequency: '주파수', time: '시간', step: '단계' })
  const axisTitle = axisLabels.find(([key]) => key === x)?.[1] ?? x
  const current = presets.find((one) => x === 'frequency' && one.interpolation === interpolation && one.unit === unit)

  return (
    <div className="space-y-3">
      {intro && <p className="text-muted-foreground bg-muted/40 rounded px-2 py-1.5 text-xs">{intro}</p>}
      <div className="space-y-1">
        <Label htmlFor="curve-name">{fields.name?.title ?? '곡선 이름'}</Label>
        <Input id="curve-name" value={value.name} maxLength={60} onChange={(event) => set({ name: event.target.value })} />
      </div>

      {presets.length > 0 && (
        <div className="space-y-1">
          <Label>쓰임</Label>
          <div className="flex flex-wrap gap-1" role="group" aria-label="쓰임">
            {presets.map((one) => (
              <button
                key={one.label}
                type="button"
                aria-pressed={current === one}
                className={`rounded border px-2 py-1 text-xs ${current === one ? 'border-primary bg-accent font-medium' : 'text-muted-foreground'}`}
                title={`주파수 곡선 · ${one.interpolation === 'loglog' ? '로그-로그' : '선형'} 보간 · 단위 ${one.unit || '없음'}으로 맞춥니다.`}
                onClick={() => set({ x: 'frequency', interpolation: one.interpolation, unit: one.unit })}
              >
                {one.label}
              </button>
            ))}
          </div>
          <p className="text-muted-foreground text-xs">
            {current
              ? `${current.label} 하중이 이 곡선을 가리킬 수 있습니다.`
              : x === 'frequency'
                ? '이 보간 · 단위의 곡선을 가리키는 하중이 아직 없습니다. 위 단추로 맞추십시오.'
                : '시간 · 단계 곡선은 비선형 정적(하중 이력)에서 하중이 가리킵니다 — 지금은 저장만 됩니다.'}
          </p>
        </div>
      )}

      <div className="space-y-1">
        <Label>{fields.x?.title ?? '가로축'}</Label>
        <Choices
          label={fields.x?.title ?? '가로축'}
          options={axisLabels}
          value={x}
          // 로그-로그는 주파수 곡선에만 — 다른 축으로 바꾸면 선형으로.
          onPick={(next) => set(next !== 'frequency' && interpolation === 'loglog' ? { x: next, interpolation: 'linear' } : { x: next })}
        />
      </div>
      <div className="space-y-1">
        <Label>{fields.interpolation?.title ?? '보간'}</Label>
        <Choices
          label={fields.interpolation?.title ?? '보간'}
          options={labelsOf(fields.interpolation, { linear: '선형', loglog: '로그-로그', step: '계단' })}
          value={interpolation}
          disabled={x === 'frequency' ? {} : { loglog: '로그-로그 보간은 주파수 곡선에만 씁니다.' }}
          onPick={(next) => set({ interpolation: next })}
        />
        {fields.interpolation?.description && <p className="text-muted-foreground text-xs">{fields.interpolation.description}</p>}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label htmlFor="curve-unit">{fields.unit?.title ?? '값의 단위'}</Label>
          <Input id="curve-unit" value={unit} maxLength={20} placeholder="배율이면 비워 둡니다" onChange={(event) => set({ unit: event.target.value.trim() })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="curve-scale">{fields.scale?.title ?? '배율'}</Label>
          <NumberText id="curve-scale" value={value.scale ?? 1} onText={(text) => set({ scale: text.trim() === '' ? 1 : cellOf(text) })} />
        </div>
      </div>
      {fields.scale?.description && <p className="text-muted-foreground -mt-2 text-xs">{fields.scale.description}</p>}

      <FrequencyTable
        title={fields.points?.title ?? '점'}
        columns={[
          { title: axisTitle, unit: AXIS_UNITS[x] || undefined },
          { title: '값', unit: unit === PSD_UNIT ? 'g²/Hz' : unit || undefined },
        ]}
        grms={x === 'frequency' && interpolation === 'loglog' && unit === PSD_UNIT}
        description={fields.points?.description}
        plot={interpolation}
        plotScale={value.scale ?? 1}
        value={rows}
        onChange={(next) => set({ points: next ?? [] })}
      />
      {problems.length > 0 && (
        <ul className="space-y-0.5 text-xs text-amber-700 dark:text-amber-400" aria-label="곡선 문제">
          {problems.map((one) => (
            <li key={one}>⚠ {one}</li>
          ))}
        </ul>
      )}

      <div className="space-y-1">
        <Label>이 곡선을 쓰는 하중</Label>
        {users.length > 0 ? (
          <ul className="text-xs" aria-label="이 곡선을 쓰는 하중">
            {users.map((one) => (
              <li key={one}>{one}</li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-xs">아직 없습니다. 하중 창의 표 아래 ‘곡선’에서 고릅니다.</p>
        )}
      </div>
    </div>
  )
}
