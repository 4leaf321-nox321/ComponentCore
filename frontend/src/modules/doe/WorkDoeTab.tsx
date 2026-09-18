/**
 * 내 작업 › 실험계획 — **이 작업의 레시피로** 바로 훑는다.
 *
 * 독립 화면(/doe)과 같은 조각을 쓴다. 다른 것은 레시피를 고를 필요가 없다는 것뿐이다 —
 * 지금 보고 있는 작업의 현재 버전이 곧 기준이다.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { doeApi } from '@/modules/doe/api'
import { DoeForm } from '@/modules/doe/DoeForm'
import { DoeStudyView } from '@/modules/doe/DoeStudyView'
import type { Work } from '@/modules/works/api'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

export function WorkDoeTab({
  workId,
  work,
  onEditRecipe,
}: {
  workId: string
  work: Work
  /** 부품 탭으로 옮겨 편집기를 연다 — 변수를 만들러 갈 때. */
  onEditRecipe?: () => void
}) {
  const studies = useResource(() => doeApi.list({ workId }), [workId])
  const [openId, setOpenId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const study = useResource(() => (openId ? doeApi.get(openId) : Promise.resolve(null)), [openId])

  if (openId && study.data) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setOpenId(null)}>
            ← 목록으로
          </Button>
          <h3 className="font-medium">{study.data.name}</h3>
          <Link to={`/doe/${study.data.id}`} className="text-muted-foreground ml-auto text-xs underline">
            따로 열기
          </Link>
        </div>
        <DoeStudyView study={study.data} onReload={study.reload} />
      </div>
    )
  }

  if (starting) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <CardTitle>새 실험계획</CardTitle>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setStarting(false)}>
              취소
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {work.current ? (
            <DoeForm
              recipe={work.current.recipe}
              workId={workId}
              defaultName={`${work.name} 훑기`}
              onEditRecipe={onEditRecipe}
              onCreated={(id) => {
                setStarting(false)
                setOpenId(id)
                studies.reload()
              }}
            />
          ) : (
            <p className="text-muted-foreground text-sm">먼저 부품 탭에서 레시피를 저장하세요.</p>
          )}
        </CardContent>
      </Card>
    )
  }

  const rows = studies.data?.items ?? []
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <p className="text-muted-foreground text-sm">
          변수에 범위를 주면 형상을 여러 벌 만들어 **공유 폴더**에 STEP 으로 쏟습니다 — 해석으로 넘길 묶음입니다.
        </p>
        <Button className="ml-auto" onClick={() => setStarting(true)} disabled={!work.current}>
          새 실험계획
        </Button>
      </div>
      <ErrorNotice error={studies.error} />
      {rows.length === 0 ? (
        <EmptyState
          title="아직 없습니다"
          hint="「새 실험계획」 을 누르고 바꿀 변수를 고르세요. 레시피에 변수가 먼저 있어야 합니다."
          action={
            Object.keys((work.current?.recipe.params ?? {}) as Record<string, number>).length === 0 && onEditRecipe ? (
              <Button variant="outline" onClick={onEditRecipe}>
                레시피에 변수 만들러 가기
              </Button>
            ) : undefined
          }
        />
      ) : (
        <ul className="space-y-1">
          {rows.map((one) => (
            <li key={one.id}>
              <button
                type="button"
                className="hover:bg-accent/60 flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-sm"
                onClick={() => setOpenId(one.id)}
              >
                <span className="font-medium">{one.name}</span>
                <span className="text-muted-foreground text-xs">
                  {one.method === 'factorial' ? '전체 조합' : 'LHS'} · 설계점 {one.point_count}
                </span>
                <span className="text-muted-foreground ml-auto text-xs">{shownDateTime(one.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
