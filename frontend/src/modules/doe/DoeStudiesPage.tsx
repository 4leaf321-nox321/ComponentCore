/** 실험계획 목록 — 어떤 모델의 무엇을 훑었나. */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { doeApi } from '@/modules/doe/api'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'
import { useDisplay } from '@/shared/api/display'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'


const KIND_LABEL: Record<string, string> = { part: '부품', jig: '지그', assembly: '조립' }

export default function DoeStudiesPage() {
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  const PAGE = useDisplay().list_page_size
  const page = useResource(() => doeApi.list({ offset, limit: PAGE }), [offset, PAGE])
  const rows = page.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="DOE"
        description="부품 · 지그 · 조립 하나를 골라 변수에 범위를 주면 형상을 여럿 만듭니다. 다 만든 뒤 「보내기」 로 공유 폴더에 — 해석(ANSYS)은 그 폴더를 읽습니다."
        actions={<Button onClick={() => navigate('/doe/new')}>새 DOE</Button>}
      />
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title="아직 DOE 가 없습니다"
          hint="「새 DOE」 로 대상(부품 · 지그 · 조립)을 고르면 시작합니다. 도면에 변수가 먼저 있어야 합니다."
          action={<Button onClick={() => navigate('/doe/new')}>새 DOE</Button>}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>대상</TableHead>
                <TableHead>방법</TableHead>
                <TableHead>설계점</TableHead>
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
                    {row.work_id ? (
                      <Link to={`/works/${row.work_id}`} className="hover:underline">
                        {row.work_name}{' '}
                        <Badge variant="outline" className="ml-1">
                          {KIND_LABEL[row.work_kind ?? ''] ?? row.work_kind}
                        </Badge>
                      </Link>
                    ) : (
                      <span className="text-muted-foreground text-xs">스냅샷만</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{row.method === 'factorial' ? '전체 조합' : `LHS · 시드 ${row.seed}`}</Badge>
                  </TableCell>
                  <TableCell>{row.point_count}</TableCell>
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
