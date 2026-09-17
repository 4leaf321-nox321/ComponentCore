/** 생성 옵션 — 초깃값은 서버가 준다(`/jigs/options`). 손으로 두 벌 적지 않는다. */

import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/** 화면에 내는 옵션과 그 이름. 서버 `JigOptions` 의 일부 — 나머지는 기본값으로 간다. */
const FIELDS: { key: string; label: string; step?: number }[] = [
  { key: 'plate_margin', label: '판 여유 (mm)' },
  { key: 'plate_thickness', label: '판 두께 (mm)' },
  { key: 'support_count', label: '받침 수 (3 · 4)', step: 1 },
  { key: 'support_diameter', label: '받침 지름 (mm)' },
  { key: 'support_height', label: '받침 높이 (mm)' },
  { key: 'clamp_count', label: '클램프 수', step: 1 },
  { key: 'clamp_pad_diameter', label: '클램프 패드 지름 (mm)' },
  { key: 'locator_pin_clearance', label: '핀 틈 (mm)', step: 0.01 },
]

export function OptionsForm({
  values,
  onChange,
}: {
  values: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {FIELDS.map((field) => (
        <div key={field.key} className="space-y-1">
          <Label htmlFor={`opt-${field.key}`} className="text-xs">
            {field.label}
          </Label>
          <Input
            id={`opt-${field.key}`}
            type="number"
            step={field.step ?? 0.5}
            value={String(values[field.key] ?? '')}
            onChange={(event) =>
              onChange({ ...values, [field.key]: Number(event.target.value) })
            }
          />
        </div>
      ))}
    </div>
  )
}
