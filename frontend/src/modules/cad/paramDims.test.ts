import { dimLabel, dimMarks, dimText, mergeMarks } from '@/modules/cad/paramDims'
import type { ParamDim, ParamDims } from '@/modules/cad/paramDims'
import type { MeshData } from '@/shared/viewer/PickViewer'

const dim = (over: Partial<ParamDim>): ParamDim => ({
  name: '두께',
  value: 3.2,
  status: 'dimension',
  kind: 'distance',
  from: [0, 0, 0],
  to: [0, 0, 3.2],
  at: [0, 0, 1.6],
  faces: [0, 1],
  places: 1,
  message: null,
  ...over,
})

const face = (index: number) => ({ index, kind: 'plane', center: [0, 0, index], normal: [0, 0, 1], area: 1, vertices: [index], triangles: [0] })
const MESH: MeshData = { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [face(0), face(1), face(2)], edges: [] }

const RESULT: ParamDims = {
  face_count: 3,
  dims: [
    dim({}),
    dim({ name: '구멍_지름', value: 6, kind: 'diameter', faces: [2] }),
    dim({ name: '간격비', value: 2, status: 'moved', kind: null, from: null, to: null, at: [1, 1, 1], faces: [2], places: 1 }),
    dim({ name: '압력', value: 2, status: 'unused', kind: null, from: null, to: null, at: null, faces: [] }),
  ],
}

test('3D 의 글자는 이름과 값 — 지름 · 반지름 · 각은 기호를, 여러 곳이면 곳 수를 붙인다', () => {
  expect(dimText(dim({}))).toBe('두께 = 3.2')
  expect(dimText(dim({ kind: 'diameter', value: 6 }))).toBe('두께 = ⌀6')
  expect(dimText(dim({ kind: 'radius', value: 5 }))).toBe('두께 = R5')
  expect(dimText(dim({ kind: 'angle', value: 30 }))).toBe('두께 = 30°')
  expect(dimText(dim({ value: 1.23456789, places: 4 }))).toBe('두께 = 1.2346 (4곳)')
  expect(dimLabel(dim({}))).toBe('면 간 거리')
  expect(dimLabel(dim({ status: 'unused' }))).toBe('형상 무관')
})

test('짚은 것이 없으면 치수를 모두 진하게 긋고 면은 칠하지 않는다', () => {
  const marks = dimMarks(RESULT, MESH)!
  expect(marks.segments.map((one) => [one.text, one.tone])).toEqual([
    ['두께 = 3.2', 'live'],
    ['구멍_지름 = ⌀6', 'live'],
  ])
  // 값과 같은 치수가 없는 변수는 글자만, 형상에 안 쓰는 변수는 그리지 않는다.
  expect(marks.labels.map((one) => one.text)).toEqual(['간격비 = 2'])
  expect(marks.faces).toEqual([])
})

test('짚은 변수만 긋고 그 면을 칠한다 — 나머지를 남기면 글자가 겹쳐 짚은 것이 묻힌다', () => {
  const marks = dimMarks(RESULT, MESH, '구멍_지름')!
  expect(marks.segments.map((one) => one.text)).toEqual(['구멍_지름 = ⌀6'])
  expect(marks.labels).toEqual([])
  expect(marks.faces.map((one) => one.vertices)).toEqual([[2]])
  // 움직인 면은 다른 색으로.
  const moved = dimMarks(RESULT, MESH, '간격비')!
  expect(moved.faces).toHaveLength(1)
  expect(moved.faces[0].color).toBeDefined()
})

test('메시의 면 수가 서버가 센 것과 다르면 칠하지 않는다 — 엉뚱한 면보다 낫다', () => {
  const other: MeshData = { ...MESH, faces: [face(0), face(1)] }
  const marks = dimMarks(RESULT, other, '두께')!
  expect(marks.faces).toEqual([])
  expect(marks.segments).toHaveLength(1)
  expect(dimMarks(null, MESH)).toBeUndefined()
  expect(dimMarks(RESULT, null)).toBeUndefined()
})

test('측정 표시와 변수 치수를 합친다', () => {
  const a = dimMarks(RESULT, MESH)!
  expect(mergeMarks(undefined, a)).toBe(a)
  expect(mergeMarks(a, undefined)).toBe(a)
  expect(mergeMarks(a, a)!.segments).toHaveLength(4)
})
