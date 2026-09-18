/**
 * 측정 계산 — 고른 것(점 · 선 · 면) 하나 또는 둘에서 **잴 수 있는 값을 전부** 뽑는다.
 *
 * 화면은 여기서 나온 줄을 그리기만 한다. 순수 함수라 시험으로 값을 지킬 수 있다.
 * 곡면 · 곡선이 끼면 정확히 풀 수 없는 것이 있다 — 그때는 삼각형 · 꺾은선으로 **근사**하고
 * `approx` 를 세워 화면이 「≈」 를 붙이게 한다. 값을 말없이 반올림해 내놓지 않는다.
 */

import type { MeasurePick, MeshEdge, MeshFace } from '@/shared/viewer/PickViewer'

export type Vec = [number, number, number]

/** 고른 것 하나 — 3D 뷰어가 만든다(그 쪽 타입이 정본). */
export type Pick = MeasurePick

/** 측정 한 줄 — 이름과 값, 그리고 3D 에 띄울 짧은 글. */
export interface Row {
  label: string
  text: string
  /** 3D 에 크게 띄울 값(하나만). */
  headline?: boolean
  approx?: boolean
}

const EPS = 1e-6

export const sub = (a: Vec, b: Vec): Vec => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
export const add = (a: Vec, b: Vec): Vec => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
export const mul = (a: Vec, k: number): Vec => [a[0] * k, a[1] * k, a[2] * k]
export const dot = (a: Vec, b: Vec) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
export const cross = (a: Vec, b: Vec): Vec => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
export const len = (a: Vec) => Math.hypot(a[0], a[1], a[2])
export const unit = (a: Vec): Vec => {
  const l = len(a)
  return l < EPS ? [0, 0, 0] : [a[0] / l, a[1] / l, a[2] / l]
}

export function fmt(v: number, digits = 2): string {
  const rounded = Math.round(v * 10 ** digits) / 10 ** digits
  return Object.is(rounded, -0) ? '0' : String(rounded)
}

export const vecText = (p: Vec) => `(${p.map((v) => fmt(v)).join(', ')})`

/** 고른 것의 대표 점 — 치수선을 어디서 어디로 그릴지. */
export function anchor(pick: Pick): Vec {
  if (pick.kind === 'point') return pick.at
  if (pick.kind === 'edge') return (pick.edge.center as Vec | undefined) ?? (pick.edge.midpoint as Vec)
  return pick.face.center as Vec
}

export function title(pick: Pick, index: number): string {
  if (pick.kind === 'point') return `점 ${index}`
  if (pick.kind === 'edge') return `${pick.edge.kind === 'circle' ? '원' : '선'} ${index}`
  return `면 ${index}`
}

/** 꺾은선 점들 — 곡선 엣지는 서버가 24점으로 준다. */
function edgePoints(edge: MeshEdge): Vec[] {
  const out: Vec[] = []
  for (let i = 0; i + 2 < edge.points.length; i += 3) out.push([edge.points[i], edge.points[i + 1], edge.points[i + 2]])
  return out
}

function faceVertices(face: MeshFace): Vec[] {
  const out: Vec[] = []
  for (let i = 0; i + 2 < face.vertices.length; i += 3) out.push([face.vertices[i], face.vertices[i + 1], face.vertices[i + 2]])
  return out
}

/** 점과 **선분**의 가장 가까운 거리와 그 자리. */
export function pointToSegment(p: Vec, a: Vec, b: Vec): { distance: number; at: Vec } {
  const ab = sub(b, a)
  const l2 = dot(ab, ab)
  const t = l2 < EPS ? 0 : Math.max(0, Math.min(1, dot(sub(p, a), ab) / l2))
  const at = add(a, mul(ab, t))
  return { distance: len(sub(p, at)), at }
}

export function pointToPolyline(p: Vec, points: Vec[]): { distance: number; at: Vec } {
  let best = { distance: Infinity, at: points[0] ?? p }
  for (let i = 1; i < points.length; i += 1) {
    const one = pointToSegment(p, points[i - 1], points[i])
    if (one.distance < best.distance) best = one
  }
  return best
}

/** 두 꺾은선 사이의 가장 가까운 두 점 — 선분끼리 재서 가장 작은 것. */
export function polylineToPolyline(a: Vec[], b: Vec[]): { distance: number; from: Vec; to: Vec } {
  let best = { distance: Infinity, from: a[0], to: b[0] }
  for (let i = 1; i < a.length; i += 1) {
    for (let j = 1; j < b.length; j += 1) {
      const one = segmentToSegment(a[i - 1], a[i], b[j - 1], b[j])
      if (one.distance < best.distance) best = one
    }
  }
  return best
}

/** 선분과 선분의 최단 거리(평행 · 꼬인 경우 포함). */
export function segmentToSegment(p1: Vec, q1: Vec, p2: Vec, q2: Vec): { distance: number; from: Vec; to: Vec } {
  const d1 = sub(q1, p1)
  const d2 = sub(q2, p2)
  const r = sub(p1, p2)
  const a = dot(d1, d1)
  const e = dot(d2, d2)
  const f = dot(d2, r)
  let s = 0
  let t = 0
  if (a < EPS && e < EPS) {
    return { distance: len(r), from: p1, to: p2 }
  }
  if (a < EPS) {
    t = Math.max(0, Math.min(1, f / e))
  } else {
    const c = dot(d1, r)
    if (e < EPS) {
      s = Math.max(0, Math.min(1, -c / a))
    } else {
      const b = dot(d1, d2)
      const denom = a * e - b * b
      s = denom > EPS ? Math.max(0, Math.min(1, (b * f - c * e) / denom)) : 0
      t = (b * s + f) / e
      if (t < 0) {
        t = 0
        s = Math.max(0, Math.min(1, -c / a))
      } else if (t > 1) {
        t = 1
        s = Math.max(0, Math.min(1, (b - c) / a))
      }
    }
  }
  const from = add(p1, mul(d1, s))
  const to = add(p2, mul(d2, t))
  return { distance: len(sub(from, to)), from, to }
}

const isPlane = (face: MeshFace) => face.kind === 'plane'
const isStraight = (edge: MeshEdge) => edge.kind === 'line'

function edgeDirection(edge: MeshEdge): Vec {
  const points = edgePoints(edge)
  return unit(sub(points[points.length - 1], points[0]))
}

/** 두 방향 사이의 각(0~90°) — 선 · 법선은 방향이 뒤집혀도 같은 것으로 본다. */
export function angleBetween(a: Vec, b: Vec): number {
  const c = Math.min(1, Math.abs(dot(unit(a), unit(b))))
  return (Math.acos(c) * 180) / Math.PI
}

function deltas(from: Vec, to: Vec): string {
  const d = sub(to, from)
  return `ΔX ${fmt(d[0])} · ΔY ${fmt(d[1])} · ΔZ ${fmt(d[2])}`
}

/** 하나만 골랐을 때 — 그 자체의 치수. */
export function single(pick: Pick): Row[] {
  if (pick.kind === 'point') return [{ label: '자리', text: vecText(pick.at), headline: true }]
  if (pick.kind === 'edge') {
    const edge = pick.edge
    const points = edgePoints(edge)
    const rows: Row[] = []
    if (edge.radius) {
      rows.push({ label: '지름', text: `⌀${fmt(edge.radius * 2)} mm`, headline: true })
      rows.push({ label: '반지름', text: `R${fmt(edge.radius)} mm` })
      if (edge.center) rows.push({ label: '중심', text: vecText(edge.center as Vec) })
    } else {
      rows.push({ label: '길이', text: `${fmt(edge.length)} mm`, headline: true })
    }
    rows.push({ label: '종류', text: edge.kind })
    if (isStraight(edge)) rows.push({ label: '양 끝', text: `${vecText(points[0])} → ${vecText(points[points.length - 1])}` })
    rows.push({ label: '중점', text: vecText(edge.midpoint as Vec) })
    return rows
  }
  const face = pick.face
  const rows: Row[] = [{ label: '넓이', text: `${fmt(face.area)} mm²`, headline: true }]
  if (face.radius) {
    rows.push({ label: '지름', text: `⌀${fmt(face.radius * 2)} mm` })
    rows.push({ label: '반지름', text: `R${fmt(face.radius)} mm` })
  }
  rows.push({ label: '종류', text: face.kind })
  rows.push({ label: '중심', text: vecText(face.center as Vec) })
  rows.push({ label: '법선', text: vecText(face.normal as Vec) })
  return rows
}

/** 둘을 골랐을 때 — 거리 · 각도 · 나란한가. 치수선은 `from`→`to` 에 그린다. */
export function pair(a: Pick, b: Pick): { rows: Row[]; from: Vec; to: Vec } {
  // --- 점 ↔ 점
  if (a.kind === 'point' && b.kind === 'point') {
    return {
      rows: [
        { label: '거리', text: `${fmt(len(sub(b.at, a.at)))} mm`, headline: true },
        { label: '축별', text: deltas(a.at, b.at) },
      ],
      from: a.at,
      to: b.at,
    }
  }
  // --- 점 ↔ 선
  if ((a.kind === 'point' && b.kind === 'edge') || (a.kind === 'edge' && b.kind === 'point')) {
    const point = (a.kind === 'point' ? a : (b as { kind: 'point'; at: Vec })).at
    const edge = (a.kind === 'edge' ? a : (b as { kind: 'edge'; edge: MeshEdge })).edge
    const near = pointToPolyline(point, edgePoints(edge))
    const rows: Row[] = [
      { label: '거리', text: `${fmt(near.distance)} mm`, headline: true, approx: !isStraight(edge) },
      { label: '축별', text: deltas(point, near.at) },
      { label: '가까운 자리', text: vecText(near.at) },
    ]
    if (edge.radius && edge.center) {
      rows.push({ label: '원 중심까지', text: `${fmt(len(sub(point, edge.center as Vec)))} mm` })
    }
    return { rows, from: point, to: near.at }
  }
  // --- 점 ↔ 면
  if ((a.kind === 'point' && b.kind === 'face') || (a.kind === 'face' && b.kind === 'point')) {
    const point = (a.kind === 'point' ? a : (b as { kind: 'point'; at: Vec })).at
    const face = (a.kind === 'face' ? a : (b as { kind: 'face'; face: MeshFace })).face
    if (isPlane(face)) {
      const n = unit(face.normal as Vec)
      const gap = dot(sub(point, face.center as Vec), n)
      const foot = sub(point, mul(n, gap))
      return {
        rows: [
          { label: '면까지 수직 거리', text: `${fmt(Math.abs(gap))} mm`, headline: true },
          { label: '어느 쪽', text: gap >= 0 ? '법선 쪽(+)' : '법선 반대(−)' },
          { label: '발 자리', text: vecText(foot) },
        ],
        from: point,
        to: foot,
      }
    }
    const near = nearestVertex(point, faceVertices(face))
    return {
      rows: [
        { label: '거리', text: `${fmt(near.distance)} mm`, headline: true, approx: true },
        { label: '가까운 자리', text: vecText(near.at) },
      ],
      from: point,
      to: near.at,
    }
  }
  // --- 선 ↔ 선
  if (a.kind === 'edge' && b.kind === 'edge') {
    const near = polylineToPolyline(edgePoints(a.edge), edgePoints(b.edge))
    const straight = isStraight(a.edge) && isStraight(b.edge)
    const centers = a.edge.center && b.edge.center ? ([a.edge.center, b.edge.center] as [Vec, Vec]) : null
    const rows: Row[] = []
    // 구멍 둘이면 **중심 사이(피치)**가 재려던 값이다 — 가장자리 사이 틈이 아니라.
    if (centers) {
      rows.push({ label: '중심 사이', text: `${fmt(len(sub(centers[1], centers[0])))} mm`, headline: true })
      rows.push({ label: '축별', text: deltas(centers[0], centers[1]) })
      rows.push({ label: '지름', text: `⌀${fmt((a.edge.radius ?? 0) * 2)} · ⌀${fmt((b.edge.radius ?? 0) * 2)}` })
    }
    rows.push({ label: '최단 거리', text: `${fmt(near.distance)} mm`, headline: !centers, approx: !straight })
    if (straight) {
      const angle = angleBetween(edgeDirection(a.edge), edgeDirection(b.edge))
      rows.push({ label: '사잇각', text: `${fmt(angle)}°` })
      rows.push({ label: '관계', text: angle < 0.5 ? '나란합니다' : angle > 89.5 ? '직각입니다' : '비스듬합니다' })
      rows.push({ label: '중점 사이', text: `${fmt(len(sub(b.edge.midpoint as Vec, a.edge.midpoint as Vec)))} mm` })
    }
    return centers ? { rows, from: centers[0], to: centers[1] } : { rows, from: near.from, to: near.to }
  }
  // --- 선 ↔ 면
  if ((a.kind === 'edge' && b.kind === 'face') || (a.kind === 'face' && b.kind === 'edge')) {
    const edge = (a.kind === 'edge' ? a : (b as { kind: 'edge'; edge: MeshEdge })).edge
    const face = (a.kind === 'face' ? a : (b as { kind: 'face'; face: MeshFace })).face
    const points = edgePoints(edge)
    if (isPlane(face)) {
      const n = unit(face.normal as Vec)
      const gaps = points.map((p) => dot(sub(p, face.center as Vec), n))
      const near = gaps.reduce((best, gap, i) => (Math.abs(gap) < Math.abs(gaps[best]) ? i : best), 0)
      const far = gaps.reduce((best, gap, i) => (Math.abs(gap) > Math.abs(gaps[best]) ? i : best), 0)
      const parallel = Math.abs(Math.abs(gaps[near]) - Math.abs(gaps[far])) < 1e-3
      const foot = sub(points[near], mul(n, gaps[near]))
      const rows: Row[] = [{ label: parallel ? '면까지 거리' : '가장 가까운 거리', text: `${fmt(Math.abs(gaps[near]))} mm`, headline: true }]
      if (isStraight(edge)) {
        const angle = 90 - angleBetween(edgeDirection(edge), n)
        rows.push({ label: '면과 이루는 각', text: `${fmt(angle)}°` })
        rows.push({ label: '관계', text: angle < 0.5 ? '면과 나란합니다' : angle > 89.5 ? '면에 수직입니다' : '비스듬합니다' })
      }
      if (!parallel) rows.push({ label: '가장 먼 거리', text: `${fmt(Math.abs(gaps[far]))} mm` })
      return { rows, from: points[near], to: foot }
    }
    const near = nearestVertex(points[0], faceVertices(face))
    return { rows: [{ label: '거리', text: `${fmt(near.distance)} mm`, headline: true, approx: true }], from: points[0], to: near.at }
  }
  // --- 면 ↔ 면
  const fa = (a as { kind: 'face'; face: MeshFace }).face
  const fb = (b as { kind: 'face'; face: MeshFace }).face
  const angle = angleBetween(fa.normal as Vec, fb.normal as Vec)
  const rows: Row[] = []
  if (isPlane(fa) && isPlane(fb) && angle < 0.5) {
    const n = unit(fa.normal as Vec)
    const gap = Math.abs(dot(sub(fb.center as Vec, fa.center as Vec), n))
    rows.push({ label: '면 사이 거리', text: `${fmt(gap)} mm`, headline: true })
    rows.push({ label: '관계', text: '나란한 두 면입니다 — 두께 · 간격' })
  } else {
    const near = nearestPair(faceVertices(fa), faceVertices(fb))
    rows.push({ label: '가장 가까운 거리', text: `${fmt(near.distance)} mm`, headline: true, approx: true })
    rows.push({ label: '사잇각', text: `${fmt(angle)}°` })
    rows.push({ label: '관계', text: angle > 89.5 ? '직각입니다' : '비스듬합니다' })
  }
  if (fa.radius && fb.radius) rows.push({ label: '지름', text: `⌀${fmt(fa.radius * 2)} · ⌀${fmt(fb.radius * 2)}` })
  rows.push({ label: '중심 사이', text: `${fmt(len(sub(fb.center as Vec, fa.center as Vec)))} mm` })
  rows.push({ label: '넓이', text: `${fmt(fa.area)} · ${fmt(fb.area)} mm²` })
  return { rows, from: fa.center as Vec, to: fb.center as Vec }
}

function nearestVertex(point: Vec, vertices: Vec[]): { distance: number; at: Vec } {
  let best = { distance: Infinity, at: point }
  for (const v of vertices) {
    const d = len(sub(point, v))
    if (d < best.distance) best = { distance: d, at: v }
  }
  return best
}

function nearestPair(a: Vec[], b: Vec[]): { distance: number; from: Vec; to: Vec } {
  let best = { distance: Infinity, from: a[0], to: b[0] }
  for (const p of a) {
    for (const q of b) {
      const d = len(sub(p, q))
      if (d < best.distance) best = { distance: d, from: p, to: q }
    }
  }
  return best
}

/** 점 셋 — 가운데 점에서 이루는 각. */
export function angleOfThree(a: Vec, b: Vec, c: Vec): number {
  return angleBetweenSigned(sub(a, b), sub(c, b))
}

function angleBetweenSigned(u: Vec, v: Vec): number {
  const c = Math.max(-1, Math.min(1, dot(unit(u), unit(v))))
  return (Math.acos(c) * 180) / Math.PI
}

/** 고른 것들로 낼 수 있는 값 전부 + 치수선. */
export function measurement(picks: Pick[]): { rows: Row[]; from?: Vec; to?: Vec } {
  if (picks.length === 0) return { rows: [] }
  if (picks.length === 1) return { rows: single(picks[0]) }
  if (picks.length === 2) {
    const got = pair(picks[0], picks[1])
    return { rows: got.rows, from: got.from, to: got.to }
  }
  const [a, b, c] = picks.slice(-3).map(anchor)
  return {
    rows: [
      { label: '각도', text: `${fmt(angleOfThree(a, b, c))}°`, headline: true },
      { label: '변 길이', text: `${fmt(len(sub(a, b)))} · ${fmt(len(sub(c, b)))} mm` },
      { label: '끝점 사이', text: `${fmt(len(sub(c, a)))} mm` },
    ],
    from: a,
    to: c,
  }
}

/** 3D 에 크게 띄울 한 줄. */
export function headline(rows: Row[]): string {
  const first = rows.find((row) => row.headline) ?? rows[0]
  return first ? `${first.approx ? '≈ ' : ''}${first.text}` : ''
}
