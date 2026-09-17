/** 계정 관리 — 시스템 관리자만. 임시 비밀번호는 응답에서 한 번만 나오므로 화면에 바로 띄운다. */

import { useState } from 'react'
import type { FormEvent } from 'react'

import { accountsApi } from '@/modules/accounts/api'
import { ApiError } from '@/shared/api/client'
import type { Account } from '@/shared/api/types'
import { useAuth } from '@/shared/auth/AuthContext'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { shownDate } from '@/shared/lib/datetime'

function TemporaryPasswordNotice({ value, onClose }: { value: string; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>임시 비밀번호</DialogTitle>
          <DialogDescription>
            지금 한 번만 보입니다. 본인에게 전달하세요 — 첫 로그인에서 바꾸게 됩니다.
          </DialogDescription>
        </DialogHeader>
        <p className="bg-muted rounded-md p-3 font-mono text-lg select-all">{value}</p>
        <DialogFooter>
          <Button onClick={onClose}>닫기</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function AccountsAdminPage() {
  const { user: me } = useAuth()
  const accounts = useResource(() => accountsApi.list(), [])
  const [creating, setCreating] = useState(false)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [asAdmin, setAsAdmin] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [temporary, setTemporary] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<Account | null>(null)

  async function create(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      const made = await accountsApi.create({ email, display_name: name, is_system_admin: asAdmin })
      setCreating(false)
      setEmail('')
      setName('')
      setAsAdmin(false)
      setTemporary(made.temporary_password)
      accounts.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  async function act(work: () => Promise<unknown>) {
    setError(null)
    try {
      await work()
      accounts.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  const rows = accounts.data ?? []

  return (
    <div>
      <PageHeader
        title="계정"
        description="계정은 여기서 만듭니다. 지우면 접근만 끊기고 그 사람의 프로젝트는 남습니다."
        actions={<Button onClick={() => setCreating(true)}>계정 만들기</Button>}
      />
      <ErrorNotice error={error ?? accounts.error} className="mb-4" />

      {rows.length === 0 && !accounts.loading ? (
        <EmptyState title="계정이 없습니다" hint="오른쪽 위에서 첫 계정을 만드세요." />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>아이디</TableHead>
              <TableHead>이름</TableHead>
              <TableHead>상태</TableHead>
              <TableHead>권한</TableHead>
              <TableHead>만든 날</TableHead>
              <TableHead className="text-right">동작</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const self = row.id === me?.id
              return (
                <TableRow key={row.id}>
                  <TableCell className="font-mono text-xs">{row.email}</TableCell>
                  <TableCell>{row.display_name}</TableCell>
                  <TableCell>
                    <StatusBadge kind="account" value={row.status} />
                    {row.must_change_password && (
                      <span className="text-muted-foreground ml-2 text-xs">임시 비밀번호</span>
                    )}
                  </TableCell>
                  <TableCell>{row.is_system_admin ? '시스템 관리자' : '사용자'}</TableCell>
                  <TableCell>{shownDate(row.created_at)}</TableCell>
                  <TableCell className="space-x-1 text-right">
                    {row.status === 'active' ? (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={self}
                        onClick={() => act(() => accountsApi.suspend(row.id))}
                      >
                        정지
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => act(() => accountsApi.activate(row.id))}
                      >
                        복구
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={self}
                      onClick={() => act(() => accountsApi.setSystemAdmin(row.id, !row.is_system_admin))}
                    >
                      {row.is_system_admin ? '관리자 해제' : '관리자 지정'}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        act(async () => {
                          const made = await accountsApi.resetPassword(row.id)
                          setTemporary(made.temporary_password)
                        })
                      }
                    >
                      비밀번호 초기화
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={self}
                      onClick={() => setDeleting(row)}
                    >
                      삭제
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}

      <Dialog open={creating} onOpenChange={(open) => !open && setCreating(false)}>
        <DialogContent>
          <form onSubmit={create} className="space-y-4">
            <DialogHeader>
              <DialogTitle>계정 만들기</DialogTitle>
              <DialogDescription>임시 비밀번호가 만들어지고, 첫 로그인에서 바꾸게 됩니다.</DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="new-email">아이디</Label>
              <Input id="new-email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-name">이름</Label>
              <Input id="new-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={asAdmin} onChange={(e) => setAsAdmin(e.target.checked)} />
              시스템 관리자로 만든다
            </label>
            <ErrorNotice error={error} />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreating(false)}>
                취소
              </Button>
              <Button type="submit">만들기</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {temporary && <TemporaryPasswordNotice value={temporary} onClose={() => setTemporary(null)} />}

      <ConfirmDialog
        open={deleting !== null}
        title="계정을 지웁니다"
        description={
          <>
            <b>{deleting?.email}</b> 은 더 이상 로그인할 수 없습니다. 이 사람이 만든 지그
            프로젝트는 남고, 소유자 이름은 그대로 보입니다.
          </>
        }
        confirmLabel="지우기"
        destructive
        onConfirm={async () => {
          if (deleting) await accountsApi.remove(deleting.id)
          setDeleting(null)
          accounts.reload()
        }}
        onClose={() => setDeleting(null)}
      />
    </div>
  )
}
