/**
 * 서버 상태 — 지금 뭐가 깔렸나, DB 는 맞춰져 있나, 무엇이 얼마나 쌓였나. 그리고 **설정** —
 * 관리자가 화면에서 바꾸는 값(.env 는 서버를 다시 띄워야 하고 관리자가 손댈 수 없다).
 */

import { useState } from 'react'

import { api, ApiError } from '@/shared/api/client'
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
