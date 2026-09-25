/**
 * 3D 에서 고른 점 · 선 · 면을 **원점 · 회전**으로 — 좌표계를 숫자로 적지 않고 화면에서 지정한다.
 *
 * 화면 안에서는 원점 · 회전(X → Y → Z 고정 축 순서, 도)으로 셈하고, 저장할 때 그 좌표계가 쓰는
 * 방식(회전 또는 X · Y 방향 벡터)으로 적는다(`frameFields`). 축의 정본 계산은 서버다
 * (`core/frames.py`). 여기서는 **고른 것 → 원점 · 회전** 한 방향만 셈한다 — 서버가 그 원점 ·
 * 회전으로 다시 축을 푸므로, 여기가 틀리면 3D 에 그려진 축이 고른 것과 어긋나 바로 보인다.
 */

import type { MeasurePick } from '@/shared/viewer/PickViewer'

export type Vec3 = [number, number, number]

const DEG = 180 / Math.PI
const round = (v: number) => Math.round(v * 1e4) / 1e4 + 0

function unit(v: number[]): Vec3 {
  const size = Math.hypot(v[0], v[1], v[2]) || 1
  return [v[0] / size, v[1] / size, v[2] / size]
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
}

const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

/** 회전(도, X → Y → Z 고정 축) → 세 축. 서버의 `from_rotation` 과 같은 규칙. */
export function axesOf(rotate: number[]): [Vec3, Vec3, Vec3] {
  const [rx, ry, rz] = rotate.map((one) => (Number(one) || 0) / DEG)
  const turn = (v: Vec3): Vec3 => {
    let [x, y, z] = v
    ;[y, z] = [y * Math.cos(rx) - z * Math.sin(rx), y * Math.sin(rx) + z * Math.cos(rx)]
    ;[x, z] = [x * Math.cos(ry) + z * Math.sin(ry), -x * Math.sin(ry) + z * Math.cos(ry)]
    ;[x, y] = [x * Math.cos(rz) - y * Math.sin(rz), x * Math.sin(rz) + y * Math.cos(rz)]
    return [x, y, z]
  }
  return [turn([1, 0, 0]), turn([0, 1, 0]), turn([0, 0, 1])]
}

/** 세 축 → 회전(도). R = Rz · Ry · Rx 를 푼다(짐벌 잠김이면 rx 를 0 으로). */
export function rotationOf(x: Vec3, y: Vec3, z: Vec3): Vec3 {
  // R 의 열이 x · y · z 축이다. R[2][0] = -sin(ry).
  const sy = -x[2]
  const ry = Math.asin(Math.max(-1, Math.min(1, sy)))
  let rx: number
  let rz: number
  if (Math.abs(Math.cos(ry)) > 1e-6) {
    rx = Math.atan2(y[2], z[2])
    rz = Math.atan2(x[1], x[0])
  } else {
    rx = 0
    rz = Math.atan2(-y[0], y[1])
  }
  return [round(rx * DEG), round(ry * DEG), round(rz * DEG)]
}

/**
 * 고른 것으로 원점 · 회전을 정한다 — **지금 방향을 되도록 살린다.**
 *
 * - 점: 원점만 옮긴다.
 * - 선(엣지): 원점 = 엣지 중점, **X = 엣지 방향**(Z 는 지금 Z 를 그 방향에 수직으로 맞춘 것).
 * - 면: 원점 = 누른 자리, **Z = 면의 법선**(X 는 지금 X 를 그 면에 눕힌 것).
 */
export function framePlacement(pick: MeasurePick, rotate: number[]): { origin: Vec3; rotate: Vec3 } | null {
  const [x0, , z0] = axesOf(rotate)
  if (pick.kind === 'point') return { origin: pick.at.map(round) as Vec3, rotate: rotate.map((one) => Number(one) || 0) as Vec3 }
  if (pick.kind === 'edge') {
    const p = pick.edge.points
    const last = p.length - 3
    const x = unit([p[last] - p[0], p[last + 1] - p[1], p[last + 2] - p[2]])
    // 지금 Z 를 X 에 수직으로 — 나란하면 지금 Y 로.
    let z: Vec3 = unit(z0.map((v, i) => v - dot(z0, x) * x[i]))
    if (Math.abs(dot(z0, x)) > 0.99) z = unit(cross(x, z0))
    return { origin: pick.edge.midpoint.map(round) as Vec3, rotate: rotationOf(x, cross(z, x), z) }
  }
  if (pick.kind === 'face') {
    const z = unit(pick.face.normal)
    let x: Vec3 = unit(x0.map((v, i) => v - dot(x0, z) * z[i]))
    if (Math.abs(dot(x0, z)) > 0.99) x = unit(cross([0, 1, 0], z))
    return { origin: pick.face.center.map(round) as Vec3, rotate: rotationOf(x, cross(z, x), z) }
  }
  return null
}

/** 좌표계의 방향을 적는 방식 — 서버는 `x_axis` 가 있으면 벡터, 없으면 회전으로 읽는다. */
export type FrameMethod = 'vectors' | 'rotate'

type Values = (number | string)[]

export function methodOf(item: { x_axis?: Values | null; rotate?: Values | null }): FrameMethod {
  return item.x_axis ? 'vectors' : 'rotate'
}

const numbers = (v?: Values | null) =>
  v && v.length === 3 && v.every((one) => typeof one === 'number') ? (v as number[]) : null

/** X · Y 방향(길이 · 직교 상관없음) → 세 축. 서버의 `from_vectors` 와 같은 규칙. 나란하면 null. */
export function axesFromVectors(xAxis: number[], yAxis: number[]): [Vec3, Vec3, Vec3] | null {
  const x = unit(xAxis)
  const zRaw = cross(x, unit(yAxis))
  if (Math.hypot(...zRaw) < 1e-6 || Math.hypot(xAxis[0], xAxis[1], xAxis[2]) === 0) return null
  const z = unit(zRaw)
  return [x, cross(z, x), z]
}

/** 회전 → X · Y 방향 벡터(적을 값). */
export function vectorsOf(rotate: number[]): { x_axis: Vec3; y_axis: Vec3 } {
  const [x, y] = axesOf(rotate)
  return { x_axis: x.map(round) as Vec3, y_axis: y.map(round) as Vec3 }
}

/**
 * 화면이 셈한 원점 · 회전을 **그 좌표계의 방식대로** 적을 칸들. 벡터로 적던 것은 벡터로, 회전으로
 * 적던 것은 회전으로 — 3D 에서 지정해도 사용자가 고른 방식이 바뀌지 않는다.
 */
export function frameFields(
  method: FrameMethod,
  origin: number[],
  rotate: number[],
): { origin: Vec3; x_axis?: Vec3; y_axis?: Vec3; rotate?: Vec3 } {
  const at = origin.map(round) as Vec3
  if (method === 'vectors') return { origin: at, ...vectorsOf(rotate), rotate: undefined }
  return { origin: at, rotate: rotate.map(round) as Vec3, x_axis: undefined, y_axis: undefined }
}

/**
 * 방식을 바꾼다 — 지금 방향을 그대로 옮겨 적는다. 칸에 식이 섞여 셈할 수 없으면 전역 방향에서
 * 시작한다.
 */
export function switchMethod<T extends { x_axis?: Values; y_axis?: Values; rotate?: Values }>(
  item: T,
  method: FrameMethod,
): T {
  if (methodOf(item) === method) return item
  if (method === 'vectors') {
    const rotate = numbers(item.rotate) ?? [0, 0, 0]
    return { ...item, ...vectorsOf(rotate), rotate: undefined }
  }
  const x = numbers(item.x_axis)
  const axes = x ? axesFromVectors(x, numbers(item.y_axis) ?? [0, 1, 0]) : null
  return { ...item, rotate: axes ? rotationOf(...axes) : [0, 0, 0], x_axis: undefined, y_axis: undefined }
}

/**
 * 손잡이 · 고르기가 시작할 **숫자** 원점 · 회전. 칸이 다 숫자면 그것(벡터면 회전으로 바꿔서), 식이
 * 섞였으면 서버가 지금 치수로 푼 축(`resolved`)에서 되돌린다 — 식은 화면이 못 푼다.
 */
export function numericFrame(
  item: { origin?: Values; rotate?: Values; x_axis?: Values; y_axis?: Values },
  resolved?: { origin: number[]; x: number[]; y: number[]; z: number[] },
): { origin: Vec3; rotate: Vec3 } {
  const origin = numbers(item.origin)
  let rotate: number[] | null = null
  if (methodOf(item) === 'vectors') {
    const x = numbers(item.x_axis)
    const y = item.y_axis ? numbers(item.y_axis) : [0, 1, 0]
    const axes = x && y ? axesFromVectors(x, y) : null
    rotate = axes ? rotationOf(...axes) : null
  } else {
    rotate = item.rotate ? numbers(item.rotate) : [0, 0, 0]
  }
  if (origin && rotate) return { origin: origin as Vec3, rotate: rotate as Vec3 }
  if (resolved) {
    return { origin: resolved.origin as Vec3, rotate: rotationOf(resolved.x as Vec3, resolved.y as Vec3, resolved.z as Vec3) }
  }
  return { origin: (origin ?? [0, 0, 0]) as Vec3, rotate: (rotate ?? [0, 0, 0]) as Vec3 }
}
