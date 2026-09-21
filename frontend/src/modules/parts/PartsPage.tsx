/** 부품 카탈로그 — 승격된 부품. 로그인한 누구나 본다. */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { partsApi } from '@/modules/parts/api'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { SearchBox } from '@/shared/components/SearchBox'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useDisplay } from '@/shared/api/display'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'


export default function PartsPage() {
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')
  const PAGE = useDisplay().list_page_size
  const page = useResource(() => partsApi.list(offset, PAGE, q), [offset, q, PAGE])
  const rows = page.data?.items ?? []

  return (
    <div>
      <PageHeader title="부품" description="내 작업에서 승격된 부품. 버전은 바뀌지 않고, 고치려면 내 공간으로 복사합니다." />
      <div className="mb-4">
        <SearchBox value={q} onChange={(next) => { setQ(next); setOffset(0) }} />
      </div>
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        <EmptyState title="아직 올라온 부품이 없습니다" hint="내 작업의 부품 탭에서 「부품으로 승격」 하면 여기 뜹니다." />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>버전</TableHead>
                <TableHead>지그</TableHead>
                <TableHead>올린 사람</TableHead>
                <TableHead>갱신</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <Link to={`/parts/${row.id}`} className="font-medium hover:underline">
                      {row.name}
                    </Link>
                    {row.description && <p className="text-muted-foreground max-w-md truncate text-xs">{row.description}</p>}
                  </TableCell>
                  <TableCell>v{row.current_version}</TableCell>
                  <TableCell>{row.jig_count}</TableCell>
                  <TableCell>{row.owner_name}</TableCell>
                  <TableCell className="text-sm">{shownDateTime(row.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {page.data && <Pagination total={page.data.total} limit={page.data.limit} offset={page.data.offset} onChange={setOffset} />}
        </>
      )}
    </div>
  )
}
