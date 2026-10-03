/**
 * 비슷한 것 — 이 부품 · 지그 · 작업과 형상이 닮은 것(최신 버전끼리).
 *
 * 「이 제품에 맞는 지그가 이미 있나」 를 이름으로는 못 찾는다 — 사람마다 이름을 다르게 붙인다.
 * 형상 색인(크기 · 비율 · 꽉 찬 정도 · 구멍 · 만든 방식)으로 견주고, **비슷한 부품에는 그 부품의
 * 지그**를 붙여 보인다. 점수만 보고 고르지 않게 「왜」 를 함께 적는다.
 */

import { Link } from 'react-router-dom'

import { placeOf, searchApi } from '@/modules/search/api'
import type { SimilarWhere } from '@/modules/search/api'
import { describeShape } from '@/shared/components/ShapeFilter'
import type { ShapeIndex } from '@/shared/components/ShapeFilter'
import { Badge } from '@/shared/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { useResource } from '@/shared/hooks/useResource'

export function SimilarCard({ source, where, limit = 8, className }: { source: string; where?: SimilarWhere[]; limit?: number; className?: string }) {
  const answer = useResource(() => searchApi.similar({ source, where, limit }), [source, (where ?? []).join(','), limit])
  const items = answer.data?.items ?? []
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>비슷한 것</CardTitle>
        <p className="text-muted-foreground text-xs">최신 버전의 형상끼리 — 크기 · 비율 · 꽉 찬 정도 · 구멍 · 만든 방식.</p>
      </CardHeader>
      <CardContent>
        {answer.loading && !answer.data ? (
          <p className="text-muted-foreground text-sm">찾는 중…</p>
        ) : answer.error ? (
          // 색인이 없는 버전(이 기능 전) · 아직 평가 중 — 오류라기보다 아직 못 견주는 것이다.
          <p className="text-muted-foreground text-sm">{answer.error.message}</p>
        ) : items.length === 0 ? (
          <p className="text-muted-foreground text-sm">비슷한 것이 없습니다(가장 긴 변이 네 배 안에서 {answer.data?.compared ?? 0} 개를 견줬습니다).</p>
        ) : (
          <ul className="space-y-2" aria-label="비슷한 것">
            {items.map((one) => {
              const place = placeOf(one.source)
              const percent = Math.round(one.score * 100)
              return (
                <li key={one.source} className="space-y-0.5 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="w-10 shrink-0 text-right font-mono text-xs" title="닮음">
                      {percent}%
                    </span>
                    <span className="bg-muted h-1.5 w-12 shrink-0 overflow-hidden rounded" aria-hidden>
                      <span className="bg-primary block h-full" style={{ width: `${percent}%` }} />
                    </span>
                    <Link to={place.to} className="min-w-0 truncate font-medium hover:underline">
                      {one.name}
                    </Link>
                    <Badge variant="outline" className="shrink-0 text-[10px]">
                      {place.label}
                    </Badge>
                  </div>
                  <div className="text-muted-foreground flex flex-wrap items-center gap-1 pl-[5.5rem] text-[11px]">
                    {one.why.map((reason) => (
                      <span key={reason} className="bg-accent rounded-full px-1.5">
                        {reason}
                      </span>
                    ))}
                    {one.shape?.size && <span className="font-mono">{describeShape(one.shape as ShapeIndex)}</span>}
                  </div>
                  {one.jigs && one.jigs.length > 0 && (
                    <p className="pl-[5.5rem] text-[11px]">
                      이 부품의 지그:{' '}
                      {one.jigs.map((jig, index) => (
                        <span key={jig.source}>
                          {index > 0 && ' · '}
                          <Link to={placeOf(jig.source).to} className="hover:underline">
                            {jig.name}
                          </Link>
                        </span>
                      ))}
                    </p>
                  )}
                  {one.part_name && <p className="text-muted-foreground pl-[5.5rem] text-[11px]">부품: {one.part_name}</p>}
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
