/** 모든 CAD 뷰어의 오른쪽 위 — 표준 뷰(등각 · 정면 · 윗면 · 우측)와 투시/정사영 전환. */

import { useState } from 'react'

import { STANDARD_VIEWS } from '@/shared/viewer/cameraRig'
import type { CameraRig, Projection } from '@/shared/viewer/cameraRig'

export function ViewerToolbar({ rig, inline = false }: { rig: () => CameraRig | null; inline?: boolean }) {
  // 카메라와 같이 **정사영에서 시작**한다(cameraRig) — 글자가 실제와 어긋나면 누를 때마다 헷갈린다.
  const [projection, setProjection] = useState<Projection>('orthographic')
  const button = 'bg-background/80 hover:bg-accent rounded border px-2 py-1 text-[11px] shadow-sm'
  // 뷰어 위에 띄우거나(absolute), 칸 이름표와 겹칠 수 있는 격자에서는 제 줄에(inline).
  return (
    <div className={inline ? 'mb-1 flex justify-end gap-1' : 'absolute top-2 right-2 z-10 flex gap-1'}>
      {STANDARD_VIEWS.map((view) => (
        <button key={view.key} type="button" onClick={() => rig()?.look(view.dir)} className={button} title={`${view.label} 뷰`}>
          {view.label}
        </button>
      ))}
      <button
        type="button"
        className={`${button} ml-1`}
        title={projection === 'perspective' ? '투시 — 멀수록 작게. 누르면 정사영(평행 투영)' : '정사영 — 치수를 견주기 좋다. 누르면 투시'}
        aria-pressed={projection === 'orthographic'}
        onClick={() => {
          const next: Projection = projection === 'perspective' ? 'orthographic' : 'perspective'
          rig()?.setProjection(next)
          setProjection(next)
        }}
      >
        {projection === 'perspective' ? '투시' : '정사영'}
      </button>
    </div>
  )
}
