/**
 * 조립 구속 — 구성품을 **숫자 대신 관계로** 놓는다.
 *
 * 「이 바닥면을 지그 윗면에 맞대고, 이 구멍을 저 구멍과 동심으로」. 자리를 숫자로 적어 두면
 * 지그 높이가 실험계획으로 바뀌는 순간 부품이 허공에 뜬다 — 구속은 설계점마다 다시 풀린다.
 *
 * 고르는 법: 종류를 정하고 「이것」 을 누른 뒤 3D 에서 이 구성품의 면을, 「상대」 를 누른 뒤
 * 앞에 놓인 구성품의 면을 누른다(또는 상대를 기준면 · 기준축으로). 서버가 누른 면을 **질의로**
 * 바꿔 준다(`/cad/recipe/mate-pick`) — 치수가 바뀌어도 그 면을 따라가게.
 */

import { Crosshair, Trash2 } from 'lucide-react'

import type { Mate, Placement } from '@/modules/cad/api'
import { NumberField } from '@/modules/cad/NumberField'
import { Button } from '@/shared/components/ui/button'

export const MATE_TYPES: { value: Mate['type']; label: string; help: string }[] = [
  { value: 'touch', label: '접촉', help: '두 평면을 마주 보게 접촉시킵니다. 간극을 지정할 수 있습니다.' },
  { value: 'flush', label: '동일 평면', help: '두 평면이 같은 방향을 향하며 동일 평면에 놓입니다.' },
  { value: 'concentric', label: '동심', help: '구멍과 축을 동축으로 맞춥니다. 원통면을 클릭하십시오.' },
  { value: 'parallel', label: '평행', help: '방향만 평행하게 맞춥니다.' },
  { value: 'perpendicular', label: '직각', help: '방향만 직각으로 맞춥니다.' },
  { value: 'angle', label: '각도', help: '두 방향 사이의 각도를 지정합니다.' },
]
const TYPE_LABEL = Object.fromEntries(MATE_TYPES.map((one) => [one.value, one.label])) as Record<Mate['type'], string>

/** 기준 — 3D 에서 누르지 않고 상대로 고른다. */
const DATUMS = [
  { value: 'XY', label: 'XY 평면' },
  { value: 'XZ', label: 'XZ 평면' },
  { value: 'YZ', label: 'YZ 평면' },
  { value: 'X', label: 'X축' },
  { value: 'Y', label: 'Y축' },
  { value: 'Z', label: 'Z축' },
]
const DATUM_NAMES = new Set(DATUMS.map((one) => one.value))

const ROLE_LABEL: Record<string, string> = { top: '윗면', bottom: '아랫면', side: '옆면', step: '단의 윗면', underside: '단의 아랫면' }

function directionLabel(vector: unknown): string {
  if (!Array.isArray(vector) || vector.length !== 3) return ''
  const values = vector.map(Number)
  const index = values.reduce((best, value, i) => (Math.abs(value) > Math.abs(values[best]) ? i : best), 0)
  if (Math.abs(values[index]) < 0.999) return '경사'
  return `${values[index] > 0 ? '+' : '-'}${'XYZ'[index]}`
}

/** 질의를 사람 말로 — 「아랫면」 · 「R4 원통면」 · 「+X 평면 (누른 자리)」. */
export function describeSelect(select: Record<string, unknown> | null | undefined): string {
  if (!select) return '—'
  const words: string[] = []
  if (typeof select.body === 'string') words.push(`‘${select.body}’`)
  const kind = select.kind
  if (typeof select.role === 'string') words.push(ROLE_LABEL[select.role] ?? select.role)
  else if (kind === 'plane') words.push(`${directionLabel(select.normal)} 평면`.trim())
  else if (kind === 'cylinder' || kind === 'cone') {
    const radius = typeof select.radius === 'number' ? `R${select.radius} ` : ''
    const axis = select.axis ? `${directionLabel(select.axis).replace(/^[+-]/, '')}축 ` : ''
    words.push(`${radius}${axis}${kind === 'cylinder' ? '원통면' : '원뿔면'}`)
  } else if (select.what === 'edges') words.push(kind === 'circle' ? '원 엣지' : kind === 'line' ? '직선 엣지' : '엣지')
  else words.push('면')
  if (select.near) words.push('(클릭 위치)')
  return words.join(' ')
}

/** 만드는 중인 구속 — 「이것」 · 「상대」 를 다 고르면 더한다. */
export interface MateDraft {
  type: Mate['type']
  this?: Record<string, unknown>
  to?: string
  select?: Record<string, unknown> | null
}

export function MatesPanel({
  node,
  earlier,
  mates,
  params,
  onCreateParam,
  onChange,
  draft,
  onDraft,
  picking,
  onPicking,
  placement,
  note,
}: {
  node: { id: string; label?: string }
  /** 앞에 놓인 구성품 — 구속은 이것들과 기준에만 건다. */
  earlier: { id: string; label?: string }[]
  mates: Mate[]
  params: Record<string, number>
  onCreateParam: (name: string, value: number) => void
  onChange: (next: Mate[]) => void
  draft: MateDraft | null
  onDraft: (next: MateDraft | null) => void
  picking: 'this' | 'to' | null
  onPicking: (next: 'this' | 'to' | null) => void
  placement?: Placement | null
  /** 고르다 생긴 말(다른 구성품을 눌렀다 등). */
  note?: string | null
}) {
  const name = node.label || node.id
  const labelOf = (id: string) => DATUMS.find((one) => one.value === id)?.label ?? earlier.find((one) => one.id === id)?.label ?? id
  const ready = draft && draft.this && draft.to && (DATUM_NAMES.has(draft.to) || draft.select)

  function set(index: number, patch: Partial<Mate>) {
    onChange(mates.map((one, i) => (i === index ? { ...one, ...patch } : one)))
  }

  function add() {
    if (!draft || !ready) return
    const made: Mate = { type: draft.type, this: draft.this!, to: draft.to! }
    if (!DATUM_NAMES.has(draft.to!)) made.select = draft.select
    if (draft.type === 'angle') made.angle = 90
    onChange([...mates, made])
    onDraft(null)
    onPicking(null)
  }

  return (
    <div>
      <p className="text-muted-foreground mb-1 text-xs">구속: 좌표 대신 관계로 배치</p>
      {placement && (mates.length > 0 || placement.mates) ? (
        <p className="mb-1 text-[11px]" role="status">
          {placement.free_rotation === 0 && placement.free_translation === 0
            ? '모든 자유도가 구속되었습니다. 드래그해도 움직이지 않습니다.'
            : `남은 자유도: 회전 ${placement.free_rotation ?? 3}, 이동 ${placement.free_translation ?? 3}. 드래그하면 남은 자유도 방향으로만 움직입니다.`}
        </p>
      ) : null}
      {mates.length > 0 && (
        <ul className="mb-2 space-y-1">
          {mates.map((mate, index) => (
            <li key={index} className="rounded border px-2 py-1 text-xs">
              <div className="flex items-center gap-1">
                <span className="font-medium">
                  {index + 1}. {TYPE_LABEL[mate.type]}
                </span>
                <span className="text-muted-foreground min-w-0 flex-1 truncate" title={JSON.stringify({ this: mate.this, to: mate.to, select: mate.select })}>
                  {describeSelect(mate.this)} → {labelOf(mate.to)}
                  {mate.select ? ` ${describeSelect(mate.select)}` : ''}
                </span>
                <button type="button" className="text-muted-foreground hover:text-destructive rounded p-0.5" aria-label={`구속 ${index + 1} 제거`} onClick={() => onChange(mates.filter((_, i) => i !== index))}>
                  <Trash2 className="size-3.5" />
                </button>
              </div>
              {(mate.type === 'touch' || mate.type === 'flush') && (
                <div className="mt-1 flex items-center gap-1">
                  <span className="text-muted-foreground w-14">{mate.type === 'touch' ? '간극' : '오프셋'} (mm)</span>
                  <NumberField params={params} onCreateParam={onCreateParam} aria-label={`구속 ${index + 1} 간극`} value={mate.offset ?? 0} onChange={(next) => set(index, { offset: next ?? 0 })} />
                </div>
              )}
              {mate.type === 'angle' && (
                <div className="mt-1 flex items-center gap-1">
                  <span className="text-muted-foreground w-14">각도 (°)</span>
                  <NumberField params={params} onCreateParam={onCreateParam} aria-label={`구속 ${index + 1} 각도`} value={mate.angle ?? 90} onChange={(next) => set(index, { angle: next ?? 90 })} />
                </div>
              )}
              {(mate.type === 'concentric' || mate.type === 'parallel') && (
                <label className="mt-1 flex items-center gap-1">
                  <input type="checkbox" checked={!!mate.flip} onChange={(e) => set(index, { flip: e.target.checked })} />
                  <span className="text-muted-foreground">방향 반전</span>
                </label>
              )}
            </li>
          ))}
        </ul>
      )}

      {draft ? (
        <div className="space-y-1 rounded border border-dashed p-2 text-xs">
          <div className="flex items-center gap-1">
            <select
              aria-label="구속 종류"
              className="bg-background h-7 rounded-md border px-1"
              value={draft.type}
              onChange={(e) => onDraft({ ...draft, type: e.target.value as Mate['type'] })}
            >
              {MATE_TYPES.map((one) => (
                <option key={one.value} value={one.value}>
                  {one.label}
                </option>
              ))}
            </select>
            <span className="text-muted-foreground truncate">{MATE_TYPES.find((one) => one.value === draft.type)?.help}</span>
          </div>
          <div className="flex items-center gap-1">
            <Button size="sm" variant={picking === 'this' ? 'default' : 'outline'} className="h-7 px-2 text-xs" onClick={() => onPicking(picking === 'this' ? null : 'this')}>
              <Crosshair className="size-3" /> 이 구성품
            </Button>
            <span className="text-muted-foreground truncate">{draft.this ? describeSelect(draft.this) : picking === 'this' ? `3D 화면에서 ‘${name}’의 면을 클릭하십시오.` : '선택되지 않음'}</span>
          </div>
          <div className="flex items-center gap-1">
            <Button size="sm" variant={picking === 'to' ? 'default' : 'outline'} className="h-7 px-2 text-xs" disabled={earlier.length === 0} onClick={() => onPicking(picking === 'to' ? null : 'to')}>
              <Crosshair className="size-3" /> 상대
            </Button>
            <select
              aria-label="상대 기준"
              className="bg-background h-7 rounded-md border px-1"
              value={draft.to && DATUM_NAMES.has(draft.to) ? draft.to : ''}
              onChange={(e) => {
                onDraft({ ...draft, to: e.target.value || undefined, select: null })
                if (e.target.value) onPicking(null)
              }}
            >
              <option value="">3D에서 선택</option>
              {DATUMS.map((one) => (
                <option key={one.value} value={one.value}>
                  {one.label}
                </option>
              ))}
            </select>
            <span className="text-muted-foreground min-w-0 truncate">
              {draft.to && !DATUM_NAMES.has(draft.to) ? `${labelOf(draft.to)} ${describeSelect(draft.select)}` : picking === 'to' ? '먼저 배치된 구성품의 면을 클릭하십시오.' : ''}
            </span>
          </div>
          {note && <p className="text-destructive">{note}</p>}
          <div className="flex justify-end gap-1">
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => {
                onDraft(null)
                onPicking(null)
              }}>
              취소
            </Button>
            <Button size="sm" className="h-7 px-2 text-xs" disabled={!ready} onClick={add}>
              구속 추가
            </Button>
          </div>
        </div>
      ) : (
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-2 text-xs"
          disabled={mates.length >= 6}
          title={earlier.length === 0 ? '먼저 배치된 구성품이 없으면 기준면 또는 기준축에만 구속할 수 있습니다.' : undefined}
          onClick={() => {
            onDraft({ type: 'touch' })
            onPicking('this')
          }}
        >
          + 구속
        </Button>
      )}
    </div>
  )
}
