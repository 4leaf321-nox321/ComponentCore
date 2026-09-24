/**
 * DOE 결과 — 설계점 표(바꾼 변수 · 파일 · 상태) · CSV · **공유 폴더로 보내기**.
 *
 * 질량 · 크기 같은 값은 여기 없다 — 결과는 해석(ANSYS)이 내고, 그것을 표에 붙이는 것이 다음
 * 일이다. 그때까지 표는 「어느 점이 어느 파일인가」 만 말한다.
 *
 * 이 화면의 끝은 「폴더를 열어 해석으로 넘긴다」 이다. 그래서 경로를 크게 보여 주고 복사까지
 * 한 번에 되게 둔다 — 경로를 손으로 옮겨 적다 틀리면 엉뚱한 폴더를 해석한다.
 */

import { Check, Copy, Download, Eye, EyeOff, FolderOpen, RefreshCw, Send } from 'lucide-react'
import { useEffect, useState } from 'react'

import { doeApi } from '@/modules/doe/api'
import type { DoeStudy } from '@/modules/doe/api'
import { PointsGallery, PointsNav, pointRowProps } from '@/modules/doe/PointsGallery'
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
  const [rerunning, setRerunning] = useState(false)
  const [hiding, setHiding] = useState(false)
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
  /**
   * **다시 만들기** — 파일이 없어도 이력이 뜻을 갖게 하는 길.
   *
   * 설계점 파일은 보관 기한이 지나면 치워지지만, 다시 만들 재료(레시피 · 인자 · 시드 · 조건)는
   * 스냅샷으로 DB 에 남아 있다. 그래서 같은 스터디에 **같은 것이 그대로** 다시 난다.
   */
  async function again(only: 'all' | 'failed') {
    setRerunning(true)
    setExportError(null)
    try {
      await doeApi.rerun(study.id, only)
      onReload()
    } catch (caught) {
      setExportError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setRerunning(false)
    }
  }
  /**
   * **누가 보나.** 기본은 공개다 — DOE 는 이 조직의 설계 이력이고, 옆 사람이 같은 훑기를
   * 다시 도는 것이 더 큰 손해다. 감추는 것이 예외다.
   */
  async function setSeen(value: 'read' | 'private') {
    setHiding(true)
    setExportError(null)
    try {
      await doeApi.setVisibility(study.id, value)
      onReload()
    } catch (caught) {
      setExportError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setHiding(false)
    }
  }
  useEffect(() => {
    if (job && isFinished(job) && job.status !== study.job?.status) onReload()
  }, [job, study.job?.status, onReload])

  const names = study.factors.filter((one) => one.mode !== 'fixed').map((one) => one.name)
  const rows = study.points
  const viewable = study.points.filter((one) => one.status === 'ok').map((one) => one.number)
  /** 조립을 훑었으면 점마다 겹침이 붙어 있다 — 그때만 열을 보인다. */
  const hasInterference = study.points.some((one) => one.interference)

  return (
    <div className="space-y-4">
      {/*
        설계점 파일이 치워졌을 때. **이력이 남아 있다는 말이 헛말이 되지 않게** 여기서 길을 준다 —
        표와 3D 는 스냅샷으로 그대로 뜨지만(3D 는 레시피로 다시 만든다) STEP 은 없으므로
        「보내기」 가 막힌다. 그 사실과 할 일을 한자리에서 말한다.
      */}
      {finished && study.done > 0 && !study.local_ready && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 dark:border-amber-700 dark:bg-amber-950/40">
          <RefreshCw className="size-4 shrink-0 text-amber-700 dark:text-amber-400" />
          <div className="min-w-0">
            <p className="text-xs font-medium">설계점 파일이 보관 기한을 지나 정리되었습니다</p>
            <p className="text-muted-foreground text-xs">설정(레시피 · 인자 · 시드 · 조건)은 그대로 남아 있습니다 — 「다시 만들기」 를 누르면 같은 것이 다시 납니다.</p>
          </div>
          <Button size="sm" className="ml-auto" disabled={rerunning || running} onClick={() => void again('all')}>
            <RefreshCw className="size-3.5" />
            {rerunning ? '거는 중…' : '다시 만들기'}
          </Button>
        </div>
      )}

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
              <p className="text-muted-foreground text-xs">{!finished ? '다 만들어지면 공유 폴더로 보낼 수 있습니다.' : study.local_ready ? '「공유 폴더로 보내기」 를 누르면 해석이 읽는 폴더에 복사됩니다.' : '보낼 파일이 없습니다 — 「다시 만들기」 를 먼저 누르세요.'}</p>
            </>
          )}
        </div>
        <ErrorNotice error={exportError} />
        <Button size="sm" className="ml-auto" disabled={!finished || study.done === 0 || !study.local_ready || exporting} onClick={() => void send()}>
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
        {/*
          누가 만들었고 누가 돌렸나. 기계(오케스트레이터)가 대행하면 둘이 달라진다 — 소유자는
          사람이고 돌린 것은 서비스 계정이다. 둘 다 안 보이면 「이건 누가 왜 돌렸지」 에
          답할 수 없다.
        */}
        {study.owner_name && (
          <Badge variant="outline" className="font-normal">
            {study.owner_name}
            {study.requested_by_name && ` (${study.requested_by_name} 대행)`}
          </Badge>
        )}
        <Button size="sm" variant="ghost" disabled={hiding} onClick={() => void setSeen(study.visibility === 'read' ? 'private' : 'read')}>
          {study.visibility === 'read' ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
          {study.visibility === 'read' ? '모두 봅니다' : '나만 봅니다'}
        </Button>
        <span>
          설계점 {study.point_count} 개 — 만든 것 <b>{study.done}</b>
          {study.failed > 0 && <span className="text-destructive"> · 실패 {study.failed}</span>}
        </span>
        {/* 실패한 점만 한 번 더. 범위를 고쳐 다시 돌리는 것이 아니라 **같은 값으로** 다시 해 보는 것이다. */}
        {finished && study.failed > 0 && (
          <Button size="sm" variant="outline" disabled={rerunning || running} onClick={() => void again('failed')}>
            <RefreshCw className="size-3.5" />
            실패한 {study.failed} 점만 다시
          </Button>
        )}
        {running && (
          <span className="text-muted-foreground">
            만드는 중… {job?.progress?.at(-1)?.detail ?? ''}
            <button type="button" className="ml-1 underline" onClick={onReload}>
              새로 고침
            </button>
          </span>
        )}
      </div>

      {/* 왼쪽 도면 · 오른쪽 목록, 3:1. 목록은 세로로 길어지니 제 안에서 스크롤한다. */}
      <div className="grid gap-4 lg:grid-cols-4">
        <div className="lg:col-span-3">
          <PointsGallery study={study} focus={focus} picked={picked} onPicked={setPicked} mode={galleryMode} onMode={setGalleryMode} />
        </div>
        <div className="space-y-2 lg:col-span-1">
          {galleryMode === 'single' ? (
            <PointsNav study={study} focus={focus} onFocus={setFocus} />
          ) : (
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={viewable.length > 0 && viewable.every((n) => picked.includes(n))}
                onChange={(event) => setPicked(event.target.checked ? viewable : [])}
                aria-label="전체 선택"
              />
              전체 선택 ({viewable.length})
            </label>
          )}
          {/* 변수가 많으면 가로로도 스크롤 — 표가 내용만큼 넓어지게(min-w-max) 두고 줄바꿈을 막는다. */}
          <div className="max-h-[calc(100vh-15rem)] overflow-auto rounded-md border">
            <Table className="min-w-max whitespace-nowrap">
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
                  {hasInterference && <TableHead title="구성품끼리 겹침 — 조립일 때">간섭</TableHead>}
                  <TableHead>상태</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((point) => {
                  const row = pointRowProps(point, focus, picked, setFocus, setPicked, galleryMode)
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
                    {hasInterference && (
                      <TableCell className="text-xs">
                        {point.interference ? (
                          point.interference.ok ? (
                            <span className="text-muted-foreground">없음</span>
                          ) : (
                            <span className="text-destructive" title={point.interference.items.filter((one) => !one.ok).map((one) => `${one.a} × ${one.b} ${one.volume} mm³`).join('\n')}>
                              {point.interference.items.filter((one) => !one.ok).length}건
                            </span>
                          )
                        ) : (
                          '—'
                        )}
                      </TableCell>
                    )}
                    <TableCell className="text-xs">
                      {point.status === 'ok' ? '만듦' : point.status === 'failed' ? <span title={point.error}>실패</span> : '기다리는 중'}
                    </TableCell>
                  </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    </div>
  )
}
