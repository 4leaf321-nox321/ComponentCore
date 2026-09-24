/**
 * 3D 뷰어 — glTF 를 three.js 로 그린다.
 *
 * **쓰는 화면에서 `lazy()` 로 받는다.** three 한 덩어리가 크고, 지그를 안 보는 화면(로그인 ·
 * 계정)까지 매번 그만큼을 받을 이유가 없다.
 *
 * 제품과 지그를 **다른 파일 · 다른 색**으로 받는다 — 한 파일로 합치면 무엇이 제품이고 무엇이
 * 지그인지 화면에서 구별할 수 없다.
 */

import { useCallback, useEffect, useRef } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import { CameraRig } from '@/shared/viewer/cameraRig'
import { ViewerToolbar } from '@/shared/viewer/ViewerToolbar'
import { mountCanvas } from '@/shared/viewer/canvas'

export interface ViewerModel {
  /** Blob URL 또는 내려받을 수 있는 주소. */
  url: string
  color: string
  opacity?: number
}

export function ModelViewer({ models, className }: { models: ViewerModel[]; className?: string }) {
  const mount = useRef<HTMLDivElement | null>(null)
  const rigRef = useRef<CameraRig | null>(null)
  const rigOf = useCallback(() => rigRef.current, [])

  useEffect(() => {
    const container = mount.current
    if (!container) return

    const scene = new THREE.Scene()
    const dark = document.documentElement.classList.contains('dark')
    scene.background = new THREE.Color(dark ? '#18181b' : '#f4f4f5')

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    mountCanvas(container, renderer.domElement)

    scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2))
    const sun = new THREE.DirectionalLight(0xffffff, 1.5)
    sun.position.set(1, 2, 3)
    scene.add(sun)

    const rig = new CameraRig(renderer.domElement)
    rigRef.current = rig
    const controls = rig.controls

    const loader = new GLTFLoader()
    const group = new THREE.Group()
    // glTF 는 Y-up, CAD 는 Z-up — 판이 바닥에 눕도록 돌린다.
    group.rotation.x = -Math.PI / 2
    scene.add(group)

    let disposed = false
    let pending = models.length

    function fit() {
      const box = new THREE.Box3().setFromObject(group)
      if (box.isEmpty()) return
      const size = box.getSize(new THREE.Vector3())
      const center = box.getCenter(new THREE.Vector3())
      const radius = Math.max(size.x, size.y, size.z) || 1
      rig.fit(box)
      const grid = new THREE.GridHelper(radius * 4, 20, 0x888888, 0xcccccc)
      grid.position.set(center.x, box.min.y, center.z)
      scene.add(grid)
    }

    for (const model of models) {
      loader.load(
        model.url,
        (gltf) => {
          if (disposed) return
          const material = new THREE.MeshStandardMaterial({
            color: model.color,
            metalness: 0.1,
            roughness: 0.6,
            transparent: (model.opacity ?? 1) < 1,
            opacity: model.opacity ?? 1,
          })
          gltf.scene.traverse((node) => {
            if ((node as THREE.Mesh).isMesh) {
              const mesh = node as THREE.Mesh
              mesh.material = material
              const edges = new THREE.LineSegments(
                new THREE.EdgesGeometry(mesh.geometry, 30),
                new THREE.LineBasicMaterial({ color: 0x1f2937, transparent: true, opacity: 0.35 }),
              )
              mesh.add(edges)
            }
          })
          group.add(gltf.scene)
          if (--pending === 0) fit()
        },
        undefined,
        (failure) => {
          console.error('glTF 를 읽지 못했습니다', model.url, failure)
          if (--pending === 0) fit()
        },
      )
    }

    function resize() {
      const { clientWidth: w, clientHeight: h } = container!
      renderer.setSize(w, h, false)
      rig.setAspect(w / Math.max(h, 1))
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(container)

    let frame = 0
    function animate() {
      frame = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, rig.camera)
    }
    animate()

    return () => {
      disposed = true
      cancelAnimationFrame(frame)
      observer.disconnect()
      rig.dispose()
      rigRef.current = null
      renderer.dispose()
      container.removeChild(renderer.domElement)
    }
  }, [models])

  return (
    <div className={`relative ${className ?? 'h-[480px] w-full rounded-md border'}`}>
      <div ref={mount} className="relative h-full w-full" />
      <ViewerToolbar rig={rigOf} />
    </div>
  )
}

export default ModelViewer
