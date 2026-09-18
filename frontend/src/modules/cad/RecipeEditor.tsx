/**
 * 레시피 편집기 — 피처 트리(왼쪽) · 3D(넓게). 피처를 누르면 **모달**에서 칸 · 스케치 캔버스를
 * 고친다 — 도면이 넓어야 보이고, 칸은 잠깐만 필요하다.
 *
 * 계약: 레시피 in → 레시피 out. 칸을 고칠 때마다 서버에 모양을 묻고(`check`), 맞으면 자동으로
 * 미리보기를 다시 그린다. AI(4단계)도 같은 레시피를 만지므로 이 화면이 그 결과를 그대로 받는다.
 * JSON 으로 보고 싶은 사람을 위해 「JSON」 토글을 남긴다 — 편집기가 못 표현하는 것은 없어야 하지만,
 * 붙여 넣기와 대량 수정에는 글자가 빠르다.
 */

import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { cadApi } from '@/modules/cad/api'
import type { Recipe, RecipeSummary } from '@/modules/cad/api'
import { NodeForm } from '@/modules/cad/NodeForm'
import { OP_BY_NAME, OP_SPECS, makeNode, nodesOf, referencesOf } from '@/modules/cad/recipeSpec'
import type { RecipeNode } from '@/modules/cad/recipeSpec'
import { SketchCanvas } from '@/modules/cad/SketchCanvas'
import type { SketchShape } from '@/modules/cad/SketchCanvas'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import type { MeshData, MeshEdge, MeshFace, PickMode } from '@/shared/viewer/PickViewer'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Textarea } from '@/shared/components/ui/textarea'

const PickViewer = lazy(() => import('@/shared/viewer/PickViewer'))

export function pretty(recipe: Recipe): string {
  return JSON.stringify(recipe, null, 2)
}

const GROUPS = ['스케치', '입체', '조합', '마감', '배치'] as const

export function RecipeEditor({
  value,
  onChange,
  actions,
}: {
  value: Recipe
  onChange: (recipe: Recipe) => void
  /** 편집기 위 오른쪽 — 저장 · 내려받기 같은 단추를 호출부가 준다. */
  actions?: React.ReactNode
}) {
  const nodes = useMemo(() => nodesOf(value), [value])
  const [selectedId, setSelectedId] = useState<string | null>(nodes[nodes.length - 1]?.id ?? null)
  const [editing, setEditing] = useState(false)
  const [mode, setMode] = useState<'form' | 'json'>('form')
  const [text, setText] = useState(() => pretty(value))
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [summary, setSummary] = useState<RecipeSummary | null>(null)
  const [mesh, setMesh] = useState<MeshData | null>(null)
  const [pickMode, setPickMode] = useState<PickMode>('none')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [drawing, setDrawing] = useState(false)
  const lastDrawn = useRef<string>('')

  const selected = nodes.find((n) => n.id === selectedId) ?? null

  // --- 레시피 바꾸기 ------------------------------------------------------------

  const replaceNodes = useCallback(
    (next: RecipeNode[], result?: string | null) => {
      onChange({ ...value, nodes: next, result: result === undefined ? value.result : result })
    },
    [onChange, value],
  )

  function updateNode(next: RecipeNode) {
    const before = nodes.find((n) => n.id === selectedId)
    let list = nodes.map((n) => (n.id === selectedId ? next : n))
    // id 를 바꿨으면 그것을 가리키는 뒤 피처도 따라 바꾼다.
    if (before && before.id !== next.id) {
      list = list.map((n) => renameRef(n, before.id, next.id))
      setSelectedId(next.id)
    }
    replaceNodes(list, value.result === before?.id ? next.id : undefined)
  }

  function addNode(op: string) {
    const made = makeNode(op, nodes)
    // 참조 칸은 바로 앞의 알맞은 피처로 미리 채운다 — 「돌출」 을 누르면 방금 그린 스케치가 들어간다.
    const spec = OP_BY_NAME[op]
    for (const field of spec.fields) {
      if (field.kind === 'ref') {
        const candidate = [...nodes].reverse().find((n) => field.refKind === 'any' || (field.refKind === 'sketch') === (n.op === 'sketch'))
        if (candidate) made[field.key] = candidate.id
      }
    }
    replaceNodes([...nodes, made], null)
    setSelectedId(made.id)
    setEditing(true)
  }

  function removeNode(id: string) {
    const dependents = nodes.filter((n) => referencesOf(n).includes(id))
    if (dependents.length > 0 && !window.confirm(`${dependents.map((d) => d.id).join(', ')} 이(가) 이 피처를 씁니다. 함께 지웁니까?`)) return
    const doomed = new Set([id, ...closure(id, nodes)])
    const list = nodes.filter((n) => !doomed.has(n.id))
    replaceNodes(list, value.result && doomed.has(value.result) ? null : undefined)
    setSelectedId(list[list.length - 1]?.id ?? null)
    setEditing(false)
  }

  function moveNode(id: string, dir: -1 | 1) {
    const i = nodes.findIndex((n) => n.id === id)
    const j = i + dir
    if (i < 0 || j < 0 || j >= nodes.length) return
    const list = [...nodes]
    ;[list[i], list[j]] = [list[j], list[i]]
    replaceNodes(list)
  }

  // --- 검증 · 미리보기 ----------------------------------------------------------

  useEffect(() => {
    if (mode === 'json') return
    setText(pretty(value))
  }, [value, mode])

  useEffect(() => {
    // 빈 레시피는 검증할 것이 아니다 — 「적어도 1개」 는 오류가 아니라 아직 시작 전이다.
    if (nodesOf(value).length === 0) {
      setProblems([])
      setSummary(null)
      setMesh(null)
      lastDrawn.current = ''
      return
    }
    const key = JSON.stringify(value)
    const timer = setTimeout(async () => {
      try {
        const result = await cadApi.check(value)
        setProblems(result.problems)
        if (!result.ok || key === lastDrawn.current) return
        setDrawing(true)
        setError(null)
        try {
          const made = await cadApi.mesh(value)
          lastDrawn.current = key
          setSummary(made.summary)
          setMesh(made.mesh)
        } catch (caught) {
          setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
        } finally {
          setDrawing(false)
        }
      } catch {
        // 서버가 잠깐 안 닿는다 — 다음 변경에서 다시.
      }
    }, 500)
    return () => clearTimeout(timer)
  }, [value])

  // --- 3D 에서 고르기 -------------------------------------------------------------

  const edgePicking = selected !== null && (selected.op === 'fillet' || selected.op === 'chamfer') && isNear(selected.edges)
  useEffect(() => {
    setPickMode(edgePicking ? 'edge' : pickMode === 'edge' ? 'none' : pickMode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edgePicking])

  function sketchOnFace(face: MeshFace) {
    const made = makeNode('sketch', nodes)
    made.label = '면 위 스케치'
    made.plane = { name: 'XY', origin: face.center, normal: face.normal }
    replaceNodes([...nodes, made], null)
    setSelectedId(made.id)
    setPickMode('none')
    setEditing(true)
  }

  function toggleEdge(edge: MeshEdge) {
    if (!selected || !isNear(selected.edges)) return
    const current = selected.edges as { near: number[][]; tolerance?: number }
    const same = (p: number[]) => Math.hypot(p[0] - edge.midpoint[0], p[1] - edge.midpoint[1], p[2] - edge.midpoint[2]) <= 0.5
    const near = current.near.some(same) ? current.near.filter((p) => !same(p)) : [...current.near, edge.midpoint]
    updateNode({ ...selected, edges: { near, tolerance: current.tolerance ?? 1 } })
  }

  function applyJson() {
    try {
      const parsed = JSON.parse(text) as Recipe
      setJsonError(null)
      onChange(parsed)
      setMode('form')
      setSelectedId(nodesOf(parsed)[nodesOf(parsed).length - 1]?.id ?? null)
    } catch (caught) {
      setJsonError(caught instanceof Error ? caught.message : 'JSON 이 아닙니다')
    }
  }

  const valid = problems.length === 0
  const failedNode = error instanceof ApiError ? (error.details.node_id as string | undefined) : undefined

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm">+ 피처</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            {GROUPS.map((group, gi) => (
              <div key={group}>
                {gi > 0 && <DropdownMenuSeparator />}
                <DropdownMenuLabel className="text-xs">{group}</DropdownMenuLabel>
                {OP_SPECS.filter((s) => s.group === group && s.op !== 'import_step').map((s) => (
                  <DropdownMenuItem key={s.op} onClick={() => addNode(s.op)}>
                    {s.label}
                    <span className="text-muted-foreground ml-auto font-mono text-[10px]">{s.op}</span>
                  </DropdownMenuItem>
                ))}
              </div>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button size="sm" variant={mode === 'json' ? 'default' : 'outline'} onClick={() => (mode === 'json' ? applyJson() : setMode('json'))}>
          {mode === 'json' ? 'JSON 적용' : 'JSON'}
        </Button>
        {mode === 'json' && (
          <Button size="sm" variant="ghost" onClick={() => setMode('form')}>
            취소
          </Button>
        )}
        <span className="text-muted-foreground text-xs">
          {drawing ? '그리는 중…' : valid ? '미리보기가 자동으로 따라옵니다.' : '고칠 것이 있습니다.'}
        </span>
        <div className="flex-1" />
        {actions}
      </div>

      {mode === 'json' ? (
        <div className="space-y-1">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} className="min-h-[420px] font-mono text-xs" />
          {jsonError && <p className="text-destructive text-xs">JSON: {jsonError}</p>}
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-12">
          {/* 피처 트리 — 누르면 모달에서 고친다 */}
          <div className="lg:col-span-3">
            {nodes.length === 0 ? (
              <div className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
                빈 레시피입니다. 「+ 피처」 → 스케치부터 시작하세요. 스케치를 그리고 「돌출」 을 더하면
                입체가 됩니다.
              </div>
            ) : (
              <ol className="space-y-0.5">
                {nodes.map((node, i) => {
                  const spec = OP_BY_NAME[node.op]
                  const broken = problems.some((p) => p.includes(`nodes.${i}`) || p.includes(`nodes[${i}]`)) || failedNode === node.id
                  return (
                    <li key={node.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedId(node.id)
                          setEditing(true)
                        }}
                        className={`flex w-full items-center gap-1 rounded-md px-2 py-1 text-left text-sm ${
                          node.id === selectedId ? 'bg-accent' : 'hover:bg-accent/60'
                        } ${broken ? 'text-destructive' : ''}`}
                      >
                        <span className="text-muted-foreground w-4 text-[10px]">{i + 1}</span>
                        <span className="truncate">{node.label || spec?.label || node.op}</span>
                        <span className="text-muted-foreground ml-auto font-mono text-[10px]">{node.id}</span>
                      </button>
                    </li>
                  )
                })}
              </ol>
            )}
            {value.result && value.result !== nodes[nodes.length - 1]?.id && (
              <p className="text-muted-foreground mt-2 text-xs">결과 피처: {value.result}</p>
            )}
            {problems.length > 0 && (
              <ul className="text-destructive mt-2 list-inside list-disc text-xs">
                {problems.map((one) => (
                  <li key={one}>{one}</li>
                ))}
              </ul>
            )}
            <ErrorNotice error={error} className="mt-2" />
          </div>

          {/* 3D — 넓게 */}
          <div className="lg:col-span-9">
            <div className="mb-1 flex items-center gap-1">
              <Button size="sm" variant={pickMode === 'face' ? 'default' : 'outline'} onClick={() => setPickMode(pickMode === 'face' ? 'none' : 'face')} disabled={!mesh}>
                면에 스케치
              </Button>
              {edgePicking && (
                <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                  엣지 고르는 중 — 피처 열기
                </Button>
              )}
              <span className="text-muted-foreground text-xs">
                {pickMode === 'face'
                  ? '3D 에서 면을 누르면 그 면 위에 스케치가 생깁니다.'
                  : pickMode === 'edge'
                    ? `엣지를 눌러 고릅니다 (${(selected?.edges as { near?: number[][] })?.near?.length ?? 0} 개). 다시 누르면 뺍니다.`
                    : '끌어서 돌리고, 굴려서 확대합니다. 왼쪽 피처를 누르면 고칩니다.'}
              </span>
            </div>
            {mesh ? (
              <Suspense fallback={<Skeleton className="h-[600px] w-full" />}>
                <PickViewer
                  mesh={mesh}
                  mode={pickMode}
                  highlightEdgesNear={isNear(selected?.edges) ? (selected!.edges as { near: number[][] }).near : undefined}
                  onPickFace={sketchOnFace}
                  onPickEdge={toggleEdge}
                  className="h-[600px] w-full rounded-md border"
                />
              </Suspense>
            ) : (
              <div className="text-muted-foreground flex h-[600px] items-center justify-center rounded-md border border-dashed text-sm">
                {nodes.length === 0 ? '피처를 더하면 여기에 그려집니다.' : valid ? '그리는 중…' : '레시피가 맞으면 여기에 그려집니다.'}
              </div>
            )}
            {summary?.is_sketch && (
              <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs">
                <span>아직 스케치(2D)입니다. 입체로 만들려면:</span>
                <Button size="sm" variant="outline" className="h-7" onClick={() => addNode('extrude')}>
                  돌출 더하기
                </Button>
                <Button size="sm" variant="outline" className="h-7" onClick={() => addNode('revolve')}>
                  회전 더하기
                </Button>
                <span className="text-muted-foreground">저장 · 지그는 입체여야 합니다.</span>
              </div>
            )}
            {summary && (
              <p className="text-muted-foreground mt-1 text-xs">
                {summary.bbox.size.map((v) => v.toFixed(1)).join(' × ')} mm
                {!summary.is_sketch && ` · 부피 ${summary.volume.toLocaleString()} mm³`} · 면 {summary.face_count} · 피처{' '}
                {summary.nodes.length}
              </p>
            )}
          </div>
        </div>
      )}

      {/* 피처 편집 모달 — 머리글 · 바닥글은 붙박이, 가운데만 굴러서 화면 밖으로 안 나간다(DialogContent). */}
      <Dialog open={editing && selected !== null} onOpenChange={(open) => !open && setEditing(false)}>
        <DialogContent className={selected?.op === 'sketch' ? 'sm:max-w-5xl' : 'sm:max-w-xl'}>
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle>
                  {OP_BY_NAME[selected.op]?.label ?? selected.op}{' '}
                  <span className="text-muted-foreground font-mono text-xs">{selected.id}</span>
                </DialogTitle>
                <DialogDescription>{OP_BY_NAME[selected.op]?.help}</DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                {selected.op === 'sketch' && (
                  <SketchCanvas
                    shapes={(selected.shapes as SketchShape[]) ?? []}
                    onChange={(shapes) => updateNode({ ...selected, shapes })}
                  />
                )}
                <NodeForm node={selected} nodes={nodes} onChange={updateNode} />
                {edgePicking && (
                  <p className="text-muted-foreground text-xs">
                    엣지는 3D 에서 고릅니다 — 이 창을 닫고 3D 의 엣지를 누르세요. 고른 것은 남습니다.
                  </p>
                )}
              </div>
              <DialogFooter className="sm:justify-between">
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => moveNode(selected.id, -1)}>
                    ↑ 앞으로
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => moveNode(selected.id, 1)}>
                    ↓ 뒤로
                  </Button>
                  <Button size="sm" variant="ghost" className="text-destructive" onClick={() => removeNode(selected.id)}>
                    지우기
                  </Button>
                </div>
                <Button size="sm" onClick={() => setEditing(false)}>
                  닫기
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function isNear(edges: unknown): edges is { near: number[][]; tolerance?: number } {
  return typeof edges === 'object' && edges !== null && Array.isArray((edges as { near?: unknown }).near)
}

function renameRef(node: RecipeNode, from: string, to: string): RecipeNode {
  const next: RecipeNode = { ...node }
  for (const key of ['sketch', 'target', 'source']) {
    if (next[key] === from) next[key] = to
  }
  for (const key of ['targets', 'tools']) {
    if (Array.isArray(next[key])) next[key] = (next[key] as string[]).map((v) => (v === from ? to : v))
  }
  return next
}

/** id 를 (직접이든 건너서든) 쓰는 뒤 피처 전부. */
function closure(id: string, nodes: RecipeNode[]): string[] {
  const out = new Set<string>()
  let changed = true
  while (changed) {
    changed = false
    for (const n of nodes) {
      if (out.has(n.id)) continue
      if (referencesOf(n).some((r) => r === id || out.has(r))) {
        out.add(n.id)
        changed = true
      }
    }
  }
  return [...out]
}
