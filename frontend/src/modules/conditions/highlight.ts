/**
 * 선택 그룹을 3D 에 **비춘다** — 트리에서 그룹을 누르면 그 그룹이 지금 형상에서 집는 것들.
 *
 * 규칙(`select`)을 푸는 것은 서버다(`/cad/recipe/find` — 합 `any` · 면 나누기 태그까지). 여기서는
 * 서버가 돌려준 줄을 **뷰어의 면 · 엣지**에 짝지어 표시로 바꾼다. 짝짓기는 번호가 먼저고, 번호가
 * 안 맞으면(조립) 대표 점으로 찾는다 — 서버의 질의와 메시는 같은 면을 같은 자리로 말하지만
 * 반올림이 한 자리 다르다(질의 3자리 · 메시 4자리).
 *
 * 바디 그룹은 서버에 물을 것이 없다 — 파트 이름이 곧 답이라 그 파트의 면을 다 칠한다.
 */

import type { MeasureMarks, MeshData } from '@/shared/viewer/PickViewer'

/** 서버가 푼 한 줄 — 면은 `center`, 엣지는 `midpoint`, 점은 `point`. */
export interface FoundRow {
  index: number
  center?: number[]
  midpoint?: number[]
  point?: number[]
}

const TOLERANCE = 2e-3

function close(a: number[] | undefined, b: number[] | undefined): boolean {
  if (!a || !b) return false
  return Math.abs(a[0] - b[0]) <= TOLERANCE && Math.abs(a[1] - b[1]) <= TOLERANCE && Math.abs(a[2] - b[2]) <= TOLERANCE
}

/** 그룹 셀렉터 안의 규칙들 — 여럿을 묶었으면 그 목록. */
function rules(select: Record<string, unknown>): Record<string, unknown>[] {
  return Array.isArray(select.any) ? (select.any as Record<string, unknown>[]) : [select]
}

export function emptyMarks(): MeasureMarks {
  return { points: [], segments: [], labels: [], edges: [], faces: [] }
}

/** 바디 그룹 — 그 파트의 면 전부. 단품은 면에 파트 이름이 없고 바디가 「전체」 하나다. */
export function bodyMarks(mesh: MeshData, select: Record<string, unknown>): MeasureMarks {
  const names = new Set(rules(select).map((one) => String(one.body ?? '')))
  const out = emptyMarks()
  for (const face of mesh.faces) {
    if (names.has(face.part || '전체')) out.faces.push({ vertices: face.vertices, triangles: face.triangles, tone: 'live' })
  }
  return out
}

/** 서버가 푼 줄들 → 뷰어 표시. 짝을 못 찾은 줄은 건너뛴다(그리지 못할 뿐 그룹은 그대로다). */
export function foundMarks(mesh: MeshData, what: string, rows: FoundRow[]): MeasureMarks {
  const out = emptyMarks()
  for (const row of rows) {
    if (what === 'vertices') {
      if (row.point) out.points.push(row.point)
    } else if (what === 'faces') {
      const face = close(mesh.faces[row.index]?.center, row.center)
        ? mesh.faces[row.index]
        : mesh.faces.find((one) => close(one.center, row.center))
      if (face) out.faces.push({ vertices: face.vertices, triangles: face.triangles, tone: 'live' })
    } else {
      const edge = close(mesh.edges[row.index]?.midpoint, row.midpoint)
        ? mesh.edges[row.index]
        : mesh.edges.find((one) => close(one.midpoint, row.midpoint))
      if (edge) out.edges.push({ points: edge.points, tone: 'live' })
    }
  }
  return out
}
