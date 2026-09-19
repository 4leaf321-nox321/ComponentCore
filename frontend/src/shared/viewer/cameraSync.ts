/**
 * 뷰어 여럿의 카메라를 맞춘다 — 하나를 돌리면 나머지가 따라 돈다(나란히 견줄 때).
 *
 * 뷰어는 자기 카메라가 움직일 때 `publish` 하고, 남의 것이 오면 그대로 놓는다. 되받아 보내지
 * 않게 보낸 쪽 id 를 함께 든다. 상태 없이 순수 pub/sub 이라 어느 화면에서든 만들어 넘긴다.
 */

export interface CameraPose {
  position: [number, number, number]
  target: [number, number, number]
  up: [number, number, number]
}

export interface CameraSync {
  publish: (from: string, pose: CameraPose) => void
  subscribe: (id: string, onPose: (pose: CameraPose) => void) => () => void
  /** 마지막 자세 — 늦게 뜬 뷰어가 처음부터 맞춰 서게. */
  last: () => CameraPose | null
}

export function createCameraSync(): CameraSync {
  const listeners = new Map<string, (pose: CameraPose) => void>()
  let last: CameraPose | null = null
  return {
    publish(from, pose) {
      last = pose
      for (const [id, onPose] of listeners) if (id !== from) onPose(pose)
    },
    subscribe(id, onPose) {
      listeners.set(id, onPose)
      return () => {
        listeners.delete(id)
      }
    },
    last: () => last,
  }
}
