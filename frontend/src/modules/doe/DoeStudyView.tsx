/**
 * 실험계획 결과 — 설계점 표 · 부등식 필터 · CSV · **공유 폴더 경로**.
 *
 * 이 화면의 끝은 「폴더를 열어 해석으로 넘긴다」 이다. 그래서 경로를 크게 보여 주고 복사까지
 * 한 번에 되게 둔다 — 경로를 손으로 옮겨 적다 틀리면 엉뚱한 폴더를 해석한다.
 */

import { Check, Copy, Download, FolderOpen } from 'lucide-react'
import { useEffect, useState } from 'react'

import { doeApi } from '@/modules/doe/api'
import type { Condition, DoeStudy } from '@/modules/doe/api'
import { isFinished } from '@/modules/jobs/api'
import { TradeoffPanel } from '@/modules/doe/TradeoffPanel'
import { useJobPolling } from '@/modules/jobs/useJobPolling'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'

/** 표에 보여 줄 값 — 이름은 서버의 metrics 열쇠와 같다(CSV 와도 같다). */
const METRICS: { key: string; label: string; digits?: number }[] = [
  { key: 'mass_g', label: '질량 g', digits: 1 },
  { key: 'volume_mm3', label: '부피 mm³', digits: 0 },
  { key: 'size_x', label: 'X', digits: 1 },
  { key: 'size_y', label: 'Y', digits: 1 },
  { key: 'size_z', label: 'Z', digits: 1 },
  { key: 'izz', label: 'Izz', digits: 0 },
]

function show(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

export function DoeStudyView({ study, onReload }: { study: DoeStudy; onReload: () => void }) {
  const [conditions, setConditions] = useState<Condition[]>([])
  const [kept, setKept] = useState<Set<string> | null>(null)
  const [copied, setCopied] = useState(false)
  // 작업이 끝나면 스터디를 다시 불러온다 — 점마다 결과가 붙어야 표가 찬다.
  const job = useJobPolling(study.job)
  const running = job !== null && !isFinished(job)
  useEffect(() => {
    if (job && isFinished(job) && job.status !== study.job?.status) onReload()
  }, [job, study.job?.status, onReload])

  const names = study.factors.filter((one) => one.mode !== 'fixed').map((one) => one.name)
  const rows = study.points.filter((one) => !kept || kept.has(one.id))

  async function applyFilter(next: Condition[]) {
    setConditions(next)
    const usable = next.filter((one) => one.key && one.value !== null && Number.isFinite(one.value))
    if (usable.length === 0) {
      setKept(null)
      return
    }
    const got = await doeApi.filter(study.id, usable)
    setKept(new Set(got.map((one) => one.id)))
  }

  return (
    <div className="space-y-4">
      {/* 공유 폴더 — 이 화면의 끝 */}
      <div className="bg-muted/40 flex flex-wrap items-center gap-2 rounded-md border p-3">
        <FolderOpen className="text-muted-foreground size-4 shrink-0" />
        <div className="min-w-0">
          <p className="text-xs font-medium">공유 폴더 — 해석은 이 폴더를 읽습니다</p>
          <p className="truncate font-mono text-xs">{study.export_dir_windows}</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          onClick={() => {
            void navigator.clipboard?.writeText(study.export_dir_windows)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          }}
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          경로 복사
        </Button>
        <Button size="sm" variant="outline" asChild>
          <a href={doeApi.manifestUrl(study.id)} download>
            <Download className="size-3.5" /> CSV
          </a>
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="secondary">{study.method === 'factorial' ? '전체 조합' : `LHS · 시드 ${study.seed}`}</Badge>
        <span>
          설계점 {study.point_count} 개 — 만든 것 <b>{study.done}</b>
          {study.failed > 0 && <span className="text-destructive"> · 실패 {study.failed}</span>}
        </span>
        {running && (
          <span className="text-muted-foreground">
            만드는 중… {job?.progress?.at(-1)?.detail ?? ''}
            <button type="button" className="ml-1 underline" onClick={onReload}>
              새로 고침
            </button>
          </span>
        )}
        {kept && (
          <span className="text-muted-foreground">
            조건을 만족: {rows.length} / {study.points.length}
            <button type="button" className="ml-1 underline" onClick={() => void applyFilter([])}>
              해제
            </button>
          </span>
        )}
      </div>

      {/* 부등식 필터 — 설계 조건은 대개 「이하 · 이상」 이다 */}
      <div className="flex flex-wrap items-center gap-2 rounded-md border p-2">
        <span className="text-xs font-medium">조건</span>
        {conditions.map((condition, index) => (
          <div key={index} className="flex items-center gap-1">
            <Select value={condition.key} onValueChange={(key) => void applyFilter(conditions.map((one, i) => (i === index ? { ...one, key } : one)))}>
              <SelectTrigger className="h-8 w-32 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {METRICS.map((one) => (
                  <SelectItem key={one.key} value={one.key}>
                    {one.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={condition.op} onValueChange={(op) => void applyFilter(conditions.map((one, i) => (i === index ? { ...one, op: op as Condition['op'] } : one)))}>
              <SelectTrigger className="h-8 w-24 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="lte">이하 ≤</SelectItem>
                <SelectItem value="gte">이상 ≥</SelectItem>
                <SelectItem value="between">범위</SelectItem>
                <SelectItem value="eq">같음 =</SelectItem>
              </SelectContent>
            </Select>
            <Input
              type="number"
              value={String(condition.value ?? '')}
              onChange={(e) => void applyFilter(conditions.map((one, i) => (i === index ? { ...one, value: e.target.value === '' ? null : Number(e.target.value) } : one)))}
              className="h-8 w-24"
              aria-label={`조건 ${index + 1} 값`}
            />
            {condition.op === 'between' && (
              <Input
                type="number"
                value={String(condition.value2 ?? '')}
                onChange={(e) => void applyFilter(conditions.map((one, i) => (i === index ? { ...one, value2: e.target.value === '' ? null : Number(e.target.value) } : one)))}
                className="h-8 w-24"
                aria-label={`조건 ${index + 1} 두 번째 값`}
              />
            )}
            <button type="button" className="text-muted-foreground px-1 text-xs" onClick={() => void applyFilter(conditions.filter((_, i) => i !== index))}>
              ×
            </button>
          </div>
        ))}
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setConditions([...conditions, { key: 'mass_g', op: 'lte', value: null }])}>
          + 조건
        </Button>
        <span className="text-muted-foreground text-xs">값이 없는 점(실패)은 조건을 만족한 것으로 세지 않습니다.</span>
      </div>

      {study.done > 1 && <TradeoffPanel study={study} />}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-14">점</TableHead>
            {names.map((name) => (
              <TableHead key={name} className="font-mono text-xs">
                {name}
              </TableHead>
            ))}
            {METRICS.map((one) => (
              <TableHead key={one.key}>{one.label}</TableHead>
            ))}
            <TableHead>상태</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((point) => (
            <TableRow key={point.id} className={point.status === 'failed' ? 'text-destructive' : ''}>
              <TableCell className="font-mono text-xs">p{String(point.number).padStart(4, '0')}</TableCell>
              {names.map((name) => (
                <TableCell key={name} className="font-mono text-xs">
                  {show(point.params[name])}
                </TableCell>
              ))}
              {METRICS.map((one) => (
                <TableCell key={one.key} className="font-mono text-xs">
                  {show(point.metrics?.[one.key], one.digits)}
                </TableCell>
              ))}
              <TableCell className="text-xs">
                {point.status === 'ok' ? point.step_file.replace('points/', '') : point.status === 'failed' ? point.error.slice(0, 60) : '기다리는 중'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
