/** 지그 프로젝트 목록 — 제품 하나가 프로젝트 하나다. */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { jigsApi } from '@/modules/jigs/api'
import { ApiError } from '@/shared/api/client'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Textarea } from '@/shared/components/ui/textarea'
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

export default function JigProjectsPage() {
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  const page = useResource(() => jigsApi.list(offset, PAGE), [offset])
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  async function create(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const made = await jigsApi.create({ name, description, product_spec: null })
      navigate(`/jigs/${made.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  const rows = page.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="지그 프로젝트"
        description="제품 STEP 을 올리거나 기본 도형을 골라 지그를 만듭니다. 파일이 없으면 시연 제품으로 돕니다."
        actions={<Button onClick={() => setCreating(true)}>새 프로젝트</Button>}
      />
      <ErrorNotice error={page.error} className="mb-4" />

      {rows.length === 0 && !page.loading ? (
        <EmptyState
          title="프로젝트가 없습니다"
          hint="새 프로젝트를 만들고 제품 STEP 을 올리거나, 파일 없이 바로 지그를 만들어 보세요."
          action={<Button onClick={() => setCreating(true)}>새 프로젝트</Button>}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>제품</TableHead>
                <TableHead>소유자</TableHead>
                <TableHead>실행</TableHead>
                <TableHead>마지막 상태</TableHead>
                <TableHead>수정</TableHead>
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
                  <TableCell className="text-muted-foreground text-sm">
                    {row.product_filename ??
                      (row.product_spec ? `도형: ${String(row.product_spec.kind)}` : '시연 제품')}
                  </TableCell>
                  <TableCell>{row.owner_name}</TableCell>
                  <TableCell>{row.run_count}</TableCell>
                  <TableCell>
                    {row.last_run_status ? <StatusBadge kind="run" value={row.last_run_status} /> : '—'}
                  </TableCell>
                  <TableCell className="text-sm">{shownDateTime(row.updated_at)}</TableCell>
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

      <Dialog open={creating} onOpenChange={(open) => !open && !busy && setCreating(false)}>
        <DialogContent>
          <form onSubmit={create} className="space-y-4">
            <DialogHeader>
              <DialogTitle>새 프로젝트</DialogTitle>
              <DialogDescription>제품 파일은 만든 뒤에 올립니다.</DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="name">이름</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
            </div>
            <div className="space-y-2">
              <Label htmlFor="desc">설명</Label>
              <Textarea id="desc" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <ErrorNotice error={error} />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreating(false)} disabled={busy}>
                취소
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? '만드는 중…' : '만들기'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
