/**
 * 템플릿 공간 — 「그리기」 의 출발점을 모아 둔 곳.
 *
 * 부품 · 지그와 달리 승격이 없다. 자리가 둘이고(**내 것** · **공용**) 그 사이는 스위치 하나다 —
 * 템플릿은 시작점일 뿐이라 버전을 남길 것이 없기 때문이다. 남의 공용 템플릿은 고치지 못하고
 * 「내 것으로 복사」 해서 쓴다. 내 것과 공용이 **한 폴더 나무**를 쓴다 — 옮기는 것은 만든 사람
 * · 관리자.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { templatesApi } from '@/modules/templates/api'
import type { TemplateScope, TemplateSummary } from '@/modules/templates/api'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { ChosenBar, FolderCrumbs, FolderDialogs, FolderSelect, PickAll, PickBox, RowFolder } from '@/shared/folders/FolderParts'
import { FolderTree } from '@/shared/folders/FolderTree'
import { useFolderSpace } from '@/shared/folders/useFolderSpace'
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
  { value: 'all', label: '전체', hint: '내 템플릿과 공용 템플릿을 함께 표시합니다. 내 템플릿이 먼저 표시됩니다.' },
  { value: 'mine', label: '내 템플릿', hint: '본인이 생성한 템플릿입니다. 본인만 조회할 수 있으며, 공용으로 공개할 수 있습니다.' },
  { value: 'shared', label: '공용', hint: '모든 사용자가 시작점으로 선택할 수 있는 템플릿입니다. 다른 사용자의 템플릿은 복사하여 사용합니다.' },
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
  /** 폴더 나무는 지금 자리(scope)에 보이는 것만 센다. */
  const space = useFolderSpace(
    'templates',
    { ...templatesApi, folders: () => templatesApi.folders(scope) },
    { onRefilter: () => setOffset(0), deps: [scope] },
  )
  const page = useResource(
    () => templatesApi.list({ scope, q: query, tag, folder: space.folder, offset, limit: PAGE }),
    [scope, query, tag, offset, PAGE, space.folder, space.version],
  )
  const tags = useResource(() => templatesApi.tags(), [page.data])
  const rows = page.data?.items ?? []
  /** 옮길 수 있는 줄 — 만든 사람 · 관리자. 판정은 서버가 다시 한다. */
  const { user } = useAuth()
  const movable = (row: TemplateSummary) => row.mine || isSystemAdmin(user)

  async function act(run: () => Promise<unknown>, id: string) {
    setBusy(id)
    setError(null)
    try {
      await run()
      page.reload()
      space.refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <PageHeader
        title="템플릿"
        description="모델링의 시작점입니다. 내 템플릿으로 두거나 공용으로 공개할 수 있으며, 수정한 결과는 템플릿이 아닌 내 작업에 저장됩니다."
        actions={
          <Button variant="outline" onClick={() => navigate('/draw')}>
            새 작업 생성
          </Button>
        }
      />

      <div className="flex gap-4">
        {/* 폴더 — 넓은 화면에서 왼쪽에. 좁으면 위의 고르개로. */}
        <aside className="hidden w-56 shrink-0 md:block">
          <FolderTree space={space} allLabel="모든 템플릿" noun="템플릿" />
        </aside>
        <div className="min-w-0 flex-1">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <FolderSelect space={space} allLabel="모든 템플릿" />
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
          placeholder="이름, 설명으로 검색"
          className="h-9 w-64"
          aria-label="템플릿 검색"
        />
        <TagFilter tags={tags.data ?? []} value={tag} onChange={(next) => { setTag(next); setOffset(0) }} />
        <span className="text-muted-foreground text-xs">{SCOPES.find((one) => one.value === scope)?.hint}</span>
      </div>
      <FolderCrumbs space={space} allLabel="모든 템플릿" />
      <ChosenBar space={space} />

      <ErrorNotice error={error ?? page.error} className="mb-4" />

      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title={query || tag ? '검색 조건에 맞는 템플릿이 없습니다' : space.folder !== null ? '이 폴더에 템플릿이 없습니다' : scope === 'shared' ? '공용으로 공개된 템플릿이 없습니다' : '등록된 템플릿이 없습니다'}
          hint={space.folder !== null ? '템플릿을 이 폴더로 끌어다 놓거나, 새 작업 화면에서 저장할 때 폴더를 지정하십시오.' : '새 작업 화면의 ‘파일’ 탭에서 ‘템플릿’ 버튼으로 저장하면 이 목록에 표시됩니다'}
          action={<Button onClick={() => navigate('/draw')}>새 작업으로 이동</Button>}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <PickAll space={space} ids={rows.filter(movable).map((row) => row.id)} />
                </TableHead>
                <TableHead>이름</TableHead>
                <TableHead>공개 범위</TableHead>
                <TableHead>피처</TableHead>
                <TableHead>작성자</TableHead>
                <TableHead>수정일</TableHead>
                <TableHead className="text-right">관리</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={row.id}
                  draggable={movable(row)}
                  onDragStart={(event) => space.startDrag(event, row.id)}
                  data-state={space.chosen.has(row.id) ? 'selected' : undefined}
                >
                  <TableCell>
                    <PickBox space={space} id={row.id} name={row.name} disabled={!movable(row)} />
                  </TableCell>
                  <TableCell>
                    <button type="button" className="text-left font-medium hover:underline" onClick={() => navigate(`/draw?template=${row.id}`)}>
                      {row.name}
                    </button>
                    <RowFolder space={space} folder={row.folder} />
                    {row.description && <p className="text-muted-foreground truncate text-xs">{row.description}</p>}
                  </TableCell>
                  <TableCell>
                    {row.is_shared ? <Badge variant="secondary">공용</Badge> : <Badge variant="outline">내 템플릿</Badge>}
                  </TableCell>
                  <TableCell>{row.node_count}</TableCell>
                  <TableCell>{row.mine ? '본인' : row.owner_name}</TableCell>
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
                          {row.is_shared ? '공용 해제' : '공용으로 공개'}
                        </Button>
                        <Button size="sm" variant="ghost" disabled={busy === row.id} onClick={() => setRemoving(row)}>
                          삭제
                        </Button>
                      </>
                    ) : (
                      <Button size="sm" variant="outline" disabled={busy === row.id} onClick={() => void act(() => templatesApi.copy(row.id), row.id)}>
                        내 템플릿으로 복사
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {page.data && (
            <Pagination total={page.data.total} limit={page.data.limit} offset={page.data.offset} onChange={(next) => { setOffset(next); space.setChosen(new Set()) }} />
          )}
        </>
      )}
        </div>
      </div>
      <FolderDialogs space={space} noun="템플릿" shared />

      <ConfirmDialog
        open={removing !== null}
        title="템플릿 삭제"
        description={`‘${removing?.name ?? ''}’ 템플릿을 삭제하시겠습니까? 이 템플릿에서 시작한 작업은 그대로 유지됩니다.`}
        confirmLabel="삭제"
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
