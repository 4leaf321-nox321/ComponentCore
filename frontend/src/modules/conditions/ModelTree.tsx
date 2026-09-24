/**
 * 모델 구성 — 해석 조건 왼쪽의 트리. **한 벌에 무엇이 있는지 여기서 다 본다.**
 *
 * 도면 편집기의 피처 트리와 같은 자리 · 같은 역할이다: 더하는 것은 위의 리본 단추가 하고,
 * 트리는 있는 것을 보여 주고 누르면 고친다. 가지는 해석 전처리기의 순서를 따른다 — 파트 ·
 * 물성 · 이름표 · 조건들 · 해석 설정.
 *
 * **물성은 파트가 먼저다.** 물성마다 「어느 파트에」 를 고르게 했더니 파트가 여럿이면 물성
 * 하나씩 열고 닫기를 되풀이해야 했다. 파트를 누르면 그 자리에서 담아 둔 물성 중 하나를
 * 고른다 — 한 화면에서 파트를 차례로 누르며 끝낸다.
 *
 * 색은 3D 와 같다 — 줄 앞의 네모 색이 3D 에서 그 파트의 색이고, 아직 비어 있는 파트는
 * 회색이다. 어느 파트가 남았는지 3D 에서도 보인다.
 */

import { ChevronDownIcon, ChevronRightIcon } from 'lucide-react'
import { useState } from 'react'

import { ALL_BODIES, appliedTo, materialsOn } from '@/modules/conditions/api'
import type { Body, ConditionItem, MaterialItem, NamedSelection } from '@/modules/conditions/api'
import { Button } from '@/shared/components/ui/button'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'

/** 물성마다 한 색 — 담은 순서대로. 강조색(주황 · 빨강)은 뷰어가 선택 · 측정에 쓰므로 뺐다. */
const MATERIAL_COLORS = [0x3b82f6, 0x10b981, 0x8b5cf6, 0xf43f5e, 0x06b6d4, 0x84cc16, 0xec4899, 0x14b8a6]
/** 물성이 아직 없는 파트. */
export const UNASSIGNED_COLOR = 0x9ca3af

export const materialColor = (index: number) => MATERIAL_COLORS[index % MATERIAL_COLORS.length]
const css = (color: number) => `#${color.toString(16).padStart(6, '0')}`

/** 트리에서 펼친 것 — 파트 · 담아 둔 물성 · 이름표 하나. 조건은 펼치지 않고 창으로 연다. */
export type TreeSelection =
  | { kind: 'part'; name: string }
  | { kind: 'library'; index: number }
  | { kind: 'selection'; index: number }
  | null

/** 조건 한 줄의 「어디에」 — 접촉은 두 이름표를 잇는다. */
function targetOf(item: ConditionItem): string {
  if ('source' in item || 'target' in item) {
    return [item.source, item.target].map((one) => String(one ?? '') || '?').join(' → ')
  }
  return String(item.on ?? '')
}

const nameOf = (material: MaterialItem | undefined) =>
  String(((material?.ref ?? {}) as Record<string, unknown>).name ?? '이름 없음')

function Swatch({ color }: { color: number }) {
  return <span aria-hidden className="size-2.5 shrink-0 rounded-sm" style={{ background: css(color) }} />
}

/** 접었다 펴는 가지 하나 — 머리와 그 아래 줄들. */
function Branch({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  const Icon = open ? ChevronDownIcon : ChevronRightIcon
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        className="hover:bg-muted flex w-full items-center gap-1 rounded px-1 py-1 text-left font-medium"
        onClick={() => setOpen(!open)}
      >
        <Icon className="size-3.5 shrink-0" />
        {title} <span className="text-muted-foreground">{count}</span>
      </button>
      {open && <div className="ml-2 border-l pl-2">{children}</div>}
    </div>
  )
}

export function ModelTree({
  bodies,
  bodiesError,
  materials,
  decks,
  names,
  groups,
  analysis,
  editing,
  selected,
  onSelect,
  onAssign,
  onMaterialChange,
  onRemoveMaterial,
  onPickMaterials,
  onRemoveSelection,
  onOpenItem,
  onOpenAnalysis,
}: {
  /** `null` 이면 아직 불러오는 중이다. */
  bodies: Body[] | null
  bodiesError?: Error | null
  materials: MaterialItem[]
  /** 물성(그쪽 id)마다 생성 가능한 솔버 덱 형식. */
  decks: Record<string, { key: string; ready: boolean }[]>
  selected: TreeSelection
  onSelect: (next: TreeSelection) => void
  /** 파트에 물성을 지정한다 — `null` 이면 지정 해제. */
  onAssign: (body: string, index: number | null) => void
  onMaterialChange: (index: number, patch: Partial<MaterialItem>) => void
  onRemoveMaterial: (index: number) => void
  /** 물성 탐색기를 연다. */
  onPickMaterials: () => void
  names: NamedSelection[]
  /** 조건 묶음들 — 구속 · 하중 · 접촉 · 초기조건 · 메시 힌트. */
  groups: { key: string; label: string; items: ConditionItem[] }[]
  /** 해석 설정 한 줄 요약(종류 · 단위계). */
  analysis: string
  /** 지금 창에서 고치는 조건 — 트리에서도 그 줄이 표시된다. */
  editing: { group: string; index: number | null } | null
  onRemoveSelection: (index: number) => void
  onOpenItem: (group: string, index: number) => void
  onOpenAnalysis: () => void
}) {
  const single = bodies?.length === 1 && bodies[0].name === ALL_BODIES

  return (
    <div className="space-y-2">
      <p className="font-medium">모델 구성</p>

      <Branch title="파트" count={bodies?.length ?? 0}>
        {bodies === null && !bodiesError && <Skeleton className="h-16 w-full" />}
        {bodiesError && (
          <p className="text-muted-foreground px-1 text-xs">
            파트 목록을 불러오지 못했습니다 — 「도면」 탭에서 도면을 확인하세요.
          </p>
        )}
        <ul className="space-y-0.5">
          {(bodies ?? []).map((body) => {
            const on = materialsOn(materials, body.name)
            const open = selected?.kind === 'part' && selected.name === body.name
            return (
              <li key={body.name}>
                <button
                  type="button"
                  aria-expanded={open}
                  className={`hover:bg-muted flex w-full items-center gap-2 rounded px-2 py-1 text-left ${open ? 'bg-muted' : ''}`}
                  onClick={() => onSelect(open ? null : { kind: 'part', name: body.name })}
                >
                  <Swatch color={on.length ? materialColor(on[0]) : UNASSIGNED_COLOR} />
                  <span className="truncate">{body.name}</span>
                  {single && <span className="text-muted-foreground text-xs">단일 파트</span>}
                  <span
                    className={`ml-auto truncate text-xs ${on.length === 1 ? 'text-muted-foreground' : 'text-amber-700 dark:text-amber-400'}`}
                  >
                    {on.length === 0 ? '미지정' : on.length > 1 ? '물성 중복' : nameOf(materials[on[0]])}
                  </span>
                </button>
                {open && (
                  <div className="mt-1 mb-2 ml-4 space-y-2 border-l pl-3">
                    {on.length > 1 && (
                      <p className="text-xs text-amber-700 dark:text-amber-400">
                        물성이 둘 이상 지정되어 있습니다 — 하나를 선택하세요. 이대로는 저장되지 않습니다.
                      </p>
                    )}
                    {materials.length === 0 ? (
                      <div className="space-y-1">
                        <p className="text-muted-foreground text-xs">추가된 물성이 없습니다.</p>
                        <Button size="sm" variant="outline" onClick={onPickMaterials}>
                          물성 선택
                        </Button>
                      </div>
                    ) : (
                      <div role="radiogroup" aria-label={`${body.name} 물성`} className="space-y-0.5">
                        {[null, ...materials.map((_, index) => index)].map((index) => {
                          const checked = index === null ? on.length === 0 : on.length === 1 && on[0] === index
                          return (
                            <button
                              key={index ?? 'none'}
                              type="button"
                              role="radio"
                              aria-checked={checked}
                              className={`flex w-full items-center gap-2 rounded border px-2 py-0.5 text-left text-xs ${
                                checked ? 'border-primary bg-accent' : 'hover:bg-accent/50 border-transparent'
                              }`}
                              onClick={() => onAssign(body.name, index)}
                            >
                              <Swatch color={index === null ? UNASSIGNED_COLOR : materialColor(index)} />
                              {index === null ? '미지정' : nameOf(materials[index])}
                            </button>
                          )
                        })}
                      </div>
                    )}
                    {/* 부피를 함께 표시한다 — 이름이 비슷할 때 구분 근거가 된다. */}
                    {body.volume !== undefined && (
                      <p className="text-muted-foreground text-xs">
                        부피 {Math.round(body.volume).toLocaleString()} mm³
                      </p>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </Branch>

      <Branch title="물성" count={materials.length}>
        {materials.length === 0 && (
          <div className="space-y-1 px-1">
            <p className="text-muted-foreground text-xs">추가된 물성이 없습니다.</p>
            <Button size="sm" variant="outline" onClick={onPickMaterials}>
              물성 선택
            </Button>
          </div>
        )}
        <ul className="space-y-0.5">
          {materials.map((material, index) => {
            const ref = (material.ref ?? {}) as Record<string, unknown>
            const where = appliedTo(material)
            const open = selected?.kind === 'library' && selected.index === index
            const 고른덱 = material.deck_formats ?? []
            const 가능한덱 = (decks[String(ref.material_id ?? '')] ?? []).filter((one) => one.ready)
            return (
              <li key={index}>
                <button
                  type="button"
                  aria-expanded={open}
                  className={`hover:bg-muted flex w-full items-center gap-2 rounded px-2 py-1 text-left ${open ? 'bg-muted' : ''}`}
                  onClick={() => onSelect(open ? null : { kind: 'library', index })}
                >
                  <Swatch color={materialColor(index)} />
                  <span className="truncate">{nameOf(material)}</span>
                  <span className="text-muted-foreground ml-auto shrink-0 text-xs">
                    {where.includes(ALL_BODIES) && !single ? '전체 파트' : `파트 ${where.length}`}
                    {고른덱.length > 0 && ` · 덱 ${고른덱.length}`}
                  </span>
                </button>
                {open && (
                  <div className="mt-1 mb-2 ml-4 space-y-2 border-l pl-3 text-xs">
                    <p className="text-muted-foreground">
                      {[ref.code, ref.source].filter(Boolean).join(' · ')} — 값은 물성 플랫폼이 제공한 그대로
                      전달됩니다.
                    </p>
                    <p>
                      <span className="text-muted-foreground">적용 파트 </span>
                      {where.length === 0 ? '없음 — 파트 목록에서 지정합니다.' : where.join(', ')}
                    </p>
                    {가능한덱.length > 0 && (
                      <div className="space-y-1">
                        <Label className="text-xs">솔버 덱 포함</Label>
                        <p className="text-muted-foreground">
                          중립 물성은 그대로 전달되며, 선택한 덱이 그 옆에 추가됩니다.
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {가능한덱.map((one) => {
                            const 선택됨 = 고른덱.includes(one.key)
                            return (
                              <button
                                key={one.key}
                                type="button"
                                aria-pressed={선택됨}
                                className={`rounded border px-2 py-0.5 ${
                                  선택됨 ? 'border-primary bg-accent' : 'text-muted-foreground'
                                }`}
                                onClick={() =>
                                  onMaterialChange(index, {
                                    deck_formats: 선택됨 ? 고른덱.filter((x) => x !== one.key) : [...고른덱, one.key],
                                  })
                                }
                              >
                                {one.key}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => onRemoveMaterial(index)}>
                      물성 제외
                    </Button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </Branch>

      <Branch title="이름표" count={names.length}>
        {names.length === 0 && (
          <p className="text-muted-foreground px-1 text-xs">3D 에서 형상을 선택하여 생성합니다.</p>
        )}
        <ul className="space-y-0.5">
          {names.map((one, index) => {
            const open = selected?.kind === 'selection' && selected.index === index
            // 어느 조건이 이 이름표를 쓰나 — 지우기 전에 보여야 한다.
            const users = groups.flatMap((group) =>
              group.items
                .filter((item) => [item.on, item.source, item.target].includes(one.name))
                .map((item) => String(item.name ?? item.type ?? group.label)),
            )
            return (
              <li key={one.name}>
                <button
                  type="button"
                  aria-expanded={open}
                  className={`hover:bg-muted flex w-full items-center gap-2 rounded px-2 py-1 text-left ${open ? 'bg-muted' : ''}`}
                  onClick={() => onSelect(open ? null : { kind: 'selection', index })}
                >
                  <span className="truncate">{one.name}</span>
                  <span className="text-muted-foreground ml-auto shrink-0 text-xs">{one.entity}</span>
                </button>
                {open && (
                  <div className="mt-1 mb-2 ml-4 space-y-2 border-l pl-3 text-xs">
                    <p className="text-muted-foreground">
                      좌표가 아니라 <strong>선택 규칙</strong>으로 저장됩니다 — 치수가 변경되어도 같은 형상을
                      가리킵니다.
                    </p>
                    <pre className="bg-muted overflow-x-auto rounded p-2">{JSON.stringify(one.select ?? {}, null, 2)}</pre>
                    <p>
                      <span className="text-muted-foreground">사용하는 조건 </span>
                      {users.length === 0 ? '없음' : users.join(', ')}
                    </p>
                    <Button size="sm" variant="ghost" onClick={() => onRemoveSelection(index)}>
                      이름표 삭제
                    </Button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </Branch>

      {groups.map((group) => (
        <Branch key={group.key} title={group.label} count={group.items.length}>
          <ul className="space-y-0.5">
            {group.items.map((item, index) => {
              const where = targetOf(item)
              const open = editing?.group === group.key && editing.index === index
              return (
                <li key={index}>
                  {/* 조건은 **창으로** 고친다 — 창을 띄운 채 3D 에서 적용 대상을 지정한다. */}
                  <button
                    type="button"
                    className={`hover:bg-muted flex w-full items-center gap-2 rounded px-2 py-1 text-left ${open ? 'bg-muted' : ''}`}
                    onClick={() => onOpenItem(group.key, index)}
                  >
                    <span className="truncate">{String(item.name ?? item.type ?? '')}</span>
                    <span
                      className={`ml-auto truncate text-xs ${where && !where.includes('?') ? 'text-muted-foreground' : 'text-amber-700 dark:text-amber-400'}`}
                    >
                      {where || '대상 미지정'}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </Branch>
      ))}

      <button
        type="button"
        className={`hover:bg-muted flex w-full items-center gap-2 rounded px-1 py-1 text-left font-medium ${editing?.group === 'analysis' ? 'bg-muted' : ''}`}
        onClick={onOpenAnalysis}
      >
        해석 설정
        <span className="text-muted-foreground ml-auto truncate text-xs font-normal">{analysis}</span>
      </button>
    </div>
  )
}
