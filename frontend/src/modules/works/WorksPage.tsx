/** 내 작업 — 내 공간의 문서들. 여기 있는 것은 나(와 관리자)만 본다. */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { worksApi } from '@/modules/works/api'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Button } from '@/shared/components/ui/button'
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

export default function WorksPage() {
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  const page = useResource(() => worksApi.list(offset, PAGE), [offset])
  const rows = page.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="내 작업"
        description="그리고 있는 것들. 나만 봅니다 — 남에게 보이려면 부품이나 지그로 승격합니다."
        actions={<Button onClick={() => navigate('/draw')}>새로 그리기</Button>}
      />
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title="작업이 없습니다"
          hint="「그리기」 에서 템플릿으로 그리거나 STEP 을 올려 시작하세요."
          action={<Button onClick={() => navigate('/draw')}>그리러 가기</Button>}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>부품</TableHead>
                <TableHead>지그 생성</TableHead>
                <TableHead>승격</TableHead>
                <TableHead>수정</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <Link to={`/works/${row.id}`} className="font-medium hover:underline">
                      {row.name}
                    </Link>
                    {row.description && (
                      <p className="text-muted-foreground max-w-md truncate text-xs">{row.description}</p>
                    )}
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
                  <TableCell className="text-sm">{shownDateTime(row.updated_at)}</TableCell>
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
