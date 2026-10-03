/**
 * 점 더하기 — 이미 만든 DOE 에 설계점을 **번호를 이어** 더한다(같은 폴더).
 *
 * 첫 결과를 보고 관심 구간을 좁혀 더 뽑을 때 쓴다. 새 DOE 로 만들면 폴더 · 표가 둘로 갈라져
 * 해석 쪽이 둘을 이어 붙여야 한다. 변수는 그대로이고 **범위만** 바꾼다 — 바꾸지 않은 변수는
 * 첫 묶음의 정의를 따른다. 스터디의 제약식이 그대로 걸리고, 이미 있는 점과 같은 값은 뺀다.
 */

import { useEffect, useState } from 'react'

import { doeApi } from '@/modules/doe/api'
import type { Batch, DoeMethod, DoeStudy, ExtendBody, Factor } from '@/modules/doe/api'
import { parseTable } from '@/modules/doe/csvTable'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Textarea } from '@/shared/components/ui/textarea'

/** 형상을 안 바꾸는 인자 — 범위가 없다. */
const NON_SHAPE = new Set(['material', 'choice', 'scale'])

function numberOrNull(text: string): number | null {
  if (text.trim() === '') return null
  const value = Number(text)
  return Number.isFinite(value) ? value : null
}

/** 처음 정의에서 「구간」 으로 바꿀 때의 시작값 — 값 목록이면 가장 작은 · 큰 값. */
function rangeOf(factor: Factor): { start: number; end: number; steps: number } {
  if (factor.mode === 'range') return { start: factor.start ?? 0, end: factor.end ?? 0, steps: factor.steps ?? 5 }
  const values = (factor.values ?? []).map(Number).filter(Number.isFinite)
  if (factor.mode === 'list' && values.length) return { start: Math.min(...values), end: Math.max(...values), steps: values.length }
  return { start: factor.value ?? 0, end: factor.value ?? 0, steps: 1 }
}

export function ExtendPanel({ study, onDone }: { study: DoeStudy; onDone: () => void }) {
  const numeric = study.factors.filter((one) => !NON_SHAPE.has(one.mode))
  // 처음과 같은 방식으로 — Sobol 이면 같은 수열을 이어 뽑는 것이 기본이다.
  const [method, setMethod] = useState<DoeMethod>(study.method === 'factorial' || study.method === 'sobol' ? study.method : 'lhs')
  const [samples, setSamples] = useState<number | null>(10)
  const [seed, setSeed] = useState<number | null>(null)
  /** 바꿀 변수만 — 이름 → 새 구간. 없으면 첫 묶음의 정의 그대로. */
  const [ranges, setRanges] = useState<Record<string, { start: number | null; end: number | null; steps: number | null }>>({})
  const [tableText, setTableText] = useState('')
  const [count, setCount] = useState<Batch | null>(null)
  const [countError, setCountError] = useState<ApiError | Error | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  const overrides: Factor[] = Object.entries(ranges).map(([name, one]) => ({ name, mode: 'range', start: one.start, end: one.end, steps: one.steps }))
  const body: ExtendBody =
    method === 'table'
      ? { method, table: parseTable(tableText).rows }
      : { method, samples: samples ?? 10, seed, factors: overrides }
  const ready =
    method === 'table'
      ? (body.table ?? []).length > 0
      : (!(method === 'lhs' || method === 'sobol') || samples != null) && overrides.every((one) => one.start != null && one.end != null && one.steps != null)

  useEffect(() => {
    if (!ready) {
      setCount(null)
      return
    }
    let alive = true
    void doeApi
      .extend(study.id, body, true)
      .then((got) => {
        if (!alive) return
        setCount(got.batch)
        setCountError(null)
      })
      .catch((caught) => {
        if (!alive) return
        setCount(null)
        setCountError(caught instanceof Error ? caught : null)
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(body), ready, study.id])

  async function add() {
    setBusy(true)
    setError(null)
    try {
      await doeApi.extend(study.id, body)
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 rounded-md border p-3" aria-label="점 더하기">
      <div className="flex flex-wrap items-end gap-3 text-xs">
        <label className="space-y-1">
          <span className="text-muted-foreground block">방법</span>
          <select aria-label="더할 방법" className="bg-background h-8 rounded border px-2" value={method} onChange={(e) => setMethod(e.target.value as DoeMethod)}>
            <option value="lhs">LHS</option>
            <option value="sobol">Sobol (이어 뽑기)</option>
            <option value="factorial">전체 조합</option>
            <option value="table">표 직접 넣기</option>
          </select>
        </label>
        {(method === 'lhs' || method === 'sobol') && (
          <>
            <label className="space-y-1">
              <span className="text-muted-foreground block">표본 수</span>
              <Input aria-label="더할 표본 수" type="number" min={1} value={samples ?? ''} onChange={(e) => setSamples(numberOrNull(e.target.value))} className="h-8 w-20 text-xs" />
            </label>
            <label className="space-y-1">
              <span className="text-muted-foreground block">시드</span>
              <Input
                aria-label="더할 시드"
                type="number"
                value={seed ?? ''}
                placeholder={method === 'sobol' ? '이어서' : '자동'}
                onChange={(e) => setSeed(numberOrNull(e.target.value))}
                className="h-8 w-20 text-xs"
              />
            </label>
          </>
        )}
      </div>
      {method === 'table' ? (
        <Textarea
          aria-label="더할 설계점 표 (CSV)"
          rows={4}
          className="font-mono text-xs"
          value={tableText}
          onChange={(e) => setTableText(e.target.value)}
          placeholder={numeric.map((one) => one.name).join(',')}
        />
      ) : (
        <div className="space-y-1">
          <p className="text-muted-foreground text-xs">범위를 바꿀 변수만 고르세요 — 나머지는 첫 묶음의 정의 그대로입니다.</p>
          {numeric.map((factor) => {
            const now = ranges[factor.name]
            return (
              <div key={factor.name} className="flex flex-wrap items-center gap-2 text-xs">
                <label className="flex w-40 items-center gap-1.5 truncate font-mono">
                  <input
                    type="checkbox"
                    aria-label={`${factor.name} 범위 바꾸기`}
                    checked={!!now}
                    onChange={(e) =>
                      setRanges((all) => {
                        const next = { ...all }
                        if (e.target.checked) next[factor.name] = rangeOf(factor)
                        else delete next[factor.name]
                        return next
                      })
                    }
                  />
                  {factor.name}
                </label>
                {now ? (
                  (['start', 'end', 'steps'] as const).map((key) => (
                    <label key={key} className="flex items-center gap-1">
                      <span className="text-muted-foreground">{key === 'start' ? '시작' : key === 'end' ? '끝' : '단계'}</span>
                      <Input
                        type="number"
                        aria-label={`${factor.name} 새 ${key === 'start' ? '시작' : key === 'end' ? '끝' : '단계'}`}
                        value={now[key] ?? ''}
                        onChange={(e) => setRanges((all) => ({ ...all, [factor.name]: { ...all[factor.name], [key]: numberOrNull(e.target.value) } }))}
                        className="h-7 w-20 text-xs"
                      />
                    </label>
                  ))
                ) : (
                  <span className="text-muted-foreground">그대로</span>
                )}
              </div>
            )
          })}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {count ? (
          <span>
            <b>{count.added}</b> 점을 더합니다 — p{String(count.from).padStart(4, '0')}부터
            {count.skipped > 0 && <span className="text-muted-foreground"> · 이미 있는 값 {count.skipped} 개는 뺍니다</span>}
            {!!count.rejected && <span className="text-muted-foreground"> · 제약이 {count.rejected} 개를 걸렀습니다</span>}
          </span>
        ) : countError ? (
          <span className="text-destructive">{countError.message}</span>
        ) : (
          <span className="text-muted-foreground">빈 칸을 채우면 몇 점인지 셉니다.</span>
        )}
        <Button size="sm" className="ml-auto" disabled={busy || !count || count.added === 0} onClick={() => void add()}>
          {busy ? '더하는 중…' : '더하기'}
        </Button>
      </div>
      {study.exported_at && <p className="text-muted-foreground text-xs">공유 폴더에 이미 보냈습니다 — 더한 뒤에는 다시 보내야 해석이 새 점을 봅니다.</p>}
      <ErrorNotice error={error} />
    </div>
  )
}
