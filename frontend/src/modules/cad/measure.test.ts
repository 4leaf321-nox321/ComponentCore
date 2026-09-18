import { angleOfThree, headline, measurement, pair, segmentToSegment, single } from '@/modules/cad/measure'
import type { Pick, Vec } from '@/modules/cad/measure'
import type { MeshEdge, MeshFace } from '@/shared/viewer/PickViewer'

function edge(points: Vec[], extra: Partial<MeshEdge> = {}): MeshEdge {
  const flat = points.flat()
  return {
    index: 0,
    kind: 'line',
    midpoint: [(points[0][0] + points.at(-1)![0]) / 2, (points[0][1] + points.at(-1)![1]) / 2, (points[0][2] + points.at(-1)![2]) / 2],
    length: Math.hypot(points.at(-1)![0] - points[0][0], points.at(-1)![1] - points[0][1], points.at(-1)![2] - points[0][2]),
    vertical: false,
    points: flat,
    ...extra,
  }
}

function plane(center: Vec, normal: Vec, extra: Partial<MeshFace> = {}): MeshFace {
  return { index: 0, kind: 'plane', center, normal, area: 100, vertices: [...center], triangles: [], ...extra }
}

const point = (at: Vec): Pick => ({ kind: 'point', at })

test('점 ↔ 점 — 거리와 축별 차이', () => {
  const got = pair(point([0, 0, 0]), point([30, 40, 0]))
  expect(got.rows[0].text).toBe('50 mm')
  expect(got.rows[1].text).toContain('ΔX 30')
  expect(headline(got.rows)).toBe('50 mm')
})

test('점 ↔ 선 — 직선까지의 수직 거리와 그 발', () => {
  const got = pair(point([10, 5, 0]), { kind: 'edge', edge: edge([[0, 0, 0], [20, 0, 0]]) })
  expect(got.rows[0].text).toBe('5 mm')
  expect(got.to).toEqual([10, 0, 0])
  expect(got.rows[0].approx).toBeFalsy()
})

test('점 ↔ 면 — 평면은 정확히, 어느 쪽인지도', () => {
  const got = pair(point([0, 0, 12]), { kind: 'face', face: plane([0, 0, 2], [0, 0, 1]) })
  expect(got.rows[0].text).toBe('10 mm')
  expect(got.rows[1].text).toContain('법선 쪽')
  expect(got.to).toEqual([0, 0, 2])
})

test('구멍은 지름을 바로 준다 — 점을 찍어 재지 않는다', () => {
  const hole = edge([[3, 0, 0], [0, 3, 0], [-3, 0, 0]], { kind: 'circle', radius: 3, center: [0, 0, 0], length: 18.85 })
  const rows = single({ kind: 'edge', edge: hole })
  expect(rows[0].text).toBe('⌀6 mm')
  expect(rows.some((r) => r.text.includes('R3'))).toBe(true)
})

test('두 구멍 — 중심 사이 거리(도면이 쓰는 값)', () => {
  const a = edge([[3, 0, 0], [0, 3, 0], [-3, 0, 0]], { kind: 'circle', radius: 3, center: [0, 0, 0] })
  const b = edge([[43, 0, 0], [40, 3, 0], [37, 0, 0]], { kind: 'circle', radius: 3, center: [40, 0, 0] })
  const got = pair({ kind: 'edge', edge: a }, { kind: 'edge', edge: b })
  // 재려던 값은 피치다 — 가장자리 사이 틈이 아니라 중심 사이.
  expect(got.rows[0].label).toBe('중심 사이')
  expect(got.rows[0].text).toBe('40 mm')
  expect(headline(got.rows)).toBe('40 mm')
  expect(got.from).toEqual([0, 0, 0])
  expect(got.to).toEqual([40, 0, 0])
})

test('선 ↔ 선 — 나란한지 · 직각인지 말한다', () => {
  const along = { kind: 'edge' as const, edge: edge([[0, 0, 0], [20, 0, 0]]) }
  const above = { kind: 'edge' as const, edge: edge([[0, 0, 10], [20, 0, 10]]) }
  const across = { kind: 'edge' as const, edge: edge([[0, 0, 0], [0, 20, 0]]) }
  const parallel = pair(along, above).rows
  expect(parallel[0].text).toBe('10 mm')
  expect(parallel.find((r) => r.label === '관계')!.text).toContain('나란')
  expect(pair(along, across).rows.find((r) => r.label === '관계')!.text).toContain('직각')
})

test('나란한 두 면 — 두께 · 간격', () => {
  const rows = pair({ kind: 'face', face: plane([0, 0, 0], [0, 0, 1]) }, { kind: 'face', face: plane([5, 5, 12], [0, 0, -1]) }).rows
  expect(rows[0].text).toBe('12 mm')
  expect(rows[1].text).toContain('나란한 두 면')
})

test('비스듬한 두 면 — 사잇각. 곡면이 끼면 근사라고 밝힌다', () => {
  const slanted = pair({ kind: 'face', face: plane([0, 0, 0], [0, 0, 1]) }, { kind: 'face', face: plane([0, 0, 0], [1, 0, 0]) }).rows
  expect(slanted.find((r) => r.label === '사잇각')!.text).toBe('90°')
  expect(slanted[0].approx).toBe(true)
  expect(headline(slanted).startsWith('≈')).toBe(true)
})

test('점 셋이면 가운데 점의 각', () => {
  expect(angleOfThree([10, 0, 0], [0, 0, 0], [0, 10, 0])).toBe(90)
  const got = measurement([point([10, 0, 0]), point([0, 0, 0]), point([0, 10, 0])])
  expect(got.rows[0].text).toBe('90°')
})

test('꼬인 두 선분의 최단 거리', () => {
  const got = segmentToSegment([0, 0, 0], [10, 0, 0], [5, -5, 4], [5, 5, 4])
  expect(got.distance).toBe(4)
  expect(got.from).toEqual([5, 0, 0])
})

test('마크는 자 하나에 값을 실어 보낸다 — 어디서 어디를 쟀는지 3D 가 그린다', async () => {
  const { measureMarks } = await import('@/modules/cad/measureMarks')
  const a: Pick = { kind: 'point', at: [0, 0, 0] }
  const b: Pick = { kind: 'point', at: [40, 0, 0] }
  const marks = measureMarks([a, b])
  expect(marks.segments).toHaveLength(1)
  expect(marks.segments[0]).toMatchObject({ from: [0, 0, 0], to: [40, 0, 0], text: '40 mm', tone: 'live' })
  expect(marks.points).toHaveLength(2)
  // 값은 자 위에 붙으므로 따로 떠 있는 거리 글자는 없다.
  expect(marks.labels.filter((one) => one.tone === 'distance')).toHaveLength(0)

  // 담아 둔 것은 옅게 — 지금 재는 것과 구별된다.
  const kept = measureMarks([], [{ id: 'k', picks: [a, b], label: '' }])
  expect(kept.segments[0].tone).toBe('kept')
  expect(kept.labels).toHaveLength(0)
})
