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
    <div className="space-y-6">
      <PageHeader title="내 정보" description="표시 이름과 개인 토큰 — AI 도구(Claude · Gemini · Codex)를 붙이는 열쇠." />
      {/* 표시 이름은 한 줄이면 된다 — 토큰 · 등록 방법이 화면을 넓게 쓴다. */}
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 space-y-1">
          <Label>아이디</Label>
          <Input value={user?.email ?? ''} disabled />
        </div>
        <div className="min-w-56 space-y-1">
          <Label htmlFor="name">표시 이름</Label>
          <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <Button type="submit" disabled={busy}>
          {busy ? '저장 중…' : '저장'}
        </Button>
        {saved && <p className="text-muted-foreground text-sm">저장했습니다.</p>}
        <ErrorNotice error={error} className="w-full" />
      </form>
      <TokensPanel />
    </div>
  )
}
