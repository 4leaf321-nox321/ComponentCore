/** 지그 카탈로그 — 승격된 지그. 로그인한 누구나 본다. */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { jigsApi } from '@/modules/jigs/api'
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
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

const PAGE = 20

export default function JigsPage() {
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')
  const page = useResource(() => jigsApi.list({ offset, limit: PAGE, q }), [offset, q])
  const rows = page.data?.items ?? []

  return (
    <div>
      <PageHeader title="지그" description="내 작업에서 승격된 지그. 어느 부품 버전의 지그인지 함께 적혀 있습니다." />
      <div className="mb-4">
        <SearchBox value={q} onChange={(next) => { setQ(next); setOffset(0) }} />
      </div>
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        <EmptyState title="아직 올라온 지그가 없습니다" hint="내 작업의 지그 탭에서 결과를 「지그로 승격」 하면 여기 뜹니다." />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
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
                <TableRow key={row.id}>
                  <TableCell>
                    <Link to={`/jigs/${row.id}`} className="font-medium hover:underline">
                      {row.name}
                    </Link>
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
          {page.data && <Pagination total={page.data.total} limit={page.data.limit} offset={page.data.offset} onChange={setOffset} />}
        </>
      )}
    </div>
  )
}
