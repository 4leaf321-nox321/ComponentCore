/**
 * 템플릿 공간 — 「그리기」 의 출발점을 모아 둔 곳.
 *
 * 부품 · 지그와 달리 승격이 없다. 자리가 둘이고(**내 것** · **공용**) 그 사이는 스위치 하나다 —
 * 템플릿은 시작점일 뿐이라 버전을 남길 것이 없기 때문이다. 남의 공용 템플릿은 고치지 못하고
 * 「내 것으로 복사」 해서 쓴다.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { templatesApi } from '@/modules/templates/api'
import type { TemplateScope, TemplateSummary } from '@/modules/templates/api'
import { ApiError } from '@/shared/api/client'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useDisplay } from '@/shared/api/display'
import { TagFilter } from '@/shared/components/TagFilter'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'


const SCOPES: { value: TemplateScope; label: string; hint: string }[] = [
  { value: 'all', label: '전체', hint: '내 템플릿과 공용 템플릿을 함께 봅니다. 내 것이 먼저 옵니다.' },
  { value: 'mine', label: '내 템플릿', hint: '내가 만든 것. 나만 보이고, 공용으로 내놓을 수 있습니다.' },
  { value: 'shared', label: '공용', hint: '누구나 시작점으로 고를 수 있는 것. 남의 것은 복사해서 씁니다.' },
]

export default function TemplatesPage() {
  const navigate = useNavigate()
  const [scope, setScope] = useState<TemplateScope>('all')
  const [query, setQuery] = useState('')
  /** 고른 꼬리표 — 빈 문자열이면 안 거른다. */
  const [tag, setTag] = useState('')
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [removing, setRemoving] = useState<TemplateSummary | null>(null)
  const PAGE = useDisplay().list_page_size
  const page = useResource(() => templatesApi.list({ scope, q: query, tag, offset, limit: PAGE }), [scope, query, tag, offset, PAGE])
  const tags = useResource(() => templatesApi.tags(), [page.data])
  const rows = page.data?.items ?? []

  async function act(run: () => Promise<unknown>, id: string) {
    setBusy(id)
    setError(null)
    try {
      await run()
      page.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <PageHeader
        title="템플릿"
        description="그리기의 출발점. 내 것으로 두거나 공용으로 내놓습니다. 고친 결과는 템플릿이 아니라 내 작업으로 갑니다."
        actions={
          <Button variant="outline" onClick={() => navigate('/draw')}>
            그리기로 새로 만들기
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Tabs
          value={scope}
          onValueChange={(value) => {
            setScope(value as TemplateScope)
            setOffset(0)
          }}
        >
          <TabsList>
            {SCOPES.map((one) => (
              <TabsTrigger key={one.value} value={one.value}>
                {one.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setOffset(0)
          }}
          placeholder="이름 · 설명으로 찾기"
          className="h-9 w-64"
          aria-label="템플릿 찾기"
        />
        <TagFilter tags={tags.data ?? []} value={tag} onChange={(next) => { setTag(next); setOffset(0) }} />
        <span className="text-muted-foreground text-xs">{SCOPES.find((one) => one.value === scope)?.hint}</span>
      </div>

      <ErrorNotice error={error ?? page.error} className="mb-4" />

      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title={query ? '찾는 템플릿이 없습니다' : scope === 'shared' ? '공용으로 내놓은 템플릿이 없습니다' : '아직 템플릿이 없습니다'}
          hint="그리기에서 「파일」 탭의 「템플릿」 단추로 저장하면 여기 뜹니다."
          action={<Button onClick={() => navigate('/draw')}>그리기로 가기</Button>}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>자리</TableHead>
                <TableHead>피처</TableHead>
                <TableHead>만든 사람</TableHead>
                <TableHead>갱신</TableHead>
                <TableHead className="text-right">할 일</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <button type="button" className="text-left font-medium hover:underline" onClick={() => navigate(`/draw?template=${row.id}`)}>
                      {row.name}
                    </button>
                    {row.description && <p className="text-muted-foreground truncate text-xs">{row.description}</p>}
                  </TableCell>
                  <TableCell>
                    {row.is_shared ? <Badge variant="secondary">공용</Badge> : <Badge variant="outline">내 것</Badge>}
                  </TableCell>
                  <TableCell>{row.node_count}</TableCell>
                  <TableCell>{row.mine ? '나' : row.owner_name}</TableCell>
                  <TableCell>{shownDateTime(row.updated_at)}</TableCell>
                  <TableCell className="space-x-1 text-right">
                    <Button size="sm" onClick={() => navigate(`/draw?template=${row.id}`)}>
                      새 작업으로 열기
                    </Button>
                    {row.mine ? (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy === row.id}
                          onClick={() => void act(() => templatesApi.update(row.id, { is_shared: !row.is_shared }), row.id)}
                        >
                          {row.is_shared ? '공용에서 거두기' : '공용으로 내놓기'}
                        </Button>
                        <Button size="sm" variant="ghost" disabled={busy === row.id} onClick={() => setRemoving(row)}>
                          지우기
                        </Button>
                      </>
                    ) : (
                      <Button size="sm" variant="outline" disabled={busy === row.id} onClick={() => void act(() => templatesApi.copy(row.id), row.id)}>
                        내 것으로 복사
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {page.data && <Pagination total={page.data.total} limit={page.data.limit} offset={page.data.offset} onChange={setOffset} />}
        </>
      )}

      <ConfirmDialog
        open={removing !== null}
        title="템플릿을 지웁니다"
        description={`「${removing?.name ?? ''}」 을 지웁니다. 이 템플릿에서 시작한 작업은 그대로 남습니다.`}
        confirmLabel="지우기"
        onConfirm={async () => {
          const target = removing
          setRemoving(null)
          if (target) await act(() => templatesApi.remove(target.id), target.id)
        }}
        onClose={() => setRemoving(null)}
      />
    </div>
  )
}
