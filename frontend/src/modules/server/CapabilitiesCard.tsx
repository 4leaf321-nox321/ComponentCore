/**
 * **해석 쪽 능력표** — SimEngBay 가 솔버마다 받는 해석 · 항목 · 칸(해석 확장 설계 5장). 시스템 관리자가 여기서 갱신하면
 * 서버가 복사본을 두고, 케이스의 대상 솔버가 정해진 해석 조건을 저장하거나 DOE 를 만들 때 그 표로 거른다. 받는 쪽이
 * 꺼져 있어도 마지막으로 받은 표로 거른다.
 *
 * 토큰은 화면에 오지 않는다 — `.env` 의 `SIMENGBAY_TOKEN` 이 비었는지만 말한다. 갱신이 실패하면 서버가 고칠 것을 말한다
 * (401 은 토큰 · 계정, 403 은 읽기 범위).
 */

import { useState } from 'react'

import { api } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

interface CapabilityTable {
  solver: string
  version?: string | null
  receiver_version?: string
  analyses?: Record<string, unknown>
}

export interface CapabilitiesStatus {
  configured: boolean
  missing: string
  base_url: string
  source: string
  fetched_at: string | null
  tables: CapabilityTable[] | null
}

/** 해석 종류의 이름 — 사양표와 같은 말(모르는 종류는 그대로). */
const ANALYSIS_LABELS: Record<string, string> = {
  modal: '모달',
  static: '정적 구조',
  harmonic: '조화 응답',
  random: '랜덤 진동',
  explicit: '명시적 동해석',
  thermal: '열',
}

export function CapabilitiesCard() {
  const status = useResource(() => api.get<CapabilitiesStatus>('/server/capabilities'), [])
  const [fresh, setFresh] = useState<CapabilitiesStatus | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const s = fresh ?? status.data

  async function refresh() {
    setRefreshing(true)
    setError(null)
    try {
      setFresh(await api.post<CapabilitiesStatus>('/server/capabilities/refresh', {}))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('능력표를 갱신하지 못했습니다.'))
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>해석 쪽 능력표</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          해석 쪽(SimEngBay)이 솔버마다 받는 해석과 항목입니다. 케이스에 대상 솔버를 지정한 해석 조건을 저장하거나 DOE를 생성할 때, 이 표에 없는
          해석이나 항목은 저장되지 않습니다. 서버에 둔 복사본으로 확인하므로 SimEngBay가 꺼져 있어도 저장할 수 있습니다.
        </p>
        <ErrorNotice error={status.error ?? error} />
        {s && !s.configured && <p className="text-amber-700 dark:text-amber-400">{s.missing} 능력표를 갱신하려면 .env에 값을 넣고 서버를 다시 시작하십시오.</p>}
        {s && (
          <div className="space-y-1">
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">SimEngBay 주소</span>
              <span className="font-mono text-xs break-all">{s.base_url || '—'}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">마지막 갱신</span>
              <span className="text-xs">{s.fetched_at ? shownDateTime(s.fetched_at) : '받은 적 없음'}</span>
            </div>
            {s.source && s.source !== s.base_url && (
              <p className="text-amber-700 dark:text-amber-400">
                복사본은 다른 주소({s.source})에서 받은 것입니다. 지금 주소에서 다시 받으려면 ‘갱신’을 누르십시오.
              </p>
            )}
          </div>
        )}
        {s?.tables && s.tables.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>솔버</TableHead>
                <TableHead>솔버 버전</TableHead>
                <TableHead>SimEngBay 버전</TableHead>
                <TableHead>받는 해석</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {s.tables.map((one) => (
                <TableRow key={one.solver}>
                  <TableCell className="font-mono text-xs">{one.solver}</TableCell>
                  <TableCell className="text-xs">{one.version ?? '알 수 없음'}</TableCell>
                  <TableCell className="text-xs">{one.receiver_version || '—'}</TableCell>
                  <TableCell className="text-xs">
                    {Object.keys(one.analyses ?? {})
                      .map((kind) => ANALYSIS_LABELS[kind] ?? kind)
                      .join(', ')}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {s?.tables && s.tables.length === 0 && <p>SimEngBay가 받는 솔버가 없다고 응답했습니다.</p>}
        {s && !s.tables && <p className="text-muted-foreground">아직 받은 능력표가 없어 대상 솔버로 확인하지 않습니다.</p>}
        {s && (
          <Button size="sm" disabled={refreshing || !s.configured} onClick={() => void refresh()}>
            {refreshing ? '갱신 중…' : '갱신'}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
