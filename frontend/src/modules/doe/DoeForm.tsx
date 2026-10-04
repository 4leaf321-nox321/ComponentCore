/**
 * 실험계획 만들기 — 레시피의 **변수**를 인자로 고르고, 범위를 주고, 개수를 확인하고 실행한다.
 *
 * 실행 전에 **몇 개인지 먼저 보여 준다.** 격자는 곱으로 늘어나서, 인자 넷에 5단계면 625개다 —
 * 누르고 나서 아는 것과 누르기 전에 아는 것은 다르다.
 *
 * **재료도 훑는다** — 시뮬레이션 조건에 담아 둔 재료 중 후보를 바디마다 고르면, 설계점마다 그
 * 바디에 하나씩 바꿔 끼운다(형상은 그대로). 조건은 서버가 작업의 현재 버전에서 싣는다.
 */

import { useEffect, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { appliedTo, conditionsApi } from '@/modules/conditions/api'
import type { BodySetting, MaterialItem } from '@/modules/conditions/api'
import { choiceFactor, choiceTargets, factorName, propertyNames } from '@/modules/doe/conditionFactors'
import { doeApi } from '@/modules/doe/api'
import { CHECK_DEFAULTS, SAMPLED } from '@/modules/doe/api'
import type { Checks, DoeMethod, DoeStudy, Factor, Measure, Preview, ProbeResult } from '@/modules/doe/api'
import { formatTable, parseTable } from '@/modules/doe/csvTable'
import { MeasuresInput } from '@/modules/doe/MeasuresInput'
import { PointsScatter, ScatterDetails } from '@/modules/doe/PointsScatter'
import { ProbePanel } from '@/modules/doe/ProbePanel'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/components/ui/select'
import { Textarea } from '@/shared/components/ui/textarea'
import { useResource } from '@/shared/hooks/useResource'


/** 「0.9, 1, 1.1」 → [0.9, 1, 1.1] — 0 보다 큰 수만. */
function parseScales(text: string): number[] {
  return text
    .split(/[,\s]+/)
    .map(Number)
    .filter((v) => Number.isFinite(v) && v > 0)
}

/** 재료 인자의 이름 — 바디마다 하나. 단품(「전체」)이면 그냥 「재료」. */
function swapName(body: string): string {
  return (body === '전체' ? '재료' : `재료 · ${body}`).slice(0, 40)
}

/**
 * 재료를 부르는 이름 — 이름이 담아 둔 재료 중 하나뿐이면 이름(표에 사람이 읽는 말로 적힌다),
 * 겹치면 번호(M-…). 서버는 둘 다 받는다.
 */
function materialKey(one: MaterialItem, all: MaterialItem[]): string {
  const name = refText(one, 'name')
  const twins = all.filter((other) => refText(other, 'name') === name).length
  return twins === 1 && name ? name : refText(one, 'code') || refText(one, 'material_id') || name
}

/** 담아 둔 재료의 출처 칸(이름 · 번호) — 없으면 빈 글자. */
function refText(one: MaterialItem, key: string): string {
  const value = one.ref?.[key]
  return value === undefined || value === null ? '' : String(value)
}

/** 방식마다 언제 쓰나. */
const METHOD_HINTS: Partial<Record<DoeMethod, string>> = {
  sobol: 'Sobol: 설계 공간을 균일하게 채우는 수열입니다. 이후 ‘설계점 추가’에서 같은 수열을 이어서 생성하여 빈 영역을 채울 수 있습니다. 표본 수는 2의 거듭제곱(8, 16, 32 등)일 때 가장 균일합니다.',
  oat: '단일 인자 변경(OAT): 중심점에서 변수별로 수준을 하나씩 변경합니다(나머지 변수는 중심값으로 고정). 주요 변수를 선별할 때 사용합니다.',
  ccd: '중심 합성(면 중심, CCF): 꼭짓점 2^k개, 축점 2k개, 중심점으로 구성되며 범위를 벗어나지 않습니다. 2차 응답면 모델을 구성할 때의 표준 방법입니다. 수치 변수에만 적용됩니다.',
  bbd: 'Box-Behnken: 두 변수씩 끝값을 조합하고 나머지 변수는 중심값으로 두며, 중심점을 하나 추가합니다. 모든 변수가 끝값인 꼭짓점을 생성하지 않으므로 끝값끼리 조합되면 형상이 손상되는 경우에 적합합니다. 수치 변수가 3개 이상 필요합니다.',
}

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
      <span className="text-muted-foreground" title="값을 이 단위의 배수로 맞추어 가공 가능한 치수만 생성합니다.">
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
  conditions,
  sendConditions = false,
}: {
  recipe: Recipe
  /** 대상의 시뮬레이션 조건 — 재료 후보(담아 둔 재료)를 여기서 고른다. */
  conditions?: Record<string, unknown> | null
  /**
   * 조건을 **실어 보낸다** — 대상 작업이 없는 「다시 만들기」(스냅샷)일 때만. 작업이 있으면
   * 서버가 그 작업의 현재 조건을 싣는다.
   */
  sendConditions?: boolean
  workId?: string
  defaultName?: string
  onCreated: (id: string) => void
  /** 지난 DOE 의 설정으로 시작할 때 — 「설정 바꿔 다시 만들기」. 도면에 없어진 변수는 버린다. */
  initial?: Pick<DoeStudy, 'name' | 'description' | 'factors' | 'method' | 'samples' | 'seed' | 'constraints' | 'checks' | 'measures'> & Partial<Pick<DoeStudy, 'points' | 'outputs'>>
  /** 「치수가 없다」 일 때 편집기로 보내 준다 — 글로만 알려 주면 못 찾는다. */
  onEditRecipe?: () => void
}) {
  const params = Object.entries((recipe.params ?? {}) as Record<string, number>)
  const [name, setName] = useState(initial?.name ?? defaultName ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [method, setMethod] = useState<DoeMethod>(initial?.method ?? 'factorial')
  /**
   * 「표 직접 넣기」 의 표(CSV · 엑셀에서 복사한 탭) — 지난 DOE 가 표였으면 그 표를 되돌려 놓는다.
   * 줄 순서가 설계점 번호다.
   */
  const [tableText, setTableText] = useState(() => {
    if (initial?.method !== 'table' || !initial.points) return ''
    const columns = initial.factors.filter((one) => one.mode !== 'fixed').map((one) => one.name)
    return formatTable(
      columns,
      initial.points.filter((one) => one.number <= initial.samples).map((one) => one.params),
    )
  })
  const tableMode = method === 'table'
  const parsed = parseTable(tableText)
  // 숫자 칸은 비울 수 있다(null) — 다 지우고 처음부터 치는 것을 막으면 첫 자리부터 못 친다.
  // 비어 있으면 미리보기를 안 묻고 「만들기」 가 막힌다.
  const [samples, setSamples] = useState<number | null>(initial?.samples ?? 20)
  const [seed, setSeed] = useState<number | null>(initial?.seed ?? 1)
  const [factors, setFactors] = useState<Record<string, Factor>>(() => {
    const before = new Map((initial?.factors ?? []).map((one) => [one.name, one]))
    // 도면에 지금 있는 변수만 — 지난 설정이 있으면 그것을, 없으면 고정(지금 값).
    return Object.fromEntries(params.map(([key, value]) => [key, before.get(key) ?? { name: key, mode: 'fixed', value }]))
  })
  const materials = ((conditions?.materials ?? []) as MaterialItem[]).filter((one) => one.ref)
  // 재료를 바꿔 끼울 바디 — 서버가 정하는 이름(내보낼 때와 같다). 재료가 없으면 묻지 않는다.
  const bodies = useResource(
    () => (materials.length > 0 ? conditionsApi.bodies(recipe) : Promise.resolve({ items: [] })),
    [materials.length > 0 ? JSON.stringify(recipe) : ''],
  )
  const bodyNames = (bodies.data?.items ?? []).map((one) => one.name)
  const properties = propertyNames(materials)
  /** 바디 → 훑을 후보 재료(이름 · 번호). 비었으면 그 바디는 조건 그대로. */
  const [swaps, setSwaps] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(
      (initial?.factors ?? [])
        .filter((one) => one.mode === 'material')
        .map((one) => [(one.bodies ?? [])[0] ?? '전체', (one.values ?? []).map(String)]),
    ),
  )
  const swapFactors: Factor[] = Object.entries(swaps)
    .filter(([, values]) => values.length > 0)
    .map(([body, values]) => ({ name: swapName(body), mode: 'material', bodies: [body], values }))

  // **조건 인자** — 고르는 칸(종류 · 선택 그룹 · 켬끔 …)과 물성 배율. 칸 목록은 서버 사양표에서.
  const hasConditions = !!conditions && Object.keys(conditions).length > 0
  /** 쉘로 푸는 파트가 있으면 서버가 중간면을 늘 함께 낸다(`conditions.has_shell`) — 칸을 잠가 보인다. */
  const shellParts = ((conditions?.body_settings ?? []) as BodySetting[]).some(
    (one) => one.representation === 'shell' && !one.suppressed,
  )
  const schema = useResource(() => (hasConditions ? conditionsApi.schema() : Promise.resolve(null)), [hasConditions])
  const targets = choiceTargets(conditions, schema.data)
  /** 칸 열쇠 → 고른 후보 값들. 열쇠가 있으면 그 칸을 훑는 중(값이 비면 아직 고르는 중). */
  const [choices, setChoices] = useState<Record<string, unknown[]>>(() =>
    Object.fromEntries(
      (initial?.factors ?? [])
        .filter((one) => one.mode === 'choice' && one.target)
        .map((one) => [`${one.target!.group}|${one.target!.item ?? ''}|${one.target!.field}`, one.values ?? []]),
    ),
  )
  /** 바디 → 물성 배율(물성 · 「0.9, 1, 1.1」). */
  const [scales, setScales] = useState<Record<string, { property: string; text: string }>>(() =>
    Object.fromEntries(
      (initial?.factors ?? [])
        .filter((one) => one.mode === 'scale')
        .map((one) => [(one.bodies ?? [])[0] ?? '전체', { property: one.property ?? '', text: (one.values ?? []).join(', ') }]),
    ),
  )
  const taken = new Set<string>([...params.map(([key]) => key), ...swapFactors.map((one) => one.name)])
  const choiceFactors: Factor[] = targets
    .filter((one) => (choices[one.key] ?? []).length > 0)
    .map((one) => choiceFactor(one, choices[one.key], factorName(one.label, taken)))
  const scaleFactors: Factor[] = Object.entries(scales)
    .map(([body, one]) => ({ body, property: one.property, values: parseScales(one.text) }))
    .filter((one) => one.property && one.values.length > 0)
    .map((one) => ({
      name: factorName(`${one.property} 배율${one.body === '전체' ? '' : ` · ${one.body}`}`, taken),
      mode: 'scale',
      bodies: [one.body],
      property: one.property,
      values: one.values,
    }))
  /** 변수끼리의 조건 — 「간격 > 2 * 지름」. 빈 줄은 보내지 않는다. */
  const [constraints, setConstraints] = useState<string[]>(initial?.constraints ?? [])
  const rules = constraints.map((one) => one.trim()).filter(Boolean)
  /** 점마다 잴 값 — 고른 것만 표의 열이 된다. */
  const [measures, setMeasures] = useState<Measure[]>(initial?.measures ?? [])
  /** 점마다 중간면 STEP 도 — 얇은 판을 셸 요소로 푸는 쪽이 받는다. */
  const [midsurface, setMidsurface] = useState(Boolean(initial?.outputs?.includes('midsurface')))
  /** 측정값이 부를 선택 그룹 — 해석 조건의 것(바디 그룹은 빼고). */
  const regions = ((conditions?.named_selections ?? []) as { name?: string; entity?: string }[])
    .filter((one) => one.name && one.entity !== 'body')
    .map((one) => one.name as string)
  /** 형상 점검 기준(mm) — 칸은 늘 다 보이고, 서버에는 기본값과 다른 것만 보낸다. */
  const [checks, setChecks] = useState<Required<Checks>>({ enabled: true, ...CHECK_DEFAULTS, ...initial?.checks })
  const changedChecks: Checks = Object.fromEntries(
    Object.entries(checks).filter(([key, value]) => (key === 'enabled' ? value === false : value !== CHECK_DEFAULTS[key as keyof typeof CHECK_DEFAULTS])),
  )
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewError, setPreviewError] = useState<ApiError | Error | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)
  /** 끝 점 미리 만들어 보기 — 결과와 그때의 설정(설정이 바뀌면 옛 결과라고 말한다). */
  const [probe, setProbe] = useState<{ result: ProbeResult; signature: string } | null>(null)
  const [probing, setProbing] = useState(false)
  const [probeError, setProbeError] = useState<ApiError | Error | null>(null)

  /**
   * 보낼 인자 — 표로 넣으면 표가 값을 주는 변수는 서버가 표에 맞추고, 표에 없는 치수는 **고정**
   * 이다(구간 · 값 목록으로 둔 것도). 표가 곧 설계점이기 때문이다.
   */
  const list = [
    ...Object.values(factors).map((one) => (tableMode && one.mode !== 'fixed' ? { name: one.name, mode: 'fixed' as const, value: one.value ?? Number(recipe.params?.[one.name] ?? 0) } : one)),
    ...swapFactors,
    ...choiceFactors,
    ...scaleFactors,
  ]
  const varying: Factor[] = tableMode ? parsed.columns.map((name) => ({ name, mode: 'list' })) : list.filter((one) => one.mode !== 'fixed')
  /** 표에 있는데 도면 변수도 재료 · 조건 인자도 아닌 열 — 서버가 「레시피에 없는 치수」 로 거절한다. */
  const strangeColumns = parsed.columns.filter((name) => !(name in factors) && !list.some((one) => one.name === name))
  /** 빈 칸이 있으면 아직 쓰는 중이다 — 서버에 묻지도, 만들지도 않는다. */
  const incomplete = tableMode
    ? parsed.rows.length === 0
    : varying.some((one) =>
        one.mode === 'range' ? one.start == null || one.end == null || one.steps == null : (one.values ?? []).length === 0,
      ) ||
      (SAMPLED.includes(method) && (samples == null || seed == null))
  /** 미리보기 · 만들기 · 미리 만들어 보기가 함께 보내는 계획. */
  const planBody = {
    factors: list,
    method,
    samples: samples ?? 20,
    seed: seed ?? 1,
    ...(tableMode ? { table: parsed.rows } : {}),
  }

  useEffect(() => {
    if (varying.length === 0 || incomplete) {
      setPreview(null)
      return
    }
    let alive = true
    // 제약식은 쓰는 중에 틀린 것이 보통이다 — 오류는 표 아래에 적고 개수만 지운다.
    void doeApi
      .preview({ ...planBody, ...(rules.length ? { constraints: rules, recipe } : {}) })
      .then((got) => {
        if (!alive) return
        setPreview(got)
        setPreviewError(null)
      })
      .catch((caught) => {
        if (!alive) return
        setPreview(null)
        setPreviewError(caught instanceof Error ? caught : null)
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(planBody), incomplete, JSON.stringify(rules)])

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

  /** 지금 설정의 지문 — 미리 만들어 본 결과가 지금 것인지 가린다. */
  const signature = JSON.stringify([planBody, rules, changedChecks, measures])

  async function tryEnds() {
    setProbing(true)
    setProbeError(null)
    try {
      const result = await doeApi.probe({
        ...planBody,
        recipe,
        constraints: rules,
        checks: changedChecks,
        measures,
        work_id: workId ?? null,
        ...(sendConditions && conditions ? { conditions } : {}),
      })
      setProbe({ result, signature })
    } catch (caught) {
      setProbeError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setProbing(false)
    }
  }

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const made = await doeApi.create({
        name,
        description,
        recipe,
        ...planBody,
        constraints: rules,
        checks: changedChecks,
        measures,
        outputs: midsurface ? ['midsurface'] : [],
        work_id: workId ?? null,
        ...(sendConditions && conditions ? { conditions } : {}),
      })
      onCreated(made.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  if (params.length === 0 && materials.length === 0 && !hasConditions) {
    return (
      <div className="space-y-3 rounded-md border border-dashed p-4 text-sm">
        <p className="font-medium">먼저 도면에 ‘변수’를 생성해야 합니다.</p>
        <p className="text-muted-foreground">DOE는 <strong>변수</strong>만 탐색합니다. 이름이 없는 값은 변경 대상으로 인식할 수 없습니다.</p>
        <ol className="text-muted-foreground list-inside list-decimal space-y-1 text-xs">
          <li>‘수정’을 클릭하여 편집기를 엽니다.</li>
          <li>
            왼쪽 위 <b>변수</b> 상자의 <b>+</b>로 이름과 값을 생성합니다(예: <code>두께</code>, 6).
          </li>
          <li>
            변경할 피처(또는 스케치 도형)를 열고, 해당 숫자 입력란의 <b>fx</b>를 클릭한 뒤 <code>=두께</code>를 입력합니다.
          </li>
          <li>새 버전으로 저장하면 이 화면에서 해당 치수를 탐색할 수 있습니다.</li>
        </ol>
        {onEditRecipe && (
          <Button size="sm" onClick={onEditRecipe}>
            도면 수정
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor="doe-name">이름</Label>
        <Input id="doe-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="브래킷 두께 탐색" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="doe-desc">목적</Label>
        <Textarea id="doe-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} placeholder="예: 세트 공진 440 Hz에 맞는 두께 선정" />
      </div>

      <div className="rounded-md border">
        <div className="bg-muted/40 grid grid-cols-[1fr_auto_2fr] items-center gap-2 border-b px-3 py-2 text-xs font-medium">
          <span>변수</span>
          <span>방식</span>
          <span>값</span>
        </div>
        {params.map(([key]) => {
          const factor = factors[key]
          if (tableMode) {
            // 표로 넣을 때 — 표에 있는 변수는 표가 값을 주고, 없는 것은 고정값 하나.
            const fromTable = parsed.columns.includes(key)
            return (
              <div key={key} className="grid grid-cols-[minmax(6rem,1fr)_auto_minmax(0,3fr)] items-center gap-3 border-b px-3 py-2 last:border-b-0">
                <span className="truncate font-mono text-xs" title={key}>
                  {key}
                </span>
                <span className="text-muted-foreground w-28 text-xs">{fromTable ? '표의 값' : '고정'}</span>
                {fromTable ? (
                  <span className="text-muted-foreground font-mono text-[11px]">{[...new Set(parsed.rows.map((row) => row[key]))].slice(0, 8).join(' · ')}</span>
                ) : (
                  <Input type="number" step={0.5} value={factor.value ?? ''} onChange={(e) => set(key, { value: numberOrNull(e.target.value) })} className="h-8" aria-label={`${key} 고정값`} />
                )}
              </div>
            )
          }
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

      {/* 제약식 — 범위만으로는 말이 안 되는 조합(벽이 구멍보다 얇은 판)을 만들기 전에 거른다. */}
      <div className="rounded-md border" aria-label="제약식">
        <div className="bg-muted/40 flex items-center gap-3 border-b px-3 py-2 text-xs font-medium">
          <span>제약식 (위반하는 조합은 생성하지 않음)</span>
          <button type="button" className="text-muted-foreground hover:text-foreground ml-auto font-normal" onClick={() => setConstraints([...constraints, ''])}>
            + 제약 추가
          </button>
        </div>
        {constraints.length === 0 ? (
          <p className="text-muted-foreground px-3 py-2 text-xs">
            예: <code>구멍_간격 &gt; 2 * 구멍_지름</code>, <code>4 &lt;= 두께 &lt;= 높이 / 2</code>. 도면의 다른 변수(수식으로 정의된 변수 포함)도 참조할 수 있습니다.
          </p>
        ) : (
          constraints.map((text, index) => {
            const hit = preview?.hits?.[rules.indexOf(text.trim())]
            return (
              <div key={index} className="flex items-center gap-2 border-b px-3 py-1.5 last:border-b-0">
                <span className="text-muted-foreground w-5 text-xs">{index + 1}</span>
                <Input
                  value={text}
                  onChange={(e) => setConstraints(constraints.map((one, i) => (i === index ? e.target.value : one)))}
                  placeholder="간격 > 2 * 지름"
                  className="h-8 flex-1 font-mono text-xs"
                  aria-label={`제약 ${index + 1}`}
                />
                {text.trim() && hit !== undefined && (
                  <span className={`shrink-0 text-xs ${hit > 0 ? 'text-amber-700 dark:text-amber-400' : 'text-muted-foreground'}`}>{hit > 0 ? `${hit}개 위반` : '위반 없음'}</span>
                )}
                <button type="button" className="text-muted-foreground hover:text-foreground text-xs" onClick={() => setConstraints(constraints.filter((_, i) => i !== index))} aria-label={`제약 ${index + 1} 제거`}>
                  제거
                </button>
              </div>
            )
          })
        )}
        {constraints.length > 0 && (
          <p className="text-muted-foreground px-3 py-1.5 text-[11px]">
            사용 가능한 이름: {params.map(([key]) => key).join(', ') || '(없음)'}. 비교 연산자: &lt; &lt;= &gt; &gt;= == !=. 논리 연산자: and, or, not.
          </p>
        )}
      </div>

      <MeasuresInput value={measures} onChange={setMeasures} regions={regions} />

      <label className="flex items-center gap-1.5 rounded-md border px-3 py-2 text-xs" title="두께가 일정한 판(판금, 절곡 판, 쉘)이면 설계점마다 두께 중간면을 STEP으로 출력합니다(표의 mid_file 열). 판이 아닌 설계점은 warnings 열에 사유를 기록합니다.">
        <input type="checkbox" checked={midsurface || shellParts} disabled={shellParts} onChange={(e) => setMidsurface(e.target.checked)} />
        <span className="font-medium">중간면 STEP 출력</span>
        <span className="text-muted-foreground">
          {shellParts
            ? '(파트별 설정에 쉘 파트가 있어 자동으로 출력합니다)'
            : '(얇은 판을 셸 요소로 해석할 때 사용, 설계점마다 <형상>_mid.step)'}
        </span>
      </label>

      {/* 형상 점검 — 해석이 메시를 못 만들 점(얇은 벽 · 짧은 모서리 · 좁은 면 · 쪼개진 바디)을 표에 적는다. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border px-3 py-2 text-xs" aria-label="형상 점검">
        <label className="flex items-center gap-1.5 font-medium">
          <input type="checkbox" checked={checks.enabled} onChange={(e) => setChecks({ ...checks, enabled: e.target.checked })} />
          형상 점검
        </label>
        {(
          [
            ['min_wall', '최소 벽 두께'],
            ['short_edge', '짧은 모서리'],
            ['narrow_face', '좁은 면'],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex items-center gap-1">
            <span className="text-muted-foreground">{label}</span>
            <Input
              type="number"
              min={0}
              step={0.05}
              disabled={!checks.enabled}
              value={checks[key]}
              onChange={(e) => setChecks({ ...checks, [key]: numberOrNull(e.target.value) ?? 0 })}
              className="h-7 w-20 text-xs"
              aria-label={`${label} 기준`}
            />
            <span className="text-muted-foreground">mm</span>
          </label>
        ))}
        <span className="text-muted-foreground">이 값보다 작으면 표의 ‘점검’ 열에 경고로 기록합니다. 메시 생성에 실패할 설계점을 사전에 파악할 수 있습니다.</span>
      </div>

      {materials.length > 0 && (
        <div className="rounded-md border" aria-label="재료 탐색">
          <div className="bg-muted/40 grid grid-cols-[minmax(6rem,1fr)_minmax(0,3fr)] gap-3 border-b px-3 py-2 text-xs font-medium">
            <span>재료 (바디)</span>
            <span>탐색할 재료 (선택하지 않으면 시뮬레이션 조건의 재료를 사용)</span>
          </div>
          {bodyNames.map((body) => {
            const now = materials.find((one) => appliedTo(one).includes(body))
            const picked = swaps[body] ?? []
            return (
              <div key={body} className="grid grid-cols-[minmax(6rem,1fr)_minmax(0,3fr)] items-start gap-3 border-b px-3 py-2 last:border-b-0">
                <div className="min-w-0">
                  <div className="truncate font-mono text-xs" title={body}>
                    {body}
                  </div>
                  <div className="text-muted-foreground truncate text-[11px]">현재: {now ? refText(now, 'name') : '재료 없음'}</div>
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {materials.map((one) => {
                    const key = materialKey(one, materials)
                    const on = picked.includes(key)
                    return (
                      <label key={key} className="flex items-center gap-1 text-xs">
                        <input
                          type="checkbox"
                          checked={on}
                          aria-label={`${body} 후보 ${refText(one, 'name') || key}`}
                          onChange={() =>
                            setSwaps((all) => ({ ...all, [body]: on ? picked.filter((v) => v !== key) : [...picked, key] }))
                          }
                        />
                        <span className="truncate" title={refText(one, 'code')}>
                          {refText(one, 'name') || key}
                        </span>
                      </label>
                    )
                  })}
                  {/* 물성 배율 — 재료는 그대로 두고 값 하나에 곱한다(민감도). 원본은 안 바뀐다. */}
                  <div className="flex w-full flex-wrap items-center gap-2 pt-1 text-xs">
                    <span className="text-muted-foreground">물성 배율</span>
                    <select
                      aria-label={`${body} 배율 물성`}
                      className="bg-background rounded border px-1.5 py-0.5 text-xs"
                      value={scales[body]?.property ?? ''}
                      onChange={(e) => setScales((all) => ({ ...all, [body]: { property: e.target.value, text: all[body]?.text ?? '0.9, 1, 1.1' } }))}
                    >
                      <option value="">(적용 안 함)</option>
                      {properties.map((one) => (
                        <option key={one} value={one}>
                          {one}
                        </option>
                      ))}
                    </select>
                    {scales[body]?.property && (
                      <Input
                        aria-label={`${body} 배율 값`}
                        className="h-7 w-40 font-mono text-xs"
                        value={scales[body]?.text ?? ''}
                        placeholder="0.9, 1, 1.1"
                        onChange={(e) => setScales((all) => ({ ...all, [body]: { ...all[body], text: e.target.value } }))}
                      />
                    )}
                  </div>
                </div>
              </div>
            )
          })}
          <p className="text-muted-foreground px-3 py-2 text-xs">
            후보는 시뮬레이션 조건에 <b>추가된 재료</b>입니다. 다른 재료를 탐색하려면 조건 화면의 ‘물성’에서 추가하십시오(파트에 지정하지 않아도 됩니다).
            형상은 변하지 않으므로 하나의 형상을 공유합니다.
          </p>
        </div>
      )}
      {targets.length > 0 && (
        <div className="rounded-md border" aria-label="조건 변경">
          <div className="bg-muted/40 flex items-center gap-3 border-b px-3 py-2 text-xs font-medium">
            <span>조건 변경</span>
            <select
              aria-label="변경할 필드 추가"
              className="bg-background ml-auto rounded border px-1.5 py-0.5 text-xs font-normal"
              value=""
              onChange={(e) => e.target.value && setChoices((all) => ({ ...all, [e.target.value]: [] }))}
            >
              <option value="">필드 추가</option>
              {targets
                .filter((one) => !(one.key in choices))
                .map((one) => (
                  <option key={one.key} value={one.key}>
                    {one.label}
                  </option>
                ))}
            </select>
          </div>
          {targets
            .filter((one) => one.key in choices)
            .map((one) => {
              const picked = choices[one.key] ?? []
              const has = (value: unknown) => picked.some((v) => JSON.stringify(v) === JSON.stringify(value))
              return (
                <div key={one.key} className="grid grid-cols-[minmax(8rem,1fr)_minmax(0,3fr)_auto] items-start gap-3 border-b px-3 py-2 text-xs last:border-b-0">
                  <span className="truncate" title={one.label}>
                    {one.label}
                  </span>
                  <div className="flex flex-wrap gap-x-3 gap-y-1">
                    {one.options.map((option) => (
                      <label key={JSON.stringify(option.value)} className="flex items-center gap-1">
                        <input
                          type="checkbox"
                          aria-label={`${one.label} 후보 ${option.label}`}
                          checked={has(option.value)}
                          onChange={() =>
                            setChoices((all) => ({
                              ...all,
                              [one.key]: has(option.value)
                                ? picked.filter((v) => JSON.stringify(v) !== JSON.stringify(option.value))
                                : one.options.map((o) => o.value).filter((v) => has(v) || JSON.stringify(v) === JSON.stringify(option.value)),
                            }))
                          }
                        />
                        {option.label}
                      </label>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-foreground"
                    onClick={() =>
                      setChoices((all) => {
                        const next = { ...all }
                        delete next[one.key]
                        return next
                      })
                    }
                  >
                    제거
                  </button>
                </div>
              )
            })}
          <p className="text-muted-foreground px-3 py-2 text-xs">
            종류, 선택 그룹, 켜짐/꺼짐과 같은 <b>선택형 필드</b>를 설계점마다 변경합니다. 하중 크기, 마찰계수와 같은 <b>수치</b>는 도면에 변수를 생성하고
            조건 필드에 <code>=변수</code>로 입력하여 위 표에서 탐색합니다. 변경할 값에 필요한 필드(마찰이면 마찰계수)는 조건에 미리 입력하십시오.
          </p>
        </div>
      )}
      {conditions && Object.keys(conditions).length > 0 && (
        <p className="text-muted-foreground text-xs">
          <b>저장된</b> 시뮬레이션 조건(구속, 하중, 접촉, 물성, 해석 설정)이 함께 포함되어 설계점마다 적용됩니다. 조건 화면에서 수정한 뒤
          저장하지 않은 내용은 포함되지 않습니다.
        </p>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="doe-method">방법</Label>
          <Select value={method} onValueChange={(v) => setMethod(v as DoeMethod)}>
            <SelectTrigger id="doe-method" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="factorial">전체 조합 (격자)</SelectItem>
              <SelectItem value="lhs">라틴 하이퍼큐브 (LHS)</SelectItem>
              <SelectItem value="sobol">Sobol 수열</SelectItem>
              <SelectItem value="oat">단일 인자 변경 (OAT)</SelectItem>
              <SelectItem value="ccd">중심 합성 (CCF)</SelectItem>
              <SelectItem value="bbd">Box-Behnken</SelectItem>
              <SelectItem value="table">표 직접 입력 (CSV)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {SAMPLED.includes(method) && (
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
          {tableMode && parsed.rows.length === 0 ? (
            '아래에 설계점 표를 붙여 넣거나 CSV 파일을 여십시오.'
          ) : varying.length === 0 ? (
            '변경할 변수를 하나 이상 ‘구간’ 또는 ‘값 목록’으로 지정하십시오.'
          ) : incomplete ? (
            '빈 입력란을 채우면 설계점 수를 계산합니다.'
          ) : preview ? (
            <span className={preview.too_many || preview.count === 0 ? 'text-destructive' : ''}>
              설계점 <b>{preview.count}</b>개
              {preview.too_many && `: 한 번에 최대 ${preview.max}개까지 생성할 수 있습니다(서버 설정 DOE_MAX_POINTS). 단계 수를 줄이거나 LHS로 표본 수를 지정하십시오.`}
              {!!preview.rejected && (
                <span className="text-muted-foreground">
                  {' '}
                  (후보 {preview.candidates}개 중 {preview.rejected}개가 제약 조건으로 제외되었습니다)
                </span>
              )}
              {!!preview.shortfall && <span className="text-destructive"> (제약 조건이 엄격하여 {preview.shortfall}개를 생성하지 못했습니다)</span>}
            </span>
          ) : previewError && (rules.length > 0 || tableMode) ? (
            <span className="text-destructive">{previewError.message}</span>
          ) : (
            '계산 중…'
          )}
        </div>
        <Button className="ml-auto" disabled={busy || !name.trim() || varying.length === 0 || incomplete || !!preview?.too_many || preview?.count === 0} onClick={() => void run()}>
          {busy ? '생성 중…' : '생성'}
        </Button>
      </div>
      {SAMPLED.includes(method) && (
        <p className="text-muted-foreground text-xs">시드를 기록해 두면 <strong>동일한 표</strong>를 다시 생성할 수 있습니다. 시드는 해석 결과와 형상을 연결하는 기준입니다.</p>
      )}
      {/* 설계점 분포 — 만들기 전에 고르게 퍼졌는지, 제약이 어디를 잘랐는지. */}
      {preview && !preview.too_many && preview.points.length > 0 && varying.length > 0 && (
        <ScatterDetails summary="설계점 분포 (균일성 및 제약 조건에 의한 제외 영역 확인)">
          {() => (
            <PointsScatter
              names={varying.map((one) => one.name)}
              points={[
                ...(preview.rejected_points ?? []).map((values) => ({ values, status: 'rejected' as const })),
                ...preview.points.map((values) => ({ values })),
              ]}
            />
          )}
        </ScatterDetails>
      )}
      {/* 방식마다 언제 쓰는지 — 이름만으로는 고를 수 없다. */}
      {METHOD_HINTS[method] && <p className="text-muted-foreground text-xs">{METHOD_HINTS[method]}</p>}
      {/* 표 직접 넣기 — 엑셀에서 짠 표 · 해석 쪽 최적화기가 고른 점을 그대로 만든다. */}
      {tableMode && (
        <div className="space-y-1.5 rounded-md border p-3" aria-label="설계점 표">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium">설계점 표</span>
            <span className="text-muted-foreground">첫 행은 변수 이름이며, 각 행이 설계점 하나입니다(행 순서가 번호). 값은 가공 단위로 보정하지 않고 그대로 생성합니다.</span>
            <label className="text-muted-foreground hover:text-foreground ml-auto cursor-pointer underline">
              CSV 파일 열기
              <input
                type="file"
                accept=".csv,.tsv,.txt,text/csv"
                className="sr-only"
                aria-label="CSV 파일 열기"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) void file.text().then(setTableText)
                }}
              />
            </label>
          </div>
          <Textarea
            value={tableText}
            onChange={(e) => setTableText(e.target.value)}
            rows={6}
            className="font-mono text-xs"
            placeholder={`${params.map(([key]) => key).join(',')}\n${params.map(([, value]) => value).join(',')}`}
            aria-label="설계점 표 (CSV)"
          />
          <p className="text-muted-foreground text-xs">
            {parsed.rows.length > 0 ? `${parsed.rows.length}행, 열: ${parsed.columns.join(', ')}.` : '엑셀에서 복사하여 붙여 넣을 수 있습니다(탭으로 구분된 표).'} 표에 없는 변수는 위 입력란의 값으로 고정됩니다.
          </p>
          {strangeColumns.length > 0 && <p className="text-destructive text-xs">도면에 없는 변수: {strangeColumns.join(', ')}</p>}
          {parsed.problems.map((one) => (
            <p key={one} className="text-xs text-amber-700 dark:text-amber-400">
              {one}
            </p>
          ))}
        </div>
      )}
      {/* 끝 점 미리 만들어 보기 — 다 돌리기 전에 범위의 끝에서 깨지는지 · 그룹이 어긋나는지. */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" disabled={probing || varying.length === 0 || incomplete} onClick={() => void tryEnds()}>
          {probing ? '사전 생성 중…' : '경계점 사전 생성'}
        </Button>
        <span className="text-muted-foreground text-xs">
          중심점, 전체 최소, 전체 최대, 변수별 최소·최대 점만 먼저 생성하여 실패, 그룹 불일치, 간섭, 소요 시간을 확인합니다. 파일은 저장하지 않습니다.
        </span>
        {probe && probe.signature !== signature && <span className="text-xs text-amber-700 dark:text-amber-400">설정이 변경되었습니다. 다시 사전 생성하십시오.</span>}
      </div>
      <ErrorNotice error={probeError} />
      {probe && <ProbePanel result={probe.result} recipe={recipe} names={varying.map((one) => one.name)} measures={measures.map((one) => one.name)} count={preview?.count ?? null} />}
      <ErrorNotice error={error} />
    </div>
  )
}
