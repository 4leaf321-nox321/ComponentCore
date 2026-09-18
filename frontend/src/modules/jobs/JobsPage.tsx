/** 내 작업 — 종류에 무관하게 걸었던 일 전부. 산출물은 여기서 다시 받는다. */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { jobsApi } from '@/modules/jobs/api'
import type { Job } from '@/modules/jobs/api'
import { downloadFile } from '@/shared/api/client'
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

const KIND_LABELS: Record<string, string> = { jig: '지그 생성', cad: '부품 평가' }

const ARTIFACT_LABELS: Record<string, string> = {
  jig_step: '지그 STEP',
  assembly_step: '지그+제품 STEP',
  jig_stl: '지그 STL',
  model_step: '부품 STEP',
}

function elapsed(job: Job): string {
  if (!job.started_at || !job.finished_at) return '—'
  const ms = new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

export default function JobsPage() {
  const [offset, setOffset] = useState(0)
  const page = useResource(() => jobsApi.list({ mine: true, offset, limit: PAGE }), [offset])
  const rows = page.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="실행 기록"
        description="내가 건 작업 전부 — 부품 평가 · 지그 생성. 앞으로 AI 편집도 여기 온다."
      />
      <ErrorNotice error={page.error} className="mb-4" />

      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title="아직 건 작업이 없습니다"
          hint="내 작업에서 부품을 저장하거나 지그를 만들면 여기 쌓입니다."
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>걸린 때</TableHead>
                <TableHead>종류</TableHead>
                <TableHead>작업</TableHead>
                <TableHead>상태</TableHead>
                <TableHead>걸린 시간</TableHead>
                <TableHead>산출물</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((job) => (
                <TableRow key={job.id}>
                  <TableCell className="text-sm">{shownDateTime(job.created_at)}</TableCell>
                  <TableCell>{KIND_LABELS[job.kind] ?? job.kind}</TableCell>
                  <TableCell>
                    {job.work_id ? (
                      <Link to={`/works/${job.work_id}`} className="hover:underline">
                        {job.work_name ?? '(이름 없음)'}
                      </Link>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge kind="run" value={job.status} />
                    {job.error && (
                      <p className="text-destructive mt-1 max-w-xs truncate text-xs" title={job.error}>
                        {job.error}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{elapsed(job)}</TableCell>
                  <TableCell className="space-x-1">
                    {job.artifacts
                      .filter((one) => one.kind in ARTIFACT_LABELS)
                      .map((one) => (
                        <Button
                          key={one.id}
                          size="sm"
                          variant="outline"
                          onClick={() => downloadFile(jobsApi.artifactPath(one.id), one.filename)}
                        >
                          {ARTIFACT_LABELS[one.kind]}
                        </Button>
                      ))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {page.data && (
            <Pagination
              total={page.data.total}
              limit={page.data.limit}
              offset={page.data.offset}
              onChange={setOffset}
            />
          )}
        </>
      )}
    </div>
  )
}
