/**
 * 격자 뷰어 — 형상 여럿을 **한 WebGL 문맥**으로 칸마다 그린다(나란히 견주기).
 *
 * 뷰어를 칸마다 하나씩 띄우면 브라우저의 WebGL 문맥 한계(열 몇 개)에 곧 닿는다. 여기서는
 * 캔버스 하나를 격자 뒤에 깔고, 칸마다 가위(scissor)로 잘라 그 칸의 장면을 그린다 — three.js
 * 의 「multiple elements」 방식. 카메라는 **하나**라 돌리면 모두 같이 돈다(나란히의 뜻이 그것).
 * 칸은 정사각형이고, 열 수는 호출부가 정한다.
 */

import { useCallback, useEffect, useRef } from 'react'
import * as THREE from 'three'

import { CameraRig } from '@/shared/viewer/cameraRig'
import type { MeshData } from '@/shared/viewer/PickViewer'
import { ViewerToolbar } from '@/shared/viewer/ViewerToolbar'
import { mountCanvas } from '@/shared/viewer/canvas'

export interface GridItem {
  key: string
  label: React.ReactNode
  mesh: MeshData
  color?: number
  /** 이 칸을 도드라지게 — 목록에서 고른 점. */
  highlight?: boolean
}

const FACE_COLOR = 0x3b82f6
const EDGE_COLOR = 0x1f2937

/** 형상 하나를 장면 하나로 — 면은 한 지오메트리로 합쳐 그리기 한 번, 엣지도 한 번. */
function sceneOf(mesh: MeshData, color: number, background: THREE.Color): THREE.Scene {
  const scene = new THREE.Scene()
  scene.background = background
  scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2))
  const sun = new THREE.DirectionalLight(0xffffff, 1.5)
  sun.position.set(1, 2, 3)
  scene.add(sun)
  const group = new THREE.Group()
  group.rotation.x = -Math.PI / 2 // CAD Z-up → three Y-up
  scene.add(group)

  const positions: number[] = []
  const indices: number[] = []
  for (const face of mesh.faces) {
    const base = positions.length / 3
    positions.push(...face.vertices)
    for (const i of face.triangles) indices.push(base + i)
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex(indices)
  geometry.computeVertexNormals()
  group.add(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color, metalness: 0.1, roughness: 0.6, side: THREE.DoubleSide })))

  const lines: number[] = []
  for (const edge of mesh.edges) {
    const p = edge.points
    for (let i = 0; i + 5 < p.length; i += 3) lines.push(p[i], p[i + 1], p[i + 2], p[i + 3], p[i + 4], p[i + 5])
  }
  const lineGeometry = new THREE.BufferGeometry()
  lineGeometry.setAttribute('position', new THREE.Float32BufferAttribute(lines, 3))
  group.add(new THREE.LineSegments(lineGeometry, new THREE.LineBasicMaterial({ color: EDGE_COLOR })))
  return scene
}

function disposeScene(scene: THREE.Scene) {
  scene.traverse((one) => {
    if (one instanceof THREE.Mesh || one instanceof THREE.LineSegments) {
      one.geometry.dispose()
      ;(one.material as THREE.Material).dispose()
    }
  })
}

export function GridViewer({ items, columns, cellClass, className }: { items: GridItem[]; columns: number; cellClass?: string; className?: string }) {
  const mount = useRef<HTMLDivElement | null>(null)
  const cells = useRef<Map<string, HTMLDivElement>>(new Map())
  const state = useRef<{
    renderer: THREE.WebGLRenderer
    rig: CameraRig
    scenes: Map<string, THREE.Scene>
    fitted: boolean
  } | null>(null)
  const itemsRef = useRef(items)
  itemsRef.current = items
  const rigOf = useCallback(() => state.current?.rig ?? null, [])

  // 한 번만: 렌더러 · 카메라 · 컨트롤 · 그리기 루프.
  useEffect(() => {
    const container = mount.current
    if (!container) return
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setScissorTest(true)
    // 캔버스는 React 자식들 **뒤에** 붙는다 — 그대로 두면 이름표 · 도구줄을 덮는다.
    renderer.domElement.style.zIndex = '0'
    mountCanvas(container, renderer.domElement)
    const rig = new CameraRig(renderer.domElement)
    const controls = rig.controls
    state.current = { renderer, rig, scenes: new Map(), fitted: false }

    function resize() {
      renderer.setSize(container!.clientWidth, container!.clientHeight, false)
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(container)

    let frame = 0
    const animate = () => {
      frame = requestAnimationFrame(animate)
      controls.update()
      const s = state.current
      if (!s) return
      const outer = container!.getBoundingClientRect()
      const height = renderer.domElement.clientHeight
      for (const item of itemsRef.current) {
        const scene = s.scenes.get(item.key)
        const cell = cells.current.get(item.key)
        if (!scene || !cell) continue
        const rect = cell.getBoundingClientRect()
        const w = Math.max(1, Math.floor(rect.width))
        const h = Math.max(1, Math.floor(rect.height))
        const left = Math.floor(rect.left - outer.left)
        const bottom = Math.floor(height - (rect.bottom - outer.top))
        renderer.setViewport(left, bottom, w, h)
        renderer.setScissor(left, bottom, w, h)
        rig.setAspect(w / h)
        renderer.render(scene, rig.camera)
      }
    }
    animate()
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      rig.dispose()
      for (const scene of state.current?.scenes.values() ?? []) disposeScene(scene)
      renderer.dispose()
      container.removeChild(renderer.domElement)
      state.current = null
    }
  }, [])

  // 도드라진 칸이 바뀌면 거기로 스크롤한다 — 목록에서 고른 것을 아래에서 찾아 내려가지 않게.
  const highlighted = items.find((one) => one.highlight)?.key ?? null
  useEffect(() => {
    if (!highlighted) return
    const cell = cells.current.get(highlighted)
    cell?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [highlighted])

  // 형상이 바뀌면 장면을 맞춘다 — 남은 것은 두고, 간 것은 버리고, 온 것은 만든다.
  useEffect(() => {
    const s = state.current
    if (!s) return
    const dark = document.documentElement.classList.contains('dark')
    const background = new THREE.Color(dark ? '#18181b' : '#f4f4f5')
    const keep = new Set(items.map((one) => one.key))
    for (const [key, scene] of s.scenes) {
      if (!keep.has(key)) {
        disposeScene(scene)
        s.scenes.delete(key)
      }
    }
    for (const item of items) {
      if (!s.scenes.has(item.key)) s.scenes.set(item.key, sceneOf(item.mesh, item.color ?? FACE_COLOR, background))
    }
    if (!s.fitted && items.length > 0) {
      // 모두를 담는 상자로 카메라를 한 번 맞춘다 — 같은 도면의 변형이라 크기가 비슷하다.
      const box = new THREE.Box3()
      for (const item of items) {
        const [x0, y0, z0] = item.mesh.bbox.min
        const [x1, y1, z1] = item.mesh.bbox.max
        // CAD (x, y, z) → three (x, z, -y)
        box.expandByPoint(new THREE.Vector3(x0, z0, -y1))
        box.expandByPoint(new THREE.Vector3(x1, z1, -y0))
      }
      s.rig.fit(box)
      s.fitted = true
    }
  }, [items])

  return (
    <div className={`flex flex-col ${className ?? ''}`}>
      {/* 도구줄은 격자 위 제 줄에 — 칸 이름표(왼쪽 위)와 겹치지 않게. */}
      <ViewerToolbar rig={rigOf} inline />
      <div ref={mount} className="relative min-h-0 flex-1">
      {/* 격자는 캔버스 위에 — 칸의 자리만 잡고 이름표를 단다. 포인터는 캔버스로 흘려보낸다. */}
      <div className={`pointer-events-none relative z-10 grid gap-2 ${cellClass ? 'h-full' : ''}`} style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
        {items.map((item) => (
          <div
            key={item.key}
            ref={(el) => {
              if (el) cells.current.set(item.key, el)
              else cells.current.delete(item.key)
            }}
            className={`relative rounded-md border ${cellClass ?? 'aspect-square'} ${item.highlight ? 'border-primary ring-primary ring-2' : ''}`}
            aria-current={item.highlight ? 'true' : undefined}
          >
            <div className="pointer-events-auto absolute top-1 left-1 rounded bg-background/80 px-1.5 py-0.5 text-xs">{item.label}</div>
          </div>
        ))}
      </div>
      </div>
    </div>
  )
}
