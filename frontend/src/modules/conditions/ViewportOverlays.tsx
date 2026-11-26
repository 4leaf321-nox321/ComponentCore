/**
 * 3D 칸 위의 것들 — 선택 대상 줄 · 접촉 범례 · 단면 조절(`ConditionsPanel` 에서 나눴다, 동작 그대로). 상태는 화면이
 * 든다 — 여기는 그리기와 누름만.
 */

import { acceptsLabel } from '@/modules/conditions/api'
import type { TargetKind } from '@/modules/conditions/api'
import { PICK_KINDS } from '@/modules/conditions/useGroupPicking'
import type { PickKind } from '@/modules/conditions/useGroupPicking'
import type { Section } from '@/shared/viewer/PickViewer'

/**
 * **무엇을 선택할지 먼저 고른다.** 없을 때는 엣지를 고르려는데 점이 먼저 잡혔다 — 뷰어가 점 · 엣지 · 면 순으로
 * 걸고, 그 순서를 사람이 바꿀 길이 없었다. 열린 조건이 받지 않는 종류는 막는다.
 */
export function PickKindBar({
  pickKind,
  accepts,
  hint,
  onPick,
}: {
  pickKind: PickKind
  /** 열린 조건이 받는 선택 그룹 종류 — 없으면(대상이 없거나 모든 것) 막지 않는다. */
  accepts: TargetKind[] | null
  /** 오른쪽 안내 — 지금 누르면 무엇이 되는지. */
  hint: string
  /** 다른 종류를 골랐다(같은 것을 다시 누르면 부르지 않는다). */
  onPick: (kind: PickKind) => void
}) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-1 border-b px-2 py-1.5">
      <span className="text-muted-foreground mr-1 text-xs">선택 대상</span>
      {PICK_KINDS.map((one) => {
        const refused = !!accepts && !accepts.some((ok) => ok.entity === one.entity)
        return (
          <button
            key={one.key}
            type="button"
            aria-pressed={pickKind === one.key}
            disabled={refused}
            title={refused && accepts ? `이 조건은 ${acceptsLabel(accepts)}에만 적용됩니다.` : undefined}
            className={`rounded border px-2 py-0.5 text-xs disabled:opacity-40 ${
              pickKind === one.key ? 'border-primary bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/50'
            }`}
            onClick={() => {
              if (one.key !== pickKind) onPick(one.key)
            }}
          >
            {one.label}
          </button>
        )
      })}
      <span className="text-muted-foreground ml-auto text-xs">{hint}</span>
    </div>
  )
}

/** 접촉 보기의 범례 — 무엇이 붉고 무엇이 푸른지, 몇 면인지. */
export function ContactLegend({ counts, none }: { counts: { tie: number; contact: number }; none: boolean }) {
  return (
    <div className="bg-background/85 pointer-events-none absolute top-2 left-2 z-10 space-x-3 rounded border px-2 py-1 text-xs" aria-label="접촉 범례">
      <span>
        <span className="mr-1 inline-block size-2.5 rounded-sm" style={{ background: '#dc2626' }} aria-hidden />
        본딩(Tie) {counts.tie}면
      </span>
      <span>
        <span className="mr-1 inline-block size-2.5 rounded-sm" style={{ background: '#2563eb' }} aria-hidden />
        기타 접촉 {counts.contact}면
      </span>
      {none && <span className="text-muted-foreground">정의된 접촉이 없습니다</span>}
    </div>
  )
}

/** 단면 — 축 · 자리 · 뒤집기. 밀대는 형상의 범위(`range`) 안에서 움직인다. 축을 바꾸면 그 축의 가운데로. */
export function SectionControls({
  section,
  range,
  onChange,
}: {
  section: Section
  range: (axis: Section['axis']) => { min: number; max: number }
  onChange: (next: Section) => void
}) {
  const { min, max } = range(section.axis)
  return (
    <div className="bg-background/90 absolute bottom-2 left-2 z-10 flex flex-wrap items-center gap-2 rounded border px-2 py-1 text-xs" aria-label="단면">
      <span className="font-medium">단면</span>
      {(['x', 'y', 'z'] as const).map((axis) => (
        <button
          key={axis}
          type="button"
          aria-pressed={section.axis === axis}
          className={`rounded border px-1.5 ${section.axis === axis ? 'border-primary bg-accent font-medium' : 'text-muted-foreground'}`}
          onClick={() => {
            const at = range(axis)
            onChange({ ...section, axis, at: Math.round(((at.min + at.max) / 2) * 1000) / 1000 })
          }}
        >
          {axis.toUpperCase()}
        </button>
      ))}
      <input
        type="range"
        aria-label="단면 위치"
        min={min}
        max={max}
        step={Math.max((max - min) / 400, 0.001)}
        value={section.at}
        onChange={(e) => onChange({ ...section, at: Number(e.target.value) })}
        className="w-40"
      />
      <span className="w-16 tabular-nums">
        {section.axis.toUpperCase()} = {section.at.toFixed(2)}
      </span>
      <label className="flex items-center gap-1">
        <input type="checkbox" checked={!!section.flip} onChange={(e) => onChange({ ...section, flip: e.target.checked })} />
        뒤집기
      </label>
    </div>
  )
}
