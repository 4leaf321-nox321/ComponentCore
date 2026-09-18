import { allowedDrops, dropProblem, moveTo, orderProblem } from '@/modules/cad/reorder'
import type { RecipeNode } from '@/modules/cad/recipeSpec'

const NODES: RecipeNode[] = [
  { id: 'plate', op: 'box' },
  { id: 'sk', op: 'sketch' },
  { id: 'ex', op: 'extrude', sketch: 'sk' },
  { id: 'cut', op: 'cut', target: 'plate', tools: ['ex'] },
]

test('끼울 자리는 빼기 전 기준의 칸 사이 번호다', () => {
  expect(moveTo([1, 2, 3, 4], 0, 2)).toEqual([2, 1, 3, 4])
  expect(moveTo([1, 2, 3, 4], 3, 1)).toEqual([1, 4, 2, 3])
  expect(moveTo([1, 2, 3, 4], 1, 1)).toEqual([1, 2, 3, 4])
})

test('쓰는 피처가 쓰이는 피처보다 앞에 오면 이유를 말한다', () => {
  expect(orderProblem(NODES)).toBeNull()
  const broken = orderProblem([NODES[2], NODES[1], NODES[0], NODES[3]])
  expect(broken).toContain('sk')
  expect(broken).toContain('먼저 올 수 없습니다')
})

test('선후관계가 있으면 그 자리에는 못 놓는다', () => {
  // 돌출(ex)을 스케치(sk) 앞으로 → 막힌다.
  expect(dropProblem(NODES, 2, 1)).not.toBeNull()
  // 스케치를 맨 끝으로 → 돌출이 앞서게 되니 막힌다.
  expect(dropProblem(NODES, 1, 4)).not.toBeNull()
  // 상자(plate)는 아무도 앞에서 안 쓰니 스케치 뒤로 갈 수 있다.
  expect(dropProblem(NODES, 0, 2)).toBeNull()
  // 제자리는 언제나 된다.
  expect(dropProblem(NODES, 2, 2)).toBeNull()
  expect(dropProblem(NODES, 2, 3)).toBeNull()
})

test('끌기 시작할 때 놓을 수 있는 자리를 미리 센다', () => {
  expect(allowedDrops(NODES, 0)).toEqual(new Set([0, 1, 2, 3]))
  // cut 은 ex · plate 뒤여야 하니 마지막 두 자리뿐이다.
  expect(allowedDrops(NODES, 3)).toEqual(new Set([3, 4]))
})
