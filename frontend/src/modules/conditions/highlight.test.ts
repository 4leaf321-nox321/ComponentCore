import { bodyMarks, CONTACT_COLOR, contactKind, contactMarks, foundMarks, mergeMarks, TIE_COLOR } from '@/modules/conditions/highlight'
import type { MeshData, MeshFace } from '@/shared/viewer/PickViewer'

function face(index: number, center: number[], part?: string): MeshFace {
  return { index, kind: 'plane', center, normal: [0, 0, 1], area: 1, vertices: [index, 0, 0, 1, 0, 0, 1, 1, 0], triangles: [0, 1, 2], part }
}

const MESH: MeshData = {
  bbox: { min: [0, 0, 0], max: [1, 1, 1] },
  faces: [face(0, [0, 0, 0], '받침'), face(1, [5, 0, 9], '기둥'), face(2, [5, 5, 9], '기둥')],
  edges: [],
} as unknown as MeshData

test('서버가 푼 면을 **번호로** 짝짓고, 번호가 안 맞으면 자리로 찾는다', () => {
  // 서버(3자리)와 메시(4자리)의 반올림이 달라도 같은 면이다.
  const marks = foundMarks(MESH, 'faces', [
    { index: 1, center: [5.0004, 0, 9] },
    // 조립에서 번호가 어긋난 줄 — 자리로 찾는다.
    { index: 7, center: [5, 5, 9] },
    // 메시에 없는 자리 — 그리지 못할 뿐 멈추지 않는다.
    { index: 9, center: [99, 99, 99] },
  ])
  expect(marks.faces.map((one) => one.vertices[0])).toEqual([1, 2])
})

test('바디 그룹은 그 파트의 면을 다 칠한다 — 여럿을 묶었으면 그 파트들', () => {
  expect(bodyMarks(MESH, { body: '기둥' }).faces).toHaveLength(2)
  expect(bodyMarks(MESH, { any: [{ body: '기둥' }, { body: '받침' }] }).faces).toHaveLength(3)
})

test('접촉 보기 — 본딩은 붉게, 그 밖의 접촉은 푸르게, 한 면이 둘에 들면 본딩이 위에', () => {
  expect([contactKind('bonded'), contactKind('frictional'), contactKind('no_separation')]).toEqual(['tie', 'contact', 'contact'])
  const marks = contactMarks(MESH, [
    { what: 'faces', rows: [{ index: 0, center: [0, 0, 0] }], kind: 'tie' },
    { what: 'faces', rows: [{ index: 1, center: [5, 0, 9] }, { index: 0, center: [0, 0, 0] }], kind: 'contact' },
  ])
  // 푸른 것 먼저, 붉은 것 나중 — 면 0 은 둘에 들어 붉은 것이 위에 그려진다.
  expect(marks.faces.map((one) => [one.vertices[0], one.color])).toEqual([
    [1, CONTACT_COLOR],
    [0, CONTACT_COLOR],
    [0, TIE_COLOR],
  ])
})

test('표시는 겹쳐 그린다 — 접촉 위에 고른 그룹, 없으면 있는 것만', () => {
  const contacts = contactMarks(MESH, [{ what: 'faces', rows: [{ index: 0, center: [0, 0, 0] }], kind: 'tie' }])
  const lit = foundMarks(MESH, 'faces', [{ index: 1, center: [5, 0, 9] }])
  expect(mergeMarks(contacts, lit)?.faces.map((one) => one.vertices[0])).toEqual([0, 1])
  expect(mergeMarks(undefined, lit)).toBe(lit)
  expect(mergeMarks(undefined, undefined)).toBeUndefined()
})
