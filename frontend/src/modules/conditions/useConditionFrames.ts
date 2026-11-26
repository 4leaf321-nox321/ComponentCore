/**
 * **좌표계** — 조건 화면이 그리는 좌표계(`ConditionsPanel` 에서 나눴다, 동작 그대로). 도면의 것(레시피, 읽기만)과
 * 조건의 것, 그리고 창에서 고치는 중인 것(확인 전에도 미리 그린다). 3D 에 그릴 축은 서버가 지금 치수로 푼다.
 */

import { useEffect, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import type { FrameDraft } from '@/modules/cad/FrameForm'
import { asConditions, conditionsApi } from '@/modules/conditions/api'
import type { NamedSelection } from '@/modules/conditions/api'
import type { FrameRow } from '@/shared/viewer/PickViewer'

export function useConditionFrames({
  recipe,
  names,
  frames,
  editing,
}: {
  recipe: Recipe
  names: NamedSelection[]
  /** 조건의 좌표계(`coordinate_systems`). */
  frames: FrameDraft[] | undefined
  /** 창에서 고치는 좌표계 — 새로(`index` 가 null) 또는 고치는 것. */
  editing: { index: number | null; item: FrameDraft } | null
}) {
  /**
   * **좌표계** — 도면의 것(레시피)과 조건의 것. 조건의 「좌표계」 칸이 이름으로 가리킨다.
   * 3D 에 그릴 축은 서버가 지금 치수로 푼다(면에 붙인 것은 그 그룹을 풀어서) — 화면이 따로
   * 셈하면 보인 방향과 내보낸 방향이 어긋난다.
   */
  const cadFrames = recipe.coordinate_systems ?? []
  const conditionFrames = frames ?? []
  const frameNames = [...cadFrames.map((one) => one.name), ...conditionFrames.map((one) => one.name)]
  /**
   * **고치는 중인 좌표계도 미리 그린다** — 창에서 확인을 누르기 전에는 한 벌에 없어서 축이 안
   * 보였다. 이름이 비었거나 겹치면 서버가 거절하므로 미리보기 이름을 따로 붙인다.
   */
  const previewFrames = (() => {
    if (!editing) return conditionFrames
    const taken = frameNames.filter((_, i) => i !== cadFrames.length + (editing.index ?? -1))
    const name = editing.item.name.trim()
    const item = {
      ...editing.item,
      name: !name || taken.includes(name) || ['global', '전역'].includes(name) ? '(미리보기)' : name,
    }
    return editing.index === null
      ? [...conditionFrames, item]
      : conditionFrames.map((one, i) => (i === editing.index ? item : one))
  })()
  const framesKey = JSON.stringify([recipe, previewFrames, names])
  const [frameRows, setFrameRows] = useState<FrameRow[]>([])
  useEffect(() => {
    if (cadFrames.length === 0 && previewFrames.length === 0) {
      setFrameRows([])
      return
    }
    let alive = true
    const timer = setTimeout(() => {
      conditionsApi
        // 좌표계에 필요한 것만 보낸다 — 고치는 중인 다른 조건 때문에 축이 사라지지 않게.
        .frames(recipe, { ...asConditions(null), named_selections: names, coordinate_systems: previewFrames })
        .then((got) => alive && setFrameRows(Array.isArray(got.items) ? got.items : []))
        .catch(() => alive && setFrameRows([]))
    }, 300)
    return () => {
      alive = false
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [framesKey])

  return { cadFrames, conditionFrames, frameNames, frameRows }
}
