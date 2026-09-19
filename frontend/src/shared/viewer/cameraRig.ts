/**
 * 카메라 한 벌 — 투시(perspective)와 정사영(orthographic)을 바꿔 가며 같은 자리를 본다.
 *
 * 모든 CAD 뷰어가 이것을 쓴다: 표준 뷰(등각 · 정면 · 윗면 · 우측)와 투시/정사영 전환이 어느
 * 화면에서나 같아야 한다. OrbitControls 는 카메라를 바꿔 끼워도 같은 목표점을 돈다.
 *
 * 좌표: CAD 는 Z-up, three 는 Y-up — 뷰어가 group 을 -90° 눕혀 두므로, CAD 방향 (x, y, z) 는
 * three 의 (x, z, -y) 다. `look` 은 CAD 방향으로 받는다.
 */

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

export type Projection = 'perspective' | 'orthographic'

export interface StandardView {
  key: string
  label: string
  /** CAD 좌표계의 시선 방향(카메라가 형상에서 이쪽으로 물러난다). */
  dir: [number, number, number]
}

export const STANDARD_VIEWS: StandardView[] = [
  { key: 'iso', label: '등각', dir: [1, -1, 0.8] },
  { key: 'front', label: '정면', dir: [0, -1, 0] },
  { key: 'top', label: '윗면', dir: [0, 0, 1] },
  { key: 'right', label: '우측', dir: [1, 0, 0] },
]

const FOV = 45

export class CameraRig {
  readonly perspective = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100_000)
  readonly orthographic = new THREE.OrthographicCamera(-1, 1, 1, -1, -100_000, 100_000)
  readonly controls: OrbitControls
  projection: Projection = 'perspective'
  private aspect = 1
  /** 형상을 담는 반지름 — 정사영 화면 크기와 near/far 의 기준. fit 이 정한다. */
  private radius = 1

  constructor(domElement: HTMLElement) {
    this.controls = new OrbitControls(this.perspective, domElement)
    this.controls.enableDamping = true
  }

  get camera(): THREE.Camera {
    return this.projection === 'perspective' ? this.perspective : this.orthographic
  }

  get target(): THREE.Vector3 {
    return this.controls.target
  }

  setAspect(aspect: number): void {
    this.aspect = aspect || 1
    this.perspective.aspect = this.aspect
    this.perspective.updateProjectionMatrix()
    this.updateOrthoFrustum()
  }

  /** 형상 전체가 보이게 — 처음 한 번, 또는 「맞춤」. */
  fit(box: THREE.Box3): void {
    if (box.isEmpty()) return
    const center = box.getCenter(new THREE.Vector3())
    this.radius = Math.max(...box.getSize(new THREE.Vector3()).toArray()) || 1
    const r = this.radius
    this.perspective.position.set(center.x + r * 1.2, center.y + r * 0.9, center.z + r * 1.4)
    this.perspective.near = r / 100
    this.perspective.far = r * 100
    this.perspective.updateProjectionMatrix()
    this.controls.target.copy(center)
    this.orthographic.position.copy(this.perspective.position)
    this.orthographic.zoom = 1
    this.updateOrthoFrustum()
    this.controls.update()
  }

  /** 표준 뷰 — 목표점은 두고 그 방향에서 본다. 거리는 지금 것을 지킨다. */
  look(dir: [number, number, number]): void {
    const world = new THREE.Vector3(dir[0], dir[2], -dir[1]).normalize()
    const center = this.controls.target.clone()
    const distance = Math.max(this.camera.position.distanceTo(center), this.radius * 0.5)
    const position = center.clone().add(world.multiplyScalar(distance))
    this.perspective.position.copy(position)
    this.orthographic.position.copy(position)
    this.perspective.up.set(0, 1, 0)
    this.orthographic.up.set(0, 1, 0)
    this.controls.update()
  }

  /** 투시 ↔ 정사영 — 같은 자리 · 같은 크기로 보이게 옮긴다. */
  setProjection(next: Projection): void {
    if (next === this.projection) return
    const center = this.controls.target
    if (next === 'orthographic') {
      // 투시에서 보이던 세로 크기 = 2 · 거리 · tan(fov/2) — 그만큼을 정사영의 화면 높이로.
      const distance = this.perspective.position.distanceTo(center)
      const halfHeight = distance * Math.tan(THREE.MathUtils.degToRad(FOV / 2))
      this.orthographic.position.copy(this.perspective.position)
      this.orthographic.up.copy(this.perspective.up)
      this.orthographic.zoom = this.radius / Math.max(halfHeight, 1e-6)
      this.updateOrthoFrustum()
      this.controls.object = this.orthographic
    } else {
      // 정사영의 화면 높이(반지름/zoom)가 같은 크기로 보이는 거리로 물러선다.
      const halfHeight = this.radius / Math.max(this.orthographic.zoom, 1e-6)
      const distance = halfHeight / Math.tan(THREE.MathUtils.degToRad(FOV / 2))
      const direction = this.orthographic.position.clone().sub(center).normalize()
      this.perspective.position.copy(center.clone().add(direction.multiplyScalar(distance)))
      this.perspective.up.copy(this.orthographic.up)
      this.controls.object = this.perspective
    }
    this.projection = next
    this.controls.update()
  }

  /** 정사영 화면: 세로 반지름, 가로는 비율만큼. zoom 이 확대 · 축소를 맡는다. */
  private updateOrthoFrustum(): void {
    const r = this.radius
    this.orthographic.left = -r * this.aspect
    this.orthographic.right = r * this.aspect
    this.orthographic.top = r
    this.orthographic.bottom = -r
    this.orthographic.near = -r * 100
    this.orthographic.far = r * 100
    this.orthographic.updateProjectionMatrix()
  }

  dispose(): void {
    this.controls.dispose()
  }
}
