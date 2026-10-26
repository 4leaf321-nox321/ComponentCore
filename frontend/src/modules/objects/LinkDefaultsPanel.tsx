/**
 * CompCore 기본 관계 — 부품 · 지그에 SP 기준정보를 잇는 관계 종류 꾸러미(백엔드 `objects/link_defaults.py`).
 *
 * 이것이 있어야 부품 · 지그 화면의 「기준정보」 칸, 목록의 기준정보 거르개, DOE 폴더의 `ontology` 가 선다.
 * 설치마다 손으로 만들면 slug 와 말이 갈리고, 해석 쪽(SimEngBay)이 받는 이름도 갈린다. 만들 수 있는 것만
 * 만들고, 이미 있는 것(같은 slug · 같은 두 타입을 잇는 관계)은 건드리지 않는다.
 *
 * 다 있으면 한 줄로 접는다 — 관계 종류 화면의 주인은 아래 표다.
 */

import { useState } from 'react'

import { linkDefaultsApi } from '@/modules/objects/api'
import type { LinkDefault } from '@/modules/objects/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

const STATUS: Record<LinkDefault['status'], string> = {
  ready: '만들 수 있음',
  exists: '있음',
  missing: '출발 타입 없음',
}

export function LinkDefaultsPanel({ onChanged }: { onChanged: () => void }) {
  const [round, setRound] = useState(0)
  const found = useResource(() => linkDefaultsApi.list(), [round])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const rows = Array.isArray(found.data) ? found.data : []
  const ready = rows.filter((one) => one.status === 'ready')

  async function apply() {
    setBusy(true)
    setError(null)
    try {
      const out = await linkDefaultsApi.apply()
      setDone(out.created.length ? `만들었습니다: ${out.created.join(', ')}` : '만들 것이 없었습니다.')
      setRound((n) => n + 1)
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  if (found.error) return <ErrorNotice error={found.error} />
  if (rows.length === 0) return null
  if (ready.length === 0 && rows.every((one) => one.status === 'exists') && !done) {
    return (
      <p className="text-muted-foreground text-xs">
        CompCore 기본 관계({rows.map((one) => `「${one.inverse_label}」`).join(' · ')})가 모두 있습니다.
      </p>
    )
  }

  return (
    <section className="space-y-2 rounded-md border p-3" aria-labelledby="link-defaults-title">
      <div className="flex items-center gap-2">
        <h2 id="link-defaults-title" className="text-sm font-semibold">
          CompCore 기본 관계
        </h2>
        <Button size="sm" onClick={() => void apply()} disabled={busy || ready.length === 0}>
          {ready.length}개 만들기
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">
        부품 · 지그에 SP 기준정보를 잇는 관계입니다. 이것이 있어야 부품 · 지그 화면의 「기준정보」 칸과 목록의
        기준정보 거르개가 생기고, DOE 폴더에 적용 모델이 실립니다. 이미 있는 것은 건드리지 않습니다.
      </p>
      {done && <p className="text-sm">{done}</p>}
      <ErrorNotice error={error} />
      <ul className="space-y-1 text-sm">
        {rows.map((one) => (
          <li key={one.slug} className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">「{one.inverse_label}」</span>
            <span className="text-muted-foreground text-xs">
              {one.source_label || one.source_type} → {one.target_label} · {one.slug}
            </span>
            <span className="rounded border px-1.5 text-xs">{STATUS[one.status]}</span>
            {one.note && <span className="text-muted-foreground text-xs">{one.note}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}
