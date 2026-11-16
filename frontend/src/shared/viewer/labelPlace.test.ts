import { labelCenter } from '@/shared/viewer/labelPlace'

/** 기준점이 `center` 일 때 글자 상자(높이 1, 폭 aspect)가 화면에서 차지하는 자리 — 기준점이 원점. */
function box(center: [number, number], aspect: number) {
  const left = -center[0] * aspect
  const bottom = -center[1]
  return { left, right: left + aspect, bottom, top: bottom + 1 }
}

test('가로로 놓인 자 — 글자는 자의 위나 아래로, 형상 가운데에서 먼 쪽에', () => {
  // 자가 형상 위쪽에 있다 → 글자는 자 위로.
  const above = box(labelCenter([-50, 100], [50, 100], [0, 0], 4), 4)
  expect(above.bottom).toBeGreaterThan(0)
  // 자가 형상 아래쪽에 있다 → 글자는 자 아래로.
  const below = box(labelCenter([-50, -100], [50, -100], [0, 0], 4), 4)
  expect(below.top).toBeLessThan(0)
})

test('세로로 놓인 자 — 글자는 자의 옆으로 비켜 자를 덮지 않는다', () => {
  // 자가 형상 오른쪽에 세로로 — 글자 상자의 왼쪽 끝이 자(x=0)보다 오른쪽이다.
  const right = box(labelCenter([0, -5], [0, 5], [-100, 0], 5), 5)
  expect(right.left).toBeGreaterThan(0)
  const left = box(labelCenter([0, -5], [0, 5], [100, 0], 5), 5)
  expect(left.right).toBeLessThan(0)
})

test('비스듬한 자도 글자 상자가 자의 직선에 닿지 않는다', () => {
  const aspect = 3
  const center = labelCenter([0, 0], [10, 10], [10, -10], aspect)
  const { left, right, bottom, top } = box(center, aspect)
  // 직선 y = x 에서 상자의 네 꼭짓점이 모두 같은 쪽(위쪽 — 형상 가운데의 반대)에 있다.
  for (const [x, y] of [[left, bottom], [left, top], [right, bottom], [right, top]]) expect(y - x).toBeGreaterThan(0)
})

test('자를 끝에서 보면(화면에서 점) 글자는 위로', () => {
  const up = box(labelCenter([3, 3], [3, 3], [3, 3], 2), 2)
  expect(up.bottom).toBeGreaterThan(0)
})
