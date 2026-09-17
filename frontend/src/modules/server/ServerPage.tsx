/** 서버 상태 — 지금 뭐가 깔렸나, DB 는 맞춰져 있나, 무엇이 얼마나 쌓였나. */

import { api } from '@/shared/api/client'
import type { ServerStatus } from '@/shared/api/types'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
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

export default function ServerPage() {
  const status = useResource(() => api.get<ServerStatus>('/server/status'), [])
  const s = status.data

  return (
    <div>
      <PageHeader title="서버" description="문제가 났을 때 첫 물음: 무슨 버전이고 어느 DB 를 보고 있나." />
      <ErrorNotice error={status.error} className="mb-4" />
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
