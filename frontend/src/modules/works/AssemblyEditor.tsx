/**
 * 조립 — 부품과 지그를 **가져다 서로 위치시킨다.**
 *
 * 조립은 그리는 것이 아니라 **놓는 것**이다. 그래서 화면이 다르다: 왼쪽은 구성(놓인 것들의
 * 목록)과 가져올 것들(내 도면 · 카탈로그), 가운데는 3D 미리보기 — 가져오는 순간 거기 나타난다.
 * 자리 · 회전 · 치수 덮어쓰기는 목록의 「편집」 이 여는 창에서 고치고, 고치는 대로 3D 가 따라온다.
 * 가져온 것은 STEP 이 아니라 **살아 있는 레시피**라, 그 치수에 조립의 변수를 물릴 수 있다(`fx`)
 * — 그래야 조립을 실험계획으로 훑는 뜻이 있다.
 */

import { Boxes, ExternalLink, Layers, Pencil, Plus, Trash2 } from 'lucide-react'
import { lazy, Suspense, useMemo, useState } from 'react'

import { cadApi } from '@/modules/cad/api'
import type { Mate, Recipe } from '@/modules/cad/api'
import { NumberField } from '@/modules/cad/NumberField'
import { ParamsPanel } from '@/modules/cad/ParamsPanel'
import { useRecipeEmit } from '@/modules/cad/useRecipeEmit'
import { useRecipeMesh } from '@/modules/cad/useRecipeMesh'
import { jigsApi } from '@/modules/jigs/api'
import { MatesPanel } from '@/modules/works/MatesPanel'
import type { MateDraft } from '@/modules/works/MatesPanel'
import { partsApi } from '@/modules/parts/api'
import { worksApi } from '@/modules/works/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useFillHeight } from '@/shared/hooks/useFillHeight'
import { useResource } from '@/shared/hooks/useResource'
import type { MeshFace } from '@/shared/viewer/PickViewer'

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
  /** 조립 구속 — 주면 translate · rotate 는 처음 자리가 된다. */
  mates?: Mate[]
}

const AXES = ['X', 'Y', 'Z'] as const

/** 구성품마다 다른 색 — 목록의 점과 3D 의 면이 같은 색이라 어느 것이 어느 것인지 보인다. */
const PALETTE = [0x3b82f6, 0xf97316, 0x10b981, 0xa855f7, 0xef4444, 0x14b8a6, 0xeab308, 0xec4899]
const colorOf = (index: number) => PALETTE[index % PALETTE.length]
const cssColor = (color: number) => `#${color.toString(16).padStart(6, '0')}`

const SOURCE_LABEL: Record<string, string> = { work: '내 도면', part: '공용 부품', jig: '공용 지그' }

/** `work:… · part:… · jig:…` → 그 화면의 주소. 모르는 꼴이면 null(단추를 안 그린다). */
export function sourceLink(source: string): string | null {
  const [kind, id] = source.split(':')
  if (!id) return null
  const path = { work: 'works', part: 'parts', jig: 'jigs' }[kind]
  return path ? `/${path}/${id}` : null
}

function nodesOf(recipe: Recipe): Record<string, unknown>[] {
  return (recipe.nodes ?? []) as Record<string, unknown>[]
}

/** 결과로 삼는 노드 — `result` 가 없으면 마지막 노드(서버 `Recipe.result_id` 와 같다). */
function resultId(recipe: Recipe): string | undefined {
  return recipe.result ?? (nodesOf(recipe).at(-1)?.id as string | undefined)
}

/** 바디가 아닌 것 — 가져온 것은 「구성」 목록에 따로 서고, 기준은 형상이 아니다. */
const NOT_DRAWN = new Set(['component', 'datum_axis', 'datum_plane'])

/**
 * 조립 안에서 **직접 그린** 바디 — 결과 묶음에 든 것 중 가져온 것이 아닌 것(묶음이 없으면 결과
 * 노드 하나). 조립은 놓는 것이라 이 화면은 이것을 고치지 않지만, **지워서도 안 된다** — AI 가
 * 바퀴 · 덮개를 조립 안에 바로 그린 작업이 있었고, 「구성」 에는 가져온 것 하나만 보였다.
 */
export function drawnBodies(recipe: Recipe): string[] {
  const nodes = nodesOf(recipe)
  const ops = new Map(nodes.map((one) => [one.id as string, one.op as string]))
  const id = resultId(recipe)
  const last = nodes.find((one) => one.id === id)
  if (!last) return []
  const bodies = last.op === 'group' ? ((last.targets ?? []) as string[]) : [id as string]
  return bodies.filter((one) => ops.has(one) && !NOT_DRAWN.has(ops.get(one)!))
}

/**
 * 구성품 목록을 레시피에 쓴다 — **가져온 것만 바꾸고 나머지는 그대로 둔다.** 묶음은 손으로
 * 관리하지 않는다: 가져온 것이 늘 모두 결과 묶음에 든다.
 *
 * 예전에는 레시피를 「가져온 것들 + 묶음 한 줄」 로 통째로 다시 썼다. 조립 안에서 직접 그린
 * 형상이 있으면 구성품 하나를 옮기기만 해도 그것들이 빠졌다. 이제는
 *
 * - 남은 구성품은 제자리에서 바뀐다(이름을 바꾼 것은 `renamed` 로 짝을 찾는다).
 * - 새로 가져온 것은 마지막 구성품 뒤, 결과 묶음보다 앞에 선다 — 참조는 앞의 것만 가리킨다.
 * - 결과 묶음은 가져온 것의 줄만 고친다. 묶음이 없으면 만들고(그린 결과가 있으면 함께 묶는다),
 *   비면 뺀다.
 */
function withGroup(next: Placed[], recipe: Recipe, renamed?: { from: string; to: string }): Recipe {
  const rename = (id: string) => (renamed && id === renamed.from ? renamed.to : id)
  const byId = new Map(next.map((one) => [one.id, one]))
  const nodes = nodesOf(recipe)
  const was = new Set(nodes.filter((one) => one.op === 'component').map((one) => rename(one.id as string)))
  const fresh = next.filter((one) => !was.has(one.id))
  const resultAt = nodes.findIndex((one) => one.id === resultId(recipe))
  const group = resultAt >= 0 && nodes[resultAt].op === 'group' ? nodes[resultAt] : null
  const lastComponent = nodes.findLastIndex((one) => one.op === 'component')
  const afterComponents = lastComponent >= 0 ? lastComponent + 1 : nodes.length
  const insertAt = group ? Math.min(afterComponents, resultAt) : afterComponents

  let result = recipe.result
  const out: Record<string, unknown>[] = []
  nodes.forEach((one, index) => {
    if (index === insertAt) out.push(...fresh)
    if (one === group) {
      const targets = [
        ...((one.targets ?? []) as string[]).map(rename).filter((id) => byId.has(id) || !was.has(id)),
        ...fresh.map((made) => made.id),
      ]
      if (targets.length > 0) out.push({ ...one, targets })
    } else if (one.op === 'component') {
      const now = byId.get(rename(one.id as string))
      if (now) out.push(now)
    } else {
      out.push(one)
    }
  })
  if (insertAt >= nodes.length) out.push(...fresh)
  if (!group && next.length > 0) {
    const before = resultAt >= 0 && !NOT_DRAWN.has(nodes[resultAt].op as string) ? [nodes[resultAt].id as string] : []
    const id = uniqueId('조립', new Set(out.map((one) => one.id as string)))
    out.push({ id, op: 'group', targets: [...next.map((one) => one.id), ...before] })
    if (result != null) result = id
  }
  // 결과로 가리키던 구성품을 뺐으면 마지막 노드로 돌아간다 — 남기면 「피처가 없습니다」.
  if (result != null && !out.some((one) => one.id === result)) result = undefined
  const made: Recipe = { ...recipe, nodes: out, result }
  if (result == null) delete made.result
  return made
}

function uniqueId(base: string, taken: Set<string>): string {
  const clean = base.replace(/[^\w가-힣-]/g, '_').slice(0, 30) || '구성품'
  if (!taken.has(clean)) return clean
  for (let n = 2; ; n += 1) if (!taken.has(`${clean}-${n}`)) return `${clean}-${n}`
}

export function AssemblyEditor({ value, onChange, conditions }: { value: Recipe; onChange: (next: Recipe) => void; conditions?: unknown }) {
  const placed = useMemo(() => nodesOf(value).filter((one) => one.op === 'component') as Placed[], [value])
  const drawn = useMemo(() => drawnBodies(value), [value])
  /** 3D 에 서는 덩어리 수 — 시뮬레이션 조건의 파트 수와 같다. */
  const total = placed.length + drawn.length
  /** 목록에서 고른 것 — 3D 에서 그것만 또렷하다. */
  const [selected, setSelected] = useState<string | null>(null)
  /** 「편집」 창을 연 것. */
  const [editing, setEditing] = useState<string | null>(null)
  /** 3D 손잡이 — 고른 구성품을 화살표로 옮기거나 고리로 돌린다. */
  const [dragMode, setDragMode] = useState<'translate' | 'rotate'>('translate')
  const [dragNote, setDragNote] = useState<string | null>(null)
  /** 만드는 중인 구속과 지금 3D 에서 고르는 쪽(이것 · 상대). 고르는 동안은 손잡이를 뗀다. */
  const [draft, setDraft] = useState<MateDraft | null>(null)
  const [picking, setPicking] = useState<'this' | 'to' | null>(null)
  const [pickNote, setPickNote] = useState<string | null>(null)
  const params = (value.params ?? {}) as Record<string, number>

  const works = useResource(() => worksApi.list(0, 100), [])
  const parts = useResource(() => partsApi.list(0, 100), [])
  const jigs = useResource(() => jigsApi.list({ limit: 100 }), [])

  const emit = useRecipeEmit(value, onChange)
  const { mesh, summary, problems, drawing, error, interference } = useRecipeMesh(value, { interference: true })
  /** 겹친 구성품 — 3D 에서 빨갛게. 목록에서도 표시한다. */
  const colliding = useMemo(() => new Set((interference?.items ?? []).filter((one) => !one.ok).flatMap((one) => [one.a, one.b])), [interference])
  const partColors = useMemo(
    () => Object.fromEntries([...placed.map((one) => one.id), ...drawn].map((id, index) => [id, colliding.has(id) ? 0xef4444 : colorOf(index)])),
    [placed, drawn, colliding],
  )

  function put(next: Placed[], renamed?: { from: string; to: string }) {
    emit((current) => withGroup(next, current, renamed))
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
    // 조립 안에서 그린 노드의 id 도 피한다 — 겹치면 레시피가 깨진다.
    const taken = new Set(nodesOf(value).map((one) => one.id as string))
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
    update(id, { translate: add(one.translate, delta.translate, '위치'), rotate: add(one.rotate, delta.rotate, '회전') })
    setDragNote(skipped.length > 0 ? `${skipped.join(', ')}은(는) 수식으로 연결되어 있어 드래그로 변경하지 않았습니다. 편집 창에서 변수를 수정하십시오.` : null)
  }

  /** 다른 구성품의 면에 얹는다 — 서버가 경계 상자로 translate 를 계산한다(「지그 윗면에 부품 바닥을」). */
  async function placeOn(id: string, onto: string, face: string, offset: number) {
    try {
      const got = await cadApi.place(value, { mover: id, onto, face, offset, align: 'center' })
      update(id, { translate: got.translate })
      setDragNote(null)
    } catch (caught) {
      setDragNote(caught instanceof Error ? caught.message : '배치하지 못했습니다.')
    }
  }

  function update(id: string, patch: Partial<Placed>) {
    // 이름이 바뀌면 그것을 상대로 건 구속도 따라간다.
    const renamed = patch.id && patch.id !== id ? patch.id : null
    put(
      placed.map((one) => {
        const next = one.id === id ? { ...one, ...patch } : one
        if (!renamed || !next.mates) return next
        return { ...next, mates: next.mates.map((mate) => (mate.to === id ? { ...mate, to: renamed } : mate)) }
      }),
      renamed ? { from: id, to: renamed } : undefined,
    )
  }

  function remove(id: string) {
    // 뺀 것을 상대로 건 구속은 함께 뺀다 — 남기면 「앞에 없는 피처」 로 도면이 깨진다.
    put(placed.filter((other) => other.id !== id).map((one) => (one.mates?.some((mate) => mate.to === id) ? { ...one, mates: one.mates.filter((mate) => mate.to !== id) } : one)))
    if (selected === id) setSelected(null)
    if (editing === id) closeEditor()
  }

  function closeEditor() {
    setEditing(null)
    setDraft(null)
    setPicking(null)
    setPickNote(null)
  }

  /** 구속을 고르는 중에 3D 의 면을 눌렀다 — 서버가 그 면을 질의로 바꿔 준다. */
  async function pickedFace(face: MeshFace) {
    if (!editing || !draft || !picking) return
    const before = placed.slice(0, placed.findIndex((one) => one.id === editing)).map((one) => one.id)
    if (picking === 'this' && face.part !== editing) {
      setPickNote('이 구성품의 면을 클릭하십시오.')
      return
    }
    if (picking === 'to' && (!face.part || !before.includes(face.part))) {
      setPickNote(face.part === editing ? '상대는 다른 구성품이어야 합니다.' : '구속은 먼저 배치된 구성품(목록에서 위에 있는 항목)에만 적용할 수 있습니다.')
      return
    }
    try {
      const got = await cadApi.matePick(value, { node: editing, side: picking, target: picking === 'to' ? face.part : undefined, point: face.center })
      setPickNote(null)
      if (picking === 'this') {
        setDraft({ ...draft, this: got.select })
        setPicking(draft.to ? null : 'to')
      } else {
        setDraft({ ...draft, to: face.part, select: got.select })
        setPicking(null)
      }
    } catch (caught) {
      setPickNote(caught instanceof Error ? caught.message : '선택하지 못했습니다.')
    }
  }

  const editingNode = placed.find((one) => one.id === editing) ?? null
  /**
   * 3D 는 **남은 높이를 다 쓴다.** `h-[520px]` 로 굳혀 두면 큰 화면에서는 아래가 남고 작은
   * 화면에서는 페이지가 스크롤된다 — 둘 다 조립을 좁게 만든다.
   */
  const fill = useFillHeight<HTMLDivElement>({
    // 바닥값은 이 자리가 원래 쓰던 높이 — 낮게 잡으면 「채우기」 가 오히려 줄인다
    // (`RecipeEditor` 의 같은 자리 참고).
    min: 520,
    // 뷰 아래에 문제 목록과 겹침 보고가 붙는다 — 그만큼 남겨 둔다.
    gap: 16,
    deps: [total, problems.length, mesh !== null, selected],
  })

  return (
    <div className="grid gap-3 lg:grid-cols-12">
      {/* 왼쪽 — 구성(놓인 것들) · 가져올 것들 · 변수 */}
      <div className="space-y-3 lg:col-span-3">
        <div className="rounded-md border">
          <p className="bg-muted/40 border-b px-2 py-1 text-xs font-medium">구성 {total > 0 && `(${total})`}</p>
          {total === 0 ? (
            <p className="text-muted-foreground p-2 text-xs">아직 구성품이 없습니다. 아래 ‘가져오기’에서 부품 또는 지그를 선택하십시오.</p>
          ) : placed.length === 0 ? null : (
            <>
              {/* **여기서 고치는 것은 자리뿐이다.** 모양을 고치러 온 사람이 「편집」 을
                  눌렀다가 자리 · 회전만 나와 막히는 자리라, 어디로 가야 하는지 적어 둔다. */}
              <p className="text-muted-foreground border-b px-2 py-1 text-[11px]">
                여기서는 <b>위치, 회전, 치수 덮어쓰기</b>만 수정합니다. 형상 자체는 원본
                도면에서 수정하십시오. 원본 도면은 행 끝의 <ExternalLink className="inline size-3" /> 아이콘으로 엽니다.
              </p>
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
                        title="위치, 회전, 치수 덮어쓰기를 편집합니다."
                        onClick={() => {
                          setSelected(one.id)
                          setEditing(one.id)
                          setDraft(null)
                          setPicking(null)
                        }}
                      >
                        <Pencil className="size-3.5" />
                      </button>
                      {/* **원본으로 가는 길.** 여기서 고치는 것은 「어디에 놓나」 뿐이고,
                          모양 자체는 가져온 도면의 것이다 — 그 도면이 어디 있는지 모르면
                          사용자는 조립 화면에서 모양을 고치려다 막힌다. 새 탭으로 연다:
                          여기 고치던 배치를 잃지 않게. */}
                      {sourceLink(one.source) && (
                        <a
                          className="text-muted-foreground hover:text-foreground rounded p-1"
                          href={sourceLink(one.source)!}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`${one.label ?? one.id} 원본 열기`}
                          title="원본 도면을 새 탭에서 엽니다. 형상은 원본 도면에서 수정하십시오."
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExternalLink className="size-3.5" />
                        </a>
                      )}
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-destructive rounded p-1"
                        aria-label={`${one.label ?? one.id} 제거`}
                        onClick={() => remove(one.id)}
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </span>
                  </li>
                )
              })}
            </ul>
            </>
          )}
          {/* **조립 안에서 직접 그린 것** — 고치지는 못하지만 보여는 준다. 안 보이면 「구성」 은
              하나인데 시뮬레이션 조건에는 파트가 열이 되어, 어느 쪽이 맞는지 모른다. */}
          {drawn.length > 0 && (
            <>
              <p className="text-muted-foreground border-y px-2 py-1 text-[11px]">
                <b>조립 안에서 직접 그린 형상 ({drawn.length})</b> — 이 화면에서는 수정할 수 없으며, 구성품을
                바꾸어도 그대로 유지됩니다. 형상을 고치려면 부품 작업으로 따로 그린 후 ‘가져오기’로 배치하십시오.
              </p>
              <ul className="p-1" aria-label="직접 그린 형상">
                {drawn.map((id) => (
                  <li key={id} className="flex items-center gap-1.5 rounded px-1.5 py-1 text-sm">
                    <span className="size-2.5 shrink-0 rounded-full" style={{ background: cssColor(partColors[id]) }} aria-hidden />
                    <span className="min-w-0 flex-1 truncate" title={id}>
                      {id}
                    </span>
                    <Badge variant="secondary" className="shrink-0 text-[10px]">
                      직접 그림
                    </Badge>
                  </li>
                ))}
              </ul>
            </>
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

        <ParamsPanel value={value} onChange={(next) => emit(() => next)} conditions={conditions} />
      </div>

      {/* 가운데 — 3D. 가져오면 여기 나타나고, 편집 창에서 고치는 대로 따라온다. */}
      <div className="space-y-2 lg:col-span-9">
        <p className="text-muted-foreground text-xs">
          {drawing
            ? '계산 중…'
            : total === 0
              ? '가져온 부품과 지그가 여기에 표시됩니다.'
              : problems.length > 0
                ? '수정이 필요한 항목이 있습니다.'
                : selected
                  ? '선택한 구성품에 핸들이 표시되었습니다. 화살표를 드래그하여 이동(0.5 mm 단위)하거나 고리를 드래그하여 회전(5° 단위)합니다. 목록에서 다시 클릭하면 선택이 해제됩니다.'
                  : '드래그하여 회전하고, 마우스 휠로 확대합니다. 목록에서 선택하면 해당 구성품이 강조되고 핸들이 표시됩니다.'}
        </p>
        {selected && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">핸들</span>
            {(
              [
                { value: 'translate', label: '이동' },
                { value: 'rotate', label: '회전' },
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
        {/* 재는 자리는 **뷰어 바로 위**다 — 위의 안내 줄까지 포함해 재면 그만큼 넘친다. */}
        <div ref={fill.ref} style={fill.style}>
        {mesh ? (
          <Suspense fallback={<Skeleton className="h-full w-full" />}>
            <PickViewer
              mesh={mesh}
              mode={picking ? 'face' : 'none'}
              onPickFace={(face) => void pickedFace(face)}
              partColors={partColors}
              emphasis={picking === 'to' ? null : selected}
              dragPart={picking ? null : selected}
              dragMode={dragMode}
              onMoved={moved}
              className="h-full w-full rounded-md border"
            />
          </Suspense>
        ) : (
          <div className="text-muted-foreground flex h-full items-center justify-center rounded-md border border-dashed text-sm">
            {total === 0 ? '왼쪽 ‘가져오기’에서 부품 또는 지그를 클릭하십시오.' : problems.length > 0 ? '도면 오류가 해결되면 여기에 표시됩니다.' : '계산 중…'}
          </div>
        )}
        </div>
        {problems.length > 0 && (
          <ul className="text-destructive list-disc pl-5 text-xs">
            {problems.map((one) => (
              <li key={one}>{one}</li>
            ))}
          </ul>
        )}
        {/* 겹침 — 서버는 겹친 채로도 저장하니 여기서 보여 줘야 한다. */}
        {mesh && interference && total > 1 && (
          <div className="flex flex-wrap items-center gap-2 text-xs" role="status">
            <StatusBadge kind="interference" value={interference.ok ? 'ok' : 'bad'} />
            {interference.ok ? (
              <span className="text-muted-foreground">구성품 {interference.parts.length}개, {interference.checked_pairs}쌍을 검사했습니다. 간섭이 없습니다.</span>
            ) : (
              <span className="text-destructive">
                간섭:{' '}
                {interference.items
                  .filter((one) => !one.ok)
                  .map((one) => `${one.a} × ${one.b} ${one.volume.toLocaleString()} mm³`)
                  .join(', ')}
                . 편집 창에서 위치를 조정하십시오.
              </span>
            )}
          </div>
        )}
        <ErrorNotice error={error} />
      </div>

      {/* 편집 창 — 3D 를 가리지 않게 오른쪽에 붙고(모달 아님), 고치는 대로 3D 가 따라온다. */}
      <Dialog open={editingNode !== null} modal={false} onOpenChange={(open) => !open && closeEditor()}>
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
                <DialogDescription>수정 사항은 3D 화면에 즉시 반영됩니다. 입력란의 fx로 조립 변수를 연결할 수 있습니다.</DialogDescription>
              </DialogHeader>
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground w-12 text-xs">이름</span>
                  <Input
                    value={editingNode.id}
                    onChange={(event) => {
                      const next = event.target.value
                      // 조립 안에서 그린 노드와도 겹치면 안 된다 — id 가 둘이면 레시피가 깨진다.
                      if (!next || nodesOf(value).some((other) => other.id === next && other.id !== editingNode.id)) return
                      update(editingNode.id, { id: next })
                      setEditing(next)
                      setSelected(next)
                    }}
                    className="h-7 flex-1 font-mono text-xs"
                    aria-label={`${editingNode.label ?? editingNode.id} 이름`}
                  />
                </div>
                <div>
                  <p className="text-muted-foreground mb-1 text-xs">위치 (mm)</p>
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
                <MatesPanel
                  node={editingNode}
                  earlier={placed.slice(0, placed.findIndex((one) => one.id === editingNode.id))}
                  mates={editingNode.mates ?? []}
                  params={params}
                  onCreateParam={createParam}
                  onChange={(next) => update(editingNode.id, { mates: next })}
                  draft={draft}
                  onDraft={setDraft}
                  picking={picking}
                  onPicking={(next) => {
                    setPicking(next)
                    setPickNote(null)
                  }}
                  placement={summary?.nodes.find((one) => one.id === editingNode.id)?.placement}
                  note={pickNote}
                />
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
      <p className="text-muted-foreground mb-1 text-xs">다른 구성품의 면에 배치</p>
      <div className="flex flex-wrap items-center gap-1 text-xs">
        <select value={target} onChange={(e) => setOnto(e.target.value)} className="h-7 rounded-md border bg-background px-1" aria-label={`${node.label ?? node.id}을(를) 배치할 구성품`}>
          {others.map((one) => (
            <option key={one.id} value={one.id}>
              {one.label || one.id}
            </option>
          ))}
        </select>
        <span className="text-muted-foreground">의</span>
        <select value={face} onChange={(e) => setFace(e.target.value)} className="h-7 rounded-md border bg-background px-1" aria-label="대상 면">
          <option value="top">윗면</option>
          <option value="bottom">아랫면</option>
          <option value="+x">+X 면</option>
          <option value="-x">-X 면</option>
          <option value="+y">+Y 면</option>
          <option value="-y">-Y 면</option>
        </select>
        <span className="text-muted-foreground">에 간극</span>
        <Input type="number" step={0.5} value={offset} onChange={(e) => setOffset(e.target.value)} className="h-7 w-16 text-xs" aria-label="간극 (mm)" />
        <Button size="sm" type="button" className="h-7 px-2 text-xs" onClick={() => onPlace(target, face, Number(offset) || 0)}>
          배치
        </Button>
      </div>
      <p className="text-muted-foreground mt-1 text-[11px]">경계 상자를 기준으로 배치합니다. 접촉면이 평면이면 정확하고, 곡면이면 근삿값입니다. 나머지 두 축은 중심을 맞춥니다.</p>
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
              aria-label={`${key} 덮어쓰기 제거`}
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
            placeholder="가져온 도면의 변수 이름 (예: 두께)"
            className="h-7 flex-1 font-mono text-xs"
            aria-label={`${node.label ?? node.id} 덮어쓸 변수 이름`}
          />
          <Button size="sm" type="submit" className="h-7 px-2 text-xs" disabled={!name.trim()}>
            추가
          </Button>
        </form>
      </div>
    </div>
  )
}
