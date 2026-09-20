/**
 * 개인 토큰 — AI 도구(Claude Code · Claude Desktop · Gemini CLI · Codex CLI)와 스크립트가 이
 * 플랫폼을 부르는 자격 증명. 평문은 발급 응답에서 **한 번만** 보인다.
 *
 * 왼쪽은 발급 · 목록 · 폐기, 오른쪽은 도구별 등록 방법. 토큰을 아직 안 발급했어도 등록 형식은
 * 늘 보이고, 방금 발급한 토큰은 그 형식에 자동으로 채워진다 — 사람이 옮겨 적다 틀리지 않게.
 */

import { BookOpen, Check, Copy, KeyRound, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, api } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Separator } from '@/shared/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'
import { copyText } from '@/shared/lib/clipboard'
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

interface McpInfo {
  url: string
  port: number
  server_name: string
}

const SCOPE_LABELS: Record<string, string> = { read: '읽기', write: '쓰기' }
/** 이름 빠른 선택 — 어느 도구에 준 토큰인지 목록에서 바로 읽히게. */
const NAME_PRESETS = ['Claude Code', 'Claude Desktop', 'Gemini CLI', 'Codex CLI', '스크립트']
/** 만료 빠른 선택 — 날짜 칸에 채운다(오늘 기준). */
const EXPIRY_PRESETS: { label: string; days: number | null }[] = [
  { label: '30일', days: 30 },
  { label: '90일', days: 90 },
  { label: '1년', days: 365 },
  { label: '없음', days: null },
]
const TOKEN_PLACEHOLDER = '<발급받은_토큰>'

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10)
}

/** 오늘 + n일의 날짜 문자열. */
function daysFromNow(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return isoDate(date)
}

/** 날짜 칸의 값을 서버가 받는 「며칠 뒤」 로 — 하루 단위로 올림(오늘 자정 기준). */
function daysUntil(date: string): number | null {
  if (!date) return null
  const target = new Date(`${date}T23:59:59`)
  const diff = Math.ceil((target.getTime() - Date.now()) / 86_400_000)
  return Math.max(1, diff)
}

function statusOf(token: Pat): { label: string; variant: 'default' | 'outline' | 'destructive' | 'secondary' } {
  if (token.revoked_at) return { label: '폐기됨', variant: 'destructive' }
  if (token.expires_at && new Date(token.expires_at) < new Date()) return { label: '만료', variant: 'outline' }
  return { label: '활성', variant: 'default' }
}

export function TokensPanel() {
  const [issued, setIssued] = useState<string | null>(null)
  const [issuedName, setIssuedName] = useState<string>('')
  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <IssueCard
        issued={issued}
        onIssued={(token, name) => {
          setIssued(token)
          setIssuedName(name)
        }}
      />
      <SetupCard issued={issued} issuedName={issuedName} />
    </div>
  )
}

function CopyButton({ text, label, size = 'sm' }: { text: string; label: string; size?: 'sm' | 'default' }) {
  const [done, setDone] = useState(false)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (!done && !failed) return
    const timer = setTimeout(() => {
      setDone(false)
      setFailed(false)
    }, 1500)
    return () => clearTimeout(timer)
  }, [done, failed])
  return (
    <Button
      type="button"
      size={size}
      variant="outline"
      onClick={() => {
        copyText(text)
          .then(() => setDone(true))
          .catch(() => setFailed(true))
      }}
    >
      {done ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {failed ? '직접 골라 복사하세요' : done ? '복사됨' : label}
    </Button>
  )
}

function IssueCard({ issued, onIssued }: { issued: string | null; onIssued: (token: string, name: string) => void }) {
  const tokens = useResource(() => api.get<Pat[]>('/auth/tokens'), [])
  const scopes = useResource(() => api.get<{ scopes: string[]; descriptions: Record<string, string> }>('/auth/token-scopes'), [])
  const [name, setName] = useState('Claude Code')
  const [chosen, setChosen] = useState<string[]>(['read', 'write'])
  /** 만료일 — 날짜 칸. 비우면 만료 없음. */
  const [expires, setExpires] = useState<string>(daysFromNow(90))
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)
  const [showRevoked, setShowRevoked] = useState(false)

  async function issue(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const made = await api.post<{ token: string }>('/auth/tokens', {
        name: name.trim(),
        scopes: chosen,
        expires_in_days: daysUntil(expires),
      })
      onIssued(made.token, name.trim())
      tokens.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  async function revoke(token: Pat) {
    if (!window.confirm(`「${token.name}」 토큰을 폐기합니까? 이 토큰을 쓰는 AI 연결은 바로 끊깁니다.`)) return
    setError(null)
    try {
      await api.delete(`/auth/tokens/${token.id}`)
      tokens.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  const rows = (tokens.data ?? []).filter((one) => showRevoked || !one.revoked_at)
  const revokedCount = (tokens.data ?? []).filter((one) => one.revoked_at).length
  const today = isoDate(new Date())

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <KeyRound className="text-muted-foreground size-4" />
          <CardTitle className="text-base">개인 토큰</CardTitle>
        </div>
        <CardDescription>
          AI 도구가 <b>내 권한</b>으로 이 플랫폼을 부르는 열쇠입니다. AI 가 만든 것은 내 작업에 출처 「AI」 로 쌓입니다. 발급된 값은 <b>한 번만</b> 보이니 바로 복사하세요. 유출되면 여기서
          폐기하면 됩니다.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {issued && (
          <div className="border-primary/40 bg-primary/5 space-y-2 rounded-md border p-3">
            <p className="text-primary text-sm font-medium">토큰이 발급되었습니다 — 지금 복사하세요. 다시 볼 수 없습니다.</p>
            <div className="flex items-center gap-2">
              <code className="bg-muted flex-1 truncate rounded px-2 py-1 font-mono text-xs select-all">{issued}</code>
              <CopyButton text={issued} label="토큰 복사" />
            </div>
            <p className="text-muted-foreground text-xs">→ 오른쪽 「도구별 등록 방법」 에 이 토큰이 채워져 있습니다. 쓰는 도구 탭을 골라 그대로 복사하세요.</p>
          </div>
        )}

        <form onSubmit={issue} className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="pat-name">이름 — 어디에 쓰는 토큰인지</Label>
            <Input id="pat-name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} placeholder="예: Claude Code (내 노트북)" />
            <div className="flex flex-wrap gap-1">
              {NAME_PRESETS.map((preset) => (
                <button key={preset} type="button" onClick={() => setName(preset)} className={`rounded-full border px-2 py-0.5 text-xs ${name === preset ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}>
                  {preset}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>권한</Label>
              <div className="flex gap-3 pt-1 text-sm">
                {(scopes.data?.scopes ?? ['read', 'write']).map((scope) => (
                  <label key={scope} className="flex items-center gap-1" title={scopes.data?.descriptions[scope]}>
                    <input type="checkbox" checked={chosen.includes(scope)} onChange={(e) => setChosen(e.target.checked ? [...chosen, scope] : chosen.filter((s) => s !== scope))} />
                    {SCOPE_LABELS[scope] ?? scope}
                  </label>
                ))}
              </div>
              <p className="text-muted-foreground text-xs">그리게 하려면 「쓰기」 가 있어야 합니다. 읽기만이면 보기 · 치수 · 그림까지.</p>
            </div>
            <div className="space-y-1">
              <Label htmlFor="pat-expires">만료일 (비우면 만료 없음)</Label>
              <Input id="pat-expires" type="date" min={today} value={expires} onChange={(e) => setExpires(e.target.value)} />
              <div className="flex flex-wrap gap-1">
                {EXPIRY_PRESETS.map((preset) => {
                  const value = preset.days === null ? '' : daysFromNow(preset.days)
                  return (
                    <button key={preset.label} type="button" onClick={() => setExpires(value)} className={`rounded-full border px-2 py-0.5 text-xs ${expires === value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}>
                      {preset.label}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
          <Button type="submit" disabled={busy || chosen.length === 0 || !name.trim()}>
            {busy ? '발급 중…' : '토큰 발급'}
          </Button>
        </form>
        <ErrorNotice error={error ?? tokens.error} />

        <Separator />

        {tokens.loading ? (
          <p className="text-muted-foreground text-sm">불러오는 중…</p>
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground text-sm">발급된 토큰이 없습니다.</p>
        ) : (
          <ul className="divide-y">
            {rows.map((one) => {
              const status = statusOf(one)
              return (
                <li key={one.id} className="flex items-center gap-2 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {one.name} <span className="text-muted-foreground font-normal">· {one.scopes.map((s) => SCOPE_LABELS[s] ?? s).join(' · ')}</span>
                    </p>
                    <p className="text-muted-foreground font-mono text-[11px]">
                      {one.prefix}… · 발급 {shownDateTime(one.created_at)} · 마지막 사용 {one.last_used_at ? shownDateTime(one.last_used_at) : '없음'} · 만료 {one.expires_at ? shownDateTime(one.expires_at) : '없음'}
                    </p>
                  </div>
                  <Badge variant={status.variant}>{status.label}</Badge>
                  {!one.revoked_at && (
                    <Button type="button" size="sm" variant="ghost" onClick={() => void revoke(one)} title="폐기" aria-label={`${one.name} 폐기`}>
                      <Trash2 className="size-3.5" />
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
        {revokedCount > 0 && (
          <button type="button" className="text-muted-foreground text-xs underline" onClick={() => setShowRevoked(!showRevoked)}>
            {showRevoked ? '폐기된 것 숨기기' : `폐기된 것 ${revokedCount}개 보기`}
          </button>
        )}
      </CardContent>
    </Card>
  )
}

/** 오른쪽 — 도구별 등록 방법. 토큰이 없으면 자리표시자로 형식을 보인다. */
function SetupCard({ issued, issuedName }: { issued: string | null; issuedName: string }) {
  const info = useResource(() => api.get<McpInfo>('/auth/mcp-info'), [])
  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
  const mcpUrl = info.data?.url || `http://${host}:${info.data?.port ?? 8062}/mcp`
  const server = info.data?.server_name ?? 'autojig'
  const token = issued ?? TOKEN_PLACEHOLDER
  const auth = `Bearer ${token}`
  /** 발급한 이름으로 첫 탭을 고른다 — 「Gemini CLI」 로 발급했으면 Gemini 탭이 먼저. */
  const initialTab = /gemini/i.test(issuedName) ? 'gemini' : /desktop/i.test(issuedName) ? 'desktop' : /codex/i.test(issuedName) ? 'codex' : 'claude-code'

  // Claude Code — streamable-http 를 바로 받는다. 브리지 없이 한 줄.
  const claudeCode = `claude mcp add --transport http ${server} ${mcpUrl} \\\n  --header "Authorization: ${auth}"`
  // Claude Desktop — 설정 파일은 stdio(command) 서버만 받으므로 mcp-remote 브리지(Node.js).
  const desktopEntry = `"${server}": ${JSON.stringify(
    {
      command: 'npx',
      args: ['-y', 'mcp-remote', mcpUrl, '--allow-http', '--header', 'Authorization:${AUTH}'],
      env: { AUTH: auth },
    },
    null,
    2,
  )}`
  // Gemini CLI — settings.json 이 HTTP 서버를 바로 받는다(httpUrl + headers).
  const geminiEntry = `"${server}": ${JSON.stringify({ httpUrl: mcpUrl, headers: { Authorization: auth } }, null, 2)}`
  // Codex CLI — config.toml, mcp-remote 브리지.
  const codexEntry = `[mcp_servers.${server}]\ncommand = "npx"\nargs = ["-y", "mcp-remote", "${mcpUrl}", "--allow-http", "--header", "Authorization:\${AUTH}"]\n\n[mcp_servers.${server}.env]\nAUTH = "${auth}"`
  // 스크립트 — 그냥 HTTP.
  const curl = `curl -H "Authorization: ${auth}" ${mcpUrl.replace(/:\d+\/mcp$/, '')}/api/works`

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <BookOpen className="text-muted-foreground size-4" />
          <CardTitle className="text-base">도구별 등록 방법</CardTitle>
        </div>
        <CardDescription>
          쓰는 AI 도구 탭을 골라 그대로 복사하세요. MCP 주소는 <code className="font-mono break-all">{mcpUrl}</code> 입니다{info.data?.url ? '' : ' (지금 접속한 호스트 기준 — 다른 PC 에서 붙이면 서버 주소로 바꾸세요)'}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!issued && (
          <div className="bg-muted/40 text-muted-foreground rounded-md border border-dashed px-3 py-2 text-xs">
            아직 토큰을 발급하지 않았습니다. 아래는 <b>형식</b>이고 토큰 자리에 <code className="font-mono">{TOKEN_PLACEHOLDER}</code> 이 있습니다. 왼쪽에서 발급하면 실제 토큰이 채워집니다.
          </div>
        )}
        <Tabs key={initialTab} defaultValue={initialTab}>
          <TabsList className="h-auto w-full flex-wrap justify-start gap-y-1">
            <TabsTrigger value="claude-code">Claude Code</TabsTrigger>
            <TabsTrigger value="desktop">Claude Desktop</TabsTrigger>
            <TabsTrigger value="gemini">Gemini CLI</TabsTrigger>
            <TabsTrigger value="codex">Codex CLI</TabsTrigger>
            <TabsTrigger value="script">스크립트</TabsTrigger>
          </TabsList>

          <TabsContent value="claude-code" className="space-y-2">
            <p className="text-muted-foreground text-xs">터미널에서 한 번 실행하면 이 PC 의 사용자 설정에 남습니다(저장소에는 안 들어감). 확인은 <code className="font-mono">claude mcp list</code>.</p>
            <Snippet text={claudeCode} label="명령 복사" />
            <p className="text-muted-foreground text-xs">그 뒤 Claude 에게 「센서 브래킷으로 볼트 고정 지그를 만들고 조립해서 두께 4~12 로 DOE 돌려 줘」 처럼 말하면 됩니다. 도구 안내(가이드)는 Claude 가 스스로 읽습니다.</p>
          </TabsContent>

          <TabsContent value="desktop" className="space-y-2">
            <p className="text-muted-foreground text-xs">
              설정 → 개발자 → 「설정 편집」 으로 <code className="font-mono">claude_desktop_config.json</code> 을 열고, 아래 항목을 <code className="font-mono">{'"mcpServers": { }'}</code> 안에 붙여넣은 뒤 Claude Desktop 을 다시 시작합니다. Desktop 은 HTTP 서버를 바로 못 받아 <code className="font-mono">npx mcp-remote</code>(Node.js 필요)를 거칩니다. 다른 항목이 이미 있으면 사이에 쉼표.
            </p>
            <Snippet text={desktopEntry} label="항목 복사" />
          </TabsContent>

          <TabsContent value="gemini" className="space-y-2">
            <p className="text-muted-foreground text-xs">
              <code className="font-mono">~/.gemini/settings.json</code> 의 <code className="font-mono">{'"mcpServers": { }'}</code> 안에 아래 항목을 붙여넣고 Gemini CLI 를 다시 시작합니다. Gemini 는 HTTP 서버를 바로 받습니다(브리지 없음). 확인은 <code className="font-mono">/mcp</code>.
            </p>
            <Snippet text={geminiEntry} label="항목 복사" />
          </TabsContent>

          <TabsContent value="codex" className="space-y-2">
            <p className="text-muted-foreground text-xs">
              <code className="font-mono">~/.codex/config.toml</code> 에 아래를 더하고 Codex 를 다시 시작합니다(<code className="font-mono">npx mcp-remote</code> 브리지, Node.js 필요).
            </p>
            <Snippet text={codexEntry} label="설정 복사" />
          </TabsContent>

          <TabsContent value="script" className="space-y-2">
            <p className="text-muted-foreground text-xs">MCP 가 아니라 REST 를 바로 부를 때 — 같은 토큰을 Bearer 헤더로. API 문서는 <code className="font-mono">/docs</code>.</p>
            <Snippet text={curl} label="예시 복사" />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

function Snippet({ text, label }: { text: string; label: string }) {
  return (
    <div className="space-y-1">
      <pre className="bg-muted overflow-x-auto rounded-md px-3 py-2 font-mono text-[11px] whitespace-pre">{text}</pre>
      <CopyButton text={text} label={label} />
    </div>
  )
}
