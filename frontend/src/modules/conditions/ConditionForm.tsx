/**
 * 조건 하나의 칸들 — **서버가 준 사양표로 그린다.**
 *
 * 종류가 열 몇이고 칸이 제각각이다(고정 지지에는 값이 없고, 압력에는 크기와 방향이, 볼트에는
 * 예압이). 화면에 `if` 를 늘어놓으면 종류를 더할 때마다 여기를 고쳐야 한다 — 칸 목록은 서버가
 * 들고 있고(`core/conditions.py`) 여기는 그것을 그린다. CAD 의 `NodeForm` 과 같은 방식이다.
 */

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

export function ConditionForm({
  group,
  item,
  names,
  frames = [],
  onChange,
}: {
  group: GroupSchema
  item: ConditionItem
  /** 있는 선택 그룹 — 조건은 **선택 그룹만** 가리킨다(좌표를 박으면 설계점이 바뀔 때 어긋난다). */
  names: NamedSelection[]
  /** 고를 수 있는 좌표계 이름 — 도면의 것과 조건의 것. 「전역」 은 늘 있다. */
  frames?: string[]
  onChange: (next: ConditionItem) => void
}) {
  const set = (key: string, value: unknown) => onChange({ ...item, [key]: value })
  const fields = Object.entries(group.fields).filter(([key]) => !HANDLED.has(key))
  const targets = 'source' in group.fields ? ['source', 'target'] : 'on' in group.fields ? ['on'] : []

  return (
    <div className="space-y-3">
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
          <Select value={String(item.type ?? '')} onValueChange={(v) => set('type', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {group.types.map((one) => (
                <SelectItem key={one} value={one}>
                  {one}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {targets.map((key) => (
        <div key={key} className="space-y-1">
          <Label>{key === 'target' ? '상대 선택 그룹' : '선택 그룹'}</Label>
          <Select value={String(item[key] ?? '')} onValueChange={(v) => set(key, v)}>
            <SelectTrigger>
              <SelectValue placeholder="선택" />
            </SelectTrigger>
            <SelectContent>
              {names.map((one) => (
                <SelectItem key={one.name} value={one.name}>
                  {one.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {names.length === 0 && (
            <p className="text-muted-foreground text-xs">
              선택 그룹이 없습니다 — 3D 에서 형상을 선택하면 생성됩니다.
            </p>
          )}
        </div>
      ))}

      {/*
        **좌표계** — 성분(x · y · z)이 어느 방향인가. 「전역」 이 기본이고, 도면 · 해석 조건에서
        이름 붙인 좌표계를 고른다(리본의 「좌표계」).
      */}
      {'cs' in group.fields && (
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

      {fields.map(([key, field]) => {
        const options = choices(field)
        const value = item[key]
        if (options) {
          return (
            <div key={key} className="space-y-1">
              <Label>{field.title ?? key}</Label>
              <Select value={String(value ?? '')} onValueChange={(v) => set(key, v)}>
                <SelectTrigger>
                  <SelectValue placeholder="(없음)" />
                </SelectTrigger>
                <SelectContent>
                  {options.map((one) => (
                    <SelectItem key={one} value={one}>
                      {one}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )
        }
        return (
          <div key={key} className="space-y-1">
            <Label htmlFor={`cond-${key}`}>{field.title ?? key}</Label>
            <Input
              id={`cond-${key}`}
              value={value === null || value === undefined ? '' : String(value)}
              placeholder={isNumeric(field) ? '수 또는 =식' : ''}
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
          </div>
        )
      })}
    </div>
  )
}
