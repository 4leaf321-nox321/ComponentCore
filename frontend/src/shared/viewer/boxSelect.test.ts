import { boxPicks, rectOf } from '@/shared/viewer/boxSelect'
import type { MeshEdge, MeshFace } from '@/shared/viewer/PickViewer'

/** 화면 = x · y 그대로(z 는 버린다) — 셈만 본다. */
const flat = (p: number[]) => ({ x: p[0], y: p[1], behind: false })

/** 한 변 `size` 인 정사각 면 — 왼쪽 아래 (x, y). */
function square(index: number, x: number, y: number, size = 10, part?: string): MeshFace {
  const v = [x, y, 0, x + size, y, 0, x + size, y + size, 0, x, y + size, 0]
  return {
    index,
    kind: 'plane',
    center: [x + size / 2, y + size / 2, 0],
    normal: [0, 0, 1],
    area: size * size,
    vertices: v,
    triangles: [0, 1, 2, 0, 2, 3],
    part,
  }
}

function line(index: number, from: number[], to: number[]): MeshEdge {
  return {
    index,
    kind: 'line',
    midpoint: from.map((v, i) => (v + to[i]) / 2),
    length: Math.hypot(to[0] - from[0], to[1] - from[1]),
    vertical: false,
    points: [...from, ...to],
  }
}

const always = () => true

test('사각형 안에 **온전히 든 면만** 고른다 — 걸친 면은 빠진다', () => {
  const faces = [square(0, 0, 0), square(1, 20, 0), square(2, 45, 0)]
  const picks = boxPicks({
    faces,
    edges: [],
    kinds: { face: true },
    // 0 과 1 은 온전히, 2(45~55)는 걸친다.
    rect: rectOf(50, 20, -5, -5),
    project: flat,
    visibleFace: always,
    visiblePoint: always,
  })
  expect(picks.map((one) => (one.kind === 'face' ? one.face.index : -1))).toEqual([0, 1])
})

test('**가려진 것은 뺀다** — 사각형은 보이는 것을 겨누는 손짓이다', () => {
  const faces = [square(0, 0, 0), square(1, 20, 0)]
  const picks = boxPicks({
    faces,
    edges: [],
    kinds: { face: true },
    rect: rectOf(-5, -5, 50, 20),
    project: flat,
    visibleFace: (face) => face.index !== 1,
    visiblePoint: always,
  })
  expect(picks).toHaveLength(1)
})

test('켠 종류만 — 엣지를 켜면 엣지, 점을 켜면 **엣지의 끝(꼭짓점)**만', () => {
  const edges = [line(0, [0, 0, 0], [10, 0, 0]), line(1, [10, 0, 0], [10, 10, 0]), line(2, [100, 0, 0], [110, 0, 0])]
  const rect = rectOf(-1, -1, 20, 20)
  const onEdges = boxPicks({ faces: [], edges, kinds: { edge: true }, rect, project: flat, visibleFace: always, visiblePoint: always })
  expect(onEdges.map((one) => (one.kind === 'edge' ? one.edge.index : -1))).toEqual([0, 1])

  const onPoints = boxPicks({ faces: [], edges, kinds: { point: true }, rect, project: flat, visibleFace: always, visiblePoint: always })
  // 끝점 셋(겹치는 (10,0,0)은 한 번) — 중점은 잡을 점일 뿐 꼭짓점이 아니다.
  expect(onPoints.map((one) => (one.kind === 'point' ? one.at : []))).toEqual([
    [0, 0, 0],
    [10, 0, 0],
    [10, 10, 0],
  ])
})

test('바디는 **그 파트의 면 전부**가 들어와야 고른다', () => {
  const faces = [square(0, 0, 0, 10, '받침'), square(1, 10, 0, 10, '받침'), square(2, 100, 0, 10, '기둥')]
  const picks = boxPicks({
    faces,
    edges: [],
    kinds: { body: true },
    rect: rectOf(-1, -1, 30, 30),
    project: flat,
    visibleFace: always,
    visiblePoint: always,
  })
  expect(picks).toEqual([{ kind: 'body', name: '받침' }])
})

test('카메라 뒤의 점은 사각형 안으로 치지 않는다', () => {
  const picks = boxPicks({
    faces: [square(0, 0, 0)],
    edges: [],
    kinds: { face: true },
    rect: rectOf(-5, -5, 50, 50),
    project: (p) => ({ x: p[0], y: p[1], behind: true }),
    visibleFace: always,
    visiblePoint: always,
  })
  expect(picks).toHaveLength(0)
})
