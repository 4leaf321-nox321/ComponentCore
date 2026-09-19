/**
 * 실험계획 만들기 — 레시피의 **변수**를 인자로 고르고, 범위를 주고, 개수를 확인하고 실행한다.
 *
 * 실행 전에 **몇 개인지 먼저 보여 준다.** 격자는 곱으로 늘어나서, 인자 넷에 5단계면 625개다 —
 * 누르고 나서 아는 것과 누르기 전에 아는 것은 다르다.
 */

import { useEffect, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { doeApi } from '@/modules/doe/api'
import type { DoeStudy, Factor, Preview } from '@/modules/doe/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/components/ui/select'
import { Textarea } from '@/shared/components/ui/textarea'


/** 서버의 기본 가공 단위와 같다(core/doe.py DEFAULT_RESOLUTION). */
const DEFAULT_RESOLUTION = 0.1
/** 고를 수 있는 가공 단위 — 밀링 · 판금에서 흔히 쓰는 것들. */
const RESOLUTIONS = [1, 0.5, 0.1, 0.05, 0.01]

/** 숫자 칸의 값 — 비었으면 null. `Number('')` 은 0 이라 그대로 두면 지운 칸이 0 이 된다. */
function numberOrNull(text: string): number | null {
  if (text.trim() === '') return null
  const value = Number(text)
  return Number.isFinite(value) ? value : null
}

/** 서버의 snap 과 같은 규칙 — 단위의 배수로, 반올림(half-up). */
function snap(value: number, unit: number): number {
  if (unit <= 0) return value
  const quotient = Number((value / unit).toFixed(9))
  return Number((Math.floor(quotient + 0.5) * unit).toFixed(10))
}

function ResolutionSelect({ name, value, onChange }: { name: string; value: number; onChange: (unit: number) => void }) {
  return (
    <label className="flex items-center gap-1 text-xs">
      <span className="text-muted-foreground" title="값을 이 단위의 배수로 맞춥니다 — 가공할 수 있는 치수만 나오게">
        단위
      </span>
      <Select value={String(value)} onValueChange={(next) => onChange(Number(next))}>
        <SelectTrigger className="h-8 w-20 text-xs" aria-label={`${name} 가공 단위`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {RESOLUTIONS.map((one) => (
            <SelectItem key={one} value={String(one)}>
              {one} mm
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  )
}

export function DoeForm({
  recipe,
  workId,
  defaultName,
  onCreated,
  onEditRecipe,
  initial,
}: {
  recipe: Recipe
  workId?: string
  defaultName?: string
  onCreated: (id: string) => void
  /** 지난 DOE 의 설정으로 시작할 때 — 「설정 바꿔 다시 만들기」. 도면에 없어진 변수는 버린다. */
  initial?: Pick<DoeStudy, 'name' | 'description' | 'factors' | 'method' | 'samples' | 'seed'>
  /** 「치수가 없다」 일 때 편집기로 보내 준다 — 글로만 알려 주면 못 찾는다. */
  onEditRecipe?: () => void
}) {
  const params = Object.entries((recipe.params ?? {}) as Record<string, number>)
  const [name, setName] = useState(initial?.name ?? defaultName ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [method, setMethod] = useState<'factorial' | 'lhs'>(initial?.method ?? 'factorial')
  // 숫자 칸은 비울 수 있다(null) — 다 지우고 처음부터 치는 것을 막으면 첫 자리부터 못 친다.
  // 비어 있으면 미리보기를 안 묻고 「만들기」 가 막힌다.
  const [samples, setSamples] = useState<number | null>(initial?.samples ?? 20)
  const [seed, setSeed] = useState<number | null>(initial?.seed ?? 1)
  const [factors, setFactors] = useState<Record<string, Factor>>(() => {
    const before = new Map((initial?.factors ?? []).map((one) => [one.name, one]))
    // 도면에 지금 있는 변수만 — 지난 설정이 있으면 그것을, 없으면 고정(지금 값).
    return Object.fromEntries(params.map(([key, value]) => [key, before.get(key) ?? { name: key, mode: 'fixed', value }]))
  })
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  const list = Object.values(factors)
  const varying = list.filter((one) => one.mode !== 'fixed')
  /** 빈 칸이 있으면 아직 쓰는 중이다 — 서버에 묻지도, 만들지도 않는다. */
  const incomplete =
    varying.some((one) => (one.mode === 'range' ? one.start == null || one.end == null || one.steps == null : (one.values ?? []).length === 0)) ||
    (method === 'lhs' && (samples == null || seed == null))

  useEffect(() => {
    if (varying.length === 0 || incomplete) {
      setPreview(null)
      return
    }
    let alive = true
    void doeApi
      .preview({ factors: list, method, samples: samples ?? 20, seed: seed ?? 1 })
      .then((got) => alive && setPreview(got))
      .catch(() => alive && setPreview(null))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(list), method, samples, seed, incomplete])

  /**
   * 방식을 바꿀 때 칸의 기본값을 **상태에도** 넣는다. 화면만 기본값을 보여 주고 상태는 비워 두면,
   * 손대지 않은 칸이 서버에 빈 채로 가서 「start 가 숫자가 아닙니다」 가 난다.
   */
  function withDefaults(factor: Factor, mode: Factor['mode']): Partial<Factor> {
    const base = factor.value ?? 0
    if (mode === 'range') return { mode, start: factor.start ?? base, end: factor.end ?? base * 2, steps: factor.steps ?? 5 }
    if (mode === 'list') return { mode, values: factor.values?.length ? factor.values : [base] }
    return { mode }
  }

  /**
   * 구간이 실제로 내는 값들 — 서버의 levels 와 같은 규칙: 끝을 포함하고, 가공 단위로 맞추고,
   * 맞추다 겹친 값은 하나만. 0.333 같은 치수는 가공할 수 없어서다.
   */
  function levelsOf(factor: Factor): number[] {
    const start = factor.start ?? 0
    const end = factor.end ?? 0
    const steps = Math.max(1, factor.steps ?? 1)
    const unit = factor.resolution ?? DEFAULT_RESOLUTION
    const raw = steps === 1 ? [start] : Array.from({ length: steps }, (_, i) => start + ((end - start) * i) / (steps - 1))
    const out: number[] = []
    for (const value of raw.map((one) => snap(one, unit))) if (out.length === 0 || out[out.length - 1] !== value) out.push(value)
    return out
  }

  function set(key: string, patch: Partial<Factor>) {
    setFactors((all) => ({ ...all, [key]: { ...all[key], ...patch } }))
  }

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const made = await doeApi.create({
        name,
        description,
        recipe,
        factors: list,
        method,
        samples: samples ?? 20,
        seed: seed ?? 1,
        work_id: workId ?? null,
      })
      onCreated(made.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  if (params.length === 0) {
    return (
      <div className="space-y-3 rounded-md border border-dashed p-4 text-sm">
        <p className="font-medium">먼저 도면에 「변수」 를 만들어야 합니다.</p>
        <p className="text-muted-foreground">DOE 는 **변수**만 훑습니다 — 값에 이름이 없으면 무엇을 바꿔야 할지 알 수 없습니다.</p>
        <ol className="text-muted-foreground list-inside list-decimal space-y-1 text-xs">
          <li>「수정」 을 눌러 편집기를 엽니다.</li>
          <li>
            왼쪽 위 <b>변수</b> 상자의 <b>+</b> 로 이름과 값을 만듭니다 — 예: <code>두께</code>, 6.
          </li>
          <li>
            바꿀 피처(또는 스케치 도형)를 눌러 열고, 그 숫자 칸의 <b>fx</b> 를 누른 뒤 <code>=두께</code> 라고 씁니다.
          </li>
          <li>「새 버전으로」 저장하면 여기서 그 치수를 훑을 수 있습니다.</li>
        </ol>
        {onEditRecipe && (
          <Button size="sm" onClick={onEditRecipe}>
            도면 고치러 가기
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor="doe-name">이름</Label>
        <Input id="doe-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="브래킷 두께 훑기" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="doe-desc">무엇을 찾는가</Label>
        <Textarea id="doe-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} placeholder="세트 공진 440 Hz 에 맞는 두께를 찾는다" />
      </div>

      <div className="rounded-md border">
        <div className="bg-muted/40 grid grid-cols-[1fr_auto_2fr] items-center gap-2 border-b px-3 py-2 text-xs font-medium">
          <span>변수</span>
          <span>방식</span>
          <span>값</span>
        </div>
        {params.map(([key]) => {
          const factor = factors[key]
          return (
            <div key={key} className="grid grid-cols-[minmax(6rem,1fr)_auto_minmax(0,3fr)] items-center gap-3 border-b px-3 py-2 last:border-b-0">
              <span className="truncate font-mono text-xs" title={key}>
                {key}
              </span>
              <Select value={factor.mode} onValueChange={(mode) => set(key, withDefaults(factor, mode as Factor['mode']))}>
                <SelectTrigger className="h-8 w-28 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="fixed">고정</SelectItem>
                  <SelectItem value="range">구간</SelectItem>
                  <SelectItem value="list">값 목록</SelectItem>
                </SelectContent>
              </Select>
              {factor.mode === 'fixed' && (
                <Input type="number" step={0.5} value={factor.value ?? ''} onChange={(e) => set(key, { value: numberOrNull(e.target.value) })} className="h-8" aria-label={`${key} 고정값`} />
              )}
              {factor.mode === 'range' && (
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <label className="flex items-center gap-1 text-xs">
                      <span className="text-muted-foreground">시작</span>
                      <Input type="number" step={0.5} value={factor.start ?? ''} onChange={(e) => set(key, { start: numberOrNull(e.target.value) })} className="h-8 w-24" aria-label={`${key} 시작`} />
                    </label>
                    <label className="flex items-center gap-1 text-xs">
                      <span className="text-muted-foreground">끝</span>
                      <Input type="number" step={0.5} value={factor.end ?? ''} onChange={(e) => set(key, { end: numberOrNull(e.target.value) })} className="h-8 w-24" aria-label={`${key} 끝`} />
                    </label>
                    <label className="flex items-center gap-1 text-xs">
                      <span className="text-muted-foreground">단계</span>
                      <Input type="number" min={1} max={50} value={factor.steps ?? ''} onChange={(e) => set(key, { steps: numberOrNull(e.target.value) })} className="h-8 w-20" aria-label={`${key} 단계`} />
                    </label>
                    <ResolutionSelect name={key} value={factor.resolution ?? DEFAULT_RESOLUTION} onChange={(unit) => set(key, { resolution: unit })} />
                  </div>
                  {/* 어떤 값들이 나오는지 바로 보인다 — 「5단계」 만으로는 6, 7.5, 9 … 를 머리로 세야 한다. */}
                  <p className="text-muted-foreground truncate font-mono text-[11px]" title={levelsOf(factor).join(', ')}>
                    {levelsOf(factor).join(' · ')}
                  </p>
                </div>
              )}
              {factor.mode === 'list' && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Input
                    value={(factor.values ?? []).join(', ')}
                    onChange={(e) => set(key, { values: e.target.value.split(/[,\s]+/).map(Number).filter((v) => Number.isFinite(v)) })}
                    placeholder="4, 8, 12"
                    className="h-8 min-w-40 flex-1 font-mono text-xs"
                    aria-label={`${key} 값 목록`}
                  />
                  <ResolutionSelect name={key} value={factor.resolution ?? DEFAULT_RESOLUTION} onChange={(unit) => set(key, { resolution: unit })} />
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="doe-method">방법</Label>
          <Select value={method} onValueChange={(v) => setMethod(v as 'factorial' | 'lhs')}>
            <SelectTrigger id="doe-method" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="factorial">전체 조합 (격자)</SelectItem>
              <SelectItem value="lhs">라틴 하이퍼큐브 (LHS)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {method === 'lhs' && (
          <>
            <div className="space-y-1">
              <Label htmlFor="doe-samples">표본 수{preview?.max_samples ? ` (≤ ${preview.max_samples})` : ''}</Label>
              <Input id="doe-samples" type="number" min={1} max={preview?.max_samples} value={samples ?? ''} onChange={(e) => setSamples(numberOrNull(e.target.value))} className="w-24" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="doe-seed">시드</Label>
              <Input id="doe-seed" type="number" value={seed ?? ''} onChange={(e) => setSeed(numberOrNull(e.target.value))} className="w-24" />
            </div>
          </>
        )}
        <div className="text-muted-foreground text-xs">
          {varying.length === 0 ? (
            '바꿀 변수를 하나는 고르세요 — 「구간」 이나 「값 목록」 으로.'
          ) : incomplete ? (
            '빈 칸을 채우면 설계점을 셉니다.'
          ) : preview ? (
            <span className={preview.too_many ? 'text-destructive' : ''}>
              설계점 <b>{preview.count}</b> 개{' '}
              {preview.too_many && `— 한 번에 ${preview.max} 개까지 만듭니다(서버 설정 DOE_MAX_POINTS). 단계를 줄이거나, LHS 로 표본 수를 정하세요.`}
            </span>
          ) : (
            '세는 중…'
          )}
        </div>
        <Button className="ml-auto" disabled={busy || !name.trim() || varying.length === 0 || incomplete || !!preview?.too_many} onClick={() => void run()}>
          {busy ? '만드는 중…' : '만들기'}
        </Button>
      </div>
      {method === 'lhs' && (
        <p className="text-muted-foreground text-xs">시드를 적어 두면 **같은 표**를 다시 만들 수 있습니다 — 해석 결과와 형상을 잇는 열쇠입니다.</p>
      )}
      <ErrorNotice error={error} />
    </div>
  )
}
