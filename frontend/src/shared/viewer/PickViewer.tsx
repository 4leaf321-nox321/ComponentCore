/**
 * 고를 수 있는 3D 뷰어 — 서버의 면 · 엣지 메시(`/cad/recipe/mesh`)를 그리고 누른 것을 알려 준다.
 *
 * glTF 뷰어(ModelViewer)와 다른 점: 면마다 Mesh 하나, 엣지마다 Line 하나라 레이캐스트로 무엇을
 * 눌렀는지 안다. 편집기 전용이다 — 결과 화면은 가벼운 glTF 를 쓴다.
 */

import { useCallback, useEffect, useRef } from 'react'
import * as THREE from 'three'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'

import { CameraRig } from '@/shared/viewer/cameraRig'
import type { CameraSync } from '@/shared/viewer/cameraSync'
import { ViewerToolbar } from '@/shared/viewer/ViewerToolbar'

export interface MeshFace {
  index: number
  kind: string
  center: number[]
  normal: number[]
  area: number
  vertices: number[]
  triangles: number[]
  /** 원통 · 구일 때만 — 측정이 지름을 바로 보여 준다. */
  radius?: number
  axis?: { origin: number[]; direction: number[] }
  /** 조립일 때 — 이 면이 속한 구성품 id. 화면이 구성품마다 색을 달리한다. */
  part?: string
}

export interface MeshEdge {
  index: number
  kind: string
  midpoint: number[]
  length: number
  vertical: boolean
  points: number[]
  /** 원 · 호일 때만 — 구멍 지름은 가장 자주 재는 값이다. */
  radius?: number
  center?: number[]
  part?: string
}

export interface MeshData {
  bbox: { min: number[]; max: number[] }
  faces: MeshFace[]
  edges: MeshEdge[]
}

export type PickMode = 'none' | 'face' | 'edge' | 'measure'

/** 측정이 3D 에 그려 달라고 넘기는 것 — 점 · 치수선 · 글자 · 강조할 엣지/면. */
export interface MeasureMarks {
  points: number[][]
  /** 잰 두 자리 — **자(치수선)** 로 그린다. `text` 가 있으면 자 위에 값이 붙는다. */
  segments: { from: number[]; to: number[]; text?: string; tone?: 'live' | 'kept' }[]
  labels: { at: number[]; text: string; tone: 'distance' | 'entity' }[]
  edges: { points: number[]; tone?: 'live' | 'kept' }[]
  faces: { vertices: number[]; triangles: number[]; tone?: 'live' | 'kept' }[]
}

/** 측정으로 고른 것 하나 — 점(꼭짓점 · 중점 · 원 중심에 스냅) · 엣지 · 면. */
export type MeasurePick =
  | { kind: 'point'; at: [number, number, number] }
  | { kind: 'edge'; edge: MeshEdge }
  | { kind: 'face'; face: MeshFace }

export interface PickViewerProps {
  mesh: MeshData | null
  mode: PickMode
  /** 강조할 엣지의 중점들(필렛의 near) — 가까운 엣지가 노랗게 보인다. */
  highlightEdgesNear?: number[][]
  onPickFace?: (face: MeshFace) => void
  onPickEdge?: (edge: MeshEdge) => void
  /** measure 모드: 누른 것을 알려 준다. 표시(점 · 선 · 글자)는 `measureMarks` 로 돌려준다. */
  onMeasure?: (pick: MeasurePick) => void
  /**
   * measure 모드에서 **고를 수 있는 종류** — 없으면 셋 다. 끄면 그 종류는 레이캐스트에서
   * 빠진다: 면만 켜면 빽빽한 모서리 사이에서도 면이 잡힌다.
   */
  measureKinds?: { point: boolean; edge: boolean; face: boolean }
  measureMarks?: MeasureMarks
  /** 조립: 구성품 id → 색. 없는 구성품(과 조립이 아닌 면)은 기본색. */
  partColors?: Record<string, number>
  /** 조립: 이 구성품만 또렷하게, 나머지는 반투명으로 — 어느 것을 고치는지 보인다. */
  emphasis?: string | null
  /** 나란히 놓인 뷰어끼리 카메라를 맞춘다 — 같은 sync 를 받은 뷰어가 함께 돈다. */
  sync?: CameraSync
  className?: string
}

const FACE_COLOR = 0x3b82f6
const HOVER_COLOR = 0xf59e0b
const EDGE_COLOR = 0x1f2937
const PICKED_COLOR = 0xf59e0b
const MEASURE_COLOR = 0xef4444
const DOT_COLOR = 0x2563eb
/** 담아 둔 측정 — 지금 재는 것(빨강)보다 옅게. */
const KEPT_COLOR = 0x9ca3af

/** 글자를 캔버스에 그려 스프라이트로 — 언제나 카메라를 본다. 3D 안에서 값을 읽게. */
function makeLabel(text: string, tone: 'distance' | 'entity'): THREE.Sprite {
  const pad = 10
  const font = 40
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  ctx.font = `bold ${font}px sans-serif`
  const width = Math.ceil(ctx.measureText(text).width) + pad * 2
  canvas.width = width
  canvas.height = font + pad * 2
  const draw = canvas.getContext('2d')!
  draw.font = `bold ${font}px sans-serif`
  draw.fillStyle = tone === 'distance' ? 'rgba(239,68,68,0.92)' : 'rgba(24,24,27,0.85)'
  draw.beginPath()
  draw.roundRect(0, 0, canvas.width, canvas.height, 10)
  draw.fill()
  draw.fillStyle = '#ffffff'
  draw.textBaseline = 'middle'
  draw.fillText(text, pad, canvas.height / 2)
  const texture = new THREE.CanvasTexture(canvas)
  texture.minFilter = THREE.LinearFilter
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true }))
  sprite.renderOrder = 10
  sprite.userData.aspect = canvas.width / canvas.height
  return sprite
}

/**
 * 굵은 선. `THREE.Line` 의 굵기는 대부분의 브라우저에서 **무시된다**(언제나 1px) — 고른 선이
 * 안 고른 선과 똑같아 보이던 까닭이다. Line2 는 화면 픽셀 단위로 굵기를 준다.
 */
function fatLine(points: number[], color: number, width: number, size: THREE.Vector2): Line2 {
  const geometry = new LineGeometry()
  geometry.setPositions(points)
  const material = new LineMaterial({ color, linewidth: width, transparent: true, depthTest: false })
  material.resolution.copy(size)
  const line = new Line2(geometry, material)
  line.computeLineDistances()
  line.renderOrder = 9
  return line
}

/**
 * **자(치수선)** — 잰 두 자리에서 보조선을 빼고, 그 끝을 잇는 선 양끝에 화살표를 세운다.
 * 도면에서 치수를 읽는 그림 그대로라, 어디서 어디를 쟀는지 형상에 가리지 않고 보인다.
 *
 * 자는 잰 자리 **옆으로 비켜** 세운다(형상 가운데에서 멀어지는 쪽) — 선 위에 겹치면 못 읽는다.
 */
function dimensionLine(
  from: THREE.Vector3,
  to: THREE.Vector3,
  center: THREE.Vector3,
  size: number,
  color: number,
  resolution: THREE.Vector2,
): { group: THREE.Group; labelAt: THREE.Vector3 } {
  const group = new THREE.Group()
  const direction = new THREE.Vector3().subVectors(to, from)
  const span = direction.length()
  const middle = new THREE.Vector3().addVectors(from, to).multiplyScalar(0.5)
  if (span < 1e-6) return { group, labelAt: middle }
  direction.normalize()

  // 비켜설 쪽: 형상 중심에서 멀어지는 방향을 선과 직각으로 뽑는다.
  const away = new THREE.Vector3().subVectors(middle, center)
  let side = away.clone().sub(direction.clone().multiplyScalar(away.dot(direction)))
  if (side.lengthSq() < 1e-9) {
    side = new THREE.Vector3(0, 0, 1).cross(direction)
    if (side.lengthSq() < 1e-9) side = new THREE.Vector3(1, 0, 0).cross(direction)
  }
  side.normalize().multiplyScalar(Math.max(size / 14, span / 8))

  const a = from.clone().add(side)
  const b = to.clone().add(side)
  // 보조선 — 잰 자리에서 자까지. 자보다 조금 더 나가게 그린다(도면의 버릇).
  const overshoot = side.clone().setLength(side.length() * 1.12)
  for (const [origin, end] of [
    [from, from.clone().add(overshoot)],
    [to, to.clone().add(overshoot)],
  ] as [THREE.Vector3, THREE.Vector3][]) {
    group.add(fatLine([origin.x, origin.y, origin.z, end.x, end.y, end.z], color, 1.5, resolution))
  }
  group.add(fatLine([a.x, a.y, a.z, b.x, b.y, b.z], color, 3, resolution))

  // 화살표 — 자의 양 끝에서 안쪽을 본다.
  const head = Math.min(size / 45, span / 6) || size / 45
  for (const [tip, towards] of [
    [a, direction.clone()],
    [b, direction.clone().negate()],
  ] as [THREE.Vector3, THREE.Vector3][]) {
    const cone = new THREE.Mesh(
      new THREE.ConeGeometry(head * 0.45, head * 1.6, 12),
      new THREE.MeshBasicMaterial({ color, depthTest: false }),
    )
    cone.position.copy(tip).add(towards.clone().multiplyScalar(head * 0.8))
    cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), towards.clone().negate())
    cone.renderOrder = 9
    group.add(cone)
  }
  return { group, labelAt: new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5) }
}

/** 동그란 점 무늬 — 네모난 기본 점은 꼭짓점처럼 안 보인다. */
function dotTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = 64
  canvas.height = 64
  const draw = canvas.getContext('2d')!
  draw.beginPath()
  draw.arc(32, 32, 26, 0, Math.PI * 2)
  draw.fillStyle = '#ffffff'
  draw.fill()
  draw.lineWidth = 8
  draw.strokeStyle = 'rgba(0,0,0,0.45)'
  draw.stroke()
  return new THREE.CanvasTexture(canvas)
}

/** 크기를 점마다 따로 주는 재질 — 손이 올라간 점만 크게 그린다. */
function dotMaterial(texture: THREE.Texture, color: number): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: { map: { value: texture }, tint: { value: new THREE.Color(color) } },
    vertexShader: `
      attribute float size;
      void main() {
        vec4 view = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = size * (300.0 / -view.z);
        gl_Position = projectionMatrix * view;
      }`,
    fragmentShader: `
      uniform sampler2D map;
      uniform vec3 tint;
      void main() {
        vec4 dot = texture2D(map, gl_PointCoord);
        if (dot.a < 0.35) discard;
        gl_FragColor = vec4(tint, dot.a);
      }`,
    transparent: true,
    depthTest: false,
  })
}

/** 잡을 점을 모은다 — 꼭짓점(엣지 끝) · 엣지 중점 · 원 중심. 겹치는 것은 하나로. */
function gatherDots(mesh: MeshData): { at: number[][]; kinds: string[] } {
  const at: number[][] = []
  const kinds: string[] = []
  const seen = new Set<string>()
  const add = (point: number[], kind: string) => {
    const key = point.map((v) => Math.round(v * 1000)).join(',')
    if (seen.has(key)) return
    seen.add(key)
    at.push(point)
    kinds.push(kind)
  }
  for (const edge of mesh.edges) {
    add([edge.points[0], edge.points[1], edge.points[2]], 'vertex')
    const last = edge.points.length - 3
    add([edge.points[last], edge.points[last + 1], edge.points[last + 2]], 'vertex')
    add(edge.midpoint, 'midpoint')
    if (edge.center) add(edge.center, 'center')
  }
  return { at, kinds }
}

/** 표준 방향 — 뒤에서 카메라가 설 자리(중심 기준 단위 벡터, CAD Z-up 기준). */
export default function PickViewer({ mesh, mode, highlightEdgesNear, onPickFace, onPickEdge, onMeasure, measureKinds, measureMarks, partColors, emphasis, sync, className }: PickViewerProps) {
  const syncId = useRef(`viewer-${Math.random().toString(36).slice(2)}`)
  const syncRef = useRef(sync)
  syncRef.current = sync
  const mount = useRef<HTMLDivElement | null>(null)
  const state = useRef<{
    scene: THREE.Scene
    rig: CameraRig
    renderer: THREE.WebGLRenderer
    group: THREE.Group
    /** 형상만 담는 자리 — 레시피가 바뀌면 이것만 비운다(측정 표시 · 잡을 점은 남는다). */
    shapes: THREE.Group
    faces: THREE.Mesh[]
    edges: THREE.Line[]
    /** 잡을 점 — 꼭짓점 · 엣지 중점 · 원 중심. 측정에서 「점」 을 켰을 때만 보인다. */
    dots: { object: THREE.Points | null; at: number[][]; kinds: string[] }
    /** 손이 올라간 선을 덧그리는 굵은 선 — 원본 선은 그대로 두고 위에 얹는다. */
    hoverLine: Line2 | null
    /** 손이 올라간 점을 감싸는 고리 — 어느 점을 잡는지 눈으로 확인하고 누른다. */
    hoverDot: THREE.Mesh | null
    /** 굵은 선이 화면 크기를 알아야 픽셀 굵기를 지킨다. */
    resolution: THREE.Vector2
    marks: THREE.Group
    fitted: boolean
  } | null>(null)
  const callbacks = useRef({ mode, onPickFace, onPickEdge, onMeasure, measureKinds })
  callbacks.current = { mode, onPickFace, onPickEdge, onMeasure, measureKinds }

  const rigOf = useCallback(() => state.current?.rig ?? null, [])

  // 한 번만: 장면 · 카메라 · 렌더러.
  useEffect(() => {
    const container = mount.current
    if (!container) return
    const scene = new THREE.Scene()
    const dark = document.documentElement.classList.contains('dark')
    scene.background = new THREE.Color(dark ? '#18181b' : '#f4f4f5')
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    container.appendChild(renderer.domElement)
    scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2))
    const sun = new THREE.DirectionalLight(0xffffff, 1.5)
    sun.position.set(1, 2, 3)
    scene.add(sun)
    const rig = new CameraRig(renderer.domElement)
    const controls = rig.controls
    const group = new THREE.Group()
    group.rotation.x = -Math.PI / 2 // CAD Z-up → three Y-up
    scene.add(group)
    const shapes = new THREE.Group()
    group.add(shapes)
    const marks = new THREE.Group()
    group.add(marks)
    state.current = {
      scene,
      rig,
      renderer,
      group,
      shapes,
      faces: [],
      edges: [],
      dots: { object: null, at: [], kinds: [] },
      hoverLine: null,
      hoverDot: null,
      resolution: new THREE.Vector2(1, 1),
      marks,
      fitted: false,
    }

    function resize() {
      const { clientWidth: w, clientHeight: h } = container!
      renderer.setSize(w, h, false)
      rig.setAspect(w / Math.max(h, 1))
      const s = state.current
      if (!s) return
      s.resolution.set(w, h)
      s.group.traverse((one) => {
        if (one instanceof Line2) one.material.resolution.set(w, h)
      })
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(container)

    // 누르기 — 끌기(회전)와 구별하려고 내려간 자리에서 거의 안 움직였을 때만.
    const raycaster = new THREE.Raycaster()
    raycaster.params.Line = { threshold: 1.5 }
    let downAt: [number, number] | null = null
    let hovered: THREE.Mesh | THREE.Line | null = null

    function pick(event: PointerEvent): THREE.Intersection | null {
      const s = state.current
      if (!s) return null
      const box = renderer.domElement.getBoundingClientRect()
      const pointer = new THREE.Vector2(((event.clientX - box.left) / box.width) * 2 - 1, -((event.clientY - box.top) / box.height) * 2 + 1)
      raycaster.setFromCamera(pointer, rig.camera)
      const { mode: m } = callbacks.current
      if (m === 'face') return raycaster.intersectObjects(s.faces, false)[0] ?? null
      if (m === 'edge') {
        raycaster.params.Line = { threshold: Math.max(0.5, (s.group.userData.size as number) / 120) }
        return raycaster.intersectObjects(s.edges, false)[0] ?? null
      }
      if (m === 'measure') {
        const kinds = callbacks.current.measureKinds ?? { point: true, edge: true, face: true }
        const size = s.group.userData.size as number
        raycaster.params.Line = { threshold: Math.max(0.3, size / 200) }
        raycaster.params.Points = { threshold: Math.max(0.4, size / 70) }
        // **점이 먼저다.** 점은 가장 정확한 자리라, 엣지 · 면 위에 겹쳐 있어도 점을 고른다.
        if (kinds.point && s.dots.object) {
          const onDot = raycaster.intersectObject(s.dots.object, false)[0]
          if (onDot) return onDot
        }
        const onEdge = kinds.edge ? raycaster.intersectObjects(s.edges, false)[0] : undefined
        const onFace = kinds.face ? raycaster.intersectObjects(s.faces, false)[0] : undefined
        if (onEdge && onFace) return onEdge.distance <= onFace.distance + size / 50 ? onEdge : onFace
        return onEdge ?? onFace ?? null
      }
      return null
    }
    /**
     * 누른 자리에서 가장 가까운 **잡을 점** — 엣지의 끝점 · 중점, 원의 중심. 충분히 가까울
     * 때만 붙는다. 중심을 주는 이유: 구멍 사이 거리는 중심으로 재는 값이다.
     */
    function snapVertex(point: THREE.Vector3): [number, number, number] | null {
      const s = state.current
      if (!s) return null
      const local = s.group.worldToLocal(point.clone())
      const radius = Math.max(0.5, (s.group.userData.size as number) / 60)
      let best: [number, number, number] | null = null
      let bestD = radius
      const consider = (v: number[]) => {
        const d = Math.hypot(v[0] - local.x, v[1] - local.y, v[2] - local.z)
        if (d < bestD) {
          bestD = d
          best = [v[0], v[1], v[2]]
        }
      }
      for (const l of s.edges) {
        const edge = l.userData.edge as MeshEdge
        consider([edge.points[0], edge.points[1], edge.points[2]])
        const last = edge.points.length - 3
        consider([edge.points[last], edge.points[last + 1], edge.points[last + 2]])
        consider(edge.midpoint)
        if (edge.center) consider(edge.center)
      }
      return best
    }
    /** 점 위에 있을 때는 그 점만 키우고 **주황 고리**를 씌운다 — 골라 놓고도 못 보면 소용없다. */
    function setHoverDot(index: number | null) {
      const s = state.current
      if (!s?.dots.object) return
      const sizes = s.dots.object.geometry.getAttribute('size') as THREE.BufferAttribute
      const base = s.dots.object.userData.base as number
      for (let i = 0; i < sizes.count; i += 1) sizes.setX(i, i === index ? base * 2.4 : base)
      sizes.needsUpdate = true
      if (s.hoverDot) {
        s.group.remove(s.hoverDot)
        s.hoverDot.geometry.dispose()
        ;(s.hoverDot.material as THREE.Material).dispose()
        s.hoverDot = null
      }
      if (index === null) return
      const at = s.dots.at[index]
      const ring = new THREE.Mesh(
        new THREE.SphereGeometry(Math.max(0.05, (s.group.userData.size as number) / 70), 16, 16),
        new THREE.MeshBasicMaterial({ color: HOVER_COLOR, transparent: true, opacity: 0.45, depthTest: false }),
      )
      ring.position.set(at[0], at[1], at[2])
      ring.renderOrder = 8
      s.group.add(ring)
      s.hoverDot = ring
      renderer.domElement.style.cursor = 'crosshair'
    }

    function setHover(object: THREE.Mesh | THREE.Line | null) {
      if (hovered === object) return
      const s = state.current
      if (hovered) {
        const mat = hovered.material as THREE.MeshStandardMaterial | THREE.LineBasicMaterial
        mat.color.set(hovered.userData.picked ? PICKED_COLOR : (hovered.userData.base as number))
      }
      if (s?.hoverLine) {
        s.group.remove(s.hoverLine)
        s.hoverLine.geometry.dispose()
        s.hoverLine.material.dispose()
        s.hoverLine = null
      }
      hovered = object
      if (hovered) {
        ;(hovered.material as THREE.MeshStandardMaterial | THREE.LineBasicMaterial).color.set(HOVER_COLOR)
        // 선은 색만 바꿔서는 **눈에 띄지 않는다**(1px). 굵은 선을 위에 얹어 준다.
        const edge = hovered.userData.edge as MeshEdge | undefined
        if (edge && s) {
          s.hoverLine = fatLine(edge.points, HOVER_COLOR, 6, s.resolution)
          s.group.add(s.hoverLine)
        }
      }
      renderer.domElement.style.cursor = hovered ? 'pointer' : 'default'
    }
    const onDown = (e: PointerEvent) => {
      downAt = [e.clientX, e.clientY]
    }
    const onMove = (e: PointerEvent) => {
      if (callbacks.current.mode === 'none') {
        setHoverDot(null)
        return setHover(null)
      }
      const hit = pick(e)
      const onDot = hit?.object === state.current?.dots.object
      setHoverDot(onDot ? (hit?.index ?? null) : null)
      setHover(onDot ? null : ((hit?.object as THREE.Mesh | THREE.Line) ?? null))
    }
    const onUp = (e: PointerEvent) => {
      if (!downAt) return
      const moved = Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1])
      downAt = null
      if (moved > 4) return
      const hit = pick(e)
      if (!hit) return
      const data = hit.object.userData
      if (callbacks.current.mode === 'face' && data.face) callbacks.current.onPickFace?.(data.face as MeshFace)
      if (callbacks.current.mode === 'edge' && data.edge) callbacks.current.onPickEdge?.(data.edge as MeshEdge)
      if (callbacks.current.mode === 'measure') {
        const kinds = callbacks.current.measureKinds ?? { point: true, edge: true, face: true }
        const dots = state.current?.dots
        // 점을 눌렀으면 **그 점의 좌표 그대로** — 화면에서 본 자리와 잰 자리가 같아야 한다.
        const onDot = dots?.object && hit.object === dots.object && hit.index !== undefined ? dots.at[hit.index] : null
        const snapped = onDot ?? (kinds.point ? snapVertex(hit.point) : null)
        if (snapped) callbacks.current.onMeasure?.({ kind: 'point', at: [snapped[0], snapped[1], snapped[2]] })
        else if (data.edge && kinds.edge) callbacks.current.onMeasure?.({ kind: 'edge', edge: data.edge as MeshEdge })
        else if (data.face && kinds.face) {
          const local = state.current!.group.worldToLocal(hit.point.clone())
          // 면을 눌렀으면 그 면 자체와 누른 점 둘 다 뜻이 있다 — 면(넓이 · 법선)을 준다.
          callbacks.current.onMeasure?.({ kind: 'face', face: { ...(data.face as MeshFace), center: [local.x, local.y, local.z] } })
        }
      }
    }
    renderer.domElement.addEventListener('pointerdown', onDown)
    renderer.domElement.addEventListener('pointermove', onMove)
    renderer.domElement.addEventListener('pointerup', onUp)

    // 카메라 맞추기 — 내가 움직이면 알리고, 남이 움직이면 그대로 놓는다. 되받은 자세를 다시
    // 보내지 않게 `following` 동안은 알리지 않는다.
    let following = false
    const onCameraChange = () => {
      const link = syncRef.current
      if (!link || following) return
      link.publish(syncId.current, {
        position: rig.camera.position.toArray() as [number, number, number],
        target: controls.target.toArray() as [number, number, number],
        up: rig.camera.up.toArray() as [number, number, number],
      })
    }
    controls.addEventListener('change', onCameraChange)
    const unsubscribe = syncRef.current?.subscribe(syncId.current, (pose) => {
      following = true
      rig.camera.position.fromArray(pose.position)
      rig.camera.up.fromArray(pose.up)
      controls.target.fromArray(pose.target)
      controls.update()
      following = false
    })

    let frame = 0
    const animate = () => {
      frame = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, rig.camera)
    }
    animate()
    return () => {
      cancelAnimationFrame(frame)
      controls.removeEventListener('change', onCameraChange)
      unsubscribe?.()
      observer.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onDown)
      renderer.domElement.removeEventListener('pointermove', onMove)
      renderer.domElement.removeEventListener('pointerup', onUp)
      rig.dispose()
      renderer.dispose()
      container.removeChild(renderer.domElement)
      state.current = null
    }
  }, [])

  // 메시가 바뀌면 다시 만든다. 카메라는 처음 한 번만 맞춘다 — 치수를 고칠 때마다 튀면 못 본다.
  useEffect(() => {
    const s = state.current
    if (!s) return
    for (const m of s.faces) {
      m.geometry.dispose()
      ;(m.material as THREE.Material).dispose()
    }
    for (const l of s.edges) {
      l.geometry.dispose()
      ;(l.material as THREE.Material).dispose()
    }
    // **형상만** 비운다. group 을 통째로 비우면 측정 표시와 잡을 점이 붙은 자리까지 떨어져
    // 나가, 다시 그려도 화면에 안 보인다(자식이 아니므로).
    s.shapes.clear()
    s.faces = []
    s.edges = []
    if (!mesh) return

    for (const face of mesh.faces) {
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(face.vertices, 3))
      geometry.setIndex(face.triangles)
      geometry.computeVertexNormals()
      const base = (face.part && partColors?.[face.part]) || FACE_COLOR
      const material = new THREE.MeshStandardMaterial({ color: base, metalness: 0.1, roughness: 0.6, side: THREE.DoubleSide })
      const m = new THREE.Mesh(geometry, material)
      m.userData = { face, base, picked: false }
      s.shapes.add(m)
      s.faces.push(m)
    }
    const near = highlightEdgesNear ?? []
    for (const edge of mesh.edges) {
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(edge.points, 3))
      const picked = near.some((p) => Math.hypot(p[0] - edge.midpoint[0], p[1] - edge.midpoint[1], p[2] - edge.midpoint[2]) <= 1)
      const material = new THREE.LineBasicMaterial({ color: picked ? PICKED_COLOR : EDGE_COLOR, linewidth: 1 })
      const l = new THREE.Line(geometry, material)
      l.userData = { edge, base: EDGE_COLOR, picked }
      s.shapes.add(l)
      s.edges.push(l)
    }

    const box = new THREE.Box3().setFromObject(s.shapes)
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    const radius = Math.max(size.x, size.y, size.z) || 1
    s.group.userData.size = radius
    if (!s.fitted) {
      s.rig.fit(box)
      // 늦게 뜬 뷰어는 먼저 뜬 것의 자세로 시작한다 — 나란히 놓였는데 처음부터 어긋나면 안 된다.
      const pose = syncRef.current?.last()
      if (pose) {
        s.rig.camera.position.fromArray(pose.position)
        s.rig.camera.up.fromArray(pose.up)
        s.rig.controls.target.fromArray(pose.target)
        s.rig.controls.update()
      }
      const grid = new THREE.GridHelper(radius * 4, 20, 0x888888, 0xcccccc)
      grid.position.set(center.x, box.min.y, center.z)
      s.scene.add(grid)
      s.fitted = true
    }
  }, [mesh, highlightEdgesNear, partColors])

  // 고른 구성품만 또렷하게 — 재질만 만지고 메시는 그대로 둔다(고를 때마다 다시 만들면 느리다).
  useEffect(() => {
    const s = state.current
    if (!s) return
    for (const m of s.faces) {
      const face = m.userData.face as MeshFace
      const dim = !!emphasis && face.part !== emphasis
      const material = m.material as THREE.MeshStandardMaterial
      material.transparent = dim
      material.opacity = dim ? 0.25 : 1
      material.depthWrite = !dim
      material.needsUpdate = true
    }
    for (const l of s.edges) {
      const edge = l.userData.edge as MeshEdge
      const dim = !!emphasis && edge.part !== emphasis
      const material = l.material as THREE.LineBasicMaterial
      material.transparent = dim
      material.opacity = dim ? 0.2 : 1
      material.needsUpdate = true
    }
  }, [mesh, emphasis])

  // 모드를 끄면 손이 올라가 있던 표시도 함께 걷는다 — 다음에 마우스를 움직일 때까지 남으면
  // 「아직 측정 중인가?」 싶다.
  useEffect(() => {
    const s = state.current
    if (!s || mode !== 'none') return
    for (const stale of [s.hoverLine, s.hoverDot]) {
      if (!stale) continue
      s.group.remove(stale)
      stale.geometry.dispose()
      ;(stale.material as THREE.Material).dispose()
    }
    s.hoverLine = null
    s.hoverDot = null
  }, [mode])

  // 잡을 점 — 「점」 을 켠 측정에서만 띄운다. 늘 띄우면 형상이 점으로 덮인다.
  const wantsDots = mode === 'measure' && (measureKinds?.point ?? true)
  useEffect(() => {
    const s = state.current
    if (!s) return
    const old = s.dots.object
    if (old) {
      s.group.remove(old)
      old.geometry.dispose()
      ;(old.material as THREE.Material).dispose()
      s.dots = { object: null, at: [], kinds: [] }
    }
    if (!mesh || !wantsDots) return
    const gathered = gatherDots(mesh)
    if (gathered.at.length === 0) return
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(gathered.at.flat(), 3))
    const base = Math.max(0.02, (s.group.userData.size as number) / 900)
    geometry.setAttribute('size', new THREE.Float32BufferAttribute(Array.from({ length: gathered.at.length }, () => base), 1))
    const points = new THREE.Points(geometry, dotMaterial(dotTexture(), DOT_COLOR))
    points.userData.base = base
    points.renderOrder = 8
    s.group.add(points)
    s.dots = { object: points, at: gathered.at, kinds: gathered.kinds }
  }, [mesh, wantsDots])

  // 측정 표시 — 점 · 치수선 · **값 글자** · 고른 엣지/면 강조. 무엇을 어디서 쟀는지 3D 에서 보인다.
  useEffect(() => {
    const s = state.current
    if (!s) return
    s.marks.clear()
    if (!measureMarks) return
    const size = (s.group.userData.size as number) || 50
    const box = new THREE.Box3().setFromObject(s.shapes)
    const center = box.isEmpty() ? new THREE.Vector3() : box.getCenter(new THREE.Vector3())
    const toneColor = (tone?: 'live' | 'kept') => (tone === 'kept' ? KEPT_COLOR : MEASURE_COLOR)

    // 고른 점 — 흰 테를 두른 구. 잡을 점(파랑)과 한눈에 구별된다.
    const r = size / 90
    for (const p of measureMarks.points) {
      const halo = new THREE.Mesh(
        new THREE.SphereGeometry(r * 1.7, 12, 12),
        new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false }),
      )
      halo.position.set(p[0], p[1], p[2])
      halo.renderOrder = 6
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(r, 14, 14),
        new THREE.MeshBasicMaterial({ color: MEASURE_COLOR, depthTest: false }),
      )
      dot.position.copy(halo.position)
      dot.renderOrder = 7
      s.marks.add(halo, dot)
    }
    // 고른 선 — 굵게 덧그린다(1px 선은 골라도 티가 안 난다).
    for (const edge of measureMarks.edges) {
      s.marks.add(fatLine(edge.points, toneColor(edge.tone), edge.tone === 'kept' ? 3 : 6, s.resolution))
    }
    // 고른 면 — 반투명으로 덮고 테두리도 함께.
    for (const face of measureMarks.faces) {
      const g = new THREE.BufferGeometry()
      g.setAttribute('position', new THREE.Float32BufferAttribute(face.vertices, 3))
      g.setIndex(face.triangles)
      g.computeVertexNormals()
      const m = new THREE.Mesh(
        g,
        new THREE.MeshBasicMaterial({
          color: toneColor(face.tone),
          transparent: true,
          opacity: face.tone === 'kept' ? 0.2 : 0.35,
          side: THREE.DoubleSide,
          depthWrite: false,
        }),
      )
      m.renderOrder = 4
      s.marks.add(m)
    }
    // 잰 자리 — 자로 그린다.
    for (const seg of measureMarks.segments) {
      const from = new THREE.Vector3(...(seg.from as [number, number, number]))
      const to = new THREE.Vector3(...(seg.to as [number, number, number]))
      const drawn = dimensionLine(from, to, center, size, toneColor(seg.tone), s.resolution)
      s.marks.add(drawn.group)
      if (seg.text) {
        // 값은 자 **위**에 — 잰 자리 한가운데에 두면 형상에 파묻힌다.
        const sprite = makeLabel(seg.text, seg.tone === 'kept' ? 'entity' : 'distance')
        const height = size / 13
        sprite.scale.set(height * (sprite.userData.aspect as number), height, 1)
        sprite.position.copy(drawn.labelAt)
        s.marks.add(sprite)
      }
    }
    for (const label of measureMarks.labels) {
      const sprite = makeLabel(label.text, label.tone)
      const height = size / 14
      sprite.scale.set(height * (sprite.userData.aspect as number), height, 1)
      sprite.position.set(label.at[0], label.at[1], label.at[2] + height * 0.7)
      s.marks.add(sprite)
    }
  }, [measureMarks])

  return (
    <div className={`relative ${className ?? 'h-[480px] w-full rounded-md border'}`}>
      <div ref={mount} className="h-full w-full" />
      <ViewerToolbar rig={rigOf} />
    </div>
  )
}
