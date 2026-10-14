/**
 * 부품 · 지그 상세의 「기준정보」 — **이 부품(지그)에 닿는 관계마다 한 줄**, 칸처럼 고르고 뺀다.
 *
 * 부품 · 지그는 온톨로지의 원 표다(`kind_class='system'`, 백엔드 `parts/system.py` ·
 * `jigs/system.py`, ADR 0008). 줄은 코드에 박지 않는다 — 관리자가 「기본 모델 → 부품」 같은 관계
 * 종류를 만들면 「적용 모델」 줄이 저절로 선다(백엔드 `objects/source_links.py`). 저장은 관계(선)다:
 * 부품의 이름 · 칸을 고치지 않고, SP 에서 이름이 바뀌면 이 줄도 따라 바뀐다.
 *
 * 잇고 빼는 것은 **이 부품을 고칠 수 있는 사람**(주인 · 관리자)이다. 추천은 이름에 든 낱말로만
 * 찾는다 — 잇는 것은 사람이다.
 *
 * 원 표를 비추는 타입이 아직 없으면 시스템 관리자에게만 만드는 자리를 알린다 — 못 만드는
 * 사람에게 띄우면 못 지우는 안내가 된다.
 */

import { useMemo, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Link } from 'react-router-dom'

import { sourceLinksApi } from '@/modules/objects/api'
import type { SourceBase, SourceLinkRow, SourceLinks } from '@/modules/objects/api'
import { useObjectOptions } from '@/modules/objects/useObjectOptions'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { SearchablePicker } from '@/shared/components/SearchablePicker'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { useResource } from '@/shared/hooks/useResource'

/** 원 표의 키(백엔드 `SystemSource.key`) → API 경로 · 화면에 적을 이름과 목적격. */
const SOURCES = {
  part: { base: 'parts', noun: '부품', object: '부품을' },
  jig: { base: 'jigs', noun: '지그', object: '지그를' },
} as const satisfies Record<string, { base: SourceBase; noun: string; object: string }>

/**
 * 원 표의 행을 고치는 CompCore 화면 — 기준정보 쪽 상세(`ObjectProfilePage`)가 「그 표의 화면」 으로
 * 보낼 곳. 여기 없는 원 표(부서 · 계정)는 SP 처럼 안내 문장만 남는다.
 */
export function sourceScreen(source: string, id: string): string | null {
  if (source === 'part') return `/parts/${id}`
  if (source === 'jig') return `/jigs/${id}`
  return null
}

interface Props {
  source: keyof typeof SOURCES
  id: string
  /** 이 부품(지그)을 고칠 수 있나 — 화면이 이미 정한 것(주인 · 관리자). 서버가 다시 본다. */
  canEdit: boolean
}

export function SourceLinksCard({ source, id, canEdit }: Props) {
  const { base, noun, object } = SOURCES[source]
  const { user } = useAuth()
  const loaded = useResource(() => sourceLinksApi.get(base, id), [base, id])
  // 고친 뒤 서버가 새 칸들을 돌려준다 — 그것을 그대로 쓴다(다시 묻지 않는다).
  const [fresh, setFresh] = useState<SourceLinks | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const data = fresh ?? loaded.data

  async function act(run: () => Promise<SourceLinks>) {
    setBusy(true)
    setError(null)
    try {
      setFresh(await run())
    } catch (caught) {
      setError(caught instanceof ApiError || caught instanceof Error ? caught.message : '실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  // **곁 카드가 부품 화면을 쓰러뜨리지 않게** — 못 읽으면 카드만 말한다.
  if (loaded.error && !fresh) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>기준정보</CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">기준정보를 불러오지 못했습니다.</CardContent>
      </Card>
    )
  }
  if (!data) return null
  const rows = Array.isArray(data.rows) ? data.rows : []

  if (!data.type_slug) {
    if (!isSystemAdmin(user)) return null
    return (
      <Card>
        <CardHeader>
          <CardTitle>기준정보</CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          관리 › 온톨로지 › 타입에서 원 표가 「{noun}」인 시스템 타입을 만들면, 기준정보(SP 에서 받은 모델 ·
          부품 등)가 이 {object} 가리킬 수 있습니다.{' '}
          <Link to="/admin/ontology/types" className="underline">
            타입 관리로
          </Link>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle>기준정보</CardTitle>
        <Link to={`/o/${data.type_slug}/${id}`} className="text-muted-foreground text-xs hover:underline">
          온톨로지에서 보기 →
        </Link>
      </CardHeader>
      <CardContent className="space-y-3">
        {rows.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            이 {object} 가리키는 관계 종류가 아직 없습니다.
            {isSystemAdmin(user) && (
              <>
                {' '}
                <Link to="/admin/ontology/relations" className="underline">
                  관계 종류 만들기
                </Link>
              </>
            )}
          </p>
        ) : (
          rows.map((row) => (
            <LinkRowView
              key={`${row.relation}:${row.incoming ? 'in' : 'out'}`}
              row={row}
              canEdit={canEdit}
              busy={busy}
              onLink={(objectId) => act(() => sourceLinksApi.link(base, id, row.relation, objectId))}
              onUnlink={(linkId) => act(() => sourceLinksApi.unlink(base, id, linkId))}
            />
          ))
        )}
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function LinkRowView({
  row,
  canEdit,
  busy,
  onLink,
  onUnlink,
}: {
  row: SourceLinkRow
  canEdit: boolean
  busy: boolean
  onLink: (objectId: string) => void
  onUnlink: (linkId: string) => void
}) {
  const [picking, setPicking] = useState(false)
  // 「하나만」 칸에 이미 걸려 있으면 고르개를 안 띄운다 — 빼고 다시 건다.
  const full = row.single && row.items.length > 0
  const hint = row.other_types.map((one) => one.label).join(' · ')
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted-foreground w-24 shrink-0 text-xs" title={hint}>
          {row.label}
        </span>
        {row.items.length === 0 && !canEdit && <span className="text-muted-foreground text-sm">—</span>}
        {row.items.map((item) => (
          <span key={item.link_id ?? item.object_id} className="bg-muted inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-sm">
            <Link to={`/o/${item.type_slug}/${item.object_id}`} className="hover:underline" title={item.key ?? item.type_label}>
              {item.label}
            </Link>
            {canEdit && item.link_id && (
              <button
                type="button"
                aria-label={`${row.label}에서 ${item.label} 빼기`}
                disabled={busy}
                onClick={() => onUnlink(item.link_id!)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            )}
          </span>
        ))}
        {canEdit && !full && !picking && (
          <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-xs" onClick={() => setPicking(true)}>
            <Plus className="size-3" />
            고르기
          </Button>
        )}
        {canEdit && !full && picking && (
          <RowPicker
            row={row}
            onPick={(objectId) => {
              setPicking(false)
              onLink(objectId)
            }}
          />
        )}
      </div>
      {canEdit && !full && row.suggestions.length > 0 && (
        <p className="text-muted-foreground pl-24 text-xs">
          추천:{' '}
          {row.suggestions.map((one, index) => (
            <span key={one.object_id}>
              {index > 0 && ' · '}
              {one.label}{' '}
              <button
                type="button"
                className="text-foreground underline"
                disabled={busy}
                aria-label={`${row.label}에 ${one.label} 잇기`}
                onClick={() => onLink(one.object_id)}
              >
                잇기
              </button>
            </span>
          ))}
        </p>
      )}
    </div>
  )
}

/** 상대 타입에서 이름 · 식별자로 찾아 하나 고른다 — 이미 건 것은 후보에서 뺀다. */
function RowPicker({ row, onPick }: { row: SourceLinkRow; onPick: (objectId: string) => void }) {
  const sources = useMemo(
    () => row.other_types.map((one) => ({ slug: one.slug, label: one.label })),
    [row.other_types],
  )
  const found = useObjectOptions(sources, { composite: false })
  const taken = new Set(row.items.map((one) => one.object_id))
  return (
    <SearchablePicker
      options={found.options.filter((one) => !taken.has(one.value))}
      total={found.total}
      loading={found.loading}
      onQueryChange={found.setQuery}
      value={null}
      onChange={onPick}
      placeholder={`${row.label} 고르기`}
      searchPlaceholder="이름·식별자로 검색"
      emptyText="맞는 것이 없습니다"
      ariaLabel={`${row.label} 고르기`}
      className="h-7 w-56"
    />
  )
}
