/**
 * 물성 탐색기 — MatNexus 에서 고른다.
 *
 * **구조를 그대로 펼친다.** 우리가 아는 항목만 골라 보여 주면, MatNexus 에 있는데 화면에 없는
 * 물성이 생기고 사람은 그것이 없는 줄 안다. 「어느 것이 영률인가」 는 솔버를 아는 쪽(해석
 * 플랫폼)의 일이라 여기서 정하지 않는다 — 고른 재료는 **payload 째로** 조건에 실린다.
 *
 * 서버가 중계한다(그쪽 CORS 는 자기 주소만 허용하고, 토큰이 화면에 나가면 안 된다). 못 닿으면
 * 관리자가 올려 둔 카탈로그로 넘어가고, **넘어갔다는 사실을 화면이 말한다.**
 *
 * ## 왜 네 칸인가
 *
 * 재료가 백 몇십이고 분류 하나(Steel)에만 110 건이 몰려 있다. 이름을 아는 사람은 검색하면
 * 되지만, **모르고 찾으러 온 사람**은 목록을 끝없이 넘기게 된다. 계열 → 분류 → 재료로
 * 좁혀 들어가면 한 칸에 몇 줄씩만 보면 된다.
 *
 * 쪽과 분류는 **검색 결과에서 뽑지 않는다**(`/materials/classifications`). 목록은 상한만큼만
 * 오므로 그렇게 만들면 「앞 서른 줄에 있는 쪽」 만 보이고, 사람은 나머지가 없는 줄 안다.
 *
 * ## 여러 개를 한 번에 담는다
 *
 * 조립이면 파트마다 재료가 다르다. 하나 고르고 닫고 다시 여는 것을 파트 수만큼 되풀이하지
 * 않게 **여러 개를 담아 한 번에 추가**한다. **줄을 누르면 담긴다**(다시 누르면 빠진다) — 처음에는
 * 담기를 작은 확인란에만 걸었는데, 누르기 어렵다는 지적을 받았다. 누른 줄의 값은 오른쪽 칸에
 * 보인다.
 */

import { Check } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type { MaterialRow } from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Skeleton } from '@/shared/components/ui/skeleton'

/** 한 번에 받아 오는 재료 수. 분류 하나에 110 건까지 있어 서른으로는 잘린다. */
const LIMIT = 200

/** 숫자를 읽을 만하게 — 아주 크거나 작으면 지수로. `7.85e-9` 은 `0.00000000785` 보다 낫다. */
function show(value: number): string {
  if (!Number.isFinite(value)) return '?'
  const size = Math.abs(value)
  if (size !== 0 && (size >= 1e6 || size < 1e-3)) return value.toExponential(4)
  return String(Number(value.toPrecision(6)))
}

/**
 * 물성 한 줄을 사람의 말로 — 온도별 점을 나란히.
 *
 * **환산은 서버가 한다**(`converted`). 여기서 또 계산하면 환산표가 두 벌(파이썬 · TS)이 되고,
 * 어느 날 어긋나면 **화면이 보여 준 값과 내보낸 값이 달라진다.** 서버는 탐색기에 줄 때와
 * 조건으로 내보낼 때 같은 함수를 쓴다 — 그래서 눈으로 검산한 값이 그대로 나간다.
 */
function propertyText(one: { unit?: string; points?: { temperature_C?: number | null; value?: number }[] }): string {
  const points = one.points ?? []
  const unit = one.unit ?? ''
  if (points.length <= 1) return `${show(points[0]?.value ?? NaN)} ${unit}`.trim()
  return points.map((p) => `${p.temperature_C ?? '?'} °C ${show(p.value ?? NaN)} ${unit}`.trim()).join(' · ')
}

/** 칸 하나 — 제목과 세로로 흐르는 목록. 네 칸이 같은 모양이라 한 번만 쓴다. */
function Column({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-0 min-w-0 flex-col rounded-md border">
      <div className="bg-muted/40 flex items-baseline gap-2 border-b px-2 py-1.5">
        <span className="text-xs font-medium">{title}</span>
        {hint && <span className="text-muted-foreground truncate text-xs">{hint}</span>}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-1">{children}</div>
    </div>
  )
}

/** 고를 수 있는 한 줄. 고른 것은 테두리와 바탕으로 말한다(색만으로 말하지 않는다). */
function Row({
  chosen,
  onClick,
  children,
}: {
  chosen: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={chosen ? 'true' : undefined}
      className={`mb-0.5 w-full rounded px-2 py-1 text-left text-sm ${
        chosen ? 'border-primary bg-accent border' : 'hover:bg-accent/50 border border-transparent'
      }`}
    >
      {children}
    </button>
  )
}

export function MaterialPicker({
  open,
  onClose,
  onAdd,
  added = [],
  system = 'mm_n_tonne',
}: {
  open: boolean
  onClose: () => void
  /** 담은 재료들 — 문헌은 값까지 받아 온 것으로 넘긴다. */
  onAdd: (rows: MaterialRow[]) => void
  /** 이미 담겨 있는 재료(그쪽 id) — 「추가됨」 으로 표시하고 다시 담지 않는다. */
  added?: string[]
  /** 어느 단위계로 **보여 줄 것인가.** 조건 한 벌이 고른 계를 그대로 쓴다. */
  system?: string
}) {
  /**
   * 어느 창고에서 고르나. **둘은 크기도 모양도 다르다**: 등록 재료는 우리 조직이 시험하고
   * 등록한 135건, 문헌은 데이터시트 · 논문에서 모은 2663건(탄성계수를 가진 것만 1025개)이다.
   */
  const [source, setSource] = useState<'registered' | 'literature'>('registered')
  const [query, setQuery] = useState('')
  const [family, setFamily] = useState('')
  const [category, setCategory] = useState('')
  const [groups, setGroups] = useState<{ family: string; category: string; count: number }[]>([])
  const [rows, setRows] = useState<MaterialRow[]>([])
  const [fallback, setFallback] = useState<string | null>(null)
  const [chosen, setChosen] = useState<MaterialRow | null>(null)
  /** 추가하려고 담은 재료 — 창고 · 분류를 바꿔도 남는다. */
  const [basket, setBasket] = useState<MaterialRow[]>([])
  /** 값까지 받아 온 문헌 재료(id → 줄). 담은 것을 추가할 때 다시 묻지 않는다. */
  const [full, setFull] = useState<Record<string, MaterialRow>>({})
  const [adding, setAdding] = useState(false)
  const [loading, setLoading] = useState(false)
  const [filling, setFilling] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 열 때마다 새로 담는다 — 지난번에 담다 만 것이 남아 있으면 모르고 함께 추가된다.
  useEffect(() => {
    if (open) setBasket([])
  }, [open])

  function toggle(row: MaterialRow) {
    setBasket((now) => (now.some((one) => one.id === row.id) ? now.filter((one) => one.id !== row.id) : [...now, row]))
  }

  /** 담은 것을 추가한다. */
  async function add() {
    const rows = basket
    if (rows.length === 0) return
    setAdding(true)
    setError(null)
    try {
      // **문헌은 목록에 값이 없다** — 담은 것만 값까지 받아 온다. 빈 payload 가 실리면 안 된다.
      const complete = await Promise.all(
        rows.map((row) =>
          row.source === 'literature'
            ? (full[row.id] ?? materialsApi.one(row.id, { system, source: 'literature' }))
            : row,
        ),
      )
      onAdd(complete)
      setBasket([])
    } catch (failure) {
      setError(failure as Error)
    } finally {
      setAdding(false)
    }
  }

  /**
   * 재료를 고른다. **문헌은 목록에 값이 없다** — 2663건을 값째로 끌면 수십 MB 라 목록은
   * 이름만 오고, 고른 그 하나만 값까지 받는다. 받아 온 것으로 갈아 끼워야 「이 물성을
   * 쓴다」 가 빈 payload 를 싣지 않는다.
   */
  function choose(row: MaterialRow) {
    setChosen(row)
    if (row.source !== 'literature') return
    setFilling(true)
    materialsApi
      .one(row.id, { system, source: 'literature' })
      .then((got) => {
        setFull((now) => ({ ...now, [row.id]: got }))
        setChosen((now) => (now?.id === row.id ? got : now))
      })
      .catch((failure) => setError(failure as Error))
      .finally(() => setFilling(false))
  }

  // 쪽 · 분류는 창고를 바꿀 때만 — 재료가 바뀌는 일보다 훨씬 드물다.
  useEffect(() => {
    if (!open) return
    let alive = true
    const asking =
      source === 'literature' ? materialsApi.catalogClassifications() : materialsApi.classifications()
    asking.then((got) => alive && setGroups(got.items)).catch(() => alive && setGroups([]))
    return () => {
      alive = false
    }
  }, [open, source])

  useEffect(() => {
    if (!open) return
    let alive = true
    setLoading(true)
    // 300ms 쉬었다 묻는다 — 글자마다 부르면 MatNexus 가 우리 때문에 바쁘다.
    const timer = setTimeout(() => {
      materialsApi
        .search({ q: query, family, category, limit: LIMIT, system, source })
        .then((got) => {
          if (!alive) return
          setRows(got.items)
          setFallback(got.fallback ? (got.detail ?? '올려 둔 카탈로그로 고르는 중입니다') : null)
          setError(null)
        })
        .catch((failure) => alive && setError(failure as Error))
        .finally(() => alive && setLoading(false))
    }, 300)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [open, query, family, category, system, source])

  const families = useMemo(() => {
    const counted = new Map<string, number>()
    // 개수가 없는 줄이 와도 NaN 을 그리지 않는다 — 숫자가 아니면 0 이다.
    for (const one of groups) {
      if (!one?.family) continue
      counted.set(one.family, (counted.get(one.family) ?? 0) + (Number(one.count) || 0))
    }
    return [...counted.entries()].sort((a, b) => b[1] - a[1])
  }, [groups])

  const categories = useMemo(
    () =>
      groups
        .filter((one) => one?.category !== undefined && (!family || one.family === family))
        .sort((a, b) => (Number(b.count) || 0) - (Number(a.count) || 0)),
    [groups, family],
  )

  /** 「무슨 계로 보고 있나」 — 칸 머리에 적는다. 안 적으면 숫자만 보고 단위를 짐작한다. */
  const unitHint = system === 'si' ? 'SI (Pa · kg/m3)' : 'mm · N · tonne (MPa · tonne/mm3)'

  const total = useMemo(
    () => groups.reduce((sum, one) => sum + (Number(one.count) || 0), 0),
    [groups],
  )

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      {/* 화면의 80% — 네 칸을 나란히 두려면 좁은 모달로는 안 된다. */}
      <DialogContent className="h-[80vh] max-h-[80vh] sm:max-w-[80vw]">
        <DialogHeader>
          <DialogTitle>물성 선택</DialogTitle>
          <DialogDescription>
            MatNexus 의 재료를 <b>전체</b> 가져옵니다 — 항목 이름과 단위를 변경하지 않습니다.
          </DialogDescription>
        </DialogHeader>

        {/*
          **어느 창고에서 고르나.** 등록 재료는 우리 조직이 시험해 등록한 것이고, 문헌은
          데이터시트 · 논문에서 모은 것이다 — 값의 모양도 다르고 수도 스무 배 차이 난다.
          한 목록에 섞으면 「이 값이 어디서 왔나」 가 흐려진다.
        */}
        <div className="flex items-center gap-2">
          {/* `shrink-0` — 검색칸이 늘어나며 토글을 밀어 줄바꿈시키던 것을 막는다. */}
          <div className="flex shrink-0 rounded-md border p-0.5" role="group" aria-label="물성 출처">
            {(
              [
                ['registered', '등록 재료'],
                ['literature', '문헌'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={source === key}
                className={`rounded px-3 py-1 text-sm whitespace-nowrap ${source === key ? 'bg-accent font-medium' : 'text-muted-foreground'}`}
                onClick={() => {
                  if (source === key) return
                  setSource(key)
                  // 창고가 바뀌면 좁혀 둔 것과 고른 것은 뜻을 잃는다.
                  setFamily('')
                  setCategory('')
                  setChosen(null)
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <Input
            autoFocus
            className="min-w-0 flex-1"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              source === 'literature'
                ? '이름 · 제조사로 검색 (예: EMC, Al 6061) — 고른 분야 · 분류 안에서'
                : '이름 · 별칭 · 번호로 검색 (예: SPCC, M-000123) — 선택한 계열 · 분류 내에서'
            }
          />
        </div>
        {fallback && <p className="text-muted-foreground text-xs">⚠ MatNexus 에 닿지 못했습니다 — {fallback}</p>}
        {error && <ErrorNotice error={error} />}

        {/* 재료 칸과 물성 칸이 넓어야 한다 — 쪽 · 분류는 이름만 보면 된다. */}
        <div className="grid min-h-0 flex-1 gap-2 md:grid-cols-[1fr_1.4fr_1.6fr_2fr]">
          <Column title={source === 'literature' ? '분야' : '계열'} hint={`${families.length}`}>
            <Row
              chosen={!family}
              onClick={() => {
                setFamily('')
                setCategory('')
              }}
            >
              전체 <span className="text-muted-foreground text-xs">{total}</span>
            </Row>
            {families.map(([name, count]) => (
              <Row
                key={name}
                chosen={family === name}
                onClick={() => {
                  setFamily(name)
                  // 쪽을 바꾸면 분류는 남길 수 없다 — 다른 쪽에는 없는 분류다.
                  setCategory('')
                }}
              >
                {name} <span className="text-muted-foreground text-xs">{count}</span>
              </Row>
            ))}
          </Column>

          <Column title="분류" hint={family || (source === 'literature' ? '모든 분야' : '전체 계열')}>
            <Row chosen={!category} onClick={() => setCategory('')}>
              전체{' '}
              <span className="text-muted-foreground text-xs">
                {categories.reduce((sum, one) => sum + (Number(one.count) || 0), 0)}
              </span>
            </Row>
            {categories.map((one) => (
              <Row
                key={`${one.family}/${one.category}`}
                chosen={category === one.category}
                onClick={() => {
                  setCategory(one.category)
                  // 분류는 쪽에 속한다 — 「전체 계열」 에서 골랐으면 쪽도 따라 정해진다.
                  if (!family) setFamily(one.family)
                }}
              >
                <span className="break-all">{one.category || '(없음)'}</span>{' '}
                <span className="text-muted-foreground text-xs">{one.count}</span>
              </Row>
            ))}
          </Column>

          <Column title="재료" hint={loading ? '검색 중…' : `${rows.length}`}>
            {loading && <Skeleton className="h-24 w-full" />}
            {!loading && rows.length === 0 && <p className="text-muted-foreground p-1 text-xs">검색 결과가 없습니다.</p>}
            {rows.map((row) => {
              const label = source === 'literature' ? row.name : row.alias || row.name
              const 추가됨 = added.includes(row.id)
              const 담김 = 추가됨 || basket.some((one) => one.id === row.id)
              return (
              // **줄 전체가 확인란이다** — 누르면 담기고(다시 누르면 빠진다) 값이 오른쪽에 보인다.
              // 이미 추가된 재료는 담기지 않고 값만 보인다.
              <button
                key={row.id || row.code}
                type="button"
                role="checkbox"
                aria-checked={담김}
                aria-disabled={추가됨 || undefined}
                aria-label={`${label} 선택`}
                className={`mb-0.5 flex w-full items-start gap-2 rounded border px-2 py-1.5 text-left text-sm ${
                  chosen?.id === row.id ? 'border-primary bg-accent' : 'hover:bg-accent/50 border-transparent'
                }`}
                onClick={() => {
                  choose(row)
                  if (!추가됨) toggle(row)
                }}
              >
                <span
                  aria-hidden
                  className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border ${
                    담김 ? 'border-primary bg-primary text-primary-foreground' : 'bg-background'
                  } ${추가됨 ? 'opacity-50' : ''}`}
                >
                  {담김 && <Check className="size-3" />}
                </span>
                <span className="min-w-0 flex-1">
                <span className="font-medium">{label}</span>
                {추가됨 && (
                  <Badge variant="outline" className="ml-1 font-normal">
                    추가됨
                  </Badge>
                )}
                {/*
                  가운뎃점은 **제 요소로** 둔다. 값에 붙여 `· 이름` 으로 쓰면 그 글자가
                  값의 일부가 되어, 이름으로 찾는 쪽(사람의 Ctrl+F 도, 시험도)이 못 찾는다.
                */}
                <div className="text-muted-foreground flex flex-wrap items-center gap-1 text-xs">
                  {/* 문헌은 번호가 없는 것이 많다 — 대신 만든 곳이 사람에게 쓸모 있다. */}
                  <span>{source === 'literature' ? row.alias || row.grade || '(출처 미상)' : row.code}</span>
                  {/*
                    **등록 재료만 이름이 둘이다** — `record_name` 은 기계가 지은 것
                    (`SRCDEMO_-_-`)이고 `alias` 가 사람이 읽는 이름이다. 하나만 보이면
                    나머지로 기억하던 사람이 못 찾는다.
                    문헌은 이름이 하나뿐이고 위에 이미 있다 — 여기 또 적으면 같은 말이 두 번이다.
                  */}
                  {source !== 'literature' && row.alias && row.name && row.alias !== row.name && (
                    <>
                      <span aria-hidden>·</span>
                      <span>{row.name}</span>
                    </>
                  )}
                  {row.grade && (
                    <>
                      <span aria-hidden>·</span>
                      <span>{row.grade}</span>
                    </>
                  )}
                  {/*
                    어느 부서 것인지 — MatNexus 가 부서로 권한을 나누므로 두 부서에 같은
                    이름이 있을 수 있다. 안 보이면 고르는 사람이 그 둘을 구별할 수 없다.
                  */}
                  {row.workspace && (
                    <Badge variant="secondary" className="font-normal">
                      {row.workspace}
                    </Badge>
                  )}
                  {row.source === 'catalog' && <Badge variant="outline">사본</Badge>}
                </div>
                </span>
              </button>
              )
            })}
            {!loading && rows.length >= LIMIT && (
              <p className="text-muted-foreground p-1 text-xs">
                {LIMIT} 건까지만 보입니다 — 분류를 좁히거나 이름으로 찾으세요.
              </p>
            )}
          </Column>

          {/*
            값은 **고른 단위계로** 보인다. `2.06e11 Pa` 는 맞는지 눈으로 알 수 없지만
            `206000 MPa` 는 안다 — 사람이 검산할 수 있어야 잘못 고른 재료를 잡는다.
          */}
          <Column title="물성값" hint={filling ? '조회 중…' : unitHint}>
            {filling && <Skeleton className="h-24 w-full" />}
            {!filling && chosen ? (
              <dl className="space-y-2 p-1">
                <div>
                  <dt className="text-muted-foreground text-xs">밀도</dt>
                  <dd className="text-sm">
                    {chosen.converted?.density === undefined
                      ? '(없음)'
                      : `${show(chosen.converted.density)} ${chosen.converted.density_unit ?? ''}`}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">푸아송비</dt>
                  <dd className="text-sm">{chosen.poisson_ratio ?? '(없음)'}</dd>
                </div>
                {(chosen.converted?.properties ?? []).map((one, index) => (
                  <div key={index}>
                    <dt className="text-muted-foreground flex flex-wrap items-baseline gap-1 text-xs">
                      <span>{one.item}</span>
                      {/* 출처 등급 — 1 이 가장 좋다. 4 를 1 인 줄 알고 쓰면 안 된다. */}
                      {one.tier !== undefined && <span className="opacity-70">tier {one.tier}</span>}
                    </dt>
                    <dd className="text-sm break-words">{propertyText(one)}</dd>
                    {/*
                      **조건이 값의 일부다.** 「85°C/85%RH 168hr」 에서 잰 흡습률을 상온
                      값으로 쓰면 틀린다 — 안 보이면 그것을 알 길이 없다.
                    */}
                    {one.conditions && Object.keys(one.conditions).length > 0 && (
                      <dd className="text-muted-foreground text-xs break-words">
                        {Object.entries(one.conditions)
                          .map(([key, value]) => `${key} ${String(value)}`)
                          .join(' · ')}
                      </dd>
                    )}
                  </div>
                ))}
                {/*
                  **해석에 바로 쓸 수 있나.** 탄성계수 · 푸아송비 · 밀도 중 빠진 것이 있으면
                  해석이 기본값(구조용 강)으로 풀고, 그 사실은 고유진동수가 틀린 뒤에야
                  드러난다 — 고를 때 말해 주는 편이 낫다. 문헌 2663건 중 탄성계수를 가진
                  것은 1025건이다.
                */}
                {(chosen.converted?.missing_structural ?? []).length > 0 ? (
                  <p className="rounded border border-amber-300 bg-amber-50 p-1 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                    ⚠ 구조 해석에 빠진 것: {(chosen.converted?.missing_structural ?? []).join(' · ')} — 이 상태로
                    전달하면 해석이 기본값으로 계산합니다.
                  </p>
                ) : (
                  chosen.converted?.properties && (
                    <p className="text-xs text-emerald-700 dark:text-emerald-400">
                      ✓ 탄성계수 · 푸아송비 · 밀도가 다 있습니다
                    </p>
                  )
                )}
                {/*
                  **못 바꾼 것은 못 바꿨다고 말한다.** 조용히 원래 값을 보여 주면 그것이
                  새 단위인 줄 알고 그대로 쓴다.
                */}
                {(chosen.converted?.unconverted ?? []).length > 0 && (
                  <p className="text-xs text-amber-700 dark:text-amber-400">
                    ⚠ 단위를 못 바꾼 항목: {(chosen.converted?.unconverted ?? []).join(' · ')} — 값은 원래
                    단위 그대로입니다.
                  </p>
                )}
              </dl>
            ) : (
              !filling && (
                <p className="text-muted-foreground p-1 text-xs">
                  재료를 선택하면 보유한 물성을 <b>그대로</b> 표시합니다.
                </p>
              )
            )}
          </Column>
        </div>

        <div className="flex items-center justify-end gap-2">
          {/* 담은 것 — 분류를 옮겨 다니며 담으므로, 무엇을 담았는지 한자리에서 보여야 한다. */}
          <div className="mr-auto flex min-w-0 flex-wrap items-center gap-1 text-xs">
            {basket.length === 0 ? (
              <span className="text-muted-foreground">
                재료 행을 클릭하여 선택합니다 — 여러 개를 함께 선택할 수 있습니다.
              </span>
            ) : (
              <>
                <span className="text-muted-foreground">선택 {basket.length}</span>
                {basket.map((one) => (
                  <Badge key={one.id} variant="secondary" className="gap-1 font-normal">
                    {one.alias || one.name}
                    <button type="button" aria-label={`${one.alias || one.name} 선택 해제`} onClick={() => toggle(one)}>
                      ×
                    </button>
                  </Badge>
                ))}
              </>
            )}
          </div>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button disabled={adding || basket.length === 0} onClick={() => void add()}>
            {adding ? '불러오는 중…' : basket.length > 0 ? `물성 추가 (${basket.length})` : '물성 추가'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
