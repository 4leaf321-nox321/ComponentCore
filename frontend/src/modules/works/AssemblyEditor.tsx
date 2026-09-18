/**
 * 조립 — 부품과 지그를 **가져다 서로 위치시킨다.**
 *
 * 조립은 그리는 것이 아니라 **놓는 것**이다. 그래서 화면이 다르다: 왼쪽은 가져올 것들(내 도면 ·
 * 카탈로그), 오른쪽은 놓인 것들과 3D. 가져온 것은 STEP 이 아니라 **살아 있는 레시피**라,
 * 그 치수에 조립의 변수를 물릴 수 있다(`fx`) — 그래야 조립을 실험계획으로 훑는 뜻이 있다.
 */

import { Boxes, Layers, Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { NumberField } from '@/modules/cad/NumberField'
import { ParamsPanel } from '@/modules/cad/ParamsPanel'
import { jigsApi } from '@/modules/jigs/api'
import { partsApi } from '@/modules/parts/api'
import { useRecipeEmit } from '@/modules/cad/useRecipeEmit'
import { worksApi } from '@/modules/works/api'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'

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
  const [selected, setSelected] = useState<string | null>(null)
  const params = (value.params ?? {}) as Record<string, number>


  const works = useResource(() => worksApi.list(0, 100), [])
  const parts = useResource(() => partsApi.list(0, 100), [])
  const jigs = useResource(() => jigsApi.list({ limit: 100 }), [])

  const emit = useRecipeEmit(value, onChange)

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

  function update(id: string, patch: Partial<Placed>) {
    put(placed.map((one) => (one.id === id ? { ...one, ...patch } : one)))
  }

  return (
    <div className="grid gap-3 lg:grid-cols-12">
      {/* 왼쪽 — 가져올 것들 */}
      <div className="space-y-3 lg:col-span-3">
        <ParamsPanel value={value} onChange={(next) => emit(() => next)} />
        <div className="rounded-md border">
          <p className="bg-muted/40 border-b px-2 py-1 text-xs font-medium">가져오기</p>
          <div className="max-h-80 space-y-3 overflow-y-auto p-2">
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
      </div>

      {/* 오른쪽 — 놓인 것들 */}
      <div className="space-y-3 lg:col-span-9">
        {placed.length === 0 ? (
          <div className="text-muted-foreground rounded-md border border-dashed p-6 text-sm">
            왼쪽에서 부품이나 지그를 <b>+</b> 로 가져오세요. 가져온 것은 살아 있는 도면이라, 그 치수를 조립의 변수로 움직일 수 있습니다.
          </div>
        ) : (
          <div className="space-y-2">
            {placed.map((one) => {
              const isCurrent = one.id === selected
              return (
                <div key={one.id} className={`rounded-md border p-2 ${isCurrent ? 'border-primary' : ''}`}>
                  <div className="flex items-center gap-2">
                    <button type="button" className="text-left text-sm font-medium" onClick={() => setSelected(isCurrent ? null : one.id)}>
                      {one.label || one.id}
                    </button>
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {one.source.split(':')[0]}
                    </Badge>
                    <Input
                      value={one.id}
                      onChange={(event) => update(one.id, { id: event.target.value })}
                      className="ml-auto h-7 w-32 font-mono text-xs"
                      aria-label={`${one.label ?? one.id} 이름`}
                    />
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-destructive rounded p-1"
                      aria-label={`${one.label ?? one.id} 빼기`}
                      onClick={() => put(placed.filter((other) => other.id !== one.id))}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>

                  {isCurrent && (
                    <div className="mt-2 grid gap-3 sm:grid-cols-2">
                      <div>
                        <p className="text-muted-foreground mb-1 text-xs">자리 (mm)</p>
                        <div className="grid grid-cols-3 gap-1">
                          {AXES.map((axis, index) => (
                            <div key={axis} className="flex items-center gap-1">
                              <span className="text-muted-foreground w-3 text-xs">{axis}</span>
                              <NumberField
                                params={params}
                                onCreateParam={createParam}
                                aria-label={`${one.label ?? one.id} ${axis}`}
                                value={(one.translate ?? [0, 0, 0])[index]}
                                onChange={(next) => {
                                  const list = [...(one.translate ?? [0, 0, 0])]
                                  list[index] = next ?? 0
                                  update(one.id, { translate: list })
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
                                aria-label={`${one.label ?? one.id} 회전 ${axis}`}
                                value={(one.rotate ?? [0, 0, 0])[index]}
                                onChange={(next) => {
                                  const list = [...(one.rotate ?? [0, 0, 0])]
                                  list[index] = next ?? 0
                                  update(one.id, { rotate: list })
                                }}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                      <ComponentParams
                        node={one}
                        params={params}
                        onCreateParam={createParam}
                        onChange={(next) => update(one.id, { params: next })}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
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
    <div className="sm:col-span-2">
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
