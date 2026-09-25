import { axesFromVectors, axesOf, frameFields, framePlacement, methodOf, numericFrame, rotationOf, switchMethod, vectorsOf } from '@/modules/cad/frameMath'
import type { MeshEdge, MeshFace } from '@/shared/viewer/PickViewer'

const close = (a: number[], b: number[]) => a.every((v, i) => Math.abs(v - b[i]) < 1e-3)

test('회전 → 축 → 회전이 되돌아온다 — 서버와 같은 규칙(X → Y → Z 고정 축)', () => {
  for (const rotate of [
    [0, 0, 0],
    [30, 0, 0],
    [0, -45, 0],
    [10, 20, 30],
    [-60, 35, 170],
  ]) {
    const [x, y, z] = axesOf(rotate)
    expect(close(rotationOf(x, y, z), rotate)).toBe(true)
  }
  // Z 로 90° 돌리면 X 축이 +Y 를 본다(서버 시험과 같은 값).
  expect(close(axesOf([0, 0, 90])[0], [0, 1, 0])).toBe(true)
})

test('점을 누르면 원점만, 선이면 X = 엣지 방향, 면이면 Z = 법선', () => {
  const point = framePlacement({ kind: 'point', at: [1, 2, 3] }, [0, 0, 45])!
  expect(point.origin).toEqual([1, 2, 3])
  expect(point.rotate).toEqual([0, 0, 45])

  const edge = { index: 0, kind: 'line', midpoint: [5, 5, 0], length: 10, vertical: false, points: [5, 0, 0, 5, 10, 0] } as MeshEdge
  const along = framePlacement({ kind: 'edge', edge }, [0, 0, 0])!
  expect(along.origin).toEqual([5, 5, 0])
  const [x, , z] = axesOf(along.rotate)
  expect(close(x, [0, 1, 0])).toBe(true)
  expect(close(z, [0, 0, 1])).toBe(true)

  const face = { index: 0, kind: 'plane', center: [40, 0, 5], normal: [1, 0, 0], area: 1, vertices: [], triangles: [] } as MeshFace
  const onFace = framePlacement({ kind: 'face', face }, [0, 0, 0])!
  expect(onFace.origin).toEqual([40, 0, 5])
  expect(close(axesOf(onFace.rotate)[2], [1, 0, 0])).toBe(true)
})

test('식이 든 좌표계는 서버가 푼 축에서 숫자를 되돌린다', () => {
  const [x, y, z] = axesOf([0, 90, 0])
  const got = numericFrame({ origin: ['=길이/2', 0, 5], rotate: [0, 90, 0] }, { origin: [40, 0, 5], x, y, z })
  expect(got.origin).toEqual([40, 0, 5])
  expect(close(got.rotate, [0, 90, 0])).toBe(true)
  expect(numericFrame({ origin: [1, 2, 3], rotate: [4, 5, 6] })).toEqual({ origin: [1, 2, 3], rotate: [4, 5, 6] })
})

test('X · Y 방향 벡터 방식 — 회전과 같은 축, 나란하면 null', () => {
  // Y 가 X 에 수직이 아니어도 수직으로 맞춘다(서버 시험과 같은 값).
  const axes = axesFromVectors([0, 2, 0], [-1, 1, 0])!
  expect(close(axes[0], [0, 1, 0]) && close(axes[1], [-1, 0, 0]) && close(axes[2], [0, 0, 1])).toBe(true)
  expect(axesFromVectors([1, 0, 0], [3, 0, 0])).toBeNull()
  expect(vectorsOf([0, 0, 90])).toEqual({ x_axis: [0, 1, 0], y_axis: [-1, 0, 0] })
  expect(close(numericFrame({ origin: [0, 0, 0], x_axis: [0, 1, 0], y_axis: [-1, 0, 0] }).rotate, [0, 0, 90])).toBe(true)
})

test('방식을 바꾸면 방향을 옮겨 적고, 화면에서 지정해도 방식은 그대로', () => {
  const vectors = switchMethod({ name: 'a', rotate: [0, 0, 90] }, 'vectors')
  expect(methodOf(vectors)).toBe('vectors')
  expect(vectors).toMatchObject({ x_axis: [0, 1, 0], y_axis: [-1, 0, 0], rotate: undefined })
  const back = switchMethod(vectors, 'rotate')
  expect(methodOf(back)).toBe('rotate')
  expect(close(back.rotate as number[], [0, 0, 90])).toBe(true)
  // 식이 섞여 셈할 수 없으면 전역에서 시작한다.
  expect(switchMethod<{ x_axis?: (number | string)[]; rotate?: (number | string)[] }>({ x_axis: ['=a', 0, 0] }, 'rotate').rotate).toEqual([0, 0, 0])

  expect(frameFields('vectors', [1, 2, 3], [0, 0, 90])).toEqual({ origin: [1, 2, 3], x_axis: [0, 1, 0], y_axis: [-1, 0, 0], rotate: undefined })
  expect(frameFields('rotate', [1, 2, 3], [0, 0, 90])).toEqual({ origin: [1, 2, 3], rotate: [0, 0, 90], x_axis: undefined, y_axis: undefined })
})
