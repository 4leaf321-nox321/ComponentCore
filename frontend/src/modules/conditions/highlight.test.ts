import { bodyMarks, foundMarks } from '@/modules/conditions/highlight'
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
