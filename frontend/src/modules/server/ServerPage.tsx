/**
 * 서버 상태 — 지금 뭐가 깔렸나, DB 는 맞춰져 있나, 무엇이 얼마나 쌓였나. 그리고 **설정** —
 * 관리자가 화면에서 바꾸는 값(.env 는 서버를 다시 띄워야 하고 관리자가 손댈 수 없다).
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, ApiError } from '@/shared/api/client'
import { refreshDisplay } from '@/shared/api/display'
import type { ServerSetting, ServerStatus } from '@/shared/api/types'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'
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
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
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
          {setting.overridden && ' · 화면에서 변경됨'}
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
              기본값 복원
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
  idle: { label: '대기', tone: 'text-emerald-700 dark:text-emerald-400' },
  busy: { label: '작업 중', tone: 'text-amber-700 dark:text-amber-400' },
  stopping: { label: '종료 중', tone: 'text-amber-700 dark:text-amber-400' },
  stopped: { label: '중지됨', tone: 'text-muted-foreground' },
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
                실행 중인 워커가 없어 작업 {data.queue.queued}개가 대기 중입니다. 워커(`python -m app.worker` 또는 `&lt;slug&gt;-worker` 서비스)를 실행하십시오.
              </p>
            )}
            <p className="text-sm">
              대기 <b>{data.queue.queued}</b> · 실행 중 <b>{data.queue.running}</b>
              {data.queue.cancelling > 0 && <> · 취소 중 {data.queue.cancelling}</>}
              {data.queue.oldest_queued_seconds !== null && (
                <span className="text-muted-foreground"> · 가장 오래된 대기 작업: {ago(data.queue.oldest_queued_seconds)} 요청</span>
              )}
            </p>
            {data.workers.length === 0 ? (
              <p className="text-muted-foreground text-sm">최근 24시간 동안 신호를 보낸 워커가 없습니다.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-muted-foreground text-xs">
                  <tr className="border-b text-left">
                    <th className="py-1 pr-2 font-medium">워커</th>
                    <th className="py-1 pr-2 font-medium">상태</th>
                    <th className="py-1 pr-2 font-medium">마지막 신호</th>
                    <th className="py-1 font-medium">현재 작업</th>
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
                            {one.job.cancelling && <span className="text-amber-700 dark:text-amber-400"> · 취소 중</span>}
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
        setNote(`완료 ${filled}${failed ? ` · STEP 읽기 실패 ${failed}` : ''} · 잔여 ${got.remaining}`)
        if (got.remaining === 0 || got.filled + got.failed === 0) break
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('형상 색인을 생성하지 못했습니다.'))
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
              '모든 최신 버전에 색인이 있습니다. 형상 검색 결과에 모든 최신 버전이 포함됩니다.'
            ) : (
              <>
                색인이 없는 최신 버전이 <b>{status.data.missing}</b>개 있습니다. 이 기능이 도입되기 전에 생성된 버전이므로 형상 검색 결과에서 제외됩니다.
              </>
            )}
          </p>
        )}
        {note && <p className="text-muted-foreground text-xs" role="status">{note}</p>}
        {status.data && status.data.missing > 0 && (
          <Button size="sm" disabled={filling} onClick={() => void fill()}>
            {filling ? '생성 중…' : '형상 색인 생성'}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

interface BendRow {
  kind: 'work' | 'part' | 'jig' | 'template' | 'doe'
  id: string
  name: string
  owner: string
  version: number | null
  node: string
  bends: number
  status: 'changed' | 'failing'
  error: string
}

const BEND_KINDS: Record<BendRow['kind'], string> = { work: '작업', part: '부품', jig: '지그', template: '템플릿', doe: 'DOE' }

function bendLink(row: BendRow): string | null {
  if (row.kind === 'work') return `/works/${row.id}`
  if (row.kind === 'part') return `/parts/${row.id}`
  if (row.kind === 'jig') return `/jigs/${row.id}`
  if (row.kind === 'doe') return `/doe/${row.id}`
  return null
}

/**
 * 판금 굽힘 점검 — 2026-10-04 의 고침(굽힘 반지름은 늘 **안쪽** 반지름)으로 모양이 바뀌거나 이제
 * 만들어지지 않는 판금을 찾는다. 두께를 굽힘 안쪽에 붙인 판은 예전에 안쪽이 r - t 로 지어졌다 —
 * 다시 평가하면 굽힘 안쪽만 커진다(바깥 치수는 그대로). 주인에게 알릴 목록이다.
 */
function BendCheckCard() {
  const [report, setReport] = useState<{ scanned: number; items: BendRow[]; failing: number; truncated: boolean } | null>(null)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function run() {
    setChecking(true)
    setError(null)
    try {
      setReport(await api.get('/server/bend-check'))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('판금 굽힘을 점검하지 못했습니다.'))
    } finally {
      setChecking(false)
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>판금 굽힘 점검</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-muted-foreground text-xs">
          v0.8.1부터 판금의 굽힘 반지름은 두께 방향과 상관없이 안쪽 반지름입니다. 두께를 굽힘 안쪽에 붙인 판금은 다시
          평가하면 굽힘 안쪽이 커지고, 짧은 구간 사이의 굽힘은 생성되지 않을 수 있습니다. 해당하는 작업, 부품, 템플릿,
          DOE를 찾습니다.
        </p>
        <ErrorNotice error={error} />
        <Button size="sm" disabled={checking} onClick={() => void run()}>
          {checking ? '점검 중…' : '점검'}
        </Button>
        {report && (
          <p role="status">
            판금이 포함된 항목 {report.scanned}개 중 모양이 바뀌는 판금 노드 <b>{report.items.length}</b>개(이 중 생성 실패{' '}
            <b>{report.failing}</b>개)
            {report.truncated ? '. 상한에 도달하여 일부만 점검했습니다' : ''}.
          </p>
        )}
        {report && report.items.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>종류</TableHead>
                <TableHead>이름</TableHead>
                <TableHead>작성자</TableHead>
                <TableHead>노드</TableHead>
                <TableHead>바뀐 굽힘</TableHead>
                <TableHead>상태</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.items.map((row) => {
                const to = bendLink(row)
                return (
                  <TableRow key={`${row.kind}-${row.id}-${row.node}`}>
                    <TableCell>{BEND_KINDS[row.kind]}</TableCell>
                    <TableCell>
                      {to ? (
                        <Link to={to} className="hover:underline">
                          {row.name}
                        </Link>
                      ) : (
                        row.name
                      )}
                      {row.version !== null && <span className="text-muted-foreground ml-1 text-xs">v{row.version}</span>}
                    </TableCell>
                    <TableCell>{row.owner || '—'}</TableCell>
                    <TableCell className="font-mono text-xs">{row.node}</TableCell>
                    <TableCell>{row.bends}</TableCell>
                    <TableCell>
                      {row.status === 'failing' ? (
                        <span className="text-destructive text-xs" title={row.error}>
                          생성 실패: {row.error}
                        </span>
                      ) : (
                        <span className="text-xs">모양 변경</span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
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
      <PageHeader title="서버" description="서버 버전, 데이터베이스 연결, 워커 상태와 설정을 확인합니다. 문제가 발생하면 먼저 이 화면을 확인하십시오." />
      <ErrorNotice error={status.error ?? settings.error} className="mb-4" />
      <WorkersCard />
      <ShapeIndexCard />
      <BendCheckCard />
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
              <CardTitle>설치 정보</CardTitle>
            </CardHeader>
            <CardContent>
              <Row label="이름" value={`${s.app_name} (${s.app_slug})`} />
              <Row label="버전" value={s.version} />
              <Row label="환경" value={s.app_env} />
              <Row label="build123d" value={s.build123d_version} />
              <Row label="기동 시각" value={shownDateTime(s.started_at)} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>데이터베이스</CardTitle>
            </CardHeader>
            <CardContent>
              <Row label="접속 정보" value={s.database_url_safe} />
              <Row label="코드 리비전" value={s.schema_head ?? '—'} />
              <Row
                label="DB 리비전"
                value={
                  <span className={s.schema_behind ? 'text-destructive' : undefined}>
                    {s.schema_current ?? '—'}
                    {s.schema_behind && ' (업그레이드 필요: alembic upgrade head)'}
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
