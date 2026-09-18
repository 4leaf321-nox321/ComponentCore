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
import { MeasurePanel, measureMarks } from '@/modules/cad/MeasurePanel'
import { NodeForm } from '@/modules/cad/NodeForm'
import { OP_BY_NAME, OP_SPECS, makeNode, nodesOf, referencesOf } from '@/modules/cad/recipeSpec'
import type { RecipeNode } from '@/modules/cad/recipeSpec'
import { SketchCanvas } from '@/modules/cad/SketchCanvas'
import type { SketchShape } from '@/modules/cad/SketchCanvas'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import type { MeasurePick, MeshData, MeshEdge, MeshFace, PickMode } from '@/shared/viewer/PickViewer'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
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
  header,
}: {
  value: Recipe
  onChange: (recipe: Recipe) => void
  /** 편집기 위 오른쪽 — 저장 · 내려받기 같은 단추를 호출부가 준다. */
  actions?: React.ReactNode
  /** 툴바 왼쪽 — 템플릿 고르기 같은 것. 전체 화면에서도 함께 나온다. */
  header?: React.ReactNode
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
  /** 면을 골라 어디에 쓰나 — 새 스케치 · 쉘의 open · 구멍의 plane. */
  const [faceTarget, setFaceTarget] = useState<'sketch' | 'shell-open' | 'hole-plane'>('sketch')
  const [measures, setMeasures] = useState<MeasurePick[]>([])
  const [fullscreen, setFullscreen] = useState(false)
  const frame = useRef<HTMLDivElement | null>(null)
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

  function onFacePicked(face: MeshFace) {
    if (faceTarget === 'shell-open' && selected?.op === 'shell') {
      const current = isNear(selected.open) ? (selected.open as { near: number[][] }) : { near: [] }
      const same = (p: number[]) => Math.hypot(p[0] - face.center[0], p[1] - face.center[1], p[2] - face.center[2]) <= 0.5
      const near = current.near.some(same) ? current.near.filter((p) => !same(p)) : [...current.near, face.center]
      updateNode({ ...selected, open: { near, tolerance: 1 } })
      return
    }
    if (faceTarget === 'hole-plane' && selected?.op === 'hole') {
      updateNode({ ...selected, plane: { name: 'XY', origin: face.center, normal: face.normal } })
      setPickMode('none')
      setFaceTarget('sketch')
      setEditing(true)
      return
    }
    const made = makeNode('sketch', nodes)
    made.label = '면 위 스케치'
    made.plane = { name: 'XY', origin: face.center, normal: face.normal }
    replaceNodes([...nodes, made], null)
    setSelectedId(made.id)
    setPickMode('none')
    setEditing(true)
  }

  /** 폼에서 「3D 에서 면 고르기」 — 모달을 닫고 3D 로 넘긴다. */
  function pickFacesFor(fieldKey: string) {
    setFaceTarget(fieldKey === 'plane' ? 'hole-plane' : 'shell-open')
    setPickMode('face')
    setEditing(false)
  }

  // --- 전체 화면 — 브라우저 밖으로(Fullscreen API). Esc 로 나오면 상태도 따라온다. ------------

  useEffect(() => {
    const sync = () => setFullscreen(document.fullscreenElement === frame.current && frame.current !== null)
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])

  async function toggleFullscreen() {
    if (document.fullscreenElement) {
      await document.exitFullscreen()
      return
    }
    try {
      await frame.current?.requestFullscreen()
    } catch {
      setFullscreen((v) => !v) // 브라우저가 막으면 화면 안에서라도 덮는다
    }
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

  const viewerHeight = fullscreen ? 'h-[calc(100vh-7.5rem)]' : 'h-[600px]'

  return (
    <div
      ref={frame}
      className={
        fullscreen
          ? 'bg-background fixed inset-0 z-50 flex flex-col gap-2 overflow-hidden p-3'
          : 'space-y-2'
      }
    >
      {/* 툴바 — 피처를 종류별로 가로로. 드롭다운 하나에 열여섯을 넣으면 매번 찾는다. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {header}
        {GROUPS.map((group) => (
          <div key={group} className="flex items-center gap-0.5 rounded-md border px-1 py-0.5">
            <span className="text-muted-foreground px-1 text-[10px]">{group}</span>
            {OP_SPECS.filter((o) => o.group === group && o.op !== 'import_step').map((o) => (
              <Button key={o.op} size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => addNode(o.op)} title={o.help}>
                {o.short ?? o.label}
              </Button>
            ))}
          </div>
        ))}
        <div className="flex items-center gap-0.5 rounded-md border px-1 py-0.5">
          <span className="text-muted-foreground px-1 text-[10px]">3D</span>
          <Button
            size="sm"
            variant={pickMode === 'face' && faceTarget === 'sketch' ? 'default' : 'ghost'}
            className="h-7 px-2 text-xs"
            onClick={() => {
              setFaceTarget('sketch')
              setPickMode(pickMode === 'face' ? 'none' : 'face')
            }}
            disabled={!mesh}
          >
            면에 스케치
          </Button>
          <Button
            size="sm"
            variant={pickMode === 'measure' ? 'default' : 'ghost'}
            className="h-7 px-2 text-xs"
            onClick={() => setPickMode(pickMode === 'measure' ? 'none' : 'measure')}
            disabled={!mesh}
          >
            측정
          </Button>
          <Button size="sm" variant={fullscreen ? 'default' : 'ghost'} className="h-7 px-2 text-xs" onClick={() => void toggleFullscreen()}>
            {fullscreen ? '전체 화면 끝' : '전체 화면'}
          </Button>
          <Button size="sm" variant={mode === 'json' ? 'default' : 'ghost'} className="h-7 px-2 text-xs" onClick={() => (mode === 'json' ? applyJson() : setMode('json'))}>
            {mode === 'json' ? 'JSON 적용' : 'JSON'}
          </Button>
          {mode === 'json' && (
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setMode('form')}>
              취소
            </Button>
          )}
        </div>
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
        <div className={`grid gap-3 lg:grid-cols-12 ${fullscreen ? 'min-h-0 flex-1' : ''}`}>
          {/* 피처 트리 — 누르면 모달에서 고친다 */}
          <div className={`lg:col-span-3 ${fullscreen ? 'max-h-[calc(100vh-7rem)] overflow-y-auto' : ''}`}>
            {nodes.length === 0 ? (
              <div className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
                빈 레시피입니다. 위 툴바에서 「스케치」 부터 누르세요. 스케치를 그리고 「돌출」 을 더하면
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
            <p className="text-muted-foreground mb-1 text-xs">
              {pickMode === 'face'
                ? faceTarget === 'sketch'
                  ? '3D 에서 면을 누르면 그 면 위에 스케치가 생깁니다.'
                  : faceTarget === 'hole-plane'
                    ? '구멍을 뚫을 면을 누르세요.'
                    : '뚫을 면을 누르세요. 다시 누르면 뺍니다. 끝나면 피처를 다시 열어 확인하세요.'
                : pickMode === 'edge'
                  ? `엣지를 눌러 고릅니다 (${(selected?.edges as { near?: number[][] })?.near?.length ?? 0} 개). 다시 누르면 뺍니다.`
                  : pickMode === 'measure'
                    ? '측정: 꼭짓점 근처를 누르면 점, 엣지를 누르면 길이, 면을 누르면 넓이.'
                    : '끌어서 돌리고, 굴려서 확대합니다. 왼쪽 피처를 누르면 고칩니다.'}
              {edgePicking && pickMode === 'edge' && (
                <button type="button" className="ml-2 underline" onClick={() => setEditing(true)}>
                  피처 열기
                </button>
              )}
            </p>
            {pickMode === 'measure' && (
              <div className="mb-1">
                <MeasurePanel picks={measures} onClear={() => setMeasures([])} onUndo={() => setMeasures((m) => m.slice(0, -1))} />
              </div>
            )}
            {mesh ? (
              <Suspense fallback={<Skeleton className={`${viewerHeight} w-full`} />}>
                <PickViewer
                  mesh={mesh}
                  mode={pickMode}
                  highlightEdgesNear={isNear(selected?.edges) ? (selected!.edges as { near: number[][] }).near : undefined}
                  onPickFace={onFacePicked}
                  onPickEdge={toggleEdge}
                  onMeasure={(pick) => setMeasures((m) => [...m, pick])}
                  measureMarks={pickMode === 'measure' ? measureMarks(measures) : undefined}
                  className={`${viewerHeight} w-full rounded-md border`}
                />
              </Suspense>
            ) : (
              <div className={`text-muted-foreground flex ${viewerHeight} items-center justify-center rounded-md border border-dashed text-sm`}>
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
                <NodeForm node={selected} nodes={nodes} onChange={updateNode} onPickFaces={pickFacesFor} />
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
