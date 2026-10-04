/**
 * 측정값 고르기 — 점마다 **형상에서 바로 나오는 값**을 표의 열로(부피 · 크기 · 그룹 넓이 · 거리 · 식).
 *
 * 해석 결과는 이 플랫폼에 돌아오지 않지만, 질량 · 거리처럼 형상만 보면 아는 값은 해석 쪽이
 * 목표 · 제약으로 쓴다. 기본은 아무것도 재지 않는다 — 고른 것만 열이 된다.
 */

import type { Measure } from '@/modules/doe/api'
import { Input } from '@/shared/components/ui/input'

const KINDS: { value: Measure['kind']; label: string }[] = [
  { value: 'volume', label: '부피 (mm³)' },
  { value: 'area', label: '표면적 (mm²)' },
  { value: 'size', label: '크기 (mm)' },
  { value: 'region_area', label: '선택 그룹 면적' },
  { value: 'distance', label: '두 그룹 간 거리' },
  { value: 'expr', label: '수식' },
]

/** 종류를 고르면 붙는 이름 — 사람이 고칠 수 있다. */
function defaultName(kind: Measure['kind'], taken: string[]): string {
  const base = { volume: '부피', area: '겉넓이', size: '크기_z', region_area: '그룹_넓이', distance: '거리', expr: '식' }[kind]
  let name = base
  for (let i = 2; taken.includes(name); i += 1) name = `${base}${i}`
  return name
}

export function MeasuresInput({ value, onChange, regions }: { value: Measure[]; onChange: (next: Measure[]) => void; regions: string[] }) {
  const set = (index: number, patch: Partial<Measure>) => onChange(value.map((one, i) => (i === index ? { ...one, ...patch } : one)))
  const select = (label: string, current: string | undefined, onPick: (v: string) => void) => (
    <select aria-label={label} className="bg-background h-7 rounded border px-1.5 text-xs" value={current ?? ''} onChange={(e) => onPick(e.target.value)}>
      <option value="">그룹 선택</option>
      {regions.map((one) => (
        <option key={one} value={one}>
          {one}
        </option>
      ))}
    </select>
  )
  return (
    <div className="rounded-md border" aria-label="측정값">
      <div className="bg-muted/40 flex items-center gap-3 border-b px-3 py-2 text-xs font-medium">
        <span>측정값 (설계점마다 측정하여 표에 열로 추가)</span>
        <select
          aria-label="측정값 추가"
          className="bg-background ml-auto rounded border px-1.5 py-0.5 text-xs font-normal"
          value=""
          onChange={(e) => {
            const kind = e.target.value as Measure['kind']
            if (!kind) return
            const name = defaultName(kind, value.map((one) => one.name))
            onChange([...value, { name, kind, ...(kind === 'size' ? { axis: 'z' } : {}) }])
          }}
        >
          <option value="">측정값 추가</option>
          {KINDS.map((one) => (
            <option key={one.value} value={one.value}>
              {one.label}
            </option>
          ))}
        </select>
      </div>
      {value.length === 0 ? (
        <p className="text-muted-foreground px-3 py-2 text-xs">
          측정하지 않습니다. 질량은 ‘수식’으로 <code>부피 * 밀도</code>(예: 강 7.85e-6 kg/mm³)와 같이 정의하십시오. 재료와 단위계가 해석마다 다르므로 자동으로 계산하지 않습니다.
        </p>
      ) : (
        value.map((one, index) => (
          <div key={index} className="flex flex-wrap items-center gap-2 border-b px-3 py-1.5 text-xs last:border-b-0">
            <Input aria-label={`측정값 ${index + 1} 이름`} value={one.name} onChange={(e) => set(index, { name: e.target.value })} className="h-7 w-32 font-mono text-xs" />
            <span className="text-muted-foreground w-28">{KINDS.find((k) => k.value === one.kind)?.label}</span>
            {one.kind === 'size' && (
              <select aria-label={`측정값 ${index + 1} 축`} className="bg-background h-7 rounded border px-1.5 text-xs" value={one.axis ?? 'z'} onChange={(e) => set(index, { axis: e.target.value as Measure['axis'] })}>
                <option value="x">x</option>
                <option value="y">y</option>
                <option value="z">z</option>
              </select>
            )}
            {one.kind === 'region_area' && select(`측정값 ${index + 1} 그룹`, one.region, (v) => set(index, { region: v }))}
            {one.kind === 'distance' && (
              <>
                {select(`측정값 ${index + 1} 그룹 a`, one.a, (v) => set(index, { a: v }))}
                <span className="text-muted-foreground">↔</span>
                {select(`측정값 ${index + 1} 그룹 b`, one.b, (v) => set(index, { b: v }))}
              </>
            )}
            {one.kind === 'expr' && (
              <Input aria-label={`측정값 ${index + 1} 식`} value={one.expr ?? ''} placeholder="부피 * 7.85e-6" onChange={(e) => set(index, { expr: e.target.value })} className="h-7 flex-1 font-mono text-xs" />
            )}
            {(one.kind === 'region_area' || one.kind === 'distance') && regions.length === 0 && (
              <span className="text-destructive">해석 조건에 선택 그룹이 없습니다.</span>
            )}
            <button type="button" className="text-muted-foreground hover:text-foreground ml-auto" onClick={() => onChange(value.filter((_, i) => i !== index))} aria-label={`측정값 ${index + 1} 제거`}>
              제거
            </button>
          </div>
        ))
      )}
    </div>
  )
}
