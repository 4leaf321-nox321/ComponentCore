/**
 * **준비 점검 패널** — 흩어진 ⚠ 를 한 자리에(`readiness`). 줄을 누르면 고칠 자리를 연다(트리의 파트 · 물성 · 선택
 * 그룹, 또는 조건 창). 접어 둘 수 있고, 경고가 없으면 한 줄만 보인다.
 */

import { ChevronDownIcon, ChevronRightIcon, ClipboardCheck } from 'lucide-react'
import { useState } from 'react'

import type { ReadinessItem, ReadinessOpen } from '@/modules/conditions/readiness'

export function ReadinessPanel({ items, onOpen }: { items: ReadinessItem[]; onOpen: (where: ReadinessOpen) => void }) {
  const [open, setOpen] = useState(true)
  const warns = items.filter((one) => one.level === 'warn').length
  const infos = items.length - warns
  const Icon = open ? ChevronDownIcon : ChevronRightIcon
  return (
    <div className="rounded-md border px-3 py-1.5 text-xs" aria-label="준비 점검 패널">
      <button
        type="button"
        aria-expanded={open}
        disabled={items.length === 0}
        className="flex w-full items-center gap-1.5 text-left font-medium disabled:cursor-default"
        onClick={() => setOpen(!open)}
      >
        {items.length > 0 ? <Icon className="size-3.5 shrink-0" /> : <ClipboardCheck className="size-3.5 shrink-0" />}
        준비 점검
        {warns > 0 ? (
          <span className="text-amber-700 dark:text-amber-400">⚠ {warns}</span>
        ) : (
          <span className="text-muted-foreground font-normal">지금 보이는 문제가 없습니다</span>
        )}
        {infos > 0 && <span className="text-muted-foreground font-normal">· 알림 {infos}</span>}
        <span className="text-muted-foreground ml-auto font-normal">저장 · 내보내기 때 서버가 다시 확인합니다.</span>
      </button>
      {open && items.length > 0 && (
        <ul className="mt-1 space-y-0.5" aria-label="준비 점검">
          {items.map((one, index) => {
            const tone = one.level === 'warn' ? 'text-amber-700 dark:text-amber-400' : 'text-muted-foreground'
            const body = (
              <>
                <span className="font-medium">{one.where}</span> · {one.text}
              </>
            )
            const target = one.open
            return (
              <li key={index} className={tone}>
                {target ? (
                  <button type="button" className="hover:bg-muted w-full rounded px-1 text-left" title="눌러서 고칠 자리를 엽니다." onClick={() => onOpen(target)}>
                    {body}
                  </button>
                ) : (
                  <span className="px-1">{body}</span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
