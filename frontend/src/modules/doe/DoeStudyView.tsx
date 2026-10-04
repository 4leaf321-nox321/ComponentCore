/**
 * DOE 결과 — 설계점 표(바꾼 변수 · 파일 · 상태) · CSV · **공유 폴더로 보내기**.
 *
 * 질량 · 크기 같은 값은 여기 없다 — 결과는 해석(ANSYS)이 내고, 그것을 표에 붙이는 것이 다음
 * 일이다. 그때까지 표는 「어느 점이 어느 파일인가」 만 말한다.
 *
 * 이 화면의 끝은 「폴더를 열어 해석으로 넘긴다」 이다. 그래서 경로를 크게 보여 주고 복사까지
 * 한 번에 되게 둔다 — 경로를 손으로 옮겨 적다 틀리면 엉뚱한 폴더를 해석한다.
 */

import { Check, Copy, Download, Eye, EyeOff, FolderOpen, Plus, RefreshCw, Send } from 'lucide-react'
import { useEffect, useState } from 'react'

import { doeApi, METHOD_LABELS, methodBadge } from '@/modules/doe/api'
import { ExtendPanel } from '@/modules/doe/ExtendPanel'
import { PointsScatter, ScatterDetails } from '@/modules/doe/PointsScatter'
import type { DoeStudy } from '@/modules/doe/api'
import { PointsGallery, PointsNav, pointRowProps } from '@/modules/doe/PointsGallery'
import type { GalleryMode } from '@/modules/doe/PointsGallery'
import { isFinished, runState } from '@/modules/jobs/api'
import { CancelJobButton } from '@/modules/jobs/CancelJobButton'
import { ApiError, downloadFile } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { shownDateTime } from '@/shared/lib/datetime'
import { useJobPolling } from '@/modules/jobs/useJobPolling'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'

function show(value: number | string | boolean | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  // 재료 · 고르기 인자는 글자(재료 이름 · 칸의 값)나 켬 · 끔이다.
  if (typeof value === 'string') return value
  if (typeof value === 'boolean') return value ? '켜짐' : '꺼짐'
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

export function DoeStudyView({
  study,
  onReload,
  editable = true,
}: {
  study: DoeStudy
  onReload: () => void
  /**
   * 고칠 수 있나(소유자 · 관리자). 아니면 보내기 · 재생성 · 점 추가 · 멈추기 · 공개 바꾸기를
   * 숨긴다 — 눌러도 서버가 막으므로, 보이면 「왜 안 되지」 만 남는다. 이어 하려면 복제한다.
   */
  editable?: boolean
}) {
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
  /** 점 더하기 패널 — 첫 결과를 보고 관심 구간을 좁혀 더 뽑는다. */
  const [extending, setExtending] = useState(false)
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
      setExportError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
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
      setExportError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
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
      setExportError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setHiding(false)
    }
  }
  useEffect(() => {
    if (job && isFinished(job) && job.status !== study.job?.status) onReload()
  }, [job, study.job?.status, onReload])

  /** 바꾼 변수 — 더한 묶음에서 범위를 준 변수도(첫 묶음에선 고정이었어도). */
  const batches = study.batches ?? []
  const names = study.factors
    .filter((one) => one.mode !== 'fixed' || batches.some((batch) => batch.factors.some((other) => other.name === one.name && other.mode !== 'fixed')))
    .map((one) => one.name)
  /** 측정값 열 — 스터디가 정한 것(점마다 형상에서 잰 값). */
  const measureNames = (study.measures ?? []).map((one) => one.name)
  /** 이 점은 몇째 묶음인가 — 더한 묶음이 없으면 묻지 않는다. */
  const batchOf = (number: number) => batches.find((one) => number >= one.from && number <= one.to)?.number ?? 1
  const rows = study.points
  const viewable = study.points.filter((one) => one.status === 'ok').map((one) => one.number)
  /** 조립을 훑었으면 점마다 겹침이 붙어 있다 — 그때만 열을 보인다. */
  const hasInterference = study.points.some((one) => one.interference)
  /** 형상 점검 — 잰 점이 하나라도 있으면 열을 보인다. 경고 수만 적고 내용은 말풍선에. */
  const hasQuality = study.points.some((one) => one.quality)
  const warned = study.points.filter((one) => (one.quality?.warnings.length ?? 0) > 0).length
  /** 아직 안 만든 점 — 멈춘 DOE 면 이어 만들 수 있다. */
  const pending = study.points.filter((one) => one.status === 'pending').length

  return (
    <div className="space-y-4">
      {/*
        설계점 파일이 치워졌을 때. **이력이 남아 있다는 말이 헛말이 되지 않게** 여기서 길을 준다 —
        표와 3D 는 스냅샷으로 그대로 뜨지만(3D 는 레시피로 다시 만든다) STEP 은 없으므로
        「보내기」 가 막힌다. 그 사실과 할 일을 한자리에서 말한다.
      */}
      {editable && finished && study.done > 0 && !study.local_ready && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 dark:border-amber-700 dark:bg-amber-950/40">
          <RefreshCw className="size-4 shrink-0 text-amber-700 dark:text-amber-400" />
          <div className="min-w-0">
            <p className="text-xs font-medium">설계점 파일이 보관 기한 경과로 정리되었습니다.</p>
            <p className="text-muted-foreground text-xs">설정(레시피, 인자, 시드, 조건)은 보존되어 있습니다. ‘재생성’을 클릭하면 동일한 설계점이 다시 생성됩니다.</p>
          </div>
          <Button size="sm" className="ml-auto" disabled={rerunning || running} onClick={() => void again('all')}>
            <RefreshCw className="size-3.5" />
            {rerunning ? '요청 중…' : '재생성'}
          </Button>
        </div>
      )}

      {/* 공유 폴더 — 이 화면의 끝. 만들기는 서버 안에서 끝나고, 「보내기」 를 눌러야 해석이 읽는 폴더로 간다. */}
      <div className="bg-muted/40 flex flex-wrap items-center gap-2 rounded-md border p-3">
        <FolderOpen className="text-muted-foreground size-4 shrink-0" />
        <div className="min-w-0">
          {study.exported_at ? (
            <>
              <p className="text-xs font-medium">공유 폴더로 내보냈습니다({shownDateTime(study.exported_at)}). 해석은 이 폴더를 사용합니다.</p>
              <p className="truncate font-mono text-xs">{study.export_dir_windows}</p>
            </>
          ) : (
            <>
              <p className="text-xs font-medium">아직 서버에만 저장되어 있습니다.</p>
              <p className="text-muted-foreground text-xs">
                {!editable
                  ? '소유자가 공유 폴더로 내보내면 해석에 사용할 수 있습니다.'
                  : !finished
                    ? '생성이 완료되면 공유 폴더로 내보낼 수 있습니다.'
                    : study.local_ready
                      ? '‘공유 폴더로 내보내기’를 클릭하면 해석용 폴더로 복사됩니다.'
                      : '내보낼 파일이 없습니다. 먼저 ‘재생성’을 클릭하십시오.'}
              </p>
            </>
          )}
        </div>
        {study.export_stale && (
          <p className="w-full text-xs text-amber-700 dark:text-amber-400">내보낸 뒤 설계점이 추가되었습니다. 해석에 새 설계점을 반영하려면 다시 내보내십시오.</p>
        )}
        <ErrorNotice error={exportError} />
        {editable && (
          <Button size="sm" className="ml-auto" disabled={!finished || study.done === 0 || !study.local_ready || exporting} onClick={() => void send()}>
            <Send className="size-3.5" />
            {exporting ? '내보내는 중…' : study.exported_at ? '다시 내보내기' : '공유 폴더로 내보내기'}
          </Button>
        )}
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
        <Button size="sm" variant="outline" onClick={() => void downloadFile(doeApi.manifestPath(study.id), `${study.name}-manifest.csv`)}>
          <Download className="size-3.5" /> CSV
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="secondary">{methodBadge(study)}</Badge>
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
        {editable ? (
          <Button size="sm" variant="ghost" disabled={hiding} onClick={() => void setSeen(study.visibility === 'read' ? 'private' : 'read')}>
            {study.visibility === 'read' ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
            {study.visibility === 'read' ? '전체 공개' : '비공개'}
          </Button>
        ) : (
          <Badge variant="outline" className="font-normal">
            {study.visibility === 'read' ? '전체 공개' : '비공개'}
          </Badge>
        )}
        <span>
          설계점 {study.point_count}개: 생성 <b>{study.done}</b>
          {study.failed > 0 && <span className="text-destructive">, 실패 {study.failed}</span>}
          {warned > 0 && <span className="text-amber-700 dark:text-amber-400">, 점검 경고 {warned}</span>}
        </span>
        {/* 멈춘 DOE — 만든 점은 남아 있고, 남은 점은 같은 값으로 이어 만든다. */}
        {editable && finished && job?.status === 'cancelled' && pending > 0 && (
          <Button size="sm" disabled={rerunning} onClick={() => void again('failed')}>
            <RefreshCw className="size-3.5" />
            남은 설계점 {pending}개 이어서 생성
          </Button>
        )}
        {/* 실패한 점만 한 번 더. 범위를 고쳐 다시 돌리는 것이 아니라 **같은 값으로** 다시 해 보는 것이다. */}
        {editable && finished && study.failed > 0 && (
          <Button size="sm" variant="outline" disabled={rerunning || running} onClick={() => void again('failed')}>
            <RefreshCw className="size-3.5" />
            실패한 설계점 {study.failed}개 재생성
          </Button>
        )}
        {editable && finished && (
          <Button size="sm" variant="outline" disabled={rerunning || running} onClick={() => setExtending(!extending)} aria-expanded={extending}>
            <Plus className="size-3.5" />
            설계점 추가
          </Button>
        )}
        {running && job && (
          <>
            <StatusBadge kind="run" value={runState(job)} />
            {editable && (
              <CancelJobButton
                job={job}
                what="DOE 생성"
                keeps="그때까지 생성된 설계점과 표는 보존되며, 남은 설계점은 ‘이어서 생성’으로 계속 생성할 수 있습니다."
                cancel={() => doeApi.cancel(study.id)}
              />
            )}
          </>
        )}
        {running && (
          <span className="text-muted-foreground">
            생성 중… {job?.progress?.at(-1)?.detail ?? ''}
            <button type="button" className="ml-1 underline" onClick={onReload}>
              새로고침
            </button>
          </span>
        )}
      </div>

      {extending && (
        <ExtendPanel
          study={study}
          onDone={() => {
            setExtending(false)
            onReload()
          }}
        />
      )}
      {study.outputs?.includes('midsurface') && (
        <p className="text-muted-foreground text-xs">설계점마다 중간면 STEP도 출력합니다(셸 요소용, 표의 mid_file 열). 판이 아닌 설계점은 warnings 열에 사유가 기록됩니다.</p>
      )}
      {/* 더한 묶음의 이력 — 「이 점은 어디서 왔나」. 첫 묶음은 위의 방식 배지가 말한다. */}
      {batches.length > 0 && (
        <ul className="text-muted-foreground space-y-0.5 text-xs" aria-label="추가 배치">
          {batches.map((one) => (
            <li key={one.number}>
              배치 {one.number}: {METHOD_LABELS[one.method] ?? one.method} 설계점 {one.added}개{one.method === 'lhs' ? `, 시드 ${one.seed}` : ''}, p
              {String(one.from).padStart(4, '0')}–p{String(one.to).padStart(4, '0')}
              {one.skipped > 0 && `, 중복 ${one.skipped}개 제외`}
              {one.requested_by && `, ${one.requested_by}`}
            </li>
          ))}
        </ul>
      )}
      {/* 설계점 분포 — 몰린 곳 · 빈 곳 · 실패가 모인 구석. 점을 누르면 그 점의 형상을 본다. */}
      {names.length > 0 && rows.length > 1 && (
        <ScatterDetails summary="설계점 분포 (밀집 영역, 빈 영역, 실패한 설계점의 위치 확인)">
          {() => (
            <PointsScatter
              names={names}
              batches={batches.length + 1}
              focus={focus}
              onPick={(number) => {
                setGalleryMode('single')
                setFocus(number)
              }}
              points={rows.map((point) => ({
                number: point.number,
                values: point.params,
                status: point.status,
                batch: batchOf(point.number),
              }))}
            />
          )}
        </ScatterDetails>
      )}
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
                    <TableHead className="w-8" title="중첩 보기·병렬 보기 대상 설계점">
                      <span className="sr-only">선택</span>
                    </TableHead>
                  )}
                  <TableHead className="w-14">설계점</TableHead>
                  {batches.length > 0 && <TableHead title="설계점이 추가된 배치 번호">배치</TableHead>}
                  {names.map((name) => (
                    <TableHead key={name} className="font-mono text-xs">
                      {name}
                    </TableHead>
                  ))}
                  {measureNames.map((name) => (
                    <TableHead key={`m-${name}`} className="font-mono text-xs text-sky-700 dark:text-sky-400" title="측정값: 형상에서 측정한 값">
                      {name}
                    </TableHead>
                  ))}
                  {hasInterference && <TableHead title="구성품 간 간섭(조립인 경우)">간섭</TableHead>}
                  {hasQuality && <TableHead title="형상 점검: 얇은 벽, 짧은 모서리, 좁은 면, 분리된 바디">점검</TableHead>}
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
                        {row.viewable && <input type="checkbox" checked={row.isPicked} onChange={row.toggle} aria-label={`p${String(point.number).padStart(4, '0')} 선택`} />}
                      </TableCell>
                    )}
                    <TableCell className="font-mono text-xs">p{String(point.number).padStart(4, '0')}</TableCell>
                    {batches.length > 0 && <TableCell className="text-xs">{batchOf(point.number)}</TableCell>}
                    {names.map((name) => (
                      <TableCell key={name} className="font-mono text-xs">
                        {show(point.params[name])}
                      </TableCell>
                    ))}
                    {measureNames.map((name) => (
                      <TableCell key={`m-${name}`} className="font-mono text-xs">
                        {show(point.measures?.[name], 4)}
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
                    {hasQuality && (
                      <TableCell className="text-xs">
                        {!point.quality ? (
                          '—'
                        ) : point.quality.warnings.length > 0 ? (
                          <span className="text-amber-700 dark:text-amber-400" title={point.quality.warnings.join('\n')}>
                            경고 {point.quality.warnings.length}
                          </span>
                        ) : (
                          <span className="text-muted-foreground" title={point.quality.notes?.join('\n') || undefined}>
                            통과
                          </span>
                        )}
                      </TableCell>
                    )}
                    <TableCell className="text-xs">
                      {point.status === 'ok' ? '생성됨' : point.status === 'failed' ? <span title={point.error}>실패</span> : '대기 중'}
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
