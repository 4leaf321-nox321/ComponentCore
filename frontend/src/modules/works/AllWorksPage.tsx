/**
 * 모든 작업 — **시스템 관리자만.** 남의 내 작업을 찾아 연다(퇴사자의 작업 · 도와 달라는 사람의
 * 작업). 여는 것은 원래 관리자에게 열려 있었고(`require_owner`), 이 화면은 그것을 찾게 해 줄
 * 뿐이다. 옮기기 · 지우기 같은 정리는 주인이 내 작업에서 한다 — 여기는 둘러보기만.
 */

import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { accountsApi } from '@/modules/accounts/api'
import { worksApi } from '@/modules/works/api'
import { KindFilter } from '@/modules/works/KindFilter'
import type { KindChoice } from '@/modules/works/KindFilter'
import { useDisplay } from '@/shared/api/display'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { SearchBox } from '@/shared/components/SearchBox'
import { describeShape } from '@/shared/components/ShapeFilter'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { TagFilter } from '@/shared/components/TagFilter'
import { Badge } from '@/shared/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

export default function AllWorksPage() {
  /** 고른 사람은 주소에 — 계정 화면에서 「작업」 으로 바로 온다. */
  const [params, setParams] = useSearchParams()
  const owner = params.get('owner') || 'all'
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const [kind, setKind] = useState<KindChoice>('all')
  const [trashed, setTrashed] = useState(false)
  const PAGE = useDisplay().list_page_size
  const accounts = useResource(() => accountsApi.list(), [])
  const page = useResource(
    () => worksApi.list(offset, PAGE, { owner, q, tag, kind: kind === 'all' ? '' : kind, trashed }),
    [offset, PAGE, owner, q, tag, kind, trashed],
  )
  const tags = useResource(() => worksApi.tags(owner), [owner])
  const rows = page.data?.items ?? []

  function refilter(apply: () => void) {
    apply()
    setOffset(0)
  }

  function pickOwner(next: string) {
    refilter(() => {
      setTag('')
      setParams(next === 'all' ? {} : { owner: next }, { replace: true })
    })
  }

  return (
    <div>
      <PageHeader
        title="모든 작업"
        description="모든 사람의 내 작업 — 시스템 관리자만 봅니다. 열어 보는 것은 괜찮지만, 고치면 그 사람의 작업에 새 버전이 생깁니다."
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          aria-label="만든 사람"
          className="bg-background h-9 rounded-md border px-2 text-sm"
          value={owner}
          onChange={(event) => pickOwner(event.target.value)}
        >
          <option value="all">모든 사람</option>
          {(accounts.data ?? []).map((one) => (
            <option key={one.id} value={one.id}>
              {one.display_name} ({one.email})
            </option>
          ))}
        </select>
        <SearchBox value={q} onChange={(next) => refilter(() => setQ(next))} />
        <KindFilter value={kind} onChange={(next) => refilter(() => setKind(next))} />
        <TagFilter tags={tags.data ?? []} value={tag} onChange={(next) => refilter(() => setTag(next))} />
        <button
          type="button"
          onClick={() => refilter(() => setTrashed(!trashed))}
          aria-pressed={trashed}
          className={`ml-auto rounded-md border px-3 py-1 text-sm ${trashed ? 'bg-destructive/10 border-destructive/40' : 'hover:bg-accent'}`}
        >
          {trashed ? '휴지통 보는 중 — 작업으로' : '휴지통'}
        </button>
      </div>
      <ErrorNotice error={page.error ?? accounts.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title={trashed ? '휴지통이 비었습니다' : '맞는 작업이 없습니다'}
          hint="사람 · 찾는 말(만든 사람의 이름도 찾습니다) · 종류 · 꼬리표를 바꿔 보세요."
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>만든 사람</TableHead>
                <TableHead>종류</TableHead>
                <TableHead>버전</TableHead>
                <TableHead>승격</TableHead>
                <TableHead>{trashed ? '지움' : '수정'}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <Link to={`/works/${row.id}`} className="font-medium hover:underline">
                      {row.name}
                    </Link>
                    {row.folder && <span className="text-muted-foreground ml-2 text-xs">{row.folder}</span>}
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
                    <button type="button" className="hover:underline" onClick={() => pickOwner(row.owner_id)}>
                      {row.owner_name}
                    </button>
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
                    {shownDateTime(trashed && row.deleted_at ? row.deleted_at : row.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {page.data && (
            <Pagination total={page.data.total} limit={page.data.limit} offset={page.data.offset} onChange={setOffset} />
          )}
        </>
      )}
    </div>
  )
}
