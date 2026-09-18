/**
 * 레시피를 고치는 **하나뿐인 길**.
 *
 * 한 동작이 레시피를 두 번 고치는 일이 있다 — 「이 칸의 값을 변수로」 는 (1) 변수를 만들고
 * (2) 칸을 `=이름` 으로 바꾼다. 둘 다 `value` 프롭에서 새 레시피를 만들면, 두 번째가 **아직
 * 다시 그려지기 전의 낡은 값** 위에서 만들어져 첫 번째를 덮는다 — 변수가 만들어졌다가 곧바로
 * 사라진다(편집기에서 한 번, 조립에서 또 한 번 났다).
 *
 * 그래서 **방금 내보낸 것**을 들고, 이어지는 갱신은 그 위에 쌓는다. 레시피를 고치는 화면은
 * 모두 이것을 쓴다.
 */

import { useCallback, useRef } from 'react'

import type { Recipe } from '@/modules/cad/api'

export function useRecipeEmit(value: Recipe, onChange: (next: Recipe) => void) {
  const latest = useRef(value)
  latest.current = value
  return useCallback(
    (change: (current: Recipe) => Recipe) => {
      const next = change(latest.current)
      latest.current = next
      onChange(next)
    },
    [onChange],
  )
}
