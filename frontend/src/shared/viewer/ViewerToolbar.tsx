/** 모든 CAD 뷰어의 오른쪽 위 — 표준 뷰(등각 · 정면 · 윗면 · 우측)와 투시/정사영 전환. */

import { useState } from 'react'

import { STANDARD_VIEWS } from '@/shared/viewer/cameraRig'
import type { CameraRig, Projection } from '@/shared/viewer/cameraRig'

export function ViewerToolbar({ rig }: { rig: () => CameraRig | null }) {
  const [projection, setProjection] = useState<Projection>('perspective')
  const button = 'bg-background/80 hover:bg-accent rounded border px-2 py-1 text-[11px] shadow-sm'
  return (
    <div className="absolute top-2 right-2 flex gap-1">
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
