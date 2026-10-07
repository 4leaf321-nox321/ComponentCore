/**
 * **시험 규격** — 공개 규격(ASTM · ISO · IEC · JEDEC)과 사내 규격의 프리셋 목록. 시편 시험(굽힘 ·
 * 인장 · 전단 · 접착 이음)은 규격을 골라 시편 · 시험 지그 · 해석 조건이 붙은 내 작업을 만들고, 제품
 * 시험(정하중 · 손잡이 · 압축 · 비틀림 · 진동 · 고유진동수)은 **사용자의 제품에** 시험을 건다. 사내
 * 규격은 시스템 관리자가 공개 규격을 복사해 고친다(판정은 서버 — 여기서는 단추만 가린다).
 *
 * 굽힘을 뺀 종류의 표 · 편집 칸은 종류의 정의(`kinds.ts`)에서 읽는다.
 *
 * 값마다 출처가 있고, 규격서와 대조하기 전이면 「검토 필요」 로 보인다. 공개 규격의 값을 고치는
 * 길은 코드(릴리스)뿐이다 — 틀린 값을 찾으면 사내 규격으로 복사해 바로 쓰고, 코드는 따로 고친다.
 *
 * 표의 칸은 기본이 줄바꿈 금지라, 글이 긴 칸(출처 · 규칙)은 줄을 바꾸게 둔다 — 그러지 않으면 좁은
 * 화면에서 옆 칸을 덮었다(2026-10-05).
 *
 * **규격이 많아져도 찾게** — 검색어(규격 번호 · 이름 · 출처 · 메모), 시험 종류 탭(개수), 구분(공개 ·
 * 사내) · 상태(검토 필요 · 대조 완료) · 규격 번호 필터, 표 안에서는 규격 번호마다 묶음 머리줄. 목록은
 * 서버가 한 번에 주고(수백 개 규모) 거르기는 화면에서 한다. 사내 규격은 하늘색 줄 · 배지 · 왼쪽 띠로
 * 공개 규격과 가른다.
 */

import { Fragment, useState } from 'react'
import type { ReactNode } from 'react'

import { CouponDialog } from '@/modules/specimens/CouponDialog'
import { KINDS } from '@/modules/specimens/kinds'
import { PresetDialog } from '@/modules/specimens/PresetDialog'
import { PresetFieldsDialog } from '@/modules/specimens/PresetFieldsDialog'
import { ProductTestDialog } from '@/modules/specimens/ProductTestDialog'
import { SpecimenDialog } from '@/modules/specimens/SpecimenDialog'
import { isBending, isCoupon, isProduct, loadSpanText, radiusText, spanText, specimensApi, TESTS } from '@/modules/specimens/api'
import type { BendingPreset, CouponPreset, PresetRow, ProductPreset, TestKey } from '@/modules/specimens/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { SearchBox } from '@/shared/components/SearchBox'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

type Editing = { row: PresetRow; mode: 'copy' | 'edit' }
type TestFilter = 'all' | TestKey
type OriginFilter = 'all' | 'builtin' | 'internal'
type StatusFilter = 'all' | 'review' | 'verified'

const TEST_TABS: { value: TestFilter; label: string }[] = [{ value: 'all', label: '전체' }, ...TESTS]

const SELECT = 'bg-background h-8 rounded-md border px-2 text-sm'

/** 사내 규격 줄의 바탕 — 공개 규격과 한눈에 가른다. */
const INTERNAL_ROW = 'bg-sky-50/70 hover:bg-sky-100/70 dark:bg-sky-950/30 dark:hover:bg-sky-900/30'

/** 검색어의 낱말이 모두 규격 번호 · 이름 · 출처 · 메모 · id 어딘가에 있으면. */
function matches(row: PresetRow, query: string): boolean {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return true
  const haystack = [row.standard, row.name, row.preset.source, row.preset.note, row.id].join(' ').toLowerCase()
  return words.every((word) => haystack.includes(word))
}

/** 규격 번호마다 묶는다 — 서버가 이미 규격 번호 순으로 준다(순서를 지킨다). */
function byStandard<R extends PresetRow>(rows: R[]): [string, R[]][] {
  const groups = new Map<string, R[]>()
  for (const row of rows) groups.set(row.standard, [...(groups.get(row.standard) ?? []), row])
  return [...groups.entries()]
}

function GroupRow({ standard, count, columns }: { standard: string; count: number; columns: number }) {
  return (
    <TableRow className="bg-muted/40 hover:bg-muted/40">
      <TableCell colSpan={columns} className="py-1 text-xs font-semibold">
        {standard} <span className="text-muted-foreground font-normal">· {count}개</span>
      </TableCell>
    </TableRow>
  )
}

function NameCell({ row }: { row: PresetRow }) {
  const internal = row.origin === 'internal'
  return (
    <TableCell className={`min-w-56 align-top whitespace-normal ${internal ? 'border-l-4 border-l-sky-500' : ''}`}>
      <span className="font-medium">{row.name}</span>
      {internal && <Badge className="ml-1 bg-sky-600 text-white">사내 규격</Badge>}
      <p className="text-muted-foreground max-w-md text-xs break-words">{row.preset.source}</p>
      {row.preset.note && <p className="text-muted-foreground max-w-md text-xs break-words">{row.preset.note}</p>}
      {internal && row.updated_at && (
        <p className="text-xs text-sky-700 dark:text-sky-300">
          {row.updated_by_name ? `${row.updated_by_name} · ` : ''}
          {shownDateTime(row.updated_at)} 수정
        </p>
      )}
    </TableCell>
  )
}

function StatusCell({ row }: { row: PresetRow }) {
  return <TableCell className="align-top">{row.preset.verified ? <Badge variant="outline">대조 완료</Badge> : <Badge variant="destructive">검토 필요</Badge>}</TableCell>
}

/** 작업 칸 — 주 단추 하나와 관리자의 복사 · 수정 · 삭제. 좁아지면 아래로 쌓인다. */
function ActionsCell({ row, admin, primary, onEdit, onRemove }: { row: PresetRow; admin: boolean; primary: ReactNode; onEdit: (mode: 'copy' | 'edit') => void; onRemove: () => void }) {
  return (
    <TableCell className="min-w-32 align-top whitespace-normal">
      <div className="flex flex-wrap justify-end gap-1">
        {primary}
        {admin && row.origin === 'builtin' && (
          <Button size="sm" variant="outline" onClick={() => onEdit('copy')}>
            사내 규격으로 복사
          </Button>
        )}
        {admin && row.origin === 'internal' && (
          <>
            <Button size="sm" variant="outline" onClick={() => onEdit('edit')}>
              수정
            </Button>
            <Button size="sm" variant="ghost" onClick={onRemove}>
              삭제
            </Button>
          </>
        )}
      </div>
    </TableCell>
  )
}

function Section({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="text-sm font-semibold">{title}</h2>
      <p className="text-muted-foreground mb-2 text-xs">{hint}</p>
      {children}
    </section>
  )
}

export default function SpecimensPage() {
  const { user } = useAuth()
  const admin = isSystemAdmin(user)
  const presets = useResource(() => specimensApi.list(), [])
  const [making, setMaking] = useState<PresetRow<BendingPreset> | null>(null)
  const [coupon, setCoupon] = useState<PresetRow<CouponPreset> | null>(null)
  const [applying, setApplying] = useState<PresetRow<ProductPreset> | null>(null)
  const [editing, setEditing] = useState<Editing | null>(null)
  const [removing, setRemoving] = useState<PresetRow | null>(null)
  const [query, setQuery] = useState('')
  const [test, setTest] = useState<TestFilter>('all')
  const [origin, setOrigin] = useState<OriginFilter>('all')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [standard, setStandard] = useState('')
  const rows = presets.data ?? []
  // 탭을 뺀 거르기 — 탭마다 개수를 보여 주려고 탭은 따로 건다.
  const filtered = rows.filter(
    (row) =>
      (origin === 'all' || row.origin === origin) &&
      (status === 'all' || (status === 'verified') === row.preset.verified) &&
      (!standard || row.standard === standard) &&
      matches(row, query),
  )
  const countOf = (value: TestFilter) => (value === 'all' ? filtered.length : filtered.filter((row) => row.preset.test === value).length)
  const shown = filtered.filter((row) => test === 'all' || row.preset.test === test)
  const standards = [...new Set(rows.filter((row) => test === 'all' || row.preset.test === test).map((row) => row.standard))].sort()
  const bending = shown.filter(isBending)
  const internalCount = rows.filter((row) => row.origin === 'internal').length
  const reviewCount = rows.filter((row) => !row.preset.verified).length
  const narrowed = Boolean(query.trim() || origin !== 'all' || status !== 'all' || standard)
  const reset = () => {
    setQuery('')
    setOrigin('all')
    setStatus('all')
    setStandard('')
  }
  const actions = (row: PresetRow, primary: ReactNode) => (
    <ActionsCell row={row} admin={admin} primary={primary} onEdit={(mode) => setEditing({ row, mode })} onRemove={() => setRemoving(row)} />
  )
  const primary = (row: PresetRow) =>
    isProduct(row) ? (
      <Button size="sm" onClick={() => setApplying(row)}>
        제품에 적용
      </Button>
    ) : isCoupon(row) ? (
      <Button size="sm" onClick={() => setCoupon(row)}>
        시편 생성
      </Button>
    ) : null

  return (
    <div>
      <PageHeader
        title="시험 규격"
        description="공개 규격과 사내 규격의 시편, 시험 지그, 해석 조건입니다. 굽힘, 인장, 전단, 접착 이음은 규격의 시편으로 해석 모델을 생성하고, 정하중, 손잡이·벽걸이, 적층 압축, 비틀림, 진동, 고유진동수는 선택한 제품에 시험을 적용합니다. 사내 규격은 관리자가 공개 규격을 복사하여 등록합니다."
      />
      <ErrorNotice error={presets.error} className="mb-4" />
      {rows.length === 0 && !presets.loading && <EmptyState title="시험 규격이 없습니다" hint="서버 버전을 확인하십시오." />}
      {rows.length > 0 && (
        <div className="mb-4 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <SearchBox value={query} onChange={setQuery} placeholder="규격 번호, 이름, 출처로 검색" className="w-64" />
            <select aria-label="구분 필터" className={SELECT} value={origin} onChange={(event) => setOrigin(event.target.value as OriginFilter)}>
              <option value="all">모든 구분</option>
              <option value="builtin">공개 규격</option>
              <option value="internal">사내 규격</option>
            </select>
            <select aria-label="상태 필터" className={SELECT} value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
              <option value="all">모든 상태</option>
              <option value="review">검토 필요</option>
              <option value="verified">대조 완료</option>
            </select>
            <select aria-label="규격 번호 필터" className={SELECT} value={standard} onChange={(event) => setStandard(event.target.value)}>
              <option value="">모든 규격 번호</option>
              {standards.map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </select>
            {narrowed && (
              <Button size="sm" variant="ghost" onClick={reset}>
                필터 초기화
              </Button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Tabs
              value={test}
              onValueChange={(value) => {
                setTest(value as TestFilter)
                setStandard('')
              }}
            >
              <TabsList className="h-auto flex-wrap">
                {TEST_TABS.map((one) => (
                  <TabsTrigger key={one.value} value={one.value}>
                    {`${one.label} ${countOf(one.value)}`}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <span className="text-muted-foreground flex items-center gap-1 text-xs">
              <span className="inline-block size-3 rounded-sm border-l-4 border-l-sky-500 bg-sky-100 dark:bg-sky-900" aria-hidden />
              사내 규격: 이 서버에서 관리자가 등록한 규격입니다.
            </span>
            <span className="text-muted-foreground ml-auto text-xs">
              공개 규격 {rows.length - internalCount}개 · 사내 규격 {internalCount}개 · 검토 필요 {reviewCount}개
            </span>
          </div>
        </div>
      )}
      {rows.length > 0 && shown.length === 0 && <EmptyState title="조건에 맞는 규격이 없습니다" hint="검색어나 필터를 변경하십시오." />}

      {bending.length > 0 && (
        <Section title="굽힘" hint="규격의 시편과 지지 롤러, 로딩 노즈, 해석 조건이 포함된 작업을 생성합니다. 제품에 굽힘 지그를 적용하려면 지그 생성에서 이 규격을 선택하십시오.">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>규격</TableHead>
                <TableHead>방식</TableHead>
                <TableHead>시편 (mm)</TableHead>
                <TableHead>지지 간격</TableHead>
                <TableHead>반지름 (지지 / 노즈)</TableHead>
                <TableHead>상태</TableHead>
                <TableHead className="text-right">작업</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {byStandard(bending).map(([group, members]) => (
                <Fragment key={group}>
                  <GroupRow standard={group} count={members.length} columns={7} />
                  {members.map((row) => {
                    const preset = row.preset
                    const inner = loadSpanText(preset)
                    return (
                      <TableRow key={row.id} className={row.origin === 'internal' ? INTERNAL_ROW : undefined}>
                        <NameCell row={row} />
                        <TableCell className="align-top">{preset.setup.points}점</TableCell>
                        <TableCell className="align-top font-mono text-xs">
                          {preset.specimen.length} × {preset.specimen.width} × {preset.specimen.thickness}
                        </TableCell>
                        <TableCell className="min-w-28 align-top text-xs whitespace-normal">
                          {spanText(preset)}
                          {inner && <p className="text-muted-foreground">하중 간격 {inner}</p>}
                        </TableCell>
                        <TableCell className="min-w-28 align-top text-xs whitespace-normal">
                          {radiusText(preset.setup.support_radius)} / {radiusText(preset.setup.nose_radius)}
                        </TableCell>
                        <StatusCell row={row} />
                        {actions(
                          row,
                          <Button size="sm" onClick={() => setMaking(row)}>
                            시편 생성
                          </Button>,
                        )}
                      </TableRow>
                    )
                  })}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}

      {KINDS.map((spec) => {
        const members = shown.filter((row) => row.preset.test === spec.test)
        if (members.length === 0) return null
        const columns = spec.columns.length + 3
        return (
          <Section key={spec.test} title={spec.label} hint={spec.hint}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>규격</TableHead>
                  {spec.columns.map((column) => (
                    <TableHead key={column.head}>{column.head}</TableHead>
                  ))}
                  <TableHead>상태</TableHead>
                  <TableHead className="text-right">작업</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {byStandard(members).map(([group, list]) => (
                  <Fragment key={group}>
                    <GroupRow standard={group} count={list.length} columns={columns} />
                    {list.map((row) => (
                      <TableRow key={row.id} className={row.origin === 'internal' ? INTERNAL_ROW : undefined}>
                        <NameCell row={row} />
                        {spec.columns.map((column) => (
                          <TableCell key={column.head} className="min-w-20 align-top text-xs whitespace-normal">
                            {column.text(row.preset)}
                          </TableCell>
                        ))}
                        <StatusCell row={row} />
                        {actions(row, primary(row))}
                      </TableRow>
                    ))}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          </Section>
        )
      })}

      {making && <SpecimenDialog row={making} onClose={() => setMaking(null)} />}
      {coupon && <CouponDialog row={coupon} onClose={() => setCoupon(null)} />}
      {applying && <ProductTestDialog row={applying} onClose={() => setApplying(null)} />}
      {editing && isBending(editing.row) && (
        <PresetDialog
          row={editing.row}
          mode={editing.mode}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            presets.reload()
          }}
        />
      )}
      {editing && !isBending(editing.row) && (
        <PresetFieldsDialog
          row={editing.row}
          mode={editing.mode}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            presets.reload()
          }}
        />
      )}
      <ConfirmDialog
        open={removing !== null}
        title="사내 규격 삭제"
        description={`‘${removing?.name ?? ''}’을(를) 삭제합니다. 이 규격으로 이미 생성한 작업과 지그는 그대로 유지됩니다.`}
        confirmLabel="삭제"
        destructive
        onConfirm={async () => {
          if (!removing) return
          await specimensApi.remove(removing.id)
          presets.reload()
        }}
        onClose={() => setRemoving(null)}
      />
    </div>
  )
}
