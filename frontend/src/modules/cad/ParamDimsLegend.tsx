/**
 * 변수 치수의 범례 — 변수마다 `두께 3.2 면 간 거리`. 마우스를 올리면 3D 에 그 치수만 남는다.
 *
 * 3D 에 그릴 것이 없는 변수(형상에 안 쓰는 변수 · 못 찾은 변수)도 여기서 그렇다고 말한다 — 안
 * 그려진 까닭을 모르면 사람은 화면이 고장 난 줄 안다.
 */

import { dimLabel, shownValue } from '@/modules/cad/paramDims'
import type { ParamDim, ParamDimsState } from '@/modules/cad/paramDims'

const TONES: Record<ParamDim['status'], string> = {
  dimension: '',
  moved: 'border-amber-500/50 text-amber-800 dark:text-amber-300',
  unused: 'text-muted-foreground border-dashed',
  failed: 'text-muted-foreground border-dashed',
  skipped: 'text-muted-foreground border-dashed',
}

export function ParamDimsLegend({
  state,
  focus,
  onFocus,
}: {
  state: ParamDimsState
  focus: string | null
  onFocus: (name: string | null) => void
}) {
  if (state.loading) {
    return (
      <p className="text-muted-foreground text-xs" role="status">
        치수 위치 계산 중…
      </p>
    )
  }
  if (state.error) {
    return (
      <p className="text-destructive text-xs" role="alert">
        치수 위치를 찾지 못했습니다: {state.error.message}
      </p>
    )
  }
  if (!state.data || state.data.dims.length === 0) return null
  return (
    <ul className="flex flex-wrap gap-1.5 text-xs" aria-label="변수 치수">
      {state.data.dims.map((dim) => (
        <li key={dim.name}>
          <button
            type="button"
            onMouseEnter={() => onFocus(dim.name)}
            onMouseLeave={() => onFocus(null)}
            onFocus={() => onFocus(dim.name)}
            onBlur={() => onFocus(null)}
            aria-pressed={focus === dim.name}
            title={dim.message ?? '마우스를 올리면 3D에서 해당 치수를 강조합니다.'}
            className={`hover:bg-accent flex items-center gap-1 rounded-md border px-2 py-0.5 ${focus === dim.name ? 'bg-accent' : ''} ${TONES[dim.status]}`}
          >
            <span className="font-mono">{dim.name}</span>
            <span className="font-mono">{shownValue(dim.value)}</span>
            <span className="text-muted-foreground">{dimLabel(dim)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
