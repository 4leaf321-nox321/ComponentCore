/**
 * **접촉 점검** — 조립에서 맞닿은 쌍과 걸어 둔 접촉을 견준다.
 *
 * CalculiX 로 끝까지 풀어 보니(2026-11-16) 받침-덮개 접촉을 빠뜨린 조립에서 덮개가 떠 모드
 * 여섯이 모두 0 Hz 였고, 어느 쪽도 말하지 않았다. 부품이 수십 개면 하나쯤 빠뜨리기 쉽다. 그래서
 * 조건을 고치는 동안 서버가 맞닿은 쌍을 재고, 접촉 없이 맞닿은 쌍을 자리와 함께 말하며, 그 쌍의
 * 맞닿은 면으로 **본딩을 한 번에 채울 것**을 준다(면 규칙은 3D 에서 누를 때와 같다). 모달에서
 * 마찰 · 미끄럼 접촉이 어떻게 풀리는지도 여기서 말한다.
 *
 * 도면을 만들어야 해서 식 알림보다 무겁다 — 더 오래 멈췄을 때 한 번 부른다.
 */

import { Link2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { conditionsApi } from '@/modules/conditions/api'
import type { Conditions, ContactReport } from '@/modules/conditions/api'
import { Button } from '@/shared/components/ui/button'

export function ContactCheck({ recipe, draft, onApply }: { recipe: Recipe; draft: Conditions; onApply: (next: Conditions) => void }) {
  const [report, setReport] = useState<ContactReport | null>(null)
  const key = JSON.stringify([draft.named_selections, draft.contacts, draft.constraints, draft.analysis, recipe])
  useEffect(() => {
    let alive = true
    const timer = setTimeout(() => {
      conditionsApi
        .contacts(draft, recipe)
        .then((got) => alive && setReport(got))
        .catch(() => alive && setReport(null))
    }, 900)
    return () => {
      alive = false
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  // 맞닿은 쌍이 없으면(단품 · 떨어진 부품) 말할 것이 없다.
  if (!report || !report.touching?.length) return null
  const proposal = { named_selections: report.proposal?.named_selections ?? [], contacts: report.proposal?.contacts ?? [] }
  const fill = proposal.contacts.length
  const notes = [...(report.notes ?? [])].sort((a, b) => (a.level === b.level ? 0 : a.level === 'warn' ? -1 : 1))
  return (
    <div className="space-y-1 rounded-md border px-3 py-1.5 text-xs" aria-label="접촉 점검">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">접촉 점검</span>
        <span className="text-muted-foreground">
          맞닿은 바디 쌍 {report.touching.length} · 접촉 없음 {report.missing?.length ?? 0}
        </span>
        {fill > 0 && (
          <Button
            size="sm"
            variant="outline"
            className="h-6 text-xs"
            onClick={() =>
              onApply({
                ...draft,
                named_selections: [...draft.named_selections, ...proposal.named_selections],
                contacts: [...draft.contacts, ...proposal.contacts],
              })
            }
          >
            <Link2 className="size-3.5" />
            맞닿은 면으로 본딩 채우기 ({fill}쌍)
          </Button>
        )}
      </div>
      {notes.length > 0 && (
        <ul className="space-y-0.5">
          {notes.map((one, index) => (
            <li key={index} className={one.level === 'warn' ? 'text-amber-700 dark:text-amber-400' : 'text-muted-foreground'}>
              <span className="font-medium">{one.where}</span> · {one.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
