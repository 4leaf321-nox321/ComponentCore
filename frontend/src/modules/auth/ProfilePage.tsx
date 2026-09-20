/** 내 정보 — 표시 이름만 바꾼다. 아이디는 로그인 식별자라 관리자의 일이다. */

import { useState } from 'react'
import type { FormEvent } from 'react'

import { TokensPanel } from '@/modules/auth/TokensPanel'
import { ApiError, api } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

export default function ProfilePage() {
  const { user, reload } = useAuth()
  const [name, setName] = useState(user?.display_name ?? '')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      await api.patch('/auth/me', { display_name: name })
      await reload()
      setSaved(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-8">
      <PageHeader title="내 정보" description="표시 이름과 개인 토큰 — AI 도구(Claude · Gemini · Codex)를 붙이는 열쇠." />
      <form onSubmit={submit} className="max-w-lg space-y-4">
        <div className="space-y-2">
          <Label>아이디</Label>
          <Input value={user?.email ?? ''} disabled />
        </div>
        <div className="space-y-2">
          <Label htmlFor="name">표시 이름</Label>
          <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <ErrorNotice error={error} />
        {saved && <p className="text-muted-foreground text-sm">저장했습니다.</p>}
        <Button type="submit" disabled={busy}>
          {busy ? '저장 중…' : '저장'}
        </Button>
      </form>
      <TokensPanel />
    </div>
  )
}
