/** 내 작업 — 종류에 무관하게 걸었던 일 전부. 산출물은 여기서 다시 받는다. */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { jobsApi, runState } from '@/modules/jobs/api'
import { CancelJobButton } from '@/modules/jobs/CancelJobButton'
import type { Job } from '@/modules/jobs/api'
import { downloadFile } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
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
import { useDisplay } from '@/shared/api/display'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'


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
  const PAGE = useDisplay().list_page_size
  const { user } = useAuth()
  const admin = isSystemAdmin(user)
  /** 시스템 관리자는 모든 사용자의 실행 기록도 조회한다(서버의 `mine=false`) — 「모든 작업」 과 같은 권한. */
  const [everyone, setEveryone] = useState(false)
  const all = admin && everyone
  const page = useResource(() => jobsApi.list({ mine: !all, offset, limit: PAGE }), [offset, PAGE, all])
  const rows = page.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="실행 기록"
        description={
          all
            ? '모든 사용자가 실행한 작업의 기록입니다. 시스템 관리자만 조회할 수 있습니다.'
            : '본인이 실행한 모든 작업(부품 평가, 지그 생성)의 기록입니다. 향후 AI 편집 작업도 이곳에 표시됩니다.'
        }
      />
      {admin && (
        <div className="mb-4 flex items-center gap-1" role="group" aria-label="조회 범위">
          {(
            [
              { value: false, label: '내 실행' },
              { value: true, label: '전체 사용자' },
            ] as const
          ).map((one) => (
            <button
              key={one.label}
              type="button"
              aria-pressed={everyone === one.value}
              onClick={() => {
                setEveryone(one.value)
                setOffset(0)
              }}
              className={`rounded-md border px-3 py-1 text-sm ${
                everyone === one.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
              }`}
            >
              {one.label}
            </button>
          ))}
        </div>
      )}
      <ErrorNotice error={page.error} className="mb-4" />

      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title="실행한 작업이 없습니다"
          hint="내 작업에서 부품을 저장하거나 지그를 생성하면 이곳에 기록됩니다."
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>요청 일시</TableHead>
                {all && <TableHead>요청자</TableHead>}
                <TableHead>종류</TableHead>
                <TableHead>작업</TableHead>
                <TableHead>상태</TableHead>
                <TableHead>소요 시간</TableHead>
                <TableHead>산출물</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((job) => (
                <TableRow key={job.id}>
                  <TableCell className="text-sm">{shownDateTime(job.created_at)}</TableCell>
                  {all && <TableCell className="text-sm">{job.requested_by_name ?? '—'}</TableCell>}
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
                    <StatusBadge kind="run" value={runState(job)} />
                    {job.error && (
                      <p className="text-destructive mt-1 max-w-xs truncate text-xs" title={job.error}>
                        {job.error}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{elapsed(job)}</TableCell>
                  <TableCell className="space-x-1">
                    <CancelJobButton job={job} onCancelled={page.reload} />
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
