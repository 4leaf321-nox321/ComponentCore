/** 내 작업 — 내 공간의 문서들. 여기 있는 것은 나(와 관리자)만 본다. */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { worksApi } from '@/modules/works/api'
import type { WorkKind } from '@/modules/works/api'
import { AssembleDialog } from '@/modules/works/AssembleDialog'
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
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

const PAGE = 20

export default function WorksPage() {
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  /** 「내 지그가 어디 있지」 를 한 번에 — 종류로 가려 본다. */
  const [kind, setKind] = useState<'all' | WorkKind>('all')
  const [starting, setStarting] = useState(false)
  const [assembling, setAssembling] = useState(false)
  const page = useResource(() => worksApi.list(offset, PAGE), [offset])

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
  const all = page.data?.items ?? []
  const rows = kind === 'all' ? all : all.filter((one) => one.kind === kind)

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
      <div className="mb-4 flex items-center gap-1">
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
            onClick={() => setKind(one.value)}
            aria-pressed={kind === one.value}
            className={`rounded-md border px-3 py-1 text-sm ${
              kind === one.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
            }`}
          >
            {one.label}
            {one.value !== 'all' && (
              <span className="ml-1 text-xs opacity-70">{all.filter((row) => row.kind === one.value).length}</span>
            )}
          </button>
        ))}
      </div>
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title="작업이 없습니다"
          hint="「새 작업」 에서 빈 화면 · 템플릿 · STEP 으로 그려 저장하세요."
          action={<Button onClick={() => navigate('/draw')}>새 작업 만들기</Button>}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>종류</TableHead>
                <TableHead>버전</TableHead>
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
      <AssembleDialog key={String(assembling)} open={assembling} onClose={() => setAssembling(false)} onMade={(id) => navigate(`/works/${id}`)} />
    </div>
  )
}
