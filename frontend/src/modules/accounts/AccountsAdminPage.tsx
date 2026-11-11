/** 계정 관리 — 시스템 관리자만. 임시 비밀번호는 응답에서 한 번만 나오므로 화면에 바로 띄운다. */

import { Mail } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

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
import { Textarea } from '@/shared/components/ui/textarea'
import { useResource } from '@/shared/hooks/useResource'
import { copyText } from '@/shared/lib/clipboard'
import { shownDate } from '@/shared/lib/datetime'

const MAIL = /^[^\s@]+@[^\s@]+$/

/**
 * 받는 사람 칸에 그대로 붙일 주소 목록 — `; ` 로 잇는다(Outlook 은 쌍반점을 늘 받고, Gmail 도
 * 붙여 넣으면 나눈다). 아이디가 메일 주소가 아닌 계정은 빼고 알려 준다. 같은 주소는 한 번.
 */
export function mailList(accounts: Account[]): { text: string; count: number; skipped: string[] } {
  const seen = new Set<string>()
  const out: string[] = []
  const skipped: string[] = []
  for (const one of accounts) {
    const address = one.email.trim()
    if (!MAIL.test(address)) {
      skipped.push(address)
      continue
    }
    if (seen.has(address.toLowerCase())) continue
    seen.add(address.toLowerCase())
    out.push(address)
  }
  return { text: out.join('; '), count: out.length, skipped }
}

/** 자동 복사가 막혔을 때 — 주소를 골라 둔 채로 보여 주고 Ctrl+C 로 복사하게 한다. */
function ManualCopyDialog({ text, onClose }: { text: string; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>메일 주소</DialogTitle>
          <DialogDescription>
            브라우저가 자동 복사를 허용하지 않았습니다. 아래 주소가 선택된 상태에서 Ctrl+C(맥은 ⌘+C)로 복사하십시오.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          readOnly
          autoFocus
          value={text}
          onFocus={(event) => event.currentTarget.select()}
          className="h-32 font-mono text-xs"
          aria-label="복사할 메일 주소"
        />
        <DialogFooter>
          <Button onClick={onClose}>닫기</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function TemporaryPasswordNotice({ value, onClose }: { value: string; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>임시 비밀번호</DialogTitle>
          <DialogDescription>
            이 비밀번호는 지금 한 번만 표시됩니다. 해당 사용자에게 전달하십시오. 첫 로그인 시 비밀번호를 변경해야 합니다.
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
  const accounts = useResource(() => accountsApi.all(), [])
  const [creating, setCreating] = useState(false)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [asAdmin, setAsAdmin] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [temporary, setTemporary] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<Account | null>(null)
  /** 메일을 보낼 계정 — 고른 것의 주소를 한 번에 복사한다. */
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [mailNote, setMailNote] = useState<string | null>(null)
  const [manual, setManual] = useState<string | null>(null)

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
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    }
  }

  async function act(work: () => Promise<unknown>) {
    setError(null)
    try {
      await work()
      accounts.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    }
  }

  const rows = accounts.data ?? []
  const chosen = rows.filter((row) => picked.has(row.id))
  const allPicked = rows.length > 0 && chosen.length === rows.length

  function pick(next: Set<string>) {
    setPicked(next)
    setMailNote(null)
  }

  async function copyMails() {
    const { text, count, skipped } = mailList(chosen)
    const left = skipped.length > 0 ? ` 메일 주소가 아닌 아이디 ${skipped.length}개(${skipped.join(', ')})는 제외했습니다.` : ''
    if (count === 0) {
      setMailNote(`복사할 메일 주소가 없습니다.${left}`)
      return
    }
    try {
      await copyText(text)
      setMailNote(`메일 주소 ${count}개를 복사했습니다. 메일의 받는 사람 칸에 붙여 넣으십시오.${left}`)
    } catch {
      setManual(text)
      setMailNote(left.trim() || null)
    }
  }

  return (
    <div>
      <PageHeader
        title="계정"
        description="계정을 생성하고 관리합니다. 계정을 삭제하면 로그인만 차단되며, 해당 사용자가 생성한 데이터는 유지됩니다."
        actions={<Button onClick={() => setCreating(true)}>계정 생성</Button>}
      />
      <ErrorNotice error={error ?? accounts.error} className="mb-4" />

      {rows.length === 0 && !accounts.loading ? (
        <EmptyState title="계정이 없습니다" hint="오른쪽 위의 ‘계정 생성’ 버튼으로 첫 계정을 생성하십시오." />
      ) : (
        <>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={chosen.length === 0} onClick={() => void copyMails()}>
            <Mail className="size-3.5" />
            메일 주소 복사{chosen.length > 0 && ` (${chosen.length})`}
          </Button>
          <span className="text-muted-foreground text-xs" role="status">
            {mailNote ?? (chosen.length === 0 ? '메일을 보낼 계정을 선택하십시오. 맨 위 칸으로 전체를 선택합니다.' : '')}
          </span>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8">
                <input
                  type="checkbox"
                  aria-label="전체 선택"
                  checked={allPicked}
                  onChange={() => pick(allPicked ? new Set() : new Set(rows.map((row) => row.id)))}
                />
              </TableHead>
              <TableHead>아이디</TableHead>
              <TableHead>이름</TableHead>
              <TableHead>상태</TableHead>
              <TableHead>권한</TableHead>
              <TableHead>생성일</TableHead>
              <TableHead className="text-right">관리</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const self = row.id === me?.id
              return (
                <TableRow key={row.id}>
                  <TableCell>
                    <input
                      type="checkbox"
                      aria-label={`${row.email} 선택`}
                      checked={picked.has(row.id)}
                      onChange={() => {
                        const next = new Set(picked)
                        if (next.has(row.id)) next.delete(row.id)
                        else next.add(row.id)
                        pick(next)
                      }}
                    />
                  </TableCell>
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
                    {/* 이 사람의 내 작업 — 모든 작업 화면에서 이 사람으로 거른다. */}
                    <Button size="sm" variant="outline" asChild>
                      <Link to={`/admin/works?owner=${row.id}`}>작업</Link>
                    </Button>
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
        </>
      )}

      {manual && <ManualCopyDialog text={manual} onClose={() => setManual(null)} />}

      <Dialog open={creating} onOpenChange={(open) => !open && setCreating(false)}>
        <DialogContent>
          <form onSubmit={create} className="space-y-4">
            <DialogHeader>
              <DialogTitle>계정 생성</DialogTitle>
              <DialogDescription>임시 비밀번호가 생성되며, 첫 로그인 시 비밀번호를 변경해야 합니다.</DialogDescription>
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
              시스템 관리자 권한 부여
            </label>
            <ErrorNotice error={error} />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreating(false)}>
                취소
              </Button>
              <Button type="submit">생성</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {temporary && <TemporaryPasswordNotice value={temporary} onClose={() => setTemporary(null)} />}

      <ConfirmDialog
        open={deleting !== null}
        title="계정 삭제"
        description={
          <>
            <b>{deleting?.email}</b> 계정을 삭제하시겠습니까? 삭제된 계정으로는 더 이상 로그인할 수 없습니다. 해당
            사용자가 생성한 데이터는 유지되며, 소유자 이름도 그대로 표시됩니다.
          </>
        }
        confirmLabel="삭제"
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
