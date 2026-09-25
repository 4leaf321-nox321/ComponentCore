import * as THREE from 'three'

import { CameraRig } from '@/shared/viewer/cameraRig'

function rigWithBox() {
  const rig = new CameraRig(document.createElement('div'))
  rig.setAspect(2)
  rig.fit(new THREE.Box3(new THREE.Vector3(-50, 0, -30), new THREE.Vector3(50, 20, 30)))
  return rig
}

test('투시 ↔ 정사영을 오가도 같은 자리를 같은 크기로 본다', () => {
  const rig = rigWithBox()
  const before = rig.perspective.position.clone()
  const distance = before.distanceTo(rig.target)

  rig.setProjection('orthographic')
  expect(rig.camera).toBe(rig.orthographic)
  rig.orthographic.position.toArray().forEach((v, i) => expect(v).toBeCloseTo(before.toArray()[i], 3))
  // 정사영 화면 높이(반지름/zoom) = 투시에서 보이던 높이(거리 · tan 22.5°).
  const halfHeight = 100 / rig.orthographic.zoom
  expect(halfHeight).toBeCloseTo(distance * Math.tan((22.5 * Math.PI) / 180), 3)
  expect(rig.orthographic.right / rig.orthographic.top).toBeCloseTo(2, 3) // 가로세로 비율

  rig.setProjection('perspective')
  expect(rig.camera).toBe(rig.perspective)
  expect(rig.perspective.position.distanceTo(rig.target)).toBeCloseTo(distance, 2)
})

test('표준 뷰는 목표점을 두고 그 방향에서 본다 — CAD Z 가 three Y', () => {
  const rig = rigWithBox()
  const distance = rig.perspective.position.distanceTo(rig.target)
  rig.look([0, 0, 1]) // 윗면: CAD +Z 에서 내려다본다 → three +Y
  const offset = rig.perspective.position.clone().sub(rig.target)
  expect(offset.x).toBeCloseTo(0, 2)
  expect(offset.z).toBeCloseTo(0, 2)
  expect(offset.y).toBeCloseTo(distance, 2)
  rig.look([0, -1, 0]) // 정면: CAD -Y 에서 → three +Z
  const front = rig.perspective.position.clone().sub(rig.target)
  expect(front.z).toBeCloseTo(distance, 2)
})

test('**정사영이 기본**이고, 처음 맞출 때 투시로 보던 것과 같은 크기로 본다', () => {
  const rig = rigWithBox()
  expect(rig.projection).toBe('orthographic')
  expect(rig.camera).toBe(rig.orthographic)
  const distance = rig.orthographic.position.distanceTo(rig.target)
  expect(100 / rig.orthographic.zoom).toBeCloseTo(distance * Math.tan((22.5 * Math.PI) / 180), 3)
})
