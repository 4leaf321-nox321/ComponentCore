/**
 * 개인 토큰 — MCP(AI) · 스크립트가 API 를 부르는 자격 증명. 평문은 발급 응답에서 한 번만 보인다.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, api } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

interface Pat {
  id: string
  name: string
  prefix: string
  scopes: string[]
  created_at: string
  expires_at: string | null
  last_used_at: string | null
  revoked_at: string | null
}

const SCOPE_LABELS: Record<string, string> = { read: '읽기', write: '쓰기' }

export function TokensPanel() {
  const tokens = useResource(() => api.get<Pat[]>('/auth/tokens'), [])
  const scopes = useResource(
    () => api.get<{ scopes: string[]; descriptions: Record<string, string> }>('/auth/token-scopes'),
    [],
  )
  const [name, setName] = useState('Claude Code')
  const [chosen, setChosen] = useState<string[]>(['read', 'write'])
  const [days, setDays] = useState('')
  const [issued, setIssued] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  async function issue(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const made = await api.post<{ token: string }>('/auth/tokens', {
        name,
        scopes: chosen,
        expires_in_days: days ? Number(days) : null,
      })
      setIssued(made.token)
      tokens.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  async function revoke(id: string) {
    setError(null)
    try {
      await api.delete(`/auth/tokens/${id}`)
      tokens.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  const live = (tokens.data ?? []).filter((one) => !one.revoked_at)

  return (
    <Card>
      <CardHeader>
        <CardTitle>개인 토큰 — MCP(AI) · 스크립트용</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-muted-foreground text-sm">
          Claude Code 같은 AI 를 이 플랫폼에 붙일 때 씁니다. 토큰은 <b>내 권한</b>으로 동작하고, AI 가 만든
          것은 내 작업에 출처 「AI」 로 쌓입니다. 발급하면 아래 명령으로 등록하세요:
        </p>
        <pre className="bg-muted overflow-x-auto rounded-md p-3 text-xs">
          {`claude mcp add --transport http autojig http://<서버>:8062/mcp \\\n  --header "Authorization: Bearer <토큰>"`}
        </pre>

        <form onSubmit={issue} className="grid gap-3 md:grid-cols-4">
          <div className="space-y-1">
            <Label htmlFor="pat-name">이름</Label>
            <Input id="pat-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="space-y-1">
            <Label>범위</Label>
            <div className="flex gap-3 pt-2 text-sm">
              {(scopes.data?.scopes ?? ['read', 'write']).map((scope) => (
                <label key={scope} className="flex items-center gap-1" title={scopes.data?.descriptions[scope]}>
                  <input
                    type="checkbox"
                    checked={chosen.includes(scope)}
                    onChange={(e) =>
                      setChosen(e.target.checked ? [...chosen, scope] : chosen.filter((s) => s !== scope))
                    }
                  />
                  {SCOPE_LABELS[scope] ?? scope}
                </label>
              ))}
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="pat-days">만료 (일, 비우면 없음)</Label>
            <Input id="pat-days" type="number" min={1} value={days} onChange={(e) => setDays(e.target.value)} />
          </div>
          <div className="flex items-end">
            <Button type="submit" disabled={busy || chosen.length === 0}>
              발급
            </Button>
          </div>
        </form>
        <ErrorNotice error={error ?? tokens.error} />

        {issued && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3">
            <p className="text-sm font-medium">지금 한 번만 보입니다 — 복사해 두세요.</p>
            <p className="mt-1 font-mono text-xs break-all select-all">{issued}</p>
            <Button size="sm" variant="ghost" className="mt-2" onClick={() => setIssued(null)}>
              닫기
            </Button>
          </div>
        )}

        {live.length > 0 && (
          <ul className="divide-y rounded-md border text-sm">
            {live.map((one) => (
              <li key={one.id} className="flex items-center gap-3 px-3 py-2">
                <span className="font-medium">{one.name}</span>
                <span className="text-muted-foreground font-mono text-xs">{one.prefix}…</span>
                <span className="text-muted-foreground text-xs">
                  {one.scopes.map((s) => SCOPE_LABELS[s] ?? s).join(' · ')}
                </span>
                <span className="text-muted-foreground text-xs">
                  {one.last_used_at ? `마지막 사용 ${shownDateTime(one.last_used_at)}` : '아직 안 씀'}
                  {one.expires_at && ` · 만료 ${shownDateTime(one.expires_at)}`}
                </span>
                <div className="flex-1" />
                <Button size="sm" variant="ghost" onClick={() => void revoke(one.id)}>
                  폐기
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
