/**
 * 3D 화면의 조명 — **어느 방향에서 봐도 보이게**(2026-11-17).
 *
 * 그 전에는 하늘 · 땅 조명(땅 쪽이 어두운 회색) + 장면에 박힌 해 하나(+X +Y +Z 쪽)였다. 그래서 아래에서
 * 올려다보면 바닥이 거의 검었고(밝기 13/255 — 실측), 옆으로 돌리면 해를 등진 면이 어두웠다(52).
 *
 * 이제 **머리 조명**이 카메라를 따라간다 — 보는 쪽에서 약간 위 · 오른쪽으로 비춰, 보이는 면은 늘 밝고 면마다
 * 명암이 남아 모양이 읽힌다. 하늘 · 땅 조명은 땅 쪽을 밝혀 뒤쪽 면도 묻히지 않게 바탕만 깐다.
 *
 * 세 화면(작업 · 조건의 `PickViewer`, 결과의 `ModelViewer`, DOE 의 `GridViewer`)이 이것을 함께 쓴다.
 * 그리기 전마다 `follow` 를 부른다.
 */

import * as THREE from 'three'

/** 머리 조명이 카메라에서 비켜 서는 쪽(카메라 좌표 — 오른쪽 · 위) — 거리에 곱한다. */
const HEAD_OFFSET = new THREE.Vector3(0.25, 0.4, 0)

export interface Lighting {
  /** 카메라를 따라 머리 조명을 옮긴다 — 그리기 전마다. `target` 은 보는 중심. */
  follow: (camera: THREE.Camera, target: THREE.Vector3) => void
}

export function addLighting(scene: THREE.Scene): Lighting {
  scene.add(new THREE.HemisphereLight(0xffffff, 0xd4d4d8, 1.5))
  const head = new THREE.DirectionalLight(0xffffff, 1.6)
  scene.add(head)
  scene.add(head.target)
  const offset = new THREE.Vector3()
  return {
    follow(camera, target) {
      const distance = Math.max(camera.position.distanceTo(target), 1)
      offset.copy(HEAD_OFFSET).applyQuaternion(camera.quaternion).multiplyScalar(distance)
      head.position.copy(camera.position).add(offset)
      head.target.position.copy(target)
    },
  }
}
