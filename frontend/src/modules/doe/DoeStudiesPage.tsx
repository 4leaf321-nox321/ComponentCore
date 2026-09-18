/** 실험계획 목록 — 어떤 모델의 무엇을 훑었나. */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { doeApi } from '@/modules/doe/api'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { Badge } from '@/shared/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

const PAGE = 20

export default function DoeStudiesPage() {
  const [offset, setOffset] = useState(0)
  const page = useResource(() => doeApi.list({ offset, limit: PAGE }), [offset])
  const rows = page.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="실험계획 (DOE)"
        description="치수 범위에서 형상을 여러 벌 만들어 공유 폴더에 쏟아 놓습니다. 해석(ANSYS)은 그 폴더를 읽습니다."
      />
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title="아직 실험계획이 없습니다"
          hint="내 작업의 「실험계획」 탭에서 치수에 범위를 주면 시작합니다. 레시피에 이름 붙인 치수가 먼저 있어야 합니다."
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>방법</TableHead>
                <TableHead>설계점</TableHead>
                <TableHead>재료</TableHead>
                <TableHead>만든 때</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <Link to={`/doe/${row.id}`} className="font-medium hover:underline">
                      {row.name}
                    </Link>
                    {row.description && <p className="text-muted-foreground truncate text-xs">{row.description}</p>}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{row.method === 'factorial' ? '전체 조합' : `LHS · 시드 ${row.seed}`}</Badge>
                  </TableCell>
                  <TableCell>{row.point_count}</TableCell>
                  <TableCell>{row.material}</TableCell>
                  <TableCell>{shownDateTime(row.created_at)}</TableCell>
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
