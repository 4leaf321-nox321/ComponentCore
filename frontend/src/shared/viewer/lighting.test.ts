import * as THREE from 'three'

import { addLighting } from '@/shared/viewer/lighting'

// 조명(2026-11-17) — 머리 조명이 카메라를 따라가, 어느 방향에서 봐도 보이는 면이 밝다.

test('머리 조명은 카메라 쪽에서 보는 중심을 비춘다 — 아래에서 올려다봐도', () => {
  const scene = new THREE.Scene()
  const lighting = addLighting(scene)
  const head = scene.children.find((one): one is THREE.DirectionalLight => one instanceof THREE.DirectionalLight)!
  const target = new THREE.Vector3(0, 0, 0)
  for (const from of [new THREE.Vector3(0, -100, 0.01), new THREE.Vector3(100, 20, 0), new THREE.Vector3(-50, 50, -80)]) {
    const camera = new THREE.PerspectiveCamera()
    camera.position.copy(from)
    camera.lookAt(target)
    lighting.follow(camera, target)
    expect(head.target.position.toArray()).toEqual([0, 0, 0])
    // 빛이 오는 쪽이 카메라 쪽과 거의 같다(어긋난 각이 작다) — 보이는 면이 빛을 받는다.
    const toLight = head.position.clone().sub(target).normalize()
    const toCamera = from.clone().sub(target).normalize()
    expect(toLight.dot(toCamera)).toBeGreaterThan(0.85)
  }
  // 땅 쪽 바탕빛도 밝은 회색 — 뒤쪽 면이 검게 묻히지 않는다.
  const hemi = scene.children.find((one): one is THREE.HemisphereLight => one instanceof THREE.HemisphereLight)!
  expect(hemi.groundColor.getHSL({ h: 0, s: 0, l: 0 }, THREE.SRGBColorSpace).l).toBeGreaterThan(0.7)
})
