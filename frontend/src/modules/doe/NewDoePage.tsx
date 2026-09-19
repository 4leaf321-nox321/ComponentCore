/**
 * 새 실험계획 — **대상을 먼저 고르고**, 그 도면의 변수에 범위를 준다.
 *
 * 부품 · 지그 · 조립은 저장할 때까지 「그리기 + 변수 심기」 만 한다. 여러 벌을 만드는 일은
 * 여기서 한다 — 대상 하나에 인스턴스(설계점)를 여럿 묶는 것이 실험계획이다.
 */

import { useNavigate, useSearchParams } from 'react-router-dom'

import { DoeForm } from '@/modules/doe/DoeForm'
import { worksApi } from '@/modules/works/api'
import type { WorkSummary } from '@/modules/works/api'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'

const KIND_LABEL: Record<string, string> = { part: '부품', jig: '지그', assembly: '조립' }

export default function NewDoePage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const workId = params.get('work')
  const works = useResource(() => worksApi.list(0, 100), [])
  const target = useResource(() => (workId ? worksApi.get(workId) : Promise.resolve(null)), [workId])

  // 1단계 — 대상 고르기
  if (!workId) {
    const rows = (works.data?.items ?? []).filter((one) => one.current_version > 0)
    return (
      <div>
        <PageHeader
          title="새 실험계획"
          description="무엇을 훑을지 고릅니다 — 부품 · 지그 하나, 또는 둘을 놓은 조립. 변수가 있는 도면이어야 합니다."
          back={{ to: '/doe', label: '실험계획' }}
        />
        <ErrorNotice error={works.error} className="mb-4" />
        {rows.length === 0 && !works.loading ? (
          <EmptyState
            title="훑을 도면이 없습니다"
            hint="먼저 그리기에서 부품이나 지그를 그려 저장하세요. 조립은 내 작업의 「새 조립」 으로 만듭니다."
            action={<Button onClick={() => navigate('/draw')}>그리러 가기</Button>}
          />
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((one) => (
              <TargetCard key={one.id} work={one} onPick={() => setParams({ work: one.id })} />
            ))}
          </ul>
        )}
      </div>
    )
  }

  // 2단계 — 변수에 범위 주기
  if (target.error) return <ErrorNotice error={target.error} />
  if (!target.data) return <Skeleton className="h-64 w-full" />
  const w = target.data
  return (
    <div>
      <PageHeader
        title={`실험계획 — ${w.name}`}
        description={`${KIND_LABEL[w.kind] ?? w.kind} v${w.current_version} 을 기준으로 인스턴스를 여럿 만듭니다.`}
        back={{ to: '/doe/new', label: '대상 다시 고르기' }}
      />
      {w.current ? (
        <DoeForm
          recipe={w.current.recipe}
          workId={w.id}
          defaultName={`${w.name} 훑기`}
          onCreated={(id) => navigate(`/doe/${id}`)}
          onEditRecipe={() => navigate(`/works/${w.id}`)}
        />
      ) : (
        <EmptyState title="저장된 도면이 없습니다" hint="먼저 도면을 저장하세요." />
      )}
    </div>
  )
}

function TargetCard({ work, onPick }: { work: WorkSummary; onPick: () => void }) {
  return (
    <li>
      <button type="button" onClick={onPick} className="hover:bg-accent/60 flex w-full flex-col gap-1 rounded-md border p-3 text-left">
        <div className="flex items-center gap-2">
          <span className="font-medium">{work.name}</span>
          <Badge variant={work.kind === 'part' ? 'outline' : 'secondary'}>{KIND_LABEL[work.kind] ?? work.kind}</Badge>
          <span className="text-muted-foreground ml-auto text-xs">v{work.current_version}</span>
        </div>
        {work.description && <p className="text-muted-foreground truncate text-xs">{work.description}</p>}
      </button>
    </li>
  )
}
