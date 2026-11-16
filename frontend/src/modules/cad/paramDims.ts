/**
 * 변수 치수 — 「이 변수가 어느 치수인가」 를 3D 에 긋는다(서버 `core/param_dims`).
 *
 * 서버가 변수 값을 조금 바꿔 한 번 더 만들고 견준다. 여기는 그 답을 뷰어의 표시(`MeasureMarks`)로
 * 바꾼다 — 치수는 자(치수선)와 `두께 = 3.2`, 값과 같은 치수가 없는 변수는 그 변수가 움직이는 면의
 * 이름표. 편집기의 변수 목록 · 새 DOE · DOE 결과의 3D 가 같은 것을 쓴다(2026-11-16 사용자 요청:
 * 여러 형상을 훑으면 어느 변수가 어느 치수인지 찾기 어렵다).
 *
 * **짚은 변수(`focus`)** 가 있으면 그것만 긋고 그 면을 칠한다. 짚은 것이 없으면 치수를 모두
 * 긋고 면은 칠하지 않는다 — 여럿을 칠하면 형상이 덮인다. 짚었을 때 나머지를 옅게 남겨 보니 변수가
 * 열 개인 도면(로봇 몸통)에서 글자가 겹쳐 짚은 것이 묻혔다(2026-11-17 실측).
 *
 * 면 번호는 같은 레시피로 만든 메시의 번호다. 메시의 면 수가 서버가 센 것(`face_count`)과 다르면
 * (도면이 바뀌는 사이) 칠하지 않는다 — 엉뚱한 면이 칠해지는 것보다 안 칠하는 것이 낫다.
 */

import { useEffect, useRef, useState } from 'react'

import { STORAGE_PREFIX } from '@/shared/branding'
import type { MeasureMarks, MeshData } from '@/shared/viewer/PickViewer'

export type ParamDimStatus = 'dimension' | 'moved' | 'unused' | 'failed' | 'skipped'
export type ParamDimKind = 'distance' | 'diameter' | 'radius' | 'axes' | 'axis_plane' | 'angle'

export interface ParamDim {
  name: string
  value: number | null
  status: ParamDimStatus
  kind: ParamDimKind | null
  /** 치수선의 두 끝 — `dimension` 이고 선으로 그을 수 있을 때. */
  from: number[] | null
  to: number[] | null
  /** 글자 자리 — 선이 없을 때(각도 · 움직인 면). */
  at: number[] | null
  /** 칠할 면 — 메시의 면 번호. */
  faces: number[]
  /** 같은 치수(또는 움직인 면)가 있는 곳의 수. */
  places: number
  message: string | null
}

export interface ParamDims {
  face_count: number
  dims: ParamDim[]
}

/** 움직인 면의 색 — 치수(빨강)와 구별한다. */
const MOVED_COLOR = 0xf59e0b

const KIND_LABELS: Record<ParamDimKind, string> = {
  distance: '면 간 거리',
  diameter: '지름',
  radius: '반지름',
  axes: '축 간 거리',
  axis_plane: '축과 면 거리',
  angle: '각도',
}

const STATUS_LABELS: Record<Exclude<ParamDimStatus, 'dimension'>, string> = {
  moved: '이동 면',
  unused: '형상 무관',
  failed: '찾지 못함',
  skipped: '건너뜀',
}

/** 값 — 넷째 자리까지, 끝의 0 은 뺀다. */
export function shownValue(value: number | null): string {
  return value === null || !Number.isFinite(value) ? '—' : String(Number(value.toFixed(4)))
}

/** 3D 에 붙는 글자 — `두께 = 3.2` · `구멍_지름 = ⌀6` · `노즈_반지름 = R5` · `각 = 30°`. */
export function dimText(dim: ParamDim): string {
  const value = shownValue(dim.value)
  const shown = dim.kind === 'diameter' ? `⌀${value}` : dim.kind === 'radius' ? `R${value}` : dim.kind === 'angle' ? `${value}°` : value
  return `${dim.name} = ${shown}${dim.places > 1 && dim.status === 'dimension' ? ` (${dim.places}곳)` : ''}`
}

/** 범례의 짧은 말 — 치수면 종류(`면 간 거리` · `지름`), 아니면 상태(`이동 면` · `형상 무관`). */
export function dimLabel(dim: ParamDim): string {
  if (dim.status === 'dimension') return dim.kind ? KIND_LABELS[dim.kind] : '치수'
  return STATUS_LABELS[dim.status]
}

const NOTES: Record<Exclude<ParamDimStatus, 'dimension'>, string> = {
  moved: '같은 값의 치수가 없어 움직이는 면을 칠합니다.',
  unused: '형상에 쓰이지 않는 변수입니다.',
  failed: '형상 위의 위치를 찾지 못했습니다.',
  skipped: '시간이 오래 걸려 찾지 않았습니다.',
}

/** 좁은 자리(편집기의 변수 행)에 적는 한 줄 — 3D 에 치수선이 없는 까닭. 자세한 말은 `message`. */
export function dimNote(dim: ParamDim): string {
  return dim.status === 'dimension' ? '' : NOTES[dim.status]
}

/** 서버의 답이 맞는 꼴인가 — 시험의 가짜 응답이나 옛 서버의 답을 그리지 않는다. */
function valid(data: unknown): data is ParamDims {
  return !!data && typeof data === 'object' && Array.isArray((data as ParamDims).dims) && typeof (data as ParamDims).face_count === 'number'
}

/** 뷰어에 그릴 표시. 그릴 것이 없으면 `undefined` — 뷰어가 표시를 지운다. */
export function dimMarks(result: ParamDims | null, mesh: MeshData | null, focus: string | null = null): MeasureMarks | undefined {
  if (!result || !mesh) return undefined
  const marks: MeasureMarks = { points: [], segments: [], labels: [], edges: [], faces: [] }
  const sameFaces = mesh.faces.length === result.face_count
  for (const dim of result.dims) {
    if (dim.status !== 'dimension' && dim.status !== 'moved') continue
    const focused = focus === dim.name
    if (focus !== null && !focused) continue
    const text = dimText(dim)
    if (dim.status === 'dimension' && dim.from && dim.to) {
      marks.segments.push({ from: dim.from, to: dim.to, text, tone: 'live' })
    } else if (dim.at) {
      marks.labels.push({ at: dim.at, text, tone: 'distance' })
    }
    if (!focused || !sameFaces) continue
    for (const index of dim.faces) {
      const face = mesh.faces[index]
      if (!face) continue
      marks.faces.push(
        dim.status === 'moved'
          ? { vertices: face.vertices, triangles: face.triangles, color: MOVED_COLOR, opacity: 0.45 }
          : { vertices: face.vertices, triangles: face.triangles, tone: 'live' },
      )
    }
  }
  return marks
}

/** 두 표시를 하나로 — 편집기는 측정과 변수 치수를 함께 그린다. */
export function mergeMarks(a: MeasureMarks | undefined, b: MeasureMarks | undefined): MeasureMarks | undefined {
  if (!a) return b
  if (!b) return a
  return {
    points: [...a.points, ...b.points],
    segments: [...a.segments, ...b.segments],
    labels: [...a.labels, ...b.labels],
    edges: [...a.edges, ...b.edges],
    faces: [...a.faces, ...b.faces],
  }
}

export interface ParamDimsState {
  data: ParamDims | null
  loading: boolean
  error: Error | null
}

/**
 * 변수 치수를 받아 온다 — `key` 가 바뀔 때마다(`null` 이면 묻지 않는다). 서버는 변수마다 형상을 한
 * 번 더 만드니 `delay` 만큼 쉬었다 묻는다(편집기는 칸을 고칠 때마다 도면이 바뀐다).
 *
 * 지난 열쇠의 답은 내놓지 않는다 — 다른 형상의 치수선이 새 형상 위에 남으면 거짓말이다.
 */
export function useParamDims(key: string | null, load: () => Promise<ParamDims>, delay = 0): ParamDimsState {
  const [state, setState] = useState<ParamDimsState & { key: string | null }>({ key: null, data: null, loading: false, error: null })
  const loader = useRef(load)
  loader.current = load
  useEffect(() => {
    if (key === null) {
      setState({ key: null, data: null, loading: false, error: null })
      return
    }
    let alive = true
    setState({ key, data: null, loading: true, error: null })
    const timer = setTimeout(() => {
      loader
        .current()
        .then((got) => alive && setState({ key, data: valid(got) ? got : null, loading: false, error: null }))
        .catch((caught: unknown) => alive && setState({ key, data: null, loading: false, error: caught instanceof Error ? caught : new Error('치수 위치를 찾지 못했습니다.') }))
    }, delay)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [key, delay])
  return state.key === key ? { data: state.data, loading: state.loading, error: state.error } : { data: null, loading: key !== null, error: null }
}

/**
 * 「치수 표시」 켬 · 끔 — 화면마다 따로, 이 브라우저에만 기억한다(편의일 뿐이다). 저장을 막은
 * 브라우저에서는 이번 화면에서만 기억한다.
 */
export function useDimsToggle(name: string, initial: boolean): [boolean, (next: boolean) => void] {
  const key = `${STORAGE_PREFIX}.paramDims.${name}`
  const [on, setOn] = useState<boolean>(() => {
    try {
      const raw = window.localStorage.getItem(key)
      return raw === null ? initial : raw === '1'
    } catch {
      return initial
    }
  })
  const set = (next: boolean) => {
    setOn(next)
    try {
      window.localStorage.setItem(key, next ? '1' : '0')
    } catch {
      // 저장을 막은 브라우저 — 이번 화면에서만.
    }
  }
  return [on, set]
}
