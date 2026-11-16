/**
 * 도면과 변수 치수 — 새 DOE 화면이 범위를 넣는 칸 위에 둔다.
 *
 * 변수 이름만 보고 범위를 주면 「간격이 어느 간격인가」 를 도면 편집기에 가서 찾아야 했다. 여기서
 * 바로 보인다: 변수마다 치수선과 `두께 = 6`, 변수 행(`focus`)이나 범례에 마우스를 올리면 그
 * 치수만 남는다. 접어 두면 형상도 치수도 묻지 않는다.
 */

import { lazy, Suspense, useMemo } from 'react'

import { cadApi } from '@/modules/cad/api'
import type { Recipe } from '@/modules/cad/api'
import { dimMarks, useDimsToggle, useParamDims } from '@/modules/cad/paramDims'
import { ParamDimsLegend } from '@/modules/cad/ParamDimsLegend'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'

const PickViewer = lazy(() => import('@/shared/viewer/PickViewer'))

export function ParamDimsView({
  recipe,
  names,
  focus,
  onFocus,
}: {
  recipe: Recipe
  /** 찾을 변수 — 보통 DOE 의 인자가 될 변수들. */
  names: string[]
  focus: string | null
  onFocus: (name: string | null) => void
}) {
  const [open, setOpen] = useDimsToggle('doeForm', true)
  const recipeKey = JSON.stringify(recipe)
  const shape = useResource(() => (open ? cadApi.mesh(recipe) : Promise.resolve(null)), [open, recipeKey])
  const dims = useParamDims(open && names.length > 0 ? JSON.stringify([recipeKey, names]) : null, () => cadApi.paramDims(recipe, names))
  // 시험의 가짜 응답 · 옛 서버의 답은 그리지 않는다.
  const mesh = shape.data && Array.isArray(shape.data.mesh?.faces) ? shape.data.mesh : null
  const marks = useMemo(() => dimMarks(dims.data, mesh, focus), [dims.data, mesh, focus])

  return (
    <div className="rounded-md border" aria-label="도면의 변수 위치">
      <div className="bg-muted/40 flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-3 py-2 text-xs font-medium">
        <span>도면의 변수 위치</span>
        {open && <span className="text-muted-foreground font-normal">변수 행이나 아래 항목에 마우스를 올리면 해당 치수를 강조합니다.</span>}
        <button type="button" className="text-muted-foreground hover:text-foreground ml-auto font-normal" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? '숨기기' : '표시'}
        </button>
      </div>
      {open && (
        <div className="space-y-2 p-3">
          <ErrorNotice error={shape.error} />
          {mesh ? (
            <Suspense fallback={<Skeleton className="h-96 w-full" />}>
              <PickViewer mesh={mesh} mode="none" measureMarks={marks} className="h-96 w-full rounded-md border" />
            </Suspense>
          ) : (
            !shape.error && <Skeleton className="h-96 w-full" />
          )}
          <ParamDimsLegend state={dims} focus={focus} onFocus={onFocus} />
        </div>
      )}
    </div>
  )
}
