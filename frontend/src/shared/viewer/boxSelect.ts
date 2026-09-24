/**
 * 사각형 선택 — Shift + 끌기로 그린 사각형 안에 **온전히 든 것**을 고른다.
 *
 * - **온전히 든 것만**(창 선택). 걸치기만 한 것까지 딸려 오면 작은 면 몇 개를 고르려다 모델을
 *   가로지르는 큰 면이 다 들어온다.
 * - **가려진 것은 뺀다.** 사각형은 화면에 보이는 것을 겨누는 손짓이다 — 뒷면 · 밑면까지 들어오면
 *   사람은 그것이 들어간 줄 모른다. 보이는지는 부르는 쪽이 3D 로 판정해 준다(`visible*`).
 *
 * 여기는 화면 좌표만 다루는 순수한 셈이라 WebGL 없이 시험할 수 있다(`boxSelect.test.ts`).
 */

import type { MeasurePick, MeshEdge, MeshFace } from '@/shared/viewer/PickViewer'

/** 화면의 사각형(px, 뷰어 왼쪽 위가 0). */
export interface ScreenRect {
  left: number
  top: number
  right: number
  bottom: number
}

/** 화면 좌표(px) — `behind` 면 카메라 뒤라 화면에 없는 자리다. */
export interface ScreenPoint {
  x: number
  y: number
  behind: boolean
}

/** 두 모서리로 사각형 — 어느 쪽으로 끌었든. */
export function rectOf(x0: number, y0: number, x1: number, y1: number): ScreenRect {
  return { left: Math.min(x0, x1), top: Math.min(y0, y1), right: Math.max(x0, x1), bottom: Math.max(y0, y1) }
}

function triples(flat: number[]): number[][] {
  const out: number[][] = []
  for (let i = 0; i + 2 < flat.length; i += 3) out.push([flat[i], flat[i + 1], flat[i + 2]])
  return out
}

/** 엣지의 두 끝 — 꼭짓점(위상의 점)이다. 중점 · 원 중심은 잡을 점일 뿐 꼭짓점이 아니다. */
function endpoints(edge: MeshEdge): number[][] {
  const last = edge.points.length - 3
  return [
    [edge.points[0], edge.points[1], edge.points[2]],
    [edge.points[last], edge.points[last + 1], edge.points[last + 2]],
  ]
}

export function boxPicks({
  faces,
  edges,
  kinds,
  rect,
  project,
  visibleFace,
  visiblePoint,
}: {
  faces: MeshFace[]
  edges: MeshEdge[]
  /** 켠 종류만 고른다 — 선택 대상 단추와 같다. */
  kinds: { point?: boolean; edge?: boolean; face?: boolean; body?: boolean }
  rect: ScreenRect
  project: (point: number[]) => ScreenPoint
  /** 이 면이 화면에 보이나(한 곳이라도). */
  visibleFace: (face: MeshFace) => boolean
  /** 이 점이 가려지지 않았나 — 엣지 · 꼭짓점. */
  visiblePoint: (point: number[]) => boolean
}): MeasurePick[] {
  const inside = (point: number[]) => {
    const at = project(point)
    return !at.behind && at.x >= rect.left && at.x <= rect.right && at.y >= rect.top && at.y <= rect.bottom
  }
  const allInside = (points: number[][]) => points.length > 0 && points.every(inside)
  const out: MeasurePick[] = []

  if (kinds.face) {
    for (const face of faces) {
      if (allInside(triples(face.vertices)) && visibleFace(face)) out.push({ kind: 'face', face })
    }
  }
  if (kinds.edge) {
    for (const edge of edges) {
      if (allInside(triples(edge.points)) && visiblePoint(edge.midpoint)) out.push({ kind: 'edge', edge })
    }
  }
  if (kinds.point) {
    const seen = new Set<string>()
    for (const edge of edges) {
      for (const at of endpoints(edge)) {
        const key = at.map((v) => Math.round(v * 1000)).join(',')
        if (seen.has(key)) continue
        seen.add(key)
        if (inside(at) && visiblePoint(at)) out.push({ kind: 'point', at: [at[0], at[1], at[2]] })
      }
    }
  }
  if (kinds.body) {
    // 바디는 그 파트의 면 전부가 들어와야 한다 — 단품은 면에 파트 이름이 없고 바디가 「전체」 하나다.
    const byBody = new Map<string, MeshFace[]>()
    for (const face of faces) {
      const name = face.part || '전체'
      byBody.set(name, [...(byBody.get(name) ?? []), face])
    }
    for (const [name, list] of byBody) {
      if (list.every((face) => allInside(triples(face.vertices))) && list.some(visibleFace)) {
        out.push({ kind: 'body', name })
      }
    }
  }
  return out
}

/**
 * 면 위의 점들 — 삼각형 무게중심을 **큰 것부터.** 보이는지 쏘아 볼 자리다. 면의 `center` 는
 * 곡면이면 면 위가 아니라(원통면은 축 근처) 쏘면 제 면이 아닌 것에 맞는다.
 */
export function triangleCentroids(face: MeshFace): number[][] {
  const v = face.vertices
  const t = face.triangles
  const out: { at: number[]; area: number }[] = []
  for (let i = 0; i + 2 < t.length; i += 3) {
    const [a, b, c] = [t[i] * 3, t[i + 1] * 3, t[i + 2] * 3]
    const ab = [v[b] - v[a], v[b + 1] - v[a + 1], v[b + 2] - v[a + 2]]
    const ac = [v[c] - v[a], v[c + 1] - v[a + 1], v[c + 2] - v[a + 2]]
    const cross = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]]
    out.push({
      at: [(v[a] + v[b] + v[c]) / 3, (v[a + 1] + v[b + 1] + v[c + 1]) / 3, (v[a + 2] + v[b + 2] + v[c + 2]) / 3],
      area: Math.hypot(cross[0], cross[1], cross[2]),
    })
  }
  return out.sort((x, y) => y.area - x.area).map((one) => one.at)
}
