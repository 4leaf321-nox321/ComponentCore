/**
 * 3D 에 그릴 표시 — 고른 것 강조 · 치수선 · 값 글자. 뷰어는 이대로 그리기만 한다.
 *
 * 지금 고르는 중인 것(진한 빨강)과 담아 둔 것(옅은 회색)을 함께 낸다 — 여러 곳을 한 화면에서
 * 비교하려고 담는 것이므로, 담은 것이 지워지면 담는 뜻이 없다.
 */

import { anchor, headline, measurement, title } from '@/modules/cad/measure'
import type { Pick } from '@/modules/cad/measure'
import type { KeptMeasure } from '@/modules/cad/MeasureDialog'
import type { MeasureMarks } from '@/shared/viewer/PickViewer'

function one(picks: Pick[], tone: 'live' | 'kept', marks: MeasureMarks) {
  const { rows, from, to } = measurement(picks)
  for (const [index, pick] of picks.entries()) {
    if (pick.kind === 'point') {
      marks.points.push(pick.at)
      if (tone === 'live') marks.labels.push({ at: pick.at, text: String(index + 1), tone: 'entity' })
    } else if (pick.kind === 'edge') {
      marks.edges.push(pick.edge.points)
      if (tone === 'live') marks.labels.push({ at: anchor(pick), text: title(pick, index + 1), tone: 'entity' })
    } else {
      marks.faces.push({ vertices: pick.face.vertices, triangles: pick.face.triangles })
      if (tone === 'live') marks.labels.push({ at: anchor(pick), text: title(pick, index + 1), tone: 'entity' })
    }
  }
  const text = headline(rows)
  if (from && to) {
    marks.segments.push([from, to])
    const middle = [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2, (from[2] + to[2]) / 2]
    if (text) marks.labels.push({ at: middle, text, tone: 'distance' })
  } else if (text && picks.length === 1) {
    marks.labels.push({ at: anchor(picks[0]), text, tone: 'distance' })
  }
}

export function measureMarks(picks: Pick[], kept: KeptMeasure[] = []): MeasureMarks {
  const marks: MeasureMarks = { points: [], segments: [], labels: [], edges: [], faces: [] }
  for (const keep of kept) one(keep.picks, 'kept', marks)
  one(picks, 'live', marks)
  return marks
}
