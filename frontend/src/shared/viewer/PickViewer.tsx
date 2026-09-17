/**
 * 고를 수 있는 3D 뷰어 — 서버의 면 · 엣지 메시(`/cad/recipe/mesh`)를 그리고 누른 것을 알려 준다.
 *
 * glTF 뷰어(ModelViewer)와 다른 점: 면마다 Mesh 하나, 엣지마다 Line 하나라 레이캐스트로 무엇을
 * 눌렀는지 안다. 편집기 전용이다 — 결과 화면은 가벼운 glTF 를 쓴다.
 */

import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

export interface MeshFace {
  index: number
  kind: string
  center: number[]
  normal: number[]
  area: number
  vertices: number[]
  triangles: number[]
}

export interface MeshEdge {
  index: number
  kind: string
  midpoint: number[]
  length: number
  vertical: boolean
  points: number[]
}

export interface MeshData {
  bbox: { min: number[]; max: number[] }
  faces: MeshFace[]
  edges: MeshEdge[]
}

export type PickMode = 'none' | 'face' | 'edge'

export interface PickViewerProps {
  mesh: MeshData | null
  mode: PickMode
  /** 강조할 엣지의 중점들(필렛의 near) — 가까운 엣지가 노랗게 보인다. */
  highlightEdgesNear?: number[][]
  onPickFace?: (face: MeshFace) => void
  onPickEdge?: (edge: MeshEdge) => void
  className?: string
}

const FACE_COLOR = 0x3b82f6
const HOVER_COLOR = 0xf59e0b
const EDGE_COLOR = 0x1f2937
const PICKED_COLOR = 0xf59e0b

export default function PickViewer({ mesh, mode, highlightEdgesNear, onPickFace, onPickEdge, className }: PickViewerProps) {
  const mount = useRef<HTMLDivElement | null>(null)
  const state = useRef<{
    scene: THREE.Scene
    camera: THREE.PerspectiveCamera
    renderer: THREE.WebGLRenderer
    controls: OrbitControls
    group: THREE.Group
    faces: THREE.Mesh[]
    edges: THREE.Line[]
    fitted: boolean
  } | null>(null)
  const callbacks = useRef({ mode, onPickFace, onPickEdge })
  callbacks.current = { mode, onPickFace, onPickEdge }

  // 한 번만: 장면 · 카메라 · 렌더러.
  useEffect(() => {
    const container = mount.current
    if (!container) return
    const scene = new THREE.Scene()
    const dark = document.documentElement.classList.contains('dark')
    scene.background = new THREE.Color(dark ? '#18181b' : '#f4f4f5')
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100_000)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    container.appendChild(renderer.domElement)
    scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2))
    const sun = new THREE.DirectionalLight(0xffffff, 1.5)
    sun.position.set(1, 2, 3)
    scene.add(sun)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    const group = new THREE.Group()
    group.rotation.x = -Math.PI / 2 // CAD Z-up → three Y-up
    scene.add(group)
    state.current = { scene, camera, renderer, controls, group, faces: [], edges: [], fitted: false }

    function resize() {
      const { clientWidth: w, clientHeight: h } = container!
      renderer.setSize(w, h, false)
      camera.aspect = w / Math.max(h, 1)
      camera.updateProjectionMatrix()
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
      raycaster.setFromCamera(pointer, camera)
      const { mode: m } = callbacks.current
      if (m === 'face') return raycaster.intersectObjects(s.faces, false)[0] ?? null
      if (m === 'edge') {
        raycaster.params.Line = { threshold: Math.max(0.5, (s.group.userData.size as number) / 120) }
        return raycaster.intersectObjects(s.edges, false)[0] ?? null
      }
      return null
    }
    function setHover(object: THREE.Mesh | THREE.Line | null) {
      if (hovered === object) return
      if (hovered) {
        const mat = hovered.material as THREE.MeshStandardMaterial | THREE.LineBasicMaterial
        mat.color.set(hovered.userData.picked ? PICKED_COLOR : (hovered.userData.base as number))
      }
      hovered = object
      if (hovered) (hovered.material as THREE.MeshStandardMaterial | THREE.LineBasicMaterial).color.set(HOVER_COLOR)
      renderer.domElement.style.cursor = hovered ? 'pointer' : 'default'
    }
    const onDown = (e: PointerEvent) => {
      downAt = [e.clientX, e.clientY]
    }
    const onMove = (e: PointerEvent) => {
      if (callbacks.current.mode === 'none') return setHover(null)
      const hit = pick(e)
      setHover((hit?.object as THREE.Mesh | THREE.Line) ?? null)
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
    }
    renderer.domElement.addEventListener('pointerdown', onDown)
    renderer.domElement.addEventListener('pointermove', onMove)
    renderer.domElement.addEventListener('pointerup', onUp)

    let frame = 0
    const animate = () => {
      frame = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onDown)
      renderer.domElement.removeEventListener('pointermove', onMove)
      renderer.domElement.removeEventListener('pointerup', onUp)
      controls.dispose()
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
    s.group.clear()
    s.faces = []
    s.edges = []
    if (!mesh) return

    for (const face of mesh.faces) {
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(face.vertices, 3))
      geometry.setIndex(face.triangles)
      geometry.computeVertexNormals()
      const material = new THREE.MeshStandardMaterial({ color: FACE_COLOR, metalness: 0.1, roughness: 0.6, side: THREE.DoubleSide })
      const m = new THREE.Mesh(geometry, material)
      m.userData = { face, base: FACE_COLOR, picked: false }
      s.group.add(m)
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
      s.group.add(l)
      s.edges.push(l)
    }

    const box = new THREE.Box3().setFromObject(s.group)
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    const radius = Math.max(size.x, size.y, size.z) || 1
    s.group.userData.size = radius
    if (!s.fitted) {
      s.camera.position.set(center.x + radius * 1.2, center.y + radius * 0.9, center.z + radius * 1.4)
      s.camera.near = radius / 100
      s.camera.far = radius * 100
      s.camera.updateProjectionMatrix()
      s.controls.target.copy(center)
      s.controls.update()
      const grid = new THREE.GridHelper(radius * 4, 20, 0x888888, 0xcccccc)
      grid.position.set(center.x, box.min.y, center.z)
      s.scene.add(grid)
      s.fitted = true
    }
  }, [mesh, highlightEdgesNear])

  return <div ref={mount} className={className ?? 'h-[480px] w-full rounded-md border'} />
}
