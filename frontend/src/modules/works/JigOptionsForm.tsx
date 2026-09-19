/**
 * 지그 생성 옵션 — 초깃값은 서버(`/works/jig-options`). 형식(`kind`)마다 뜻이 있는 칸만 보인다.
 *
 * 형식과 칸 이름은 서버 `core/options.py` 의 정본을 따른다 — 여기서 새 칸을 지어내지 않는다.
 */

import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/components/ui/select'

export type JigKind = 'clamped' | 'bolted' | 'bending' | 'drop'

/** 형식 — 이름 · 한 줄 설명. 서버 JIG_KINDS 와 같은 순서. */
export const JIG_KINDS: { value: JigKind; label: string; hint: string }[] = [
  { value: 'clamped', label: '판 · 클램프 고정', hint: '바닥판 위에 받침 · 위치 핀 · 클램프 (3-2-1 원칙)' },
  { value: 'bolted', label: '볼트 고정', hint: '부품의 관통 구멍으로 볼트를 넣어 판에 조인다 — 진동 · 충격 시험' },
  { value: 'bending', label: '3점 굽힘 픽스처', hint: '긴 변으로 스팬을 잡아 롤러 둘로 받치고 가운데를 누른다' },
  { value: 'drop', label: '낙하 · 충격 자세', hint: '고른 면이 아래를 보게 놓고 바닥판 · 낙하물을 둔다' },
]

type Field =
  | { key: string; label: string; kind: 'number'; step?: number }
  | { key: string; label: string; kind: 'select'; choices: { value: string; label: string }[] }
  | { key: string; label: string; kind: 'bool' }

const COMMON: Field[] = [
  { key: 'plate_margin', label: '판 여유 (mm)', kind: 'number' },
  { key: 'plate_thickness', label: '판 두께 (mm)', kind: 'number' },
]

/** 형식마다 뜻이 있는 칸. */
const FIELDS: Record<JigKind, Field[]> = {
  clamped: [
    ...COMMON,
    { key: 'support_count', label: '받침 수 (3 · 4)', kind: 'number', step: 1 },
    { key: 'support_diameter', label: '받침 지름 (mm)', kind: 'number' },
    { key: 'support_height', label: '받침 높이 (mm)', kind: 'number' },
    { key: 'clamp_count', label: '클램프 수', kind: 'number', step: 1 },
    { key: 'clamp_pad_diameter', label: '클램프 패드 지름 (mm)', kind: 'number' },
    { key: 'locator_pin_clearance', label: '핀 틈 (mm)', kind: 'number', step: 0.01 },
  ],
  bolted: [
    ...COMMON,
    { key: 'bolt_max_count', label: '볼트 수 (최대)', kind: 'number', step: 1 },
    {
      key: 'bolt_head',
      label: '머리',
      kind: 'select',
      choices: [
        { value: 'hex', label: '육각' },
        { value: 'socket', label: '소켓(원통)' },
      ],
    },
    { key: 'bolt_washer', label: '와셔', kind: 'bool' },
    { key: 'bolt_spacer_height', label: '스페이서 높이 (mm, 0 = 판에 바로)', kind: 'number' },
    { key: 'bolt_plate_engagement', label: '판 체결 깊이 (x 호칭)', kind: 'number', step: 0.1 },
  ],
  bending: [
    ...COMMON,
    { key: 'bending_span_ratio', label: '스팬 비율 (긴 변 대비)', kind: 'number', step: 0.05 },
    { key: 'bending_span', label: '스팬 (mm, 0 = 비율로)', kind: 'number' },
    { key: 'bending_roller_diameter', label: '롤러 지름 (mm)', kind: 'number' },
    { key: 'bending_nose_diameter', label: '노즈 지름 (mm)', kind: 'number' },
    { key: 'bending_roller_margin', label: '롤러 여유 (폭 밖, mm)', kind: 'number' },
    { key: 'support_height', label: '롤러 축 높이 (mm)', kind: 'number' },
  ],
  drop: [
    ...COMMON,
    {
      key: 'drop_orientation',
      label: '아래를 보는 것',
      kind: 'select',
      choices: [
        { value: 'bottom', label: '바닥면' },
        { value: 'top', label: '윗면' },
        { value: '+x', label: '+X 면' },
        { value: '-x', label: '-X 면' },
        { value: '+y', label: '+Y 면' },
        { value: '-y', label: '-Y 면' },
        { value: 'edge', label: '모서리' },
        { value: 'corner', label: '꼭짓점' },
      ],
    },
    { key: 'drop_gap', label: '바닥과 틈 (mm)', kind: 'number', step: 0.1 },
    {
      key: 'drop_impactor',
      label: '낙하물 (충격 시험)',
      kind: 'select',
      choices: [
        { value: 'none', label: '없음 — 부품이 떨어진다' },
        { value: 'ball', label: '강구' },
        { value: 'pen', label: '펜(둥근 끝)' },
      ],
    },
    { key: 'drop_ball_diameter', label: '낙하물 지름 (mm)', kind: 'number' },
    { key: 'drop_impactor_clearance', label: '낙하물 틈 (mm)', kind: 'number', step: 0.1 },
  ],
}

export function JigOptionsForm({
  values,
  onChange,
}: {
  values: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  const kind = (values.kind as JigKind) ?? 'clamped'
  const fields = FIELDS[kind] ?? FIELDS.clamped
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {fields.map((field) => (
        <div key={field.key} className="space-y-1">
          <Label htmlFor={`opt-${field.key}`} className="text-xs">
            {field.label}
          </Label>
          {field.kind === 'number' && (
            <Input
              id={`opt-${field.key}`}
              type="number"
              step={field.step ?? 0.5}
              value={String(values[field.key] ?? '')}
              onChange={(event) => onChange({ ...values, [field.key]: Number(event.target.value) })}
            />
          )}
          {field.kind === 'select' && (
            <Select value={String(values[field.key] ?? field.choices[0].value)} onValueChange={(next) => onChange({ ...values, [field.key]: next })}>
              <SelectTrigger id={`opt-${field.key}`} aria-label={field.label}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {field.choices.map((one) => (
                  <SelectItem key={one.value} value={one.value}>
                    {one.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {field.kind === 'bool' && (
            <label className="flex h-9 items-center gap-2 text-sm">
              <input id={`opt-${field.key}`} type="checkbox" checked={Boolean(values[field.key])} onChange={(event) => onChange({ ...values, [field.key]: event.target.checked })} />
              넣는다
            </label>
          )}
        </div>
      ))}
    </div>
  )
}
