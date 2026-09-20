/**
 * 조립 — 부품과 지그를 **가져다 서로 위치시킨다.**
 *
 * 조립은 그리는 것이 아니라 **놓는 것**이다. 그래서 화면이 다르다: 왼쪽은 구성(놓인 것들의
 * 목록)과 가져올 것들(내 도면 · 카탈로그), 가운데는 3D 미리보기 — 가져오는 순간 거기 나타난다.
 * 자리 · 회전 · 치수 덮어쓰기는 목록의 「편집」 이 여는 창에서 고치고, 고치는 대로 3D 가 따라온다.
 * 가져온 것은 STEP 이 아니라 **살아 있는 레시피**라, 그 치수에 조립의 변수를 물릴 수 있다(`fx`)
 * — 그래야 조립을 실험계획으로 훑는 뜻이 있다.
 */

import { Boxes, Layers, Pencil, Plus, Trash2 } from 'lucide-react'
import { lazy, Suspense, useMemo, useState } from 'react'

import { cadApi } from '@/modules/cad/api'
import type { Recipe } from '@/modules/cad/api'
import { NumberField } from '@/modules/cad/NumberField'
import { ParamsPanel } from '@/modules/cad/ParamsPanel'
import { useRecipeEmit } from '@/modules/cad/useRecipeEmit'
import { useRecipeMesh } from '@/modules/cad/useRecipeMesh'
import { jigsApi } from '@/modules/jigs/api'
import { partsApi } from '@/modules/parts/api'
import { worksApi } from '@/modules/works/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'

const PickViewer = lazy(() => import('@/shared/viewer/PickViewer'))

/** 놓인 것 하나 — 레시피의 `component` 피처. */
type Placed = Record<string, unknown> & {
  id: string
  op: 'component'
  source: string
  label?: string
  params?: Record<string, number | string>
  translate?: (number | string)[]
  rotate?: (number | string)[]
}

const AXES = ['X', 'Y', 'Z'] as const

/** 구성품마다 다른 색 — 목록의 점과 3D 의 면이 같은 색이라 어느 것이 어느 것인지 보인다. */
const PALETTE = [0x3b82f6, 0xf97316, 0x10b981, 0xa855f7, 0xef4444, 0x14b8a6, 0xeab308, 0xec4899]
const colorOf = (index: number) => PALETTE[index % PALETTE.length]
const cssColor = (color: number) => `#${color.toString(16).padStart(6, '0')}`

const SOURCE_LABEL: Record<string, string> = { work: '내 도면', part: '공용 부품', jig: '공용 지그' }

function nodesOf(recipe: Recipe): Record<string, unknown>[] {
  return (recipe.nodes ?? []) as Record<string, unknown>[]
}

/** 조립 레시피는 늘 「가져온 것들 + 묶음 한 줄」 이다 — 묶음을 손으로 관리하지 않는다. */
function withGroup(placed: Placed[], recipe: Recipe): Recipe {
  const nodes: Record<string, unknown>[] = [...placed]
  if (placed.length > 0) {
    nodes.push({ id: '조립', op: 'group', targets: placed.map((one) => one.id) })
  }
  return { ...recipe, nodes }
}

function uniqueId(base: string, taken: Set<string>): string {
  const clean = base.replace(/[^\w가-힣-]/g, '_').slice(0, 30) || '구성품'
  if (!taken.has(clean)) return clean
  for (let n = 2; ; n += 1) if (!taken.has(`${clean}-${n}`)) return `${clean}-${n}`
}

export function AssemblyEditor({ value, onChange }: { value: Recipe; onChange: (next: Recipe) => void }) {
  const placed = useMemo(() => nodesOf(value).filter((one) => one.op === 'component') as Placed[], [value])
  /** 목록에서 고른 것 — 3D 에서 그것만 또렷하다. */
  const [selected, setSelected] = useState<string | null>(null)
  /** 「편집」 창을 연 것. */
  const [editing, setEditing] = useState<string | null>(null)
  /** 3D 손잡이 — 고른 구성품을 화살표로 옮기거나 고리로 돌린다. */
  const [dragMode, setDragMode] = useState<'translate' | 'rotate'>('translate')
  const [dragNote, setDragNote] = useState<string | null>(null)
  const params = (value.params ?? {}) as Record<string, number>

  const works = useResource(() => worksApi.list(0, 100), [])
  const parts = useResource(() => partsApi.list(0, 100), [])
  const jigs = useResource(() => jigsApi.list({ limit: 100 }), [])

  const emit = useRecipeEmit(value, onChange)
  const { mesh, problems, drawing, error, interference } = useRecipeMesh(value, { interference: true })
  /** 겹친 구성품 — 3D 에서 빨갛게. 목록에서도 표시한다. */
  const colliding = useMemo(() => new Set((interference?.items ?? []).filter((one) => !one.ok).flatMap((one) => [one.a, one.b])), [interference])
  const partColors = useMemo(
    () => Object.fromEntries(placed.map((one, index) => [one.id, colliding.has(one.id) ? 0xef4444 : colorOf(index)])),
    [placed, colliding],
  )

  function put(next: Placed[]) {
    emit((current) => withGroup(next, current))
  }

  /**
   * 칸에서 조립의 변수를 만든다 — **여기가 실험계획으로 가는 문이다.** 구성품 치수 칸에서
   * 바로 만들 수 있어야 「가져온 도면의 치수를 조립이 움직인다」 가 된다.
   */
  function createParam(name: string, seed: number) {
    emit((current) => {
      const now = (current.params ?? {}) as Record<string, number>
      return name in now ? current : { ...current, params: { ...now, [name]: seed } }
    })
  }

  function add(source: string, label: string) {
    const taken = new Set(placed.map((one) => one.id))
    const made: Placed = {
      id: uniqueId(label, taken),
      op: 'component',
      source,
      label,
      params: {},
      translate: [0, 0, 0],
      rotate: [0, 0, 0],
    }
    put([...placed, made])
    setSelected(made.id)
  }

  /**
   * 3D 에서 끌어 놓은 만큼 translate · rotate 에 더한다. 식(`=변수`)이 든 축은 건드리지 않고
   * 말한다 — 변수를 끌기로 덮어쓰면 DOE 가 끊긴다.
   */
  function moved(id: string, delta: { translate: [number, number, number]; rotate: [number, number, number] }) {
    const one = placed.find((p) => p.id === id)
    if (!one) return
    const skipped: string[] = []
    const add = (now: (number | string)[] | undefined, by: [number, number, number], name: string) =>
      [0, 1, 2].map((i) => {
        const current = (now ?? [0, 0, 0])[i]
        if (typeof current === 'string') {
          if (by[i] !== 0) skipped.push(`${name} ${'XYZ'[i]}`)
          return current
        }
        return Math.round(((current ?? 0) + by[i]) * 1000) / 1000
      })
    update(id, { translate: add(one.translate, delta.translate, '자리'), rotate: add(one.rotate, delta.rotate, '회전') })
    setDragNote(skipped.length > 0 ? `${skipped.join(' · ')} 는 식으로 묶여 있어 끌기로 바꾸지 않았습니다 — 편집 창에서 변수를 고치세요.` : null)
  }

  /** 다른 구성품의 면에 얹는다 — 서버가 경계 상자로 translate 를 계산한다(「지그 윗면에 부품 바닥을」). */
  async function placeOn(id: string, onto: string, face: string, offset: number) {
    try {
      const got = await cadApi.place(value, { mover: id, onto, face, offset, align: 'center' })
      update(id, { translate: got.translate })
      setDragNote(null)
    } catch (caught) {
      setDragNote(caught instanceof Error ? caught.message : '얹지 못했습니다')
    }
  }

  function update(id: string, patch: Partial<Placed>) {
    put(placed.map((one) => (one.id === id ? { ...one, ...patch } : one)))
  }

  function remove(id: string) {
    put(placed.filter((other) => other.id !== id))
    if (selected === id) setSelected(null)
    if (editing === id) setEditing(null)
  }

  const editingNode = placed.find((one) => one.id === editing) ?? null
  const viewerHeight = 'h-[520px]'

  return (
    <div className="grid gap-3 lg:grid-cols-12">
      {/* 왼쪽 — 구성(놓인 것들) · 가져올 것들 · 변수 */}
      <div className="space-y-3 lg:col-span-3">
        <div className="rounded-md border">
          <p className="bg-muted/40 border-b px-2 py-1 text-xs font-medium">구성 {placed.length > 0 && `(${placed.length})`}</p>
          {placed.length === 0 ? (
            <p className="text-muted-foreground p-2 text-xs">아직 없습니다 — 아래 「가져오기」 에서 부품이나 지그를 고르세요.</p>
          ) : (
            <ul className="p-1">
              {placed.map((one, index) => {
                const isCurrent = one.id === selected
                return (
                  <li key={one.id} className={`group flex items-center gap-1.5 rounded px-1.5 py-1 text-sm ${isCurrent ? 'bg-accent' : 'hover:bg-accent/60'}`}>
                    <span className="size-2.5 shrink-0 rounded-full" style={{ background: cssColor(colliding.has(one.id) ? 0xef4444 : colorOf(index)) }} aria-hidden />
                    <button type="button" className="min-w-0 flex-1 truncate text-left" onClick={() => setSelected(isCurrent ? null : one.id)} title={one.id}>
                      {one.label || one.id}
                    </button>
                    <Badge variant="outline" className="shrink-0 text-[10px]">
                      {SOURCE_LABEL[one.source.split(':')[0]] ?? one.source.split(':')[0]}
                    </Badge>
                    {/* 손이 올라갔을 때만 — 늘 보이면 목록이 단추로 덮인다. 고른 줄은 늘 보인다. */}
                    <span className={`flex shrink-0 gap-0.5 ${isCurrent ? '' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100'}`}>
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-foreground rounded p-1"
                        aria-label={`${one.label ?? one.id} 편집`}
                        title="자리 · 회전 · 치수 덮어쓰기"
                        onClick={() => {
                          setSelected(one.id)
                          setEditing(one.id)
                        }}
                      >
                        <Pencil className="size-3.5" />
                      </button>
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-destructive rounded p-1"
                        aria-label={`${one.label ?? one.id} 빼기`}
                        onClick={() => remove(one.id)}
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="rounded-md border">
          <p className="bg-muted/40 border-b px-2 py-1 text-xs font-medium">가져오기</p>
          <div className="max-h-72 space-y-3 overflow-y-auto p-2">
            <Library
              title="내 도면"
              icon={Layers}
              rows={(works.data?.items ?? [])
                .filter((one) => one.kind !== 'assembly' && one.current_version > 0)
                .map((one) => ({ key: `work:${one.id}`, name: one.name, hint: one.kind === 'jig' ? '지그' : '부품' }))}
              onAdd={add}
            />
            <Library
              title="부품 카탈로그"
              icon={Layers}
              rows={(parts.data?.items ?? []).map((one) => ({
                key: `part:${one.id}`,
                name: one.name,
                hint: `v${one.current_version}`,
              }))}
              onAdd={add}
            />
            <Library
              title="지그 카탈로그"
              icon={Boxes}
              rows={(jigs.data?.items ?? []).map((one) => ({
                key: `jig:${one.id}`,
                name: one.name,
                hint: `v${one.current_version}`,
              }))}
              onAdd={add}
            />
          </div>
        </div>

        <ParamsPanel value={value} onChange={(next) => emit(() => next)} />
      </div>

      {/* 가운데 — 3D. 가져오면 여기 나타나고, 편집 창에서 고치는 대로 따라온다. */}
      <div className="space-y-2 lg:col-span-9">
        <p className="text-muted-foreground text-xs">
          {drawing
            ? '그리는 중…'
            : placed.length === 0
              ? '가져온 부품 · 지그가 여기에 그려집니다.'
              : problems.length > 0
                ? '고칠 것이 있습니다.'
                : selected
                  ? '고른 구성품에 손잡이가 붙었습니다 — 화살표를 끌어 옮기거나(0.5 mm 단위) 고리를 돌립니다(5°). 목록에서 다시 누르면 풉니다.'
                  : '끌어서 돌리고, 굴려서 확대합니다. 목록에서 고르면 그것만 또렷해지고 손잡이가 붙습니다.'}
        </p>
        {selected && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">손잡이</span>
            {(
              [
                { value: 'translate', label: '옮기기' },
                { value: 'rotate', label: '돌리기' },
              ] as const
            ).map((one) => (
              <button
                key={one.value}
                type="button"
                onClick={() => setDragMode(one.value)}
                aria-pressed={dragMode === one.value}
                className={`rounded-md border px-2 py-0.5 ${dragMode === one.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}
              >
                {one.label}
              </button>
            ))}
            {dragNote && <span className="text-destructive">{dragNote}</span>}
          </div>
        )}
        {mesh ? (
          <Suspense fallback={<Skeleton className={`${viewerHeight} w-full`} />}>
            <PickViewer
              mesh={mesh}
              mode="none"
              partColors={partColors}
              emphasis={selected}
              dragPart={selected}
              dragMode={dragMode}
              onMoved={moved}
              className={`${viewerHeight} w-full rounded-md border`}
            />
          </Suspense>
        ) : (
          <div className={`text-muted-foreground flex ${viewerHeight} items-center justify-center rounded-md border border-dashed text-sm`}>
            {placed.length === 0 ? '왼쪽 「가져오기」 에서 부품이나 지그를 누르세요.' : problems.length > 0 ? '도면이 맞으면 여기에 그려집니다.' : '그리는 중…'}
          </div>
        )}
        {problems.length > 0 && (
          <ul className="text-destructive list-disc pl-5 text-xs">
            {problems.map((one) => (
              <li key={one}>{one}</li>
            ))}
          </ul>
        )}
        {/* 겹침 — 서버는 겹친 채로도 저장하니 여기서 보여 줘야 한다. */}
        {mesh && interference && placed.length > 1 && (
          <div className="flex flex-wrap items-center gap-2 text-xs" role="status">
            <StatusBadge kind="interference" value={interference.ok ? 'ok' : 'bad'} />
            {interference.ok ? (
              <span className="text-muted-foreground">구성품 {interference.parts.length} 개, {interference.checked_pairs} 쌍 검사 — 겹치지 않습니다.</span>
            ) : (
              <span className="text-destructive">
                {interference.items
                  .filter((one) => !one.ok)
                  .map((one) => `${one.a} × ${one.b} ${one.volume.toLocaleString()} mm³`)
                  .join(' · ')}{' '}
                — 편집 창에서 자리를 옮기세요.
              </span>
            )}
          </div>
        )}
        <ErrorNotice error={error} />
      </div>

      {/* 편집 창 — 3D 를 가리지 않게 오른쪽에 붙고(모달 아님), 고치는 대로 3D 가 따라온다. */}
      <Dialog open={editingNode !== null} modal={false} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent
          overlay={false}
          className="top-24 right-6 left-auto max-h-[80vh] w-96 translate-x-0 translate-y-0 overflow-y-auto sm:max-w-md"
          onInteractOutside={(event) => event.preventDefault()}
          onOpenAutoFocus={(event) => event.preventDefault()}
        >
          {editingNode && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 text-base">
                  <span className="size-2.5 rounded-full" style={{ background: cssColor(partColors[editingNode.id] ?? PALETTE[0]) }} aria-hidden />
                  {editingNode.label || editingNode.id}
                </DialogTitle>
                <DialogDescription>고치는 대로 3D 에 바로 보입니다. 칸의 fx 로 조립의 변수를 물릴 수 있습니다.</DialogDescription>
              </DialogHeader>
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground w-12 text-xs">이름</span>
                  <Input
                    value={editingNode.id}
                    onChange={(event) => {
                      const next = event.target.value
                      if (!next || placed.some((other) => other.id === next && other.id !== editingNode.id)) return
                      update(editingNode.id, { id: next })
                      setEditing(next)
                      setSelected(next)
                    }}
                    className="h-7 flex-1 font-mono text-xs"
                    aria-label={`${editingNode.label ?? editingNode.id} 이름`}
                  />
                </div>
                <div>
                  <p className="text-muted-foreground mb-1 text-xs">자리 (mm)</p>
                  <div className="grid grid-cols-3 gap-1">
                    {AXES.map((axis, index) => (
                      <div key={axis} className="flex items-center gap-1">
                        <span className="text-muted-foreground w-3 text-xs">{axis}</span>
                        <NumberField
                          params={params}
                          onCreateParam={createParam}
                          aria-label={`${editingNode.label ?? editingNode.id} ${axis}`}
                          value={(editingNode.translate ?? [0, 0, 0])[index]}
                          onChange={(next) => {
                            const list = [...(editingNode.translate ?? [0, 0, 0])]
                            list[index] = next ?? 0
                            update(editingNode.id, { translate: list })
                          }}
                        />
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-muted-foreground mb-1 text-xs">회전 (°)</p>
                  <div className="grid grid-cols-3 gap-1">
                    {AXES.map((axis, index) => (
                      <div key={axis} className="flex items-center gap-1">
                        <span className="text-muted-foreground w-3 text-xs">{axis}</span>
                        <NumberField
                          params={params}
                          onCreateParam={createParam}
                          aria-label={`${editingNode.label ?? editingNode.id} 회전 ${axis}`}
                          value={(editingNode.rotate ?? [0, 0, 0])[index]}
                          onChange={(next) => {
                            const list = [...(editingNode.rotate ?? [0, 0, 0])]
                            list[index] = next ?? 0
                            update(editingNode.id, { rotate: list })
                          }}
                        />
                      </div>
                    ))}
                  </div>
                </div>
                <PlaceOnRow node={editingNode} others={placed.filter((one) => one.id !== editingNode.id)} onPlace={(onto, face, offset) => void placeOn(editingNode.id, onto, face, offset)} />
                <ComponentParams node={editingNode} params={params} onCreateParam={createParam} onChange={(next) => update(editingNode.id, { params: next })} />
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function Library({
  title,
  icon: Icon,
  rows,
  onAdd,
}: {
  title: string
  icon: typeof Boxes
  rows: { key: string; name: string; hint: string }[]
  onAdd: (source: string, label: string) => void
}) {
  return (
    <div>
      <p className="text-muted-foreground mb-1 flex items-center gap-1 text-[11px]">
        <Icon className="size-3" /> {title}
      </p>
      {rows.length === 0 ? (
        <p className="text-muted-foreground text-[11px]">없습니다.</p>
      ) : (
        <ul className="space-y-0.5">
          {rows.map((row) => (
            <li key={row.key}>
              <button
                type="button"
                onClick={() => onAdd(row.key, row.name)}
                className="hover:bg-accent flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-xs"
              >
                <Plus className="size-3 shrink-0" />
                <span className="truncate">{row.name}</span>
                <span className="text-muted-foreground ml-auto text-[10px]">{row.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** 「이 구성품을 저 구성품의 어느 면에」 — 숫자 대신 말로 놓는 길. 서버가 경계 상자로 잰다. */
function PlaceOnRow({ node, others, onPlace }: { node: Placed; others: Placed[]; onPlace: (onto: string, face: string, offset: number) => void }) {
  const [onto, setOnto] = useState(others[0]?.id ?? '')
  const [face, setFace] = useState('top')
  const [offset, setOffset] = useState('0')
  if (others.length === 0) return null
  const target = others.some((one) => one.id === onto) ? onto : others[0].id
  return (
    <div>
      <p className="text-muted-foreground mb-1 text-xs">다른 구성품의 면에 얹기</p>
      <div className="flex flex-wrap items-center gap-1 text-xs">
        <select value={target} onChange={(e) => setOnto(e.target.value)} className="h-7 rounded-md border bg-background px-1" aria-label={`${node.label ?? node.id} 를 얹을 구성품`}>
          {others.map((one) => (
            <option key={one.id} value={one.id}>
              {one.label || one.id}
            </option>
          ))}
        </select>
        <span className="text-muted-foreground">의</span>
        <select value={face} onChange={(e) => setFace(e.target.value)} className="h-7 rounded-md border bg-background px-1" aria-label="어느 면">
          <option value="top">윗면</option>
          <option value="bottom">아랫면</option>
          <option value="+x">+X 면</option>
          <option value="-x">-X 면</option>
          <option value="+y">+Y 면</option>
          <option value="-y">-Y 면</option>
        </select>
        <span className="text-muted-foreground">에 틈</span>
        <Input type="number" step={0.5} value={offset} onChange={(e) => setOffset(e.target.value)} className="h-7 w-16 text-xs" aria-label="틈 (mm)" />
        <Button size="sm" type="button" className="h-7 px-2 text-xs" onClick={() => onPlace(target, face, Number(offset) || 0)}>
          얹기
        </Button>
      </div>
      <p className="text-muted-foreground mt-1 text-[11px]">경계 상자로 맞춥니다 — 닿는 면이 평면이면 정확하고, 곡면이면 어림입니다. 나머지 두 축은 가운데를 맞춥니다.</p>
    </div>
  )
}

/**
 * 가져온 도면의 **변수 덮어쓰기** — 여기에 `=조립변수` 를 넣으면 조립이 구성품을 움직인다.
 *
 * 이름은 가져온 도면의 것이라 여기서는 목록으로 못 준다(서버가 안다). 사람이 이름을 적고 값을
 * 넣는다 — 틀린 이름은 저장할 때 그 도면이 거절하며 아는 이름을 알려 준다.
 */
function ComponentParams({
  node,
  params,
  onCreateParam,
  onChange,
}: {
  node: Placed
  params: Record<string, number>
  onCreateParam: (name: string, value: number) => void
  onChange: (next: Record<string, number | string>) => void
}) {
  const current = (node.params ?? {}) as Record<string, number | string>
  const [name, setName] = useState('')
  return (
    <div>
      <p className="text-muted-foreground mb-1 text-xs">이 구성품의 치수 덮어쓰기</p>
      <div className="space-y-1">
        {Object.entries(current).map(([key, value]) => (
          <div key={key} className="flex items-center gap-1">
            <span className="w-28 truncate font-mono text-xs">{key}</span>
            <NumberField
              params={params}
              onCreateParam={onCreateParam}
              aria-label={`${node.label ?? node.id} ${key}`}
              value={value}
              onChange={(next) => onChange({ ...current, [key]: next ?? 0 })}
            />
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive rounded p-1"
              aria-label={`${key} 덮어쓰기 빼기`}
              onClick={() => {
                const next = { ...current }
                delete next[key]
                onChange(next)
              }}
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
        <form
          className="flex items-center gap-1"
          onSubmit={(event) => {
            event.preventDefault()
            const key = name.trim()
            if (!key || key in current) return
            onChange({ ...current, [key]: 0 })
            setName('')
          }}
        >
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="가져온 도면의 변수 이름 — 예: 두께"
            className="h-7 flex-1 font-mono text-xs"
            aria-label={`${node.label ?? node.id} 덮어쓸 변수 이름`}
          />
          <Button size="sm" type="submit" className="h-7 px-2 text-xs" disabled={!name.trim()}>
            더하기
          </Button>
        </form>
      </div>
    </div>
  )
}
