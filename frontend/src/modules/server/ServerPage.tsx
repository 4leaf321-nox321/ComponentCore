/**
 * 서버 상태 — 지금 뭐가 깔렸나, DB 는 맞춰져 있나, 무엇이 얼마나 쌓였나. 그리고 **설정** —
 * 관리자가 화면에서 바꾸는 값(.env 는 서버를 다시 띄워야 하고 관리자가 손댈 수 없다).
 */

import { useEffect, useState } from 'react'

import { api, ApiError } from '@/shared/api/client'
import { refreshDisplay } from '@/shared/api/display'
import type { ServerSetting, ServerStatus } from '@/shared/api/types'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-mono text-xs break-all">{value}</span>
    </div>
  )
}

const gb = (bytes: number) => `${(bytes / 1024 ** 3).toFixed(1)} GB`

/** 설정 한 줄 — 칸에 적고 「저장」. 「기본값으로」 는 덮어쓴 것을 지운다. */
function SettingRow({ setting, onSaved }: { setting: ServerSetting; onSaved: (next: ServerSetting[]) => void }) {
  const [draft, setDraft] = useState(String(setting.value))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const changed = Number(draft) !== setting.value

  async function put(value: number | null) {
    setBusy(true)
    setError(null)
    try {
      const next = await api.put<ServerSetting[]>(`/server/settings/${setting.key}`, { value })
      onSaved(next)
      // 화면이 들고 있는 값(목록 줄 수 · 형상 보기 수)도 바뀌었을 수 있다 — 다시 묻게 한다.
      refreshDisplay()
      const mine = next.find((one) => one.key === setting.key)
      if (mine) setDraft(String(mine.value))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-1 border-b py-2 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{setting.label}</span>
        <span className="text-muted-foreground text-xs">
          {setting.minimum.toLocaleString()} ~ {setting.maximum.toLocaleString()} · .env 기본값 {setting.default.toLocaleString()}
          {setting.overridden && ' · 화면에서 바꿈'}
        </span>
        <form
          className="ml-auto flex items-center gap-1"
          onSubmit={(event) => {
            event.preventDefault()
            void put(Number(draft))
          }}
        >
          <Input type="number" min={setting.minimum} max={setting.maximum} value={draft} onChange={(e) => setDraft(e.target.value)} className="h-8 w-28" aria-label={setting.label} />
          <Button size="sm" type="submit" disabled={busy || !changed || draft === ''}>
            저장
          </Button>
          {setting.overridden && (
            <Button size="sm" type="button" variant="ghost" disabled={busy} onClick={() => void put(null)}>
              기본값으로
            </Button>
          )}
        </form>
      </div>
      <p className="text-muted-foreground text-xs">{setting.description}</p>
      <ErrorNotice error={error} />
    </div>
  )
}

interface WorkerRow {
  id: string
  hostname: string
  pid: number
  version: string
  /** idle · busy · stopping · stopped · lost(신호가 2분 넘게 끊김). */
  state: 'idle' | 'busy' | 'stopping' | 'stopped' | 'lost'
  started_at: string
  last_seen_at: string
  silent_seconds: number
  job: { id: string; kind: string; status: string; started_at: string | null; step: string; cancelling: boolean } | null
}

interface WorkersOverview {
  workers: WorkerRow[]
  queue: { queued: number; running: number; cancelling: number; oldest_queued_seconds: number | null }
  alive: number
}

const WORKER_STATE: Record<WorkerRow['state'], { label: string; tone: string }> = {
  idle: { label: '기다림', tone: 'text-emerald-700 dark:text-emerald-400' },
  busy: { label: '작업 중', tone: 'text-amber-700 dark:text-amber-400' },
  stopping: { label: '끝내는 중', tone: 'text-amber-700 dark:text-amber-400' },
  stopped: { label: '멈춤', tone: 'text-muted-foreground' },
  lost: { label: '응답 없음', tone: 'text-destructive' },
}

const KIND_LABELS: Record<string, string> = { jig: '지그 생성', cad: '부품 평가', doe: 'DOE' }

function ago(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}초 전`
  if (seconds < 3600) return `${Math.round(seconds / 60)}분 전`
  return `${Math.round(seconds / 3600)}시간 전`
}

/**
 * 워커 — 살아 있나 · 무엇을 하나 · 줄이 얼마나 긴가. 10초마다 다시 묻는다.
 *
 * 살아 있는 워커가 없는데 줄이 서 있으면 작업은 **영영 안 돈다** — 그 사실을 맨 위에 크게 적는다.
 */
function WorkersCard() {
  const overview = useResource(() => api.get<WorkersOverview>('/server/workers'), [])
  const { reload } = overview
  useEffect(() => {
    const timer = setInterval(reload, 10_000)
    return () => clearInterval(timer)
  }, [reload])
  const data = overview.data
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>워커</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorNotice error={overview.error} />
        {data && (
          <>
            {data.alive === 0 && data.queue.queued > 0 && (
              <p className="text-destructive text-sm font-medium">
                살아 있는 워커가 없는데 작업 {data.queue.queued} 개가 기다립니다 — 워커(`python -m app.worker` · `&lt;slug&gt;-worker` 서비스)를 띄우세요.
              </p>
            )}
            <p className="text-sm">
              대기 <b>{data.queue.queued}</b> · 도는 중 <b>{data.queue.running}</b>
              {data.queue.cancelling > 0 && <> · 멈추는 중 {data.queue.cancelling}</>}
              {data.queue.oldest_queued_seconds !== null && (
                <span className="text-muted-foreground"> · 가장 오래 기다린 것 {ago(data.queue.oldest_queued_seconds)} 걸림</span>
              )}
            </p>
            {data.workers.length === 0 ? (
              <p className="text-muted-foreground text-sm">신호를 적은 워커가 없습니다(하루 안).</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-muted-foreground text-xs">
                  <tr className="border-b text-left">
                    <th className="py-1 pr-2 font-medium">워커</th>
                    <th className="py-1 pr-2 font-medium">상태</th>
                    <th className="py-1 pr-2 font-medium">마지막 신호</th>
                    <th className="py-1 font-medium">하는 일</th>
                  </tr>
                </thead>
                <tbody>
                  {data.workers.map((one) => (
                    <tr key={one.id} className="border-b last:border-b-0">
                      <td className="py-1 pr-2 font-mono text-xs" title={`v${one.version} · ${shownDateTime(one.started_at)} 시작`}>
                        {one.id}
                      </td>
                      <td className={`py-1 pr-2 ${WORKER_STATE[one.state]?.tone ?? ''}`}>{WORKER_STATE[one.state]?.label ?? one.state}</td>
                      <td className="py-1 pr-2 text-xs">{ago(one.silent_seconds)}</td>
                      <td className="py-1 text-xs">
                        {one.job ? (
                          <>
                            {KIND_LABELS[one.job.kind] ?? one.job.kind}
                            {one.job.step && <span className="text-muted-foreground"> · {one.job.step}</span>}
                            {one.job.cancelling && <span className="text-amber-700 dark:text-amber-400"> · 멈추는 중</span>}
                          </>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * 형상 색인 — 형상으로 찾기(「M6 구멍이 있는 판」)가 보는 값. 버전을 평가할 때 적히므로 이
 * 기능 전에 만든 버전에는 없다. 여기서 남긴 STEP 을 열어 채운다 — 한 번에 몇 개씩, 다 될
 * 때까지 이어서.
 */
function ShapeIndexCard() {
  const status = useResource(() => api.get<{ missing: number }>('/server/shape-index'), [])
  const [filling, setFilling] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)

  async function fill() {
    setFilling(true)
    setError(null)
    let filled = 0
    let failed = 0
    try {
      for (let round = 0; round < 200; round += 1) {
        const got = await api.post<{ filled: number; failed: number; remaining: number }>('/server/shape-index?limit=20', {})
        filled += got.filled
        failed += got.failed
        setNote(`채움 ${filled}${failed ? ` · 못 연 STEP ${failed}` : ''} · 남음 ${got.remaining}`)
        if (got.remaining === 0 || got.filled + got.failed === 0) break
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('채우지 못했습니다'))
    } finally {
      setFilling(false)
      status.reload()
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>형상 색인</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <ErrorNotice error={status.error ?? error} />
        {status.data && (
          <p>
            {status.data.missing === 0 ? (
              '모든 최신 버전에 색인이 있습니다 — 형상으로 찾기가 다 봅니다.'
            ) : (
              <>
                색인이 없는 최신 버전 <b>{status.data.missing}</b> 개 — 이 기능 전에 만든 것이라 형상으로 찾으면 빠집니다.
              </>
            )}
          </p>
        )}
        {note && <p className="text-muted-foreground text-xs" role="status">{note}</p>}
        {status.data && status.data.missing > 0 && (
          <Button size="sm" disabled={filling} onClick={() => void fill()}>
            {filling ? '채우는 중…' : '형상 색인 채우기'}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

export default function ServerPage() {
  const status = useResource(() => api.get<ServerStatus>('/server/status'), [])
  const settings = useResource(() => api.get<ServerSetting[]>('/server/settings'), [])
  const [saved, setSaved] = useState<ServerSetting[] | null>(null)
  const s = status.data
  const rows = saved ?? settings.data ?? []

  return (
    <div>
      <PageHeader title="서버" description="문제가 났을 때 첫 물음: 무슨 버전이고 어느 DB 를 보고 있나." />
      <ErrorNotice error={status.error ?? settings.error} className="mb-4" />
      <WorkersCard />
      <ShapeIndexCard />
      {rows.length > 0 && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle>설정</CardTitle>
          </CardHeader>
          <CardContent>
            {rows.map((one) => (
              <SettingRow key={one.key} setting={one} onSaved={setSaved} />
            ))}
          </CardContent>
        </Card>
      )}
      {s && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>설치</CardTitle>
            </CardHeader>
            <CardContent>
              <Row label="이름" value={`${s.app_name} (${s.app_slug})`} />
              <Row label="버전" value={s.version} />
              <Row label="환경" value={s.app_env} />
              <Row label="build123d" value={s.build123d_version} />
              <Row label="기동" value={shownDateTime(s.started_at)} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>데이터베이스</CardTitle>
            </CardHeader>
            <CardContent>
              <Row label="접속" value={s.database_url_safe} />
              <Row label="코드 리비전" value={s.schema_head ?? '—'} />
              <Row
                label="DB 리비전"
                value={
                  <span className={s.schema_behind ? 'text-destructive' : undefined}>
                    {s.schema_current ?? '—'}
                    {s.schema_behind && ' (뒤처짐 — alembic upgrade head)'}
                  </span>
                }
              />
              {s.counts.map((one) => (
                <Row key={one.label} label={one.label} value={one.count.toLocaleString()} />
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>저장소</CardTitle>
            </CardHeader>
            <CardContent>
              {s.disk ? (
                <>
                  <Row label="경로" value={s.disk.path} />
                  <Row label="전체" value={gb(s.disk.total_bytes)} />
                  <Row label="여유" value={`${gb(s.disk.free_bytes)} (${100 - s.disk.used_percent}% )`} />
                </>
              ) : (
                <p className="text-muted-foreground text-sm">디스크 정보를 읽지 못했습니다.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
