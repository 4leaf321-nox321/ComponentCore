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
 * 재료가 백 몇십이고 갈래 하나(Steel)에만 110 건이 몰려 있다. 이름을 아는 사람은 검색하면
 * 되지만, **모르고 찾으러 온 사람**은 목록을 끝없이 넘기게 된다. 쪽(族) → 갈래 → 재료로
 * 좁혀 들어가면 한 칸에 몇 줄씩만 보면 된다.
 *
 * 쪽과 갈래는 **검색 결과에서 뽑지 않는다**(`/materials/classifications`). 목록은 상한만큼만
 * 오므로 그렇게 만들면 「앞 서른 줄에 있는 쪽」 만 보이고, 사람은 나머지가 없는 줄 안다.
 */

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

/** 한 번에 받아 오는 재료 수. 갈래 하나에 110 건까지 있어 서른으로는 잘린다. */
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
  onPick,
  system = 'mm-t-s',
}: {
  open: boolean
  onClose: () => void
  onPick: (row: MaterialRow) => void
  /** 어느 단위계로 **보여 줄 것인가.** 조건 한 벌이 고른 계를 그대로 쓴다. */
  system?: string
}) {
  const [query, setQuery] = useState('')
  const [family, setFamily] = useState('')
  const [category, setCategory] = useState('')
  const [groups, setGroups] = useState<{ family: string; category: string; count: number }[]>([])
  const [rows, setRows] = useState<MaterialRow[]>([])
  const [fallback, setFallback] = useState<string | null>(null)
  const [chosen, setChosen] = useState<MaterialRow | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 쪽 · 갈래는 열 때 한 번만 — 재료가 바뀌는 일보다 훨씬 드물다.
  useEffect(() => {
    if (!open) return
    let alive = true
    materialsApi
      .classifications()
      .then((got) => alive && setGroups(got.items))
      .catch(() => alive && setGroups([]))
    return () => {
      alive = false
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    let alive = true
    setLoading(true)
    // 300ms 쉬었다 묻는다 — 글자마다 부르면 MatNexus 가 우리 때문에 바쁘다.
    const timer = setTimeout(() => {
      materialsApi
        .search({ q: query, family, category, limit: LIMIT, system })
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
  }, [open, query, family, category, system])

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
  const unitHint = system === 'si' ? 'SI (Pa · kg/m³)' : 'mm·t·s (MPa · tonne/mm³)'

  const total = useMemo(
    () => groups.reduce((sum, one) => sum + (Number(one.count) || 0), 0),
    [groups],
  )

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      {/* 화면의 80% — 네 칸을 나란히 두려면 좁은 모달로는 안 된다. */}
      <DialogContent className="h-[80vh] max-h-[80vh] sm:max-w-[80vw]">
        <DialogHeader>
          <DialogTitle>물성 고르기</DialogTitle>
          <DialogDescription>
            MatNexus 의 재료를 <b>통째로</b> 가져옵니다 — 항목 이름도 단위도 우리가 고치지 않습니다.
          </DialogDescription>
        </DialogHeader>

        <Input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="이름 · 별칭 · 번호로 찾기 (예: SPCC, M-000123) — 고른 쪽 · 갈래 안에서 찾습니다"
        />
        {fallback && <p className="text-muted-foreground text-xs">⚠ MatNexus 에 닿지 못했습니다 — {fallback}</p>}
        {error && <ErrorNotice error={error} />}

        {/* 재료 칸과 물성 칸이 넓어야 한다 — 쪽 · 갈래는 이름만 보면 된다. */}
        <div className="grid min-h-0 flex-1 gap-2 md:grid-cols-[1fr_1.4fr_1.6fr_2fr]">
          <Column title="쪽(族)" hint={`${families.length}`}>
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
                  // 쪽을 바꾸면 갈래는 남길 수 없다 — 다른 쪽에는 없는 갈래다.
                  setCategory('')
                }}
              >
                {name} <span className="text-muted-foreground text-xs">{count}</span>
              </Row>
            ))}
          </Column>

          <Column title="갈래" hint={family || '모든 쪽'}>
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
                  // 갈래는 쪽에 속한다 — 「모든 쪽」 에서 골랐으면 쪽도 따라 정해진다.
                  if (!family) setFamily(one.family)
                }}
              >
                <span className="break-all">{one.category || '(없음)'}</span>{' '}
                <span className="text-muted-foreground text-xs">{one.count}</span>
              </Row>
            ))}
          </Column>

          <Column title="재료" hint={loading ? '찾는 중…' : `${rows.length}`}>
            {loading && <Skeleton className="h-24 w-full" />}
            {!loading && rows.length === 0 && <p className="text-muted-foreground p-1 text-xs">찾은 재료가 없습니다.</p>}
            {rows.map((row) => (
              <Row key={row.code} chosen={chosen?.code === row.code} onClick={() => setChosen(row)}>
                <span className="font-medium">{row.alias || row.name}</span>
                {/*
                  가운뎃점은 **제 요소로** 둔다. 값에 붙여 `· 이름` 으로 쓰면 그 글자가
                  값의 일부가 되어, 이름으로 찾는 쪽(사람의 Ctrl+F 도, 시험도)이 못 찾는다.
                */}
                <div className="text-muted-foreground flex flex-wrap items-center gap-1 text-xs">
                  <span>{row.code}</span>
                  {/*
                    이름이 둘이다 — `record_name` 은 기계가 지은 것(`SRCDEMO_-_-`)이고
                    `alias` 가 사람이 읽는 이름이다. 하나만 보이면 나머지로 기억하던
                    사람이 못 찾는다.
                  */}
                  {row.alias && row.name && row.alias !== row.name && (
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
              </Row>
            ))}
            {!loading && rows.length >= LIMIT && (
              <p className="text-muted-foreground p-1 text-xs">
                {LIMIT} 건까지만 보입니다 — 갈래를 좁히거나 이름으로 찾으세요.
              </p>
            )}
          </Column>

          {/*
            값은 **고른 단위계로** 보인다. `2.06e11 Pa` 는 맞는지 눈으로 알 수 없지만
            `206000 MPa` 는 안다 — 사람이 검산할 수 있어야 잘못 고른 재료를 잡는다.
          */}
          <Column title="물성값" hint={unitHint}>
            {chosen ? (
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
                    <dt className="text-muted-foreground text-xs">{one.item}</dt>
                    <dd className="text-sm break-words">{propertyText(one)}</dd>
                  </div>
                ))}
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
              <p className="text-muted-foreground p-1 text-xs">
                재료를 고르면 그것이 가진 물성을 <b>그대로</b> 펼쳐 보여 줍니다.
              </p>
            )}
          </Column>
        </div>

        <div className="flex items-center justify-end gap-2">
          {chosen && (
            <span className="text-muted-foreground mr-auto truncate text-xs">
              고른 것: {chosen.alias || chosen.name} ({chosen.code})
            </span>
          )}
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button
            disabled={!chosen}
            onClick={() => {
              if (chosen) onPick(chosen)
            }}
          >
            이 물성을 쓴다
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
