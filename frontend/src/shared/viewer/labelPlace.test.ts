import { labelCenter, rulerSide, spreadLabels } from '@/shared/viewer/labelPlace'
import type { LabelBox } from '@/shared/viewer/labelPlace'

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

const boxOf = (anchor: [number, number], center: [number, number] = [0.5, 0.5]): LabelBox => ({
  anchor,
  width: 80,
  height: 20,
  center,
  normal: [0, 1],
  tangent: [1, 0],
})

function rect(box: LabelBox, center: [number, number]) {
  const left = box.anchor[0] - center[0] * box.width
  const bottom = box.anchor[1] - center[1] * box.height
  return { left, right: left + box.width, bottom, top: bottom + box.height }
}

test('글자끼리 겹치면 뒤의 것을 옮겨 놓는다 — 앞의 것은 제자리', () => {
  const boxes = [boxOf([0, 0]), boxOf([10, 5]), boxOf([5, -3])]
  const centers = spreadLabels(boxes)
  expect(centers[0]).toEqual([0.5, 0.5])
  const rects = boxes.map((box, i) => rect(box, centers[i]))
  for (let i = 0; i < rects.length; i++)
    for (let j = i + 1; j < rects.length; j++) {
      const [a, b] = [rects[i], rects[j]]
      const apart = a.right <= b.left || b.right <= a.left || a.top <= b.bottom || b.top <= a.bottom
      expect(apart).toBe(true)
    }
})

test('안 겹치는 글자는 옮기지 않는다', () => {
  const centers = spreadLabels([boxOf([0, 0]), boxOf([500, 0], [0.2, 0.9])])
  expect(centers).toEqual([
    [0.5, 0.5],
    [0.2, 0.9],
  ])
})

test('자의 화면 방향 — 직각은 형상 가운데에서 먼 쪽, 끝에서 보면 위', () => {
  expect(rulerSide([-5, 10], [5, 10], [0, 0])).toEqual({ normal: [-0, 1], tangent: [1, 0] })
  expect(rulerSide([-5, -10], [5, -10], [0, 0]).normal).toEqual([0, -1])
  expect(rulerSide([1, 1], [1, 1], [0, 0])).toEqual({ normal: [0, 1], tangent: [1, 0] })
})
