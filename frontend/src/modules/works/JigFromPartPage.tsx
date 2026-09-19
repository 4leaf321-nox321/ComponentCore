/**
 * 부품에서 지그 생성 — 지그의 두 번째 시작점(첫째는 빈 화면에서 그리기).
 *
 * 부품 하나를 고르면 규칙(3-2-1)으로 판 · 받침 · 위치 핀 · 클램프를 놓고 간섭을 검사한다.
 * 결과는 **지그 작업**이 되어 그 화면으로 간다 — 거기서부터는 그냥 그린다(받침 옮기기 · 변수 ·
 * DOE). 생성기는 출발점을 만들어 줄 뿐이라, 부품 화면이 아니라 여기(새 작업)에 있다.
 */

import { Boxes, Layers } from 'lucide-react'
import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { JigResultView } from '@/modules/jigs/JigResultView'
import type { Job } from '@/modules/jobs/api'
import { partsApi } from '@/modules/parts/api'
import { worksApi } from '@/modules/works/api'
import type { JigPreview, Work } from '@/modules/works/api'
import { JIG_KINDS, JigOptionsForm } from '@/modules/works/JigOptionsForm'
import type { JigKind } from '@/modules/works/JigOptionsForm'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { useFillHeight } from '@/shared/hooks/useFillHeight'
import { useResource } from '@/shared/hooks/useResource'

const PickViewer = lazy(() => import('@/shared/viewer/PickViewer'))

type Source = { key: string; label: string; hint: string }

/** 미리보기 색 — 요소 종류마다. 이름표(「받침 2」)의 앞말로 고른다. */
const ELEMENT_COLORS: { prefix: string; label: string; color: number; note: string }[] = [
  { prefix: '제품', label: '제품', color: 0x3b82f6, note: '고른 부품' },
  { prefix: '바닥판', label: '바닥판', color: 0x9ca3af, note: '부품 바닥 크기 + 판 여유' },
  { prefix: '바닥', label: '바닥', color: 0x9ca3af, note: '낙하 바닥 — 부품 발자국 + 여유' },
  { prefix: '받침대', label: '받침대', color: 0xf97316, note: '바닥에 구멍이 없으면 옆면을 받침대로 잡는다' },
  { prefix: '받침', label: '받침', color: 0x10b981, note: '부품 바닥면에서 구멍을 피해 놓는다(3 · 4개)' },
  { prefix: '위치 핀', label: '위치 핀', color: 0xf97316, note: '부품 바닥의 구멍 두 개에 꽂는다(가장 먼 쌍)' },
  { prefix: '클램프', label: '클램프', color: 0xa855f7, note: '부품 윗면 가장자리를 위에서 누른다' },
  { prefix: '볼트', label: '볼트', color: 0xa855f7, note: '부품의 관통 구멍(서로 먼 것부터)을 지나 판의 탭 구멍에' },
  { prefix: '스페이서', label: '스페이서', color: 0x10b981, note: '볼트 자리마다 부품을 띄우는 원통' },
  { prefix: '롤러', label: '롤러', color: 0x10b981, note: '긴 변 방향 ±스팬/2 에 눕힌 원기둥, 받침대 위' },
  { prefix: '로딩 노즈', label: '로딩 노즈', color: 0xa855f7, note: '스팬 가운데, 부품 윗면을 누른다' },
  { prefix: '임팩터', label: '낙하물', color: 0xef4444, note: '부품 윗면 가운데 위, 틈만큼 떨어져' },
]
const colorOfLabel = (label: string) => ELEMENT_COLORS.find((one) => label.startsWith(one.prefix))?.color ?? 0x3b82f6
const cssColor = (color: number) => `#${color.toString(16).padStart(6, '0')}`

export default function JigFromPartPage() {
  const navigate = useNavigate()
  const works = useResource(() => worksApi.list(0, 100), [])
  const parts = useResource(() => partsApi.list(0, 100), [])
  const defaults = useResource(() => worksApi.jigOptions(), [])
  const [source, setSource] = useState<Source | null>(null)
  const [kind, setKind] = useState<JigKind>('clamped')
  const [name, setName] = useState('')
  const [options, setOptions] = useState<Record<string, unknown> | null>(null)
  /** 옵션은 접어 둔다 — 서른 개를 펼쳐 두면 무엇을 해야 할지 안 보인다. */
  const [showOptions, setShowOptions] = useState(false)
  const [made, setMade] = useState<{ work: Work; job: Job } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)
  /** 미리보기 — 부품이나 옵션이 바뀌면 조금 쉬었다 다시 본다. 만들기와 같은 규칙이 돈다. */
  const [preview, setPreview] = useState<JigPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [previewError, setPreviewError] = useState<ApiError | Error | null>(null)
  const [emphasis, setEmphasis] = useState<string | null>(null)
  /** 미리보기는 아래 범례 · 단추가 보일 만큼만 남기고 화면을 채운다. */
  const fill = useFillHeight<HTMLDivElement>({ min: 380, gap: 220, deps: [source?.key, preview !== null] })

  useEffect(() => {
    if (!options && defaults.data) setOptions({ ...defaults.data, kind })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaults.data, options])
  // 형식은 옵션의 일부다 — 서버가 kind 로 규칙을 고른다.
  useEffect(() => {
    setOptions((now) => (now && now.kind !== kind ? { ...now, kind } : now))
  }, [kind])

  const optionsKey = JSON.stringify(options)
  useEffect(() => {
    if (!source || !options) {
      setPreview(null)
      return
    }
    let alive = true
    setPreviewing(true)
    const timer = setTimeout(async () => {
      try {
        const got = await worksApi.jigPreview({ source: source.key, options })
        if (!alive) return
        setPreview(got)
        setPreviewError(null)
      } catch (caught) {
        if (!alive) return
        setPreview(null)
        setPreviewError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
      } finally {
        if (alive) setPreviewing(false)
      }
    }, 600)
    return () => {
      alive = false
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source?.key, optionsKey])

  const partColors = useMemo(() => {
    const labels = new Set((preview?.mesh.faces ?? []).map((face) => face.part ?? ''))
    return Object.fromEntries([...labels].filter(Boolean).map((label) => [label, colorOfLabel(label)]))
  }, [preview])
  /** 3D 에 실제로 있는 종류만 범례에 — 받침대가 없으면 받침대 줄도 없다. */
  const legend = ELEMENT_COLORS.filter((one) => Object.keys(partColors).some((label) => label.startsWith(one.prefix)))

  const mine: Source[] = (works.data?.items ?? [])
    .filter((one) => one.kind === 'part' && one.current_version > 0)
    .map((one) => ({ key: `work:${one.id}`, label: one.name, hint: `내 작업 · v${one.current_version}` }))
  const shared: Source[] = (parts.data?.items ?? []).map((one) => ({ key: `part:${one.id}`, label: one.name, hint: `공용 부품 · v${one.current_version}` }))

  /** 끝난 결과를 지그 작업의 첫 버전으로 넣고 그 화면으로. */
  async function adopt(work: Work, job: Job) {
    await worksApi.adoptJigRun(work.id, job.id)
    navigate(`/works/${work.id}`)
  }

  async function run() {
    if (!source) return
    setBusy(true)
    setError(null)
    try {
      const got = await worksApi.jigFromPart({ source: source.key, name: name.trim() || undefined, options: options ?? {} })
      setMade(got)
      // 인라인 워커면 이미 끝나 있다 — 기다릴 것 없이 바로 가져간다.
      if (got.job.status === 'done') await adopt(got.work, got.job)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  /** 실패했으면 빈 지그 작업이 남는다 — 지우고 옵션을 고쳐 다시. */
  async function retry() {
    if (made) {
      try {
        await worksApi.remove(made.work.id)
      } catch {
        // 못 지워도 다시 시도는 되게 — 내 작업에서 지울 수 있다.
      }
    }
    setMade(null)
    setShowOptions(true)
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="부품에서 지그 생성"
        description="부품 하나를 고르면 규칙으로 바닥판 · 받침 · 위치 핀 · 클램프를 놓고 간섭을 검사합니다. 결과는 지그 작업이 되고, 거기서 이어서 그립니다."
        back={{ to: '/works', label: '내 작업' }}
      />
      <ErrorNotice error={error} />

      {made ? (
        <Card>
          <CardHeader>
            <CardTitle>
              {made.work.name} <span className="text-muted-foreground text-sm font-normal">— 만드는 중이면 끝날 때 지그 작업으로 이동합니다</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <JigResultView
              key={made.job.id}
              job={made.job}
              onFinished={(job) => {
                if (job.status === 'done') void adopt(made.work, job)
              }}
              actions={
                <Button size="sm" variant="outline" onClick={() => void retry()}>
                  옵션 고쳐 다시
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-12">
          {/* 1. 어느 부품인가 */}
          <Card className="lg:col-span-4">
            <CardHeader>
              <CardTitle>1. 부품 고르기</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <SourceList title="내 작업의 부품" icon={Layers} rows={mine} picked={source?.key} onPick={setSource} empty="저장된 부품 작업이 없습니다." />
              <SourceList title="공용 부품" icon={Boxes} rows={shared} picked={source?.key} onPick={setSource} empty="공용 부품이 없습니다." />
              <ErrorNotice error={works.error ?? parts.error} />
            </CardContent>
          </Card>

          {/* 2. 미리보기 · 옵션 · 만들기 */}
          <Card className="lg:col-span-8">
            <CardHeader>
              <CardTitle>2. 미리 보고 만들기</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* 형식 — 어떤 규칙으로 놓나. 먼저 고르고, 그 형식의 옵션만 편다. */}
              <div className="space-y-1">
                <Label>형식</Label>
                <div className="grid gap-1 sm:grid-cols-2">
                  {JIG_KINDS.map((one) => (
                    <button
                      key={one.value}
                      type="button"
                      onClick={() => setKind(one.value)}
                      aria-pressed={kind === one.value}
                      className={`rounded-md border px-2 py-1.5 text-left ${kind === one.value ? 'border-primary bg-accent' : 'hover:bg-accent/60'}`}
                    >
                      <span className="text-sm font-medium">{one.label}</span>
                      <span className="text-muted-foreground block text-xs">{one.hint}</span>
                    </button>
                  ))}
                </div>
              </div>
              {source ? (
                <p className="text-sm">
                  <b>{source.label}</b> <span className="text-muted-foreground text-xs">({source.hint})</span> 의 형상을 읽어 규칙으로 놓습니다 — 아래 3D 가 만들어질 그대로입니다. 형식 · 옵션을 바꾸면 따라 바뀝니다.
                </p>
              ) : (
                <p className="text-muted-foreground text-sm">왼쪽에서 부품을 고르면 여기에 미리보기가 뜹니다.</p>
              )}

              {/* 미리보기 — 만들기와 같은 규칙. 색은 요소 종류. */}
              {source && (
                <div className="space-y-2">
                  <div ref={fill.ref} style={fill.style}>
                  {preview ? (
                    <Suspense fallback={<Skeleton className="h-full w-full" />}>
                      <PickViewer mesh={preview.mesh} mode="none" partColors={partColors} emphasis={emphasis} className="h-full w-full rounded-md border" />
                    </Suspense>
                  ) : (
                    <div className="text-muted-foreground flex h-full items-center justify-center rounded-md border border-dashed text-sm">
                      {previewing ? '미리 보는 중…' : previewError ? '이 부품에는 규칙을 적용하지 못했습니다.' : '미리 보는 중…'}
                    </div>
                  )}
                  </div>
                  <ErrorNotice error={previewError} />
                  {preview && (
                    <>
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        {previewing && <span className="text-muted-foreground">다시 보는 중…</span>}
                        <span>{planLine(preview)}</span>
                        <StatusBadge kind="interference" value={preview.interference.ok ? 'ok' : 'bad'} />
                      </div>
                      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                        {legend.map((one) => (
                          <li key={one.prefix}>
                            <button
                              type="button"
                              className="flex items-center gap-1.5 text-left"
                              title={one.note}
                              onClick={() => {
                                // 그 종류의 첫 요소만 또렷하게 — 어디에 놓였는지 찾기.
                                const first = Object.keys(partColors).find((label) => label.startsWith(one.prefix)) ?? null
                                setEmphasis(emphasis && emphasis.startsWith(one.prefix) ? null : first)
                              }}
                            >
                              <span className="size-2.5 rounded-full" style={{ background: cssColor(one.color) }} aria-hidden />
                              <span className={emphasis?.startsWith(one.prefix) ? 'font-medium' : ''}>{one.label}</span>
                              <span className="text-muted-foreground">— {one.note}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                      {preview.plan.notes.length > 0 && (
                        <ul className="text-muted-foreground list-disc pl-5 text-xs">
                          {preview.plan.notes.map((note) => (
                            <li key={note}>{note}</li>
                          ))}
                        </ul>
                      )}
                      {!preview.interference.ok && (
                        <p className="text-destructive text-xs">간섭이 있습니다 — 옵션을 바꿔 보세요. 만든 뒤 도면에서 옮길 수도 있습니다.</p>
                      )}
                    </>
                  )}
                </div>
              )}
              <div className="space-y-1">
                <Label htmlFor="jig-name">지그 작업 이름</Label>
                <Input id="jig-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={source ? `${source.label} 지그` : ''} />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => void run()} disabled={busy || !source || !options || !!previewError}>
                  {busy ? '거는 중…' : '이대로 지그 만들기'}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setShowOptions(!showOptions)}>
                  {showOptions ? '세부 옵션 접기' : '세부 옵션 펴기'}
                </Button>
                {showOptions && (
                  <Button variant="ghost" size="sm" onClick={() => defaults.data && setOptions({ ...defaults.data, kind })}>
                    기본값으로
                  </Button>
                )}
              </div>
              {showOptions && options && <JigOptionsForm values={options} onChange={setOptions} />}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

/** 계획을 한 줄로 — 형식마다 세는 것이 다르다. */
function planLine(preview: JigPreview): string {
  const p = preview.plan
  if (p.kind === 'bolted') return `볼트 ${p.bolts.length}${p.product_lift > 0 ? ` · 스페이서 ${p.bolts.length}` : ''}`
  if (p.kind === 'bending') return `롤러 ${p.rollers.length} · 로딩 노즈 1`
  if (p.kind === 'drop') return p.impactor ? `바닥 · 낙하물(${p.impactor.kind === 'ball' ? '강구' : '펜'})` : '바닥 — 부품이 떨어진다'
  const locator = p.locators.some((one) => one.kind === 'pin') ? '위치 핀' : '받침대'
  return `받침 ${p.supports.length} · ${locator} ${p.locators.length} · 클램프 ${p.clamps.length}`
}

function SourceList({
  title,
  icon: Icon,
  rows,
  picked,
  onPick,
  empty,
}: {
  title: string
  icon: typeof Boxes
  rows: Source[]
  picked?: string
  onPick: (one: Source) => void
  empty: string
}) {
  return (
    <div>
      <p className="text-muted-foreground mb-1 flex items-center gap-1 text-xs">
        <Icon className="size-3" /> {title}
      </p>
      {rows.length === 0 ? (
        <p className="text-muted-foreground text-xs">{empty}</p>
      ) : (
        <ul className="space-y-1">
          {rows.map((row) => (
            <li key={row.key}>
              <button
                type="button"
                onClick={() => onPick(row)}
                aria-pressed={picked === row.key}
                className={`flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left text-sm ${picked === row.key ? 'border-primary bg-accent' : 'hover:bg-accent/60'}`}
              >
                <span className="truncate">{row.label}</span>
                <Badge variant="outline" className="ml-auto shrink-0 text-[10px]">
                  {row.hint}
                </Badge>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
