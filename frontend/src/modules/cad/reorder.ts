/**
 * 피처 순서 규칙 — 레시피는 **위에서 아래로** 평가되고 앞의 것만 가리킬 수 있다.
 *
 * 그래서 끌어 옮기기는 아무 데나 놓을 수 없다: 쓰는 것(예: 돌출)은 쓰이는 것(스케치)보다 뒤에
 * 있어야 한다. 화면이 규칙을 알아야 **놓기 전에** 막고 이유를 말해 줄 수 있다.
 */

import { referencesOf } from '@/modules/cad/recipeSpec'
import type { RecipeNode } from '@/modules/cad/recipeSpec'

/** `from` 에 있던 것을 빼서 `to` **자리에** 끼운다(끼울 자리는 빼기 전 기준의 칸 사이 번호). */
export function moveTo<T>(list: T[], from: number, to: number): T[] {
  if (from < 0 || from >= list.length) return list
  const next = [...list]
  const [item] = next.splice(from, 1)
  next.splice(to > from ? to - 1 : to, 0, item)
  return next
}

/** 순서가 깨진 첫 자리 — 사람에게 보일 말로. 깨진 데가 없으면 null. */
export function orderProblem(nodes: RecipeNode[]): string | null {
  const seen = new Set<string>()
  for (const node of nodes) {
    for (const ref of referencesOf(node)) {
      if (!seen.has(ref)) {
        const name = node.label || node.id
        return `「${name}」 이(가) ${ref} 을(를) 씁니다 — 쓰는 피처가 먼저 올 수 없습니다.`
      }
    }
    seen.add(node.id)
  }
  return null
}

/** 그 자리에 놓아도 되나. 되면 null, 안 되면 이유. */
export function dropProblem(nodes: RecipeNode[], from: number, to: number): string | null {
  if (to === from || to === from + 1) return null // 제자리
  return orderProblem(moveTo(nodes, from, to))
}

/** 이 피처를 끼울 수 있는 자리들(칸 사이 번호) — 끌기 시작할 때 한 번 센다. */
export function allowedDrops(nodes: RecipeNode[], from: number): Set<number> {
  const out = new Set<number>()
  for (let to = 0; to <= nodes.length; to += 1) {
    if (dropProblem(nodes, from, to) === null) out.add(to)
  }
  return out
}
