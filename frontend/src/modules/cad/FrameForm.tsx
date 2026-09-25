/**
 * 좌표계 하나의 칸 — 도면(레시피)과 해석 조건이 함께 쓴다.
 *
 * 원점 · 회전은 **수치 또는 치수 식**(`=길이/2`)이다 — 식이면 실험계획이 치수를 바꿀 때 같이
 * 움직인다. 해석 조건에서는 **선택 그룹의 면에 붙일 수도** 있다(원점 = 면 중심, Z = 법선) —
 * 그 면을 설계점마다 따라간다. 회전은 도면의 `transform` 과 같다: X · Y · Z 축 순서(도).
 *
 * 축의 계산은 서버가 한다(`core/frames.py`) — 이 폼은 값을 적을 뿐이다.
 */

import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/**
 * 화면에서 지정하는 중인 것 — 점 · 선 · 면을 누르면 그것으로 원점(과 방향)을 정하고, 회전 · 이동은
 * 3D 손잡이로 돌리거나 옮긴다. 숫자로 적는 것보다 감이 온다.
 */
export type Placing = 'point' | 'edge' | 'face' | 'rotate' | 'translate' | null

const PLACING: { key: Exclude<Placing, null>; label: string; hint: string }[] = [
  { key: 'point', label: '점', hint: '누른 점이 원점이 됩니다' },
  { key: 'edge', label: '선', hint: '엣지 중점이 원점, 엣지 방향이 X 가 됩니다' },
  { key: 'face', label: '면', hint: '누른 자리가 원점, 면의 법선이 Z 가 됩니다' },
  { key: 'rotate', label: '회전', hint: '3D 의 손잡이를 끌어 돌립니다(5° 씩)' },
  { key: 'translate', label: '이동', hint: '3D 의 손잡이를 끌어 옮깁니다(0.5 mm 씩)' },
]

export interface FrameDraft {
  name: string
  origin?: (number | string)[]
  rotate?: (number | string)[]
  /** 선택 그룹의 면에 붙인다 — 해석 조건에서만. 비우면 원점 · 회전을 쓴다. */
  on?: string
}

/** `12` → 12, `=길이/2` → 그대로, 빈칸 → 0. */
function valueOf(text: string): number | string {
  if (text.trim() === '') return 0
  if (text.startsWith('=')) return text
  const number = Number(text)
  return Number.isFinite(number) ? number : text
}

function Triple({
  label,
  unit,
  value,
  onChange,
}: {
  label: string
  unit: string
  value: (number | string)[] | undefined
  onChange: (next: (number | string)[]) => void
}) {
  const now = value ?? [0, 0, 0]
  return (
    <div className="space-y-1">
      <Label className="text-xs">
        {label} <span className="text-muted-foreground">({unit})</span>
      </Label>
      <div className="grid grid-cols-3 gap-1">
        {(['X', 'Y', 'Z'] as const).map((axis, index) => (
          <Input
            key={axis}
            aria-label={`${label} ${axis}`}
            placeholder={axis}
            value={String(now[index] ?? 0)}
            onChange={(e) => {
              const next = [...now]
              next[index] = valueOf(e.target.value)
              onChange(next)
            }}
          />
        ))}
      </div>
    </div>
  )
}

export function FrameForm({
  value,
  onChange,
  groups,
  placing,
  onPlacing,
}: {
  value: FrameDraft
  onChange: (next: FrameDraft) => void
  /** 면에 붙일 수 있는 선택 그룹들 — 주면 「선택 그룹의 면」 방식을 고를 수 있다(해석 조건). */
  groups?: string[]
  /** 화면에서 지정하는 중인 것 — 주면 「화면에서 지정」 단추들이 보인다. */
  placing?: Placing
  onPlacing?: (next: Placing) => void
}) {
  const attached = !!value.on
  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <Label htmlFor="frame-name">이름</Label>
        <Input id="frame-name" value={value.name} onChange={(e) => onChange({ ...value, name: e.target.value })} />
      </div>
      {groups && (
        <div className="space-y-1">
          <Label className="text-xs">정하는 방법</Label>
          <div className="flex gap-1" role="group" aria-label="정하는 방법">
            {(
              [
                [false, '원점 · 회전'],
                [true, '선택 그룹의 면'],
              ] as const
            ).map(([on, label]) => (
              <button
                key={label}
                type="button"
                aria-pressed={attached === on}
                className={`flex-1 rounded border px-2 py-1 text-xs ${attached === on ? 'border-primary bg-accent font-medium' : 'text-muted-foreground'}`}
                onClick={() => onChange({ ...value, on: on ? (value.on || groups[0] || ' ') : '' })}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
      {attached ? (
        <div className="space-y-1">
          <Label htmlFor="frame-on">선택 그룹</Label>
          <select
            id="frame-on"
            className="bg-background w-full rounded border px-2 py-1 text-sm"
            value={value.on}
            onChange={(e) => onChange({ ...value, on: e.target.value })}
          >
            {(groups ?? []).map((one) => (
              <option key={one} value={one}>
                {one}
              </option>
            ))}
          </select>
          <p className="text-muted-foreground text-xs">
            원점은 그 그룹의 첫 면 중심, Z 는 면의 법선(원통면이면 축)입니다 — 설계점마다 그 면을 따라갑니다.
          </p>
          {groups?.length === 0 && <p className="text-xs text-amber-700 dark:text-amber-400">면 선택 그룹이 없습니다.</p>}
        </div>
      ) : (
        <>
          {onPlacing && (
            <div className="space-y-1">
              <Label className="text-xs">화면에서 지정</Label>
              <div className="grid grid-cols-5 gap-1" role="group" aria-label="화면에서 지정">
                {PLACING.map((one) => (
                  <button
                    key={one.key}
                    type="button"
                    title={one.hint}
                    aria-pressed={placing === one.key}
                    className={`rounded border px-1 py-1 text-xs ${placing === one.key ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
                    onClick={() => onPlacing(placing === one.key ? null : one.key)}
                  >
                    {one.label}
                  </button>
                ))}
              </div>
              <p className="text-muted-foreground text-xs">
                {placing
                  ? PLACING.find((one) => one.key === placing)?.hint
                  : '점 · 선 · 면을 누르거나 손잡이로 돌려 정합니다. 화면에서 지정하면 식 대신 숫자가 들어갑니다.'}
              </p>
            </div>
          )}
          <Triple label="원점" unit="mm · 수 또는 =식" value={value.origin} onChange={(origin) => onChange({ ...value, origin })} />
          <Triple
            label="회전"
            unit="도 · X → Y → Z 축 순서"
            value={value.rotate}
            onChange={(rotate) => onChange({ ...value, rotate })}
          />
        </>
      )}
    </div>
  )
}
