/** 실험계획 목록 — 어떤 모델의 무엇을 훑었나. */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { doeApi, methodBadge } from '@/modules/doe/api'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { Badge } from '@/shared/components/ui/badge'
import { SearchBox } from '@/shared/components/SearchBox'
import { TagFilter } from '@/shared/components/TagFilter'
import { Button } from '@/shared/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'
import { useDisplay } from '@/shared/api/display'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'


const KIND_LABEL: Record<string, string> = { part: '부품', jig: '지그', assembly: '조립' }

export default function DoeStudiesPage() {
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  /** 내 것 / 모두 — 남이 같은 훑기를 이미 돌았는지 보려면 「모두」. 찾기 · 꼬리표는 서버가 거른다. */
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const PAGE = useDisplay().list_page_size
  const page = useResource(() => doeApi.list({ offset, limit: PAGE, scope, q, tag }), [offset, PAGE, scope, q, tag])
  const tags = useResource(() => doeApi.tags(scope), [scope, page.data])
  const rows = page.data?.items ?? []
  const filtered = Boolean(q || tag)

  function refilter(apply: () => void) {
    apply()
    setOffset(0)
  }

  return (
    <div>
      <PageHeader
        title="DOE"
        description="부품 · 지그 · 조립 하나를 골라 변수에 범위를 주면 형상을 여럿 만듭니다. 다 만든 뒤 「보내기」 로 공유 폴더에 — 해석(ANSYS)은 그 폴더를 읽습니다."
        actions={<Button onClick={() => navigate('/doe/new')}>새 DOE</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          {(
            [
              { value: 'mine', label: '내 것' },
              { value: 'all', label: '모두' },
            ] as const
          ).map((one) => (
            <button
              key={one.value}
              type="button"
              onClick={() => refilter(() => setScope(one.value))}
              aria-pressed={scope === one.value}
              className={`rounded-md border px-3 py-1 text-sm ${scope === one.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}
            >
              {one.label}
            </button>
          ))}
        </div>
        <SearchBox value={q} onChange={(next) => refilter(() => setQ(next))} placeholder="이름 · 설명 · 대상 작업 · 만든 사람" />
        <TagFilter tags={tags.data ?? []} value={tag} onChange={(next) => refilter(() => setTag(next))} label="대상 작업의 꼬리표" />
      </div>
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        filtered || scope === 'all' ? (
          <EmptyState title="맞는 DOE 가 없습니다" hint="찾는 말 · 꼬리표를 바꾸거나 「모두」 로 남이 공개한 것까지 보세요." />
        ) : (
          <EmptyState
            title="아직 DOE 가 없습니다"
            hint="「새 DOE」 로 대상(부품 · 지그 · 조립)을 고르면 시작합니다. 도면에 변수가 먼저 있어야 합니다."
            action={<Button onClick={() => navigate('/doe/new')}>새 DOE</Button>}
          />
        )
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
                    <Badge variant="outline">{methodBadge(row)}</Badge>
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
