/** 작업 종류로 가려 보기 — 「내 지그가 어디 있지」 를 한 번에. 내 작업 · 모든 작업이 같이 쓴다. */

import type { WorkKind } from '@/modules/works/api'

const KINDS = [
  { value: 'all', label: '전체' },
  { value: 'part', label: '부품' },
  { value: 'jig', label: '지그' },
  { value: 'assembly', label: '조립' },
] as const

export type KindChoice = 'all' | WorkKind

export function KindFilter({ value, onChange }: { value: KindChoice; onChange: (next: KindChoice) => void }) {
  return (
    <div className="flex items-center gap-1">
      {KINDS.map((one) => (
        <button
          key={one.value}
          type="button"
          onClick={() => onChange(one.value)}
          aria-pressed={value === one.value}
          className={`rounded-md border px-3 py-1 text-sm ${
            value === one.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
          }`}
        >
          {one.label}
        </button>
      ))}
    </div>
  )
}
