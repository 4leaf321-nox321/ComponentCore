/**
 * DOE 결과 — 설계점 표(바꾼 변수 · 파일 · 상태) · CSV · **공유 폴더로 보내기**.
 *
 * 질량 · 크기 같은 값은 여기 없다 — 결과는 해석(ANSYS)이 내고, 그것을 표에 붙이는 것이 다음
 * 일이다. 그때까지 표는 「어느 점이 어느 파일인가」 만 말한다.
 *
 * 이 화면의 끝은 「폴더를 열어 해석으로 넘긴다」 이다. 그래서 경로를 크게 보여 주고 복사까지
 * 한 번에 되게 둔다 — 경로를 손으로 옮겨 적다 틀리면 엉뚱한 폴더를 해석한다.
 */

import { Check, Copy, Download, FolderOpen, Send } from 'lucide-react'
import { useEffect, useState } from 'react'

import { doeApi } from '@/modules/doe/api'
import type { DoeStudy } from '@/modules/doe/api'
import { PointsGallery, pointRowProps } from '@/modules/doe/PointsGallery'
import type { GalleryMode } from '@/modules/doe/PointsGallery'
import { isFinished } from '@/modules/jobs/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { shownDateTime } from '@/shared/lib/datetime'
import { useJobPolling } from '@/modules/jobs/useJobPolling'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'

function show(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

export function DoeStudyView({ study, onReload }: { study: DoeStudy; onReload: () => void }) {
  const [copied, setCopied] = useState(false)
  /** 형상 보기 — 하나씩 볼 점과 겹쳐 · 나란히 볼 점들. 표가 고르고 갤러리가 그린다. */
  const [focus, setFocus] = useState<number | null>(null)
  const [picked, setPicked] = useState<number[]>([])
  const [galleryMode, setGalleryMode] = useState<GalleryMode>('single')
  const picking = galleryMode !== 'single'
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<ApiError | Error | null>(null)
  // 작업이 끝나면 스터디를 다시 불러온다 — 점마다 결과가 붙어야 표가 찬다.
  const job = useJobPolling(study.job)
  const running = job !== null && !isFinished(job)
  const finished = job !== null && isFinished(job)

  async function send() {
    setExporting(true)
    setExportError(null)
    try {
      await doeApi.export(study.id)
      onReload()
    } catch (caught) {
      setExportError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setExporting(false)
    }
  }
  useEffect(() => {
    if (job && isFinished(job) && job.status !== study.job?.status) onReload()
  }, [job, study.job?.status, onReload])

  const names = study.factors.filter((one) => one.mode !== 'fixed').map((one) => one.name)
  const rows = study.points

  return (
    <div className="space-y-4">
      {/* 공유 폴더 — 이 화면의 끝. 만들기는 서버 안에서 끝나고, 「보내기」 를 눌러야 해석이 읽는 폴더로 간다. */}
      <div className="bg-muted/40 flex flex-wrap items-center gap-2 rounded-md border p-3">
        <FolderOpen className="text-muted-foreground size-4 shrink-0" />
        <div className="min-w-0">
          {study.exported_at ? (
            <>
              <p className="text-xs font-medium">공유 폴더에 보냈습니다 ({shownDateTime(study.exported_at)}) — 해석은 이 폴더를 읽습니다</p>
              <p className="truncate font-mono text-xs">{study.export_dir_windows}</p>
            </>
          ) : (
            <>
              <p className="text-xs font-medium">아직 서버 안에만 있습니다</p>
              <p className="text-muted-foreground text-xs">{finished ? '「공유 폴더로 보내기」 를 누르면 해석이 읽는 폴더에 복사됩니다.' : '다 만들어지면 공유 폴더로 보낼 수 있습니다.'}</p>
            </>
          )}
        </div>
        <ErrorNotice error={exportError} />
        <Button size="sm" className="ml-auto" disabled={!finished || study.done === 0 || exporting} onClick={() => void send()}>
          <Send className="size-3.5" />
          {exporting ? '보내는 중…' : study.exported_at ? '다시 보내기' : '공유 폴더로 보내기'}
        </Button>
        {study.exported_at && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              void navigator.clipboard?.writeText(study.export_dir_windows)
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            }}
          >
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
            경로 복사
          </Button>
        )}
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
      </div>

      <PointsGallery study={study} focus={focus} onFocus={setFocus} picked={picked} onPicked={setPicked} mode={galleryMode} onMode={setGalleryMode} />

      <Table>
        <TableHeader>
          <TableRow>
            {picking && (
              <TableHead className="w-8" title="겹쳐 · 나란히 볼 점">
                <span className="sr-only">고름</span>
              </TableHead>
            )}
            <TableHead className="w-14">점</TableHead>
            {names.map((name) => (
              <TableHead key={name} className="font-mono text-xs">
                {name}
              </TableHead>
            ))}
            <TableHead>파일 · 상태</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((point) => {
            const row = pointRowProps(point, focus, picked, setFocus, setPicked)
            return (
            <TableRow
              key={point.id}
              onClick={row.focus}
              aria-selected={row.isFocus}
              className={`${point.status === 'failed' ? 'text-destructive' : ''} ${row.viewable ? 'cursor-pointer' : ''} ${row.isFocus ? 'bg-accent' : ''}`}
            >
              {picking && (
                <TableCell onClick={(event) => event.stopPropagation()}>
                  {row.viewable && <input type="checkbox" checked={row.isPicked} onChange={row.toggle} aria-label={`p${String(point.number).padStart(4, '0')} 고르기`} />}
                </TableCell>
              )}
              <TableCell className="font-mono text-xs">p{String(point.number).padStart(4, '0')}</TableCell>
              {names.map((name) => (
                <TableCell key={name} className="font-mono text-xs">
                  {show(point.params[name])}
                </TableCell>
              ))}
              <TableCell className="text-xs">
                {point.status === 'ok' ? point.step_file.replace('points/', '') : point.status === 'failed' ? point.error.slice(0, 60) : '기다리는 중'}
              </TableCell>
            </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
