/**
 * 목록 거르개 — **기준정보로**(「적용 모델 = P5 플립」). 부품 · 지그 목록이 쓴다(온톨로지 이식 E 단계).
 *
 * 칸은 상세의 「기준정보」 카드와 같다 — 이 원 표에 닿는 관계 종류마다 한 줄이고 같은 말을 쓴다
 * (백엔드 `objects/source_links.py` 의 `kinds`). 칸을 고르면 그 상대 타입에서 이름 · 식별자로 찾아
 * 객체 하나를 고른다. 고른 것은 칩으로 남고 × 로 푼다.
 *
 * 칸이 하나도 없으면(관리자가 관계 종류를 아직 안 만들었으면) 아무것도 안 그린다.
 */

import { useMemo, useState } from 'react'
import { X } from 'lucide-react'

import { sourceLinksApi } from '@/modules/objects/api'
import type { SourceBase, SourceLinkKind } from '@/modules/objects/api'
import { useObjectOptions } from '@/modules/objects/useObjectOptions'
import { SearchablePicker } from '@/shared/components/SearchablePicker'
import { useResource } from '@/shared/hooks/useResource'

export interface LinkChoice {
  relation: string
  /** 칸의 말 — 「적용 모델」. */
  label: string
  objectId: string
  objectLabel: string
}

const keyOf = (row: SourceLinkKind) => `${row.relation}:${row.incoming ? 'in' : 'out'}`

export function LinkFilter({
  base,
  value,
  onChange,
}: {
  base: SourceBase
  value: LinkChoice | null
  onChange: (next: LinkChoice | null) => void
}) {
  const kinds = useResource(() => sourceLinksApi.kinds(base), [base])
  const rows = Array.isArray(kinds.data) ? kinds.data : []
  const [picked, setPicked] = useState('')
  const row = rows.find((one) => keyOf(one) === picked) ?? null
  if (rows.length === 0) return null

  if (value) {
    return (
      <span className="bg-primary text-primary-foreground inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
        {value.label}: {value.objectLabel}
        <button type="button" onClick={() => onChange(null)} aria-label="기준정보 거르개 풀기" className="opacity-80 hover:opacity-100">
          <X className="size-3" />
        </button>
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-muted-foreground text-xs">기준정보</span>
      <select
        aria-label="기준정보 칸"
        value={picked}
        onChange={(e) => setPicked(e.target.value)}
        className="bg-background text-foreground h-7 rounded border px-1 text-xs"
      >
        <option value="">칸 고르기</option>
        {rows.map((one) => (
          <option key={keyOf(one)} value={keyOf(one)}>
            {one.label}
          </option>
        ))}
      </select>
      {row && (
        <KindPicker
          row={row}
          onPick={(objectId, objectLabel) => {
            setPicked('')
            onChange({ relation: row.relation, label: row.label, objectId, objectLabel })
          }}
        />
      )}
    </span>
  )
}

/** 그 칸의 상대 타입에서 이름 · 식별자로 찾아 하나 고른다(「기준정보」 카드의 고르개와 같다). */
function KindPicker({ row, onPick }: { row: SourceLinkKind; onPick: (objectId: string, label: string) => void }) {
  const sources = useMemo(() => row.other_types.map((one) => ({ slug: one.slug, label: one.label })), [row.other_types])
  const found = useObjectOptions(sources, { composite: false })
  return (
    <SearchablePicker
      options={found.options}
      total={found.total}
      loading={found.loading}
      onQueryChange={found.setQuery}
      value={null}
      onChange={(id) => onPick(id, found.options.find((one) => one.value === id)?.label ?? id)}
      placeholder={`${row.label} 고르기`}
      searchPlaceholder="이름·식별자로 검색"
      emptyText="맞는 것이 없습니다"
      ariaLabel={`${row.label} 고르기`}
      className="h-7 w-48"
    />
  )
}
