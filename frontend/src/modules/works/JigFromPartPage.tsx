/**
 * 부품에서 지그 생성 — 지그의 두 번째 시작점(첫째는 빈 화면에서 그리기).
 *
 * 부품 하나를 고르면 규칙(3-2-1)으로 판 · 받침 · 위치 핀 · 클램프를 놓고 간섭을 검사한다.
 * 결과는 **지그 작업**이 되어 그 화면으로 간다 — 거기서부터는 그냥 그린다(받침 옮기기 · 변수 ·
 * DOE). 생성기는 출발점을 만들어 줄 뿐이라, 부품 화면이 아니라 여기(새 작업)에 있다.
 */

import { Boxes, Layers } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { JigResultView } from '@/modules/jigs/JigResultView'
import type { Job } from '@/modules/jobs/api'
import { partsApi } from '@/modules/parts/api'
import { worksApi } from '@/modules/works/api'
import type { Work } from '@/modules/works/api'
import { JigOptionsForm } from '@/modules/works/JigOptionsForm'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'

type Source = { key: string; label: string; hint: string }

export default function JigFromPartPage() {
  const navigate = useNavigate()
  const works = useResource(() => worksApi.list(0, 100), [])
  const parts = useResource(() => partsApi.list(0, 100), [])
  const defaults = useResource(() => worksApi.jigOptions(), [])
  const [source, setSource] = useState<Source | null>(null)
  const [name, setName] = useState('')
  const [options, setOptions] = useState<Record<string, unknown> | null>(null)
  /** 옵션은 접어 둔다 — 서른 개를 펼쳐 두면 무엇을 해야 할지 안 보인다. */
  const [showOptions, setShowOptions] = useState(false)
  const [made, setMade] = useState<{ work: Work; job: Job } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)

  useEffect(() => {
    if (!options && defaults.data) setOptions(defaults.data)
  }, [defaults.data, options])

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
          <Card className="lg:col-span-5">
            <CardHeader>
              <CardTitle>1. 부품 고르기</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <SourceList title="내 작업의 부품" icon={Layers} rows={mine} picked={source?.key} onPick={setSource} empty="저장된 부품 작업이 없습니다." />
              <SourceList title="공용 부품" icon={Boxes} rows={shared} picked={source?.key} onPick={setSource} empty="공용 부품이 없습니다." />
              <ErrorNotice error={works.error ?? parts.error} />
            </CardContent>
          </Card>

          {/* 2. 이름 · 옵션 · 만들기 */}
          <Card className="lg:col-span-7">
            <CardHeader>
              <CardTitle>2. 만들기</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {source ? (
                <p className="text-sm">
                  <b>{source.label}</b> <span className="text-muted-foreground text-xs">({source.hint})</span> 을 올려놓고 잡는 지그를 만듭니다. 기본값 그대로 눌러 보고, 결과를 보며 고치면 됩니다.
                </p>
              ) : (
                <p className="text-muted-foreground text-sm">왼쪽에서 부품을 고르세요.</p>
              )}
              <div className="space-y-1">
                <Label htmlFor="jig-name">지그 작업 이름</Label>
                <Input id="jig-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={source ? `${source.label} 지그` : ''} />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => void run()} disabled={busy || !source || !options}>
                  {busy ? '거는 중…' : '지그 만들기'}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setShowOptions(!showOptions)}>
                  {showOptions ? '세부 옵션 접기' : '세부 옵션 펴기'}
                </Button>
                {showOptions && (
                  <Button variant="ghost" size="sm" onClick={() => defaults.data && setOptions(defaults.data)}>
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
