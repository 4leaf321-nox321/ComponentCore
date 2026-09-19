/**
 * 새 DOE — **대상을 먼저 고르고**, 그 도면의 변수에 범위를 준다.
 *
 * 부품 · 지그 · 조립은 저장할 때까지 「그리기 + 변수 심기」 만 한다. 여러 벌을 만드는 일은
 * 여기서 한다 — 대상 하나에 인스턴스(설계점)를 여럿 묶는 것이 DOE 다.
 * `?from=<DOE id>` 로 오면 그 DOE 의 대상과 설정을 채워 시작한다 — 범위를 좁혀 다시 돌릴 때.
 */

import { useNavigate, useSearchParams } from 'react-router-dom'

import { doeApi } from '@/modules/doe/api'
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
  const fromId = params.get('from')
  const from = useResource(() => (fromId ? doeApi.get(fromId) : Promise.resolve(null)), [fromId])
  // 지난 DOE 에서 왔으면 그 대상이 곧 대상이다 — 다시 고르게 하지 않는다.
  const workId = params.get('work') ?? from.data?.work_id ?? null
  const works = useResource(() => worksApi.list(0, 100), [])
  const target = useResource(() => (workId ? worksApi.get(workId) : Promise.resolve(null)), [workId])

  if (fromId && from.error) return <ErrorNotice error={from.error} />
  if (fromId && !from.data) return <Skeleton className="h-64 w-full" />
  if (fromId && from.data && !from.data.work_id) {
    // 대상 작업이 지워진 DOE — 스냅샷으로는 다시 만들 수 있지만 도면을 고칠 수는 없다.
    const snapshot = from.data
    return (
      <div>
        <PageHeader title={`DOE — ${snapshot.name} (다시)`} description="대상 작업이 지워져 그때의 도면 스냅샷으로 만듭니다." back={{ to: `/doe/${snapshot.id}`, label: '지난 DOE' }} />
        <DoeForm recipe={snapshot.recipe} initial={snapshot} onCreated={(id) => navigate(`/doe/${id}`)} />
      </div>
    )
  }

  // 1단계 — 대상 고르기
  if (!workId) {
    const rows = (works.data?.items ?? []).filter((one) => one.current_version > 0)
    return (
      <div>
        <PageHeader
          title="새 DOE"
          description="무엇을 훑을지 고릅니다 — 부품 · 지그 하나, 또는 둘을 놓은 조립. 변수가 있는 도면이어야 합니다."
          back={{ to: '/doe', label: 'DOE' }}
        />
        <ErrorNotice error={works.error} className="mb-4" />
        {rows.length === 0 && !works.loading ? (
          <EmptyState
            title="훑을 도면이 없습니다"
            hint="먼저 「새 작업」 에서 부품이나 지그를 그려 저장하세요. 조립은 내 작업의 「새 조립」 으로 만듭니다."
            action={<Button onClick={() => navigate('/draw')}>새 작업 만들기</Button>}
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
        title={from.data ? `DOE — ${w.name} (다시)` : `DOE — ${w.name}`}
        description={
          from.data
            ? `「${from.data.name}」 의 설정을 채워 두었습니다. 지금 도면(v${w.current_version})을 기준으로 새 DOE 를 만듭니다 — 지난 것은 그대로 남습니다.`
            : `${KIND_LABEL[w.kind] ?? w.kind} v${w.current_version} 을 기준으로 인스턴스를 여럿 만듭니다.`
        }
        back={from.data ? { to: `/doe/${from.data.id}`, label: '지난 DOE' } : { to: '/doe/new', label: '대상 다시 고르기' }}
      />
      {w.current ? (
        <DoeForm
          key={from.data?.id ?? w.id}
          recipe={w.current.recipe}
          workId={w.id}
          defaultName={`${w.name} 훑기`}
          initial={from.data ?? undefined}
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
