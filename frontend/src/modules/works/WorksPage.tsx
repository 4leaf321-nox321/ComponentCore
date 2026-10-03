/** 내 작업 — 내 공간의 문서들. 여기 있는 것은 나(와 관리자)만 본다. */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { worksApi } from '@/modules/works/api'
import type { WorkKind } from '@/modules/works/api'
import { AssembleDialog } from '@/modules/works/AssembleDialog'
import { groupByYear } from '@/modules/works/folders'
import { ChosenBar, FolderCrumbs, FolderDialogs, FolderSelect, PickAll, PickBox, RowFolder } from '@/shared/folders/FolderParts'
import { FolderTree } from '@/shared/folders/FolderTree'
import { useFolderSpace } from '@/shared/folders/useFolderSpace'
import { SearchBox } from '@/shared/components/SearchBox'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
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
import { describeShape, ShapeFilter, shapeConditionCount } from '@/shared/components/ShapeFilter'
import type { ShapeQuery } from '@/shared/components/ShapeFilter'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'


export default function WorksPage() {
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  /** 「내 지그가 어디 있지」 를 한 번에 — 종류로 가려 본다. */
  const [kind, setKind] = useState<'all' | WorkKind>('all')
  const [starting, setStarting] = useState(false)
  const [assembling, setAssembling] = useState(false)
  /** 찾기 · 꼬리표 · 휴지통 — 서버가 거른다(수십 개를 넘으면 한 쪽에 다 안 온다). */
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const [trashed, setTrashed] = useState(false)
  const [year, setYear] = useState<number | null>(null)
  /** 연도별로 묶어 본다 — 만든 순으로 받아야 같은 해가 한데 모인다. */
  const [byYear, setByYear] = useState(false)
  /** 형상 조건 — 이름이 아니라 형상으로(최신 버전의 형상 색인). */
  const [shape, setShape] = useState<ShapeQuery>({})
  /** 폴더 — null 이면 모든 작업, '' 이면 폴더에 넣지 않은 것만. 고른 폴더는 하위까지 보인다. */
  const space = useFolderSpace('works', worksApi, { onRefilter: () => setOffset(0) })
  const { folder, chosen, setChosen } = space
  const PAGE = useDisplay().list_page_size
  const page = useResource(
    () =>
      worksApi.list(offset, PAGE, {
        q,
        tag,
        kind: kind === 'all' ? '' : kind,
        trashed,
        folder,
        subfolders: folder !== '',
        year,
        order: byYear ? 'created' : 'updated',
        shape,
      }),
    [offset, q, tag, kind, trashed, PAGE, folder, year, byYear, shape, space.version],
  )
  const tags = useResource(() => worksApi.tags(), [page.data])
  const years = useResource(() => worksApi.years(), [page.data])
  const [restoring, setRestoring] = useState<string | null>(null)

  /** 거르는 값이 바뀌면 첫 쪽부터, 고른 것은 비운다. */
  function refilter(apply: () => void) {
    apply()
    setOffset(0)
    setChosen(new Set())
  }

  async function restore(id: string) {
    setRestoring(id)
    try {
      await worksApi.restoreWork(id)
      page.reload()
      space.refresh()
    } finally {
      setRestoring(null)
    }
  }

  /** 빈 조립 하나를 만들고 바로 연다 — 조립은 그릴 것이 없어 그리기 화면을 거치지 않는다. */
  async function startAssembly() {
    setStarting(true)
    try {
      const made = await worksApi.create({
        name: '새 조립',
        kind: 'assembly',
        note: '빈 조립',
      })
      navigate(`/works/${made.id}`)
    } finally {
      setStarting(false)
    }
  }
  const rows = page.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="내 작업"
        description="그리고 있는 것들. 나만 봅니다 — 남에게 보이려면 부품이나 지그로 승격합니다."
        actions={
          <>
            {/* 시작하는 길 셋 — 그리기, 부품에서 생성, 놓기. 흔한 순서대로. */}
            <Button onClick={() => navigate('/draw')}>새 부품/지그</Button>
            {/* 지그의 두 번째 시작점 — 부품을 골라 규칙으로 만들고, 그 뒤는 그냥 그린다. */}
            <Button variant="outline" onClick={() => navigate('/draw/jig-from-part')}>
              부품에서 지그 생성
            </Button>
            {/* 조립은 그리는 것이 아니라 **놓는 것**이라 그리기를 거치지 않는다. 부품 + 지그면 자리를 서버가 맞춘다. */}
            <Button variant="outline" onClick={() => setAssembling(true)}>
              부품 + 지그로 조립
            </Button>
            <Button variant="outline" onClick={() => void startAssembly()} disabled={starting}>
              {starting ? '만드는 중…' : '빈 조립'}
            </Button>
          </>
        }
      />
      <div className="flex gap-4">
        {/* 폴더 · 만든 해 — 넓은 화면에서 왼쪽에. 좁으면 아래의 고르개로. */}
        <aside className="hidden w-56 shrink-0 md:block">
          <FolderTree
            space={space}
            allLabel="모든 작업"
            noun="작업"
            years={years.data ?? []}
            year={year}
            onYear={(next) => refilter(() => setYear(next))}
          />
        </aside>
        <div className="min-w-0 flex-1">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <FolderSelect space={space} allLabel="모든 작업" />
        <SearchBox value={q} onChange={(next) => refilter(() => setQ(next))} />
        <div className="flex items-center gap-1">
        {(
          [
            { value: 'all', label: '전체' },
            { value: 'part', label: '부품' },
            { value: 'jig', label: '지그' },
            { value: 'assembly', label: '조립' },
          ] as const
        ).map((one) => (
          <button
            key={one.value}
            type="button"
            onClick={() => refilter(() => setKind(one.value))}
            aria-pressed={kind === one.value}
            className={`rounded-md border px-3 py-1 text-sm ${
              kind === one.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
            }`}
          >
            {one.label}
          </button>
        ))}
        </div>
        <TagFilter tags={tags.data ?? []} value={tag} onChange={(next) => refilter(() => setTag(next))} />
        <ShapeFilter value={shape} onChange={(next) => refilter(() => setShape(next))} />
        <button
          type="button"
          onClick={() => refilter(() => setByYear(!byYear))}
          aria-pressed={byYear}
          className={`rounded-md border px-3 py-1 text-sm ${byYear ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}
        >
          연도별로 묶기
        </button>
        <button type="button" onClick={() => refilter(() => setTrashed(!trashed))} aria-pressed={trashed} className={`ml-auto rounded-md border px-3 py-1 text-sm ${trashed ? 'bg-destructive/10 border-destructive/40' : 'hover:bg-accent'}`}>
          {trashed ? '휴지통 보는 중 — 내 작업으로' : '휴지통'}
        </button>
      </div>
      {/* 지금 보는 폴더 — 위 폴더로 바로 간다. */}
      <FolderCrumbs
        space={space}
        allLabel="모든 작업"
        extra={
          year !== null && (
            <span className="ml-2 rounded-full border px-2 text-xs">
              {year}년에 만든 것{' '}
              <button type="button" aria-label="연도 거르기 풀기" onClick={() => refilter(() => setYear(null))}>
                ×
              </button>
            </span>
          )
        }
      />
      <ChosenBar space={space} />
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        trashed ? (
          <EmptyState title="휴지통이 비었습니다" hint="지운 작업이 여기 오고, 되살릴 수 있습니다." />
        ) : q || tag || folder !== null || year !== null || shapeConditionCount(shape) > 0 ? (
          <EmptyState title="맞는 작업이 없습니다" hint="찾는 말 · 꼬리표 · 폴더 · 연도 · 형상 조건을 바꿔 보세요. 빈 폴더라면 작업을 끌어다 놓으세요." />
        ) : (
          <EmptyState
            title="작업이 없습니다"
            hint="「새 작업」 에서 빈 화면 · 템플릿 · STEP 으로 그려 저장하세요."
            action={<Button onClick={() => navigate('/draw')}>새 작업 만들기</Button>}
          />
        )
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <PickAll space={space} ids={rows.map((row) => row.id)} />
                </TableHead>
                <TableHead>이름</TableHead>
                <TableHead>종류</TableHead>
                <TableHead>버전</TableHead>
                <TableHead>지그 생성</TableHead>
                <TableHead>승격</TableHead>
                <TableHead>수정</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(byYear ? groupByYear(rows) : [{ year: 0, rows }]).map((group) => [
                byYear ? (
                  <TableRow key={`year-${group.year}`} className="bg-muted/40 hover:bg-muted/40">
                    <TableCell colSpan={7} className="py-1 text-xs font-medium">
                      {group.year}년 · {group.rows.length}개{page.data && page.data.total > rows.length ? ' (이 쪽에서)' : ''}
                    </TableCell>
                  </TableRow>
                ) : null,
                ...group.rows.map((row) => (
                  <TableRow key={row.id} draggable={!trashed} onDragStart={(event) => space.startDrag(event, row.id)} data-state={chosen.has(row.id) ? 'selected' : undefined}>
                    <TableCell>
                      <PickBox space={space} id={row.id} name={row.name} />
                    </TableCell>
        <TableCell>
            <Link to={`/works/${row.id}`} className="font-medium hover:underline">
              {row.name}
            </Link>
            <RowFolder space={space} folder={row.folder} />
            {row.description && (
              <p className="text-muted-foreground max-w-md truncate text-xs">{row.description}</p>
            )}
            {row.shape && <p className="text-muted-foreground font-mono text-[11px]">{describeShape(row.shape)}</p>}
            {row.tags.length > 0 && (
              <p className="mt-0.5 flex flex-wrap gap-1">
                {row.tags.map((one) => (
                  <span key={one} className="bg-accent rounded-full px-1.5 text-[10px]">
                    {one}
                  </span>
                ))}
              </p>
            )}
          </TableCell>
          <TableCell>
            <Badge variant={row.kind === 'part' ? 'outline' : 'secondary'}>
              {row.kind === 'jig' ? '지그' : row.kind === 'assembly' ? '조립' : '부품'}
            </Badge>
          </TableCell>
          <TableCell>
            {row.current_version > 0 ? (
              <>
                v{row.current_version}{' '}
                {row.current_status && <StatusBadge kind="run" value={row.current_status} />}
              </>
            ) : (
              <span className="text-muted-foreground text-xs">없음</span>
            )}
          </TableCell>
          <TableCell>
            {row.jig_run_count > 0 ? (
              <>
                {row.jig_run_count}회{' '}
                {row.last_jig_status && <StatusBadge kind="run" value={row.last_jig_status} />}
              </>
            ) : (
              '—'
            )}
          </TableCell>
          <TableCell className="space-x-1 text-xs">
            {row.promoted_part_id && (
              <Link to={`/parts/${row.promoted_part_id}`} className="rounded border px-1.5 py-0.5 hover:underline">
                부품
              </Link>
            )}
            {row.promoted_jig_id && (
              <Link to={`/jigs/${row.promoted_jig_id}`} className="rounded border px-1.5 py-0.5 hover:underline">
                지그
              </Link>
            )}
            {!row.promoted_part_id && !row.promoted_jig_id && <span className="text-muted-foreground">—</span>}
          </TableCell>
          <TableCell className="text-sm">
            {trashed ? (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground text-xs">지움 {row.deleted_at ? shownDateTime(row.deleted_at) : ''}</span>
                <Button size="sm" variant="outline" className="h-7" disabled={restoring === row.id} onClick={() => void restore(row.id)}>
                  되살리기
                </Button>
              </div>
            ) : (
              shownDateTime(row.updated_at)
            )}
          </TableCell>
                    </TableRow>
                )),
              ])}
            </TableBody>
          </Table>
          {page.data && (
            <Pagination total={page.data.total} limit={page.data.limit} offset={page.data.offset} onChange={(next) => { setOffset(next); setChosen(new Set()) }} />
          )}
        </>
      )}
        </div>
      </div>
      <AssembleDialog key={String(assembling)} open={assembling} onClose={() => setAssembling(false)} onMade={(id) => navigate(`/works/${id}`)} />
      <FolderDialogs space={space} noun="작업" />
    </div>
  )
}
