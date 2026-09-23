/**
 * 물성 탐색기 — MatNexus 에서 고른다.
 *
 * **구조를 그대로 펼친다.** 우리가 아는 항목만 골라 보여 주면, MatNexus 에 있는데 화면에 없는
 * 물성이 생기고 사람은 그것이 없는 줄 안다. 「어느 것이 영률인가」 는 솔버를 아는 쪽(해석
 * 플랫폼)의 일이라 여기서 정하지 않는다 — 고른 재료는 **payload 째로** 조건에 실린다.
 *
 * 서버가 중계한다(그쪽 CORS 는 자기 주소만 허용하고, 토큰이 화면에 나가면 안 된다). 못 닿으면
 * 관리자가 올려 둔 카탈로그로 넘어가고, **넘어갔다는 사실을 화면이 말한다.**
 */

import { useEffect, useState } from 'react'

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

/** 선언 물성 한 줄을 사람의 말로 — 온도 표면 점을 나란히. */
function propertyText(one: Record<string, unknown>): string {
  const points = (one.points ?? []) as { temperature_C?: number; value_si?: number }[]
  const unit = String(one.si_unit ?? '')
  if (one.scale) return `${one.scale} ${points[0]?.value_si ?? ''}`
  if (points.length <= 1) return `${points[0]?.value_si ?? '?'} ${unit}`.trim()
  return points
    .map((p) => `${p.temperature_C ?? '?'} °C ${p.value_si ?? '?'} ${unit}`.trim())
    .join(' · ')
}

export function MaterialPicker({
  open,
  onClose,
  onPick,
}: {
  open: boolean
  onClose: () => void
  onPick: (row: MaterialRow) => void
}) {
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState<MaterialRow[]>([])
  const [fallback, setFallback] = useState<string | null>(null)
  const [chosen, setChosen] = useState<MaterialRow | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!open) return
    let alive = true
    setLoading(true)
    // 300ms 쉬었다 묻는다 — 글자마다 부르면 MatNexus 가 우리 때문에 바쁘다.
    const timer = setTimeout(() => {
      materialsApi
        .search(query)
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
  }, [open, query])

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>물성 고르기</DialogTitle>
          <DialogDescription>
            MatNexus 의 재료를 **통째로** 가져옵니다 — 항목 이름도 단위도 우리가 고치지 않습니다.
          </DialogDescription>
        </DialogHeader>

        <Input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="이름 · 별칭 · 번호로 찾기 (예: SPCC, M-000123)"
        />
        {fallback && (
          <p className="text-muted-foreground text-xs">
            ⚠ MatNexus 에 닿지 못했습니다 — {fallback}
          </p>
        )}
        {error && <ErrorNotice error={error} />}

        <div className="grid gap-3 md:grid-cols-2">
          <div className="max-h-80 space-y-1 overflow-y-auto">
            {loading && <Skeleton className="h-24 w-full" />}
            {!loading && rows.length === 0 && (
              <p className="text-muted-foreground text-xs">찾은 재료가 없습니다.</p>
            )}
            {rows.map((row) => (
              <button
                key={row.code}
                type="button"
                className={`w-full rounded border px-2 py-1 text-left text-sm ${
                  chosen?.code === row.code ? 'border-primary' : ''
                }`}
                onClick={() => setChosen(row)}
              >
                <span className="font-medium">{row.name}</span>
                <span className="text-muted-foreground ml-2 text-xs">{row.code}</span>
                <span className="text-muted-foreground ml-2 text-xs">
                  {[row.family, row.category, row.grade].filter(Boolean).join(' · ')}
                </span>
                {row.source === 'catalog' && (
                  <Badge variant="outline" className="ml-2">
                    사본
                  </Badge>
                )}
              </button>
            ))}
          </div>

          <div className="max-h-80 overflow-y-auto text-sm">
            {chosen ? (
              <dl className="space-y-1">
                <div>
                  <dt className="text-muted-foreground text-xs">밀도</dt>
                  <dd>
                    {chosen.density ?? '(없음)'} {chosen.density_unit}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">푸아송비</dt>
                  <dd>{chosen.poisson_ratio ?? '(없음)'}</dd>
                </div>
                {((chosen.payload.declared_properties ?? []) as Record<string, unknown>[]).map(
                  (one, index) => (
                    <div key={index}>
                      <dt className="text-muted-foreground text-xs">
                        {String(one.item ?? '')}
                        {one.source ? ` · ${String(one.source)}` : ''}
                      </dt>
                      <dd>{propertyText(one)}</dd>
                    </div>
                  ),
                )}
              </dl>
            ) : (
              <p className="text-muted-foreground text-xs">
                왼쪽에서 고르면 그 재료가 가진 물성을 **그대로** 펼쳐 보여 줍니다.
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2">
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
