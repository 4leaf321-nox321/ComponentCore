import * as THREE from 'three'

import { keptHit, sectionPlanes } from '@/shared/viewer/PickViewer'

/** 뷰어처럼 — CAD 의 Z 를 위로 세우려 X 축으로 -90° 돌린 묶음. */
function cadGroup(): THREE.Group {
  const group = new THREE.Group()
  group.rotation.x = -Math.PI / 2
  return group
}

/** CAD 좌표의 점 → 화면(world) 좌표 — 절단 평면은 world 에서 잰다. */
function world(group: THREE.Group, p: [number, number, number]): THREE.Vector3 {
  group.updateMatrixWorld(true)
  return new THREE.Vector3(...p).applyMatrix4(group.matrixWorld)
}

test('단면은 CAD 좌표의 자리보다 큰 쪽을 걷어 낸다 — 돌린 묶음을 거쳐도, 뒤집으면 반대쪽', () => {
  const group = cadGroup()
  const planes = sectionPlanes(group, { axis: 'z', at: 5 })
  expect(keptHit(planes, world(group, [0, 0, 3]))).toBe(true)
  expect(keptHit(planes, world(group, [0, 0, 7]))).toBe(false)
  const flipped = sectionPlanes(group, { axis: 'z', at: 5, flip: true })
  expect(keptHit(flipped, world(group, [0, 0, 3]))).toBe(false)
  expect(keptHit(flipped, world(group, [0, 0, 7]))).toBe(true)
  // X · Y 도 CAD 축 그대로다(돌림은 화면 쪽 일이다).
  const across = sectionPlanes(group, { axis: 'y', at: -2 })
  expect(keptHit(across, world(group, [0, -5, 9]))).toBe(true)
  expect(keptHit(across, world(group, [0, 1, 9]))).toBe(false)
})

test('단면이 없으면 평면도 없고 무엇이든 남는다', () => {
  expect(sectionPlanes(cadGroup(), null)).toEqual([])
  expect(keptHit([], new THREE.Vector3(1, 2, 3))).toBe(true)
})
