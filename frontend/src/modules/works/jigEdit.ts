/**
 * 생성된 지그를 고칠 때 — **제품을 옆에 놓고**(검사용, 저장하지 않는다) 요소를 옮기며 간섭을 본다.
 *
 * 생성된 지그의 레시피는 묶음 「지그」 하나이고, 그 자식 하나가 요소 하나다(바닥판 · 받침_1 ·
 * 위치_핀_1 · 클램프_1 …). 서버가 지그를 만들 때의 제품을 생성기 좌표계로 놓은 노드를 주면
 * (`GET /works/{id}/jig-product`) 그것을 묶음에 덧붙여 미리보기 · 간섭 검사에만 쓴다 — 서버의
 * `works.services.with_product` 와 같은 규칙이다.
 */

import type { Recipe } from '@/modules/cad/api'

type Node = Record<string, unknown> & { id: string; op: string }

/** 서버가 주는 검사용 제품 — 못 놓으면 `available: false` 와 까닭. */
export interface JigProduct {
  available: boolean
  reason?: string
  label?: string
  lift_param?: string | null
  node?: Node
}

/** 옮기지 않는 요소 — 판은 바탕이고, 제품은 검사용이다. */
const FIXED = new Set(['바닥판', '바닥'])

function nodesOf(recipe: Recipe): Node[] {
  return ((recipe as { nodes?: Node[] }).nodes ?? []) as Node[]
}

function resultOf(recipe: Recipe): string | null {
  const nodes = nodesOf(recipe)
  return ((recipe as { result?: string }).result ?? nodes[nodes.length - 1]?.id) || null
}

/** 지그 레시피에 검사용 제품을 덧붙인 **사본** — 결과 묶음의 자식으로(요소마다 간섭을 본다). */
export function withProduct(recipe: Recipe, product: Node): Recipe {
  const nodes = nodesOf(recipe)
  if (nodes.length === 0) return recipe
  const result = resultOf(recipe)
  const index = Math.max(
    nodes.findIndex((one) => one.id === result),
    0,
  )
  const target = nodes[index]
  if (target.op === 'group') {
    const group = { ...target, targets: [...((target.targets as string[]) ?? []), product.id] }
    return { ...recipe, nodes: [...nodes.slice(0, index), product, group, ...nodes.slice(index + 1)] } as Recipe
  }
  return {
    ...recipe,
    nodes: [...nodes, product, { id: '간섭_검사', op: 'group', targets: [result, product.id] }],
    result: '간섭_검사',
  } as Recipe
}

/** 결과 묶음의 자식들 — 요소 이름. 결과가 묶음이 아니면 빈 목록. */
export function elementsOf(recipe: Recipe): string[] {
  const result = resultOf(recipe)
  const group = nodesOf(recipe).find((one) => one.id === result)
  return group?.op === 'group' ? [...((group.targets as string[]) ?? [])] : []
}

/** 노드 하나가 가리키는 노드들(`target` · `targets`). */
function refsOf(node: Node): string[] {
  const out: string[] = []
  if (typeof node.target === 'string') out.push(node.target)
  if (Array.isArray(node.targets)) out.push(...(node.targets as string[]))
  return out
}

/** 이 노드가 속한 요소 — 결과 묶음의 자식 자신이거나, 그 자식이 (거슬러) 가리키는 노드. */
export function elementOf(recipe: Recipe, nodeId: string): string | null {
  const byId = new Map(nodesOf(recipe).map((one) => [one.id, one]))
  for (const element of elementsOf(recipe)) {
    const seen = new Set<string>()
    const stack = [element]
    while (stack.length) {
      const id = stack.pop()!
      if (id === nodeId) return element
      if (seen.has(id)) continue
      seen.add(id)
      const node = byId.get(id)
      if (node) stack.push(...refsOf(node))
    }
  }
  return null
}

/** 끌어 옮길 수 있는 요소인가 — 판과 검사용 제품은 아니다. */
export function movable(element: string | null, productId?: string): element is string {
  return element !== null && !FIXED.has(element) && element !== productId
}

function shifted(value: unknown, by: number): unknown {
  if (by === 0) return value
  if (typeof value === 'number') return Math.round((value + by) * 1000) / 1000
  if (typeof value === 'string' && value.startsWith('=')) return `=(${value.slice(1)}) + ${Math.round(by * 1000) / 1000}`
  return value
}

/** 자리 칸 하나(`[x, y, z]` · `[x, y]` · 점 목록)를 XY 로 옮긴다. */
function moveAt(at: unknown, dx: number, dy: number): unknown {
  if (!Array.isArray(at)) return at
  if (at.length > 0 && Array.isArray(at[0])) return at.map((one) => moveAt(one, dx, dy))
  return at.map((value, i) => (i === 0 ? shifted(value, dx) : i === 1 ? shifted(value, dy) : value))
}

/**
 * 요소를 **XY 로** 옮긴다 — 그 요소를 이루는 노드의 자리(`at`, 회전 · 이동 노드면 `translate`)를
 * 함께. 받침 · 핀은 판 위에 서 있으므로 높이(Z)는 건드리지 않는다. 회전 · 이동 노드 아래의
 * 원래 도형은 옮기지 않는다(그 노드가 옮긴다 — 둘 다 옮기면 두 번 간다).
 */
export function moveElement(recipe: Recipe, element: string, dx: number, dy: number): Recipe {
  if (dx === 0 && dy === 0) return recipe
  const byId = new Map(nodesOf(recipe).map((one) => [one.id, one]))
  const moving = new Set<string>()
  const stack = [element]
  while (stack.length) {
    const id = stack.pop()!
    if (moving.has(id)) continue
    const node = byId.get(id)
    if (!node) continue
    moving.add(id)
    if (node.op !== 'transform') stack.push(...refsOf(node))
  }
  const nodes = nodesOf(recipe).map((node) => {
    if (!moving.has(node.id)) return node
    if (node.op === 'transform') return { ...node, translate: moveAt(node.translate ?? [0, 0, 0], dx, dy) }
    if ('at' in node) return { ...node, at: moveAt(node.at, dx, dy) }
    return node
  })
  return { ...recipe, nodes } as Recipe
}
