/** 지그 카탈로그 — 승격된 지그. 로그인한 누구나 보고, 폴더로 나눠 둔다(옮기는 것은 올린 사람 · 관리자). */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { jigsApi } from '@/modules/jigs/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { canEditProject } from '@/shared/auth/roles'
import { ChosenBar, FolderCrumbs, FolderDialogs, FolderSelect, PickAll, PickBox, RowFolder } from '@/shared/folders/FolderParts'
import { FolderTree } from '@/shared/folders/FolderTree'
import { useFolderSpace } from '@/shared/folders/useFolderSpace'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { SearchBox } from '@/shared/components/SearchBox'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { StatusBadge } from '@/shared/components/StatusBadge'
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


export default function JigsPage() {
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')
  /** 고른 꼬리표 — 빈 문자열이면 안 거른다. */
  const [tag, setTag] = useState('')
  const PAGE = useDisplay().list_page_size
  const space = useFolderSpace('jigs', jigsApi, { onRefilter: () => setOffset(0) })
  const page = useResource(
    () => jigsApi.list({ offset, limit: PAGE, q, tag, folder: space.folder }),
    [offset, q, tag, PAGE, space.folder, space.version],
  )
  const tags = useResource(() => jigsApi.tags(), [page.data])
  const rows = page.data?.items ?? []
  /** 옮길 수 있는 줄 — 올린 사람 · 관리자. 판정은 서버가 다시 한다. */
  const { user } = useAuth()
  const movable = (ownerId: string) => canEditProject(user, ownerId)
  const filtered = Boolean(q || tag || space.folder !== null)

  return (
    <div>
      <PageHeader title="지그" description="내 작업에서 승격된 지그. 어느 부품 버전의 지그인지 함께 적혀 있습니다." />
      <div className="flex gap-4">
        {/* 폴더 — 넓은 화면에서 왼쪽에. 좁으면 위의 고르개로. */}
        <aside className="hidden w-56 shrink-0 md:block">
          <FolderTree space={space} allLabel="모든 지그" noun="지그" />
        </aside>
        <div className="min-w-0 flex-1">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <FolderSelect space={space} allLabel="모든 지그" />
        <SearchBox value={q} onChange={(next) => { setQ(next); setOffset(0) }} />
        <TagFilter tags={tags.data ?? []} value={tag} onChange={(next) => { setTag(next); setOffset(0) }} />
      </div>
      <FolderCrumbs space={space} allLabel="모든 지그" />
      <ChosenBar space={space} />
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        filtered ? (
          <EmptyState title="맞는 지그가 없습니다" hint="찾는 말 · 꼬리표 · 폴더를 바꿔 보세요. 빈 폴더라면 지그를 끌어다 놓으세요." />
        ) : (
          <EmptyState title="아직 올라온 지그가 없습니다" hint="내 작업의 지그 탭에서 결과를 「지그로 승격」 하면 여기 뜹니다." />
        )
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <PickAll space={space} ids={rows.filter((row) => movable(row.owner_id)).map((row) => row.id)} />
                </TableHead>
                <TableHead>이름</TableHead>
                <TableHead>부품</TableHead>
                <TableHead>버전</TableHead>
                <TableHead>간섭</TableHead>
                <TableHead>올린 사람</TableHead>
                <TableHead>갱신</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={row.id}
                  draggable={movable(row.owner_id)}
                  onDragStart={(event) => space.startDrag(event, row.id)}
                  data-state={space.chosen.has(row.id) ? 'selected' : undefined}
                >
                  <TableCell>
                    <PickBox space={space} id={row.id} name={row.name} disabled={!movable(row.owner_id)} />
                  </TableCell>
                  <TableCell>
                    <Link to={`/jigs/${row.id}`} className="font-medium hover:underline">
                      {row.name}
                    </Link>
                    <RowFolder space={space} folder={row.folder} />
                  </TableCell>
                  <TableCell>
                    {row.part_id ? (
                      <Link to={`/parts/${row.part_id}`} className="hover:underline">
                        {row.part_name}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground text-xs">스냅숏만</span>
                    )}
                  </TableCell>
                  <TableCell>v{row.current_version}</TableCell>
                  <TableCell>
                    {row.interference_ok === null ? '—' : <StatusBadge kind="interference" value={row.interference_ok ? 'ok' : 'bad'} />}
                  </TableCell>
                  <TableCell>{row.owner_name}</TableCell>
                  <TableCell className="text-sm">{shownDateTime(row.updated_at)}</TableCell>
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
      <FolderDialogs space={space} noun="지그" shared />
    </div>
  )
}
