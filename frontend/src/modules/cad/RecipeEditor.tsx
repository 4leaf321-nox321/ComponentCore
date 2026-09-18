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
import { LoadRecipeDialog, LoadWorkDialog } from '@/modules/cad/LoadDialogs'
import { keptLabel, MeasureDialog } from '@/modules/cad/MeasureDialog'
import type { KeptMeasure, PickKind } from '@/modules/cad/MeasureDialog'
import { measureMarks } from '@/modules/cad/measureMarks'
import { RibbonButton, RibbonGroup } from '@/modules/cad/Ribbon'
import { NodeForm } from '@/modules/cad/NodeForm'
import { allowedDrops, dropProblem, moveTo } from '@/modules/cad/reorder'
import { OP_BY_NAME, OP_SPECS, makeNode, nodesOf, referencesOf } from '@/modules/cad/recipeSpec'
import type { RecipeNode } from '@/modules/cad/recipeSpec'
import { SketchCanvas } from '@/modules/cad/SketchCanvas'
import type { SketchShape } from '@/modules/cad/SketchCanvas'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Boxes, Braces, BookmarkPlus, Download, FileAxis3d, FileUp, GripVertical, Image, FilePlus, FolderOpen, Files, Maximize2, Minimize2, Pencil, Redo2, Ruler, Save, SquareDashedMousePointer, Trash2, Undo2 } from 'lucide-react'

import { useFullscreen } from '@/shared/viewer/FullscreenFrame'
import type { MeasurePick, MeshData, MeshEdge, MeshFace, PickMode } from '@/shared/viewer/PickViewer'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { Textarea } from '@/shared/components/ui/textarea'

const PickViewer = lazy(() => import('@/shared/viewer/PickViewer'))

export function pretty(recipe: Recipe): string {
  return JSON.stringify(recipe, null, 2)
}

const GROUPS = ['스케치', '입체', '조합', '마감', '배치'] as const

/** 「파일」 탭이 부르는 것들 — 호출부(그리기 · 내 작업)가 준다. 없는 것은 단추가 안 뜬다. */
export interface FileActions {
  /** 「저장」 — 그리기에서는 내 작업으로, 내 작업에서는 새 버전으로. */
  save?: { label: string; run: () => void; disabled?: boolean }
  saveTemplate?: () => void
  /** STEP 파일에서 시작 — 고른 파일을 호출부가 올린다(작업이 생기고 그 화면으로 간다). */
  importStep?: { label: string; run: (file: File) => void; busy?: boolean }
  /** 형식별 내려받기 — 호출부가 blob 을 받아 저장한다. */
  download?: (format: 'step' | 'stl' | 'dxf' | 'svg') => void
  /** 불러온 뒤 알린다(출처 표시용). */
  onLoaded?: (label: string, source: 'template' | 'copy') => void
  /** 지금 작업 id — 작업 불러오기 목록에서 자기 자신은 뺀다. */
  currentWorkId?: string
}

export function RecipeEditor({ value, onChange, file }: { value: Recipe; onChange: (recipe: Recipe) => void; file?: FileActions }) {
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
  /** 담아 둔 측정 — 3D 에 남아 여러 곳을 한 화면에서 비교한다. */
  const [kept, setKept] = useState<KeptMeasure[]>([])
  const [measureKinds, setMeasureKinds] = useState<Set<PickKind>>(new Set<PickKind>(['point', 'edge', 'face']))
  const { frame, active: fullscreen, toggle: toggleFullscreen } = useFullscreen()
  const [tab, setTab] = useState<string>(nodes.length === 0 ? 'file' : '스케치')
  const [loading, setLoading] = useState<'recipe' | 'work' | null>(null)
  /** 끌고 있는 피처의 자리 · 놓을 수 있는 칸들 · 지금 가리키는 칸 · 막힌 이유. */
  const [drag, setDrag] = useState<{ from: number; allowed: Set<number>; at: number | null; refused: string | null } | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [drawing, setDrawing] = useState(false)
  const lastDrawn = useRef<string>('')
  const stepInput = useRef<HTMLInputElement | null>(null)

  const selected = nodes.find((n) => n.id === selectedId) ?? null

  // --- 실행 취소 ------------------------------------------------------------------
  // value 는 호출부 것이라 여기서는 지나간 값을 쌓아 두기만 한다. 1초 안에 잇단 변화(칸에
  // 숫자를 치는 것)는 한 걸음으로 묶는다.
  const history = useRef<{ past: Recipe[]; future: Recipe[]; last: Recipe; at: number; skip: boolean }>({
    past: [],
    future: [],
    last: value,
    at: 0,
    skip: false,
  })
  const [, bump] = useState(0)
  useEffect(() => {
    const h = history.current
    if (h.last === value) return
    if (!h.skip) {
      const now = Date.now()
      if (now - h.at > 1000) h.past = [...h.past.slice(-49), h.last]
      h.future = []
      h.at = now
    }
    h.skip = false
    h.last = value
    bump((n) => n + 1)
  }, [value])
  function undo() {
    const h = history.current
    const previous = h.past.pop()
    if (!previous) return
    h.future.push(value)
    h.skip = true
    h.at = 0
    onChange(previous)
  }
  function redo() {
    const h = history.current
    const next = h.future.pop()
    if (!next) return
    h.past.push(value)
    h.skip = true
    h.at = 0
    onChange(next)
  }
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey)) return
      const target = event.target as HTMLElement | null
      if (target && target.closest('input, textarea, select, [contenteditable]')) return
      const key = event.key.toLowerCase()
      if (key === 'z' && !event.shiftKey) {
        event.preventDefault()
        undo()
      } else if (key === 'y' || (key === 'z' && event.shiftKey)) {
        event.preventDefault()
        redo()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // --- 레시피 바꾸기 ------------------------------------------------------------

  const replaceNodes = useCallback(
    (next: RecipeNode[], result?: string | null) => {
      onChange({
        ...value,
        nodes: next,
        result: result === undefined ? value.result : result,
      })
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
      if (field.kind === 'ref' && !field.optional) {
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

  /** 한 칸 옮길 수 없는 이유 — 끝이거나 선후관계가 걸리거나. 옮길 수 있으면 null. */
  function moveRefusal(id: string, dir: -1 | 1): string | null {
    const i = nodes.findIndex((n) => n.id === id)
    const j = i + dir
    if (i < 0 || j < 0 || j >= nodes.length) return dir === -1 ? '맨 앞입니다' : '맨 뒤입니다'
    // 끌어 옮기기와 같은 규칙 — 쓰는 피처가 쓰이는 피처보다 앞설 수 없다.
    return dropProblem(nodes, i, dir === 1 ? i + 2 : i - 1)
  }

  function moveNode(id: string, dir: -1 | 1) {
    if (moveRefusal(id, dir)) return
    const i = nodes.findIndex((n) => n.id === id)
    replaceNodes(moveTo(nodes, i, dir === 1 ? i + 2 : i - 1))
  }

  /** 끌어 놓기 — 놓을 수 있는 자리는 끌기 시작할 때 미리 세어 둔다(칸마다 다시 계산하지 않게). */
  function dropNode(to: number) {
    if (!drag) return
    if (!drag.allowed.has(to)) return
    replaceNodes(moveTo(nodes, drag.from, to))
    setDrag(null)
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
    if (faceTarget === 'hole-plane' && selected && OP_BY_NAME[selected.op]?.fields.some((f) => f.key === 'plane')) {
      updateNode({
        ...selected,
        plane: { name: 'XY', origin: face.center, normal: face.normal },
      })
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

  function toggleEdge(edge: MeshEdge) {
    if (!selected || !isNear(selected.edges)) return
    const current = selected.edges as { near: number[][]; tolerance?: number }
    const same = (p: number[]) => Math.hypot(p[0] - edge.midpoint[0], p[1] - edge.midpoint[1], p[2] - edge.midpoint[2]) <= 0.5
    const near = current.near.some(same) ? current.near.filter((p) => !same(p)) : [...current.near, edge.midpoint]
    updateNode({
      ...selected,
      edges: { near, tolerance: current.tolerance ?? 1 },
    })
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

  const viewerHeight = fullscreen ? 'h-[calc(100vh-11rem)]' : 'h-[600px]'

  return (
    <div ref={frame} className={fullscreen ? 'bg-background fixed inset-0 z-50 flex flex-col gap-2 overflow-hidden p-3' : 'space-y-2'}>
      {/* 리본 — 탭이 종류를 가르고 단추는 아이콘. 새 종류가 늘어도 한 줄이 넘치지 않는다. */}
      <Tabs value={tab} onValueChange={setTab}>
        <div className="flex flex-wrap items-center gap-2">
          <TabsList>
            <TabsTrigger value="file">파일</TabsTrigger>
            {GROUPS.map((group) => (
              <TabsTrigger key={group} value={group}>
                {group}
              </TabsTrigger>
            ))}
            <TabsTrigger value="view">보기 · 측정</TabsTrigger>
          </TabsList>
          <span className="text-muted-foreground text-xs">
            {drawing ? '그리는 중…' : nodes.length === 0 ? '' : valid ? '미리보기가 자동으로 따라옵니다.' : '고칠 것이 있습니다.'}
          </span>
          <div className="ml-auto flex gap-1">
            <Button size="sm" variant="outline" onClick={undo} disabled={history.current.past.length === 0} title="실행 취소 (Ctrl+Z)" aria-label="실행 취소">
              <Undo2 className="size-4" />
            </Button>
            <Button size="sm" variant="outline" onClick={redo} disabled={history.current.future.length === 0} title="다시 실행 (Ctrl+Y)" aria-label="다시 실행">
              <Redo2 className="size-4" />
            </Button>
            {/* 전체 화면은 탭이 아니라 **늘 오른쪽 위**에 — 어느 탭에 있든 한 번에 키우고 끈다. */}
            <Button size="sm" variant={fullscreen ? 'default' : 'outline'} onClick={() => void toggleFullscreen()} title={fullscreen ? '전체 화면 끝내기 (Esc)' : '전체 화면'}>
              {fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
              <span className="ml-1 hidden sm:inline">{fullscreen ? '끝내기' : '전체 화면'}</span>
            </Button>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-2 rounded-md border p-2">
          {tab === 'file' && (
            <>
              <RibbonGroup title="시작">
                <RibbonButton
                  icon={FilePlus}
                  label="새로"
                  onClick={() => {
                    if (nodes.length > 0 && !window.confirm('지금 그린 것을 지우고 빈 레시피에서 시작합니까?')) return
                    onChange({ version: 1, nodes: [] })
                    setSelectedId(null)
                    setTab('스케치')
                  }}
                />
                <RibbonButton icon={FolderOpen} label="레시피" title="레시피 불러오기 — 내장 · 저장 템플릿" onClick={() => setLoading('recipe')} />
                <RibbonButton icon={Files} label="기존 작업" title="기존 작업 불러오기" onClick={() => setLoading('work')} />
                {file?.importStep && (
                  <>
                    <input
                      ref={stepInput}
                      type="file"
                      accept=".step,.stp"
                      className="hidden"
                      onChange={(event) => {
                        const picked = event.target.files?.[0]
                        if (picked) file.importStep?.run(picked)
                        event.target.value = '' // 같은 파일을 다시 골라도 열리게
                      }}
                    />
                    <RibbonButton
                      icon={FileUp}
                      label={file.importStep.busy ? '올리는 중…' : file.importStep.label}
                      title="STEP 파일에서 시작 — 올린 형상이 레시피의 첫 피처가 됩니다"
                      disabled={file.importStep.busy}
                      onClick={() => stepInput.current?.click()}
                    />
                  </>
                )}
              </RibbonGroup>
              <RibbonGroup title="저장">
                {file?.save && <RibbonButton icon={Save} label={file.save.label} onClick={file.save.run} disabled={file.save.disabled || nodes.length === 0} />}
                {file?.saveTemplate && <RibbonButton icon={BookmarkPlus} label="템플릿" title="템플릿으로 저장" onClick={file.saveTemplate} disabled={nodes.length === 0} />}
                {file?.download && (
                  <>
                    <RibbonButton
                      icon={Download}
                      label="STEP"
                      title="STEP 받기 — 다른 CAD 로"
                      onClick={() => file.download?.('step')}
                      disabled={nodes.length === 0 || !!summary?.is_sketch}
                    />
                    <RibbonButton
                      icon={Boxes}
                      label="STL"
                      title="STL 받기 — 3D 프린터로 뽑을 때"
                      onClick={() => file.download?.('stl')}
                      disabled={nodes.length === 0 || !!summary?.is_sketch}
                    />
                    <RibbonButton
                      icon={FileAxis3d}
                      label="DXF"
                      title="DXF 받기 — 2D 도면(레이저 · 가공). 입체면 높이 절반의 단면을 낸다"
                      onClick={() => file.download?.('dxf')}
                      disabled={nodes.length === 0}
                    />
                    <RibbonButton
                      icon={Image}
                      label="SVG"
                      title="SVG 받기 — 문서에 붙이는 2D 그림"
                      onClick={() => file.download?.('svg')}
                      disabled={nodes.length === 0}
                    />
                  </>
                )}
              </RibbonGroup>
              <RibbonGroup title="고급">
                <RibbonButton
                  icon={Braces}
                  label={mode === 'json' ? 'JSON 적용' : 'JSON'}
                  active={mode === 'json'}
                  onClick={() => (mode === 'json' ? applyJson() : setMode('json'))}
                />
              </RibbonGroup>
            </>
          )}
          {GROUPS.filter((g) => g === tab).map((group) => (
            <RibbonGroup key={group}>
              {OP_SPECS.filter((o) => o.group === group && o.op !== 'import_step').map((o) => (
                <RibbonButton key={o.op} icon={o.icon} label={o.short ?? o.label} title={o.help} onClick={() => addNode(o.op)} />
              ))}
            </RibbonGroup>
          ))}
          {tab === 'view' && (
            <>
              <RibbonGroup title="3D 에서">
                <RibbonButton
                  icon={SquareDashedMousePointer}
                  label="면에 스케치"
                  active={pickMode === 'face' && faceTarget === 'sketch'}
                  disabled={!mesh}
                  onClick={() => {
                    setFaceTarget('sketch')
                    setPickMode(pickMode === 'face' ? 'none' : 'face')
                  }}
                />
                <RibbonButton
                  icon={Ruler}
                  label="측정"
                  title="거리 · 각도 · 지름 — 창이 뜬 채로 3D 를 계속 누릅니다"
                  active={pickMode === 'measure'}
                  disabled={!mesh}
                  onClick={() => setPickMode(pickMode === 'measure' ? 'none' : 'measure')}
                />
              </RibbonGroup>
            </>
          )}
        </div>
      </Tabs>

      <MeasureDialog
        open={pickMode === 'measure'}
        picks={measures}
        kept={kept}
        kinds={measureKinds}
        onKinds={setMeasureKinds}
        onUndo={() => setMeasures((m) => m.slice(0, -1))}
        onClear={() => setMeasures([])}
        onKeep={() => {
          if (measures.length === 0) return
          setKept((list) => [...list, { id: `m-${Date.now()}`, picks: measures, label: keptLabel(measures) }])
          setMeasures([])
        }}
        onDropKept={(id) => setKept((list) => list.filter((one) => one.id !== id))}
        onClose={() => setPickMode('none')}
      />

      <LoadRecipeDialog
        open={loading === 'recipe'}
        onClose={() => setLoading(null)}
        onLoad={(loaded) => {
          if (nodes.length > 0 && !window.confirm('지금 그린 것을 지우고 불러옵니까?')) return
          onChange(loaded.recipe)
          setSelectedId(nodesOf(loaded.recipe)[nodesOf(loaded.recipe).length - 1]?.id ?? null)
          setLoading(null)
          setTab('스케치')
          file?.onLoaded?.(loaded.label, loaded.source)
        }}
      />
      <LoadWorkDialog
        open={loading === 'work'}
        currentWorkId={file?.currentWorkId}
        onClose={() => setLoading(null)}
        onLoad={(loaded) => {
          if (nodes.length > 0 && !window.confirm('지금 그린 것을 지우고 불러옵니까?')) return
          onChange(loaded.recipe)
          setSelectedId(nodesOf(loaded.recipe)[nodesOf(loaded.recipe).length - 1]?.id ?? null)
          setLoading(null)
          setTab('스케치')
          file?.onLoaded?.(loaded.label, loaded.source)
        }}
      />

      {mode === 'json' ? (
        <div className="space-y-1">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} className="min-h-[420px] font-mono text-xs" />
          {jsonError && <p className="text-destructive text-xs">JSON: {jsonError}</p>}
          <div className="flex gap-1">
            <Button size="sm" onClick={applyJson}>
              JSON 적용
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode('form')}>
              취소
            </Button>
          </div>
        </div>
      ) : (
        <div className={`grid gap-3 lg:grid-cols-12 ${fullscreen ? 'min-h-0 flex-1' : ''}`}>
          {/* 피처 트리 — 누르면 모달에서 고친다 */}
          <div className={`lg:col-span-3 ${fullscreen ? 'max-h-[calc(100vh-10rem)] overflow-y-auto' : ''}`}>
            {nodes.length === 0 ? (
              <div className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
                빈 레시피입니다. 「스케치」 탭의 스케치 단추부터 누르세요. 「파일」 탭에서 템플릿이나 기존 작업을 불러올 수도 있습니다. 스케치를 그리고 「돌출」 을 더하면 입체가
                됩니다.
              </div>
            ) : (
              <ol className="space-y-0.5" onDragLeave={(event) => event.currentTarget === event.target && setDrag((d) => (d ? { ...d, at: null } : d))}>
                {nodes.map((node, i) => {
                  const spec = OP_BY_NAME[node.op]
                  const broken = problems.some((p) => p.includes(`nodes.${i}`) || p.includes(`nodes[${i}]`)) || failedNode === node.id
                  const Icon = spec?.icon
                  return (
                    <li
                      key={node.id}
                      draggable
                      onDragStart={(event) => {
                        event.dataTransfer.effectAllowed = 'move'
                        event.dataTransfer.setData('text/plain', node.id)
                        setDrag({ from: i, allowed: allowedDrops(nodes, i), at: null, refused: null })
                      }}
                      onDragEnd={() => setDrag(null)}
                      onDragOver={(event) => {
                        if (!drag) return
                        event.preventDefault()
                        // 칸의 위 절반이면 이 앞, 아래 절반이면 이 뒤.
                        const box = event.currentTarget.getBoundingClientRect()
                        const to = event.clientY < box.top + box.height / 2 ? i : i + 1
                        const refused = drag.allowed.has(to) ? null : dropProblem(nodes, drag.from, to)
                        event.dataTransfer.dropEffect = refused ? 'none' : 'move'
                        setDrag({ ...drag, at: to, refused })
                      }}
                      onDrop={(event) => {
                        event.preventDefault()
                        if (drag?.at !== null && drag?.at !== undefined) dropNode(drag.at)
                      }}
                      className={`group relative rounded-md ${drag?.from === i ? 'opacity-40' : ''}`}
                    >
                      {/* 놓일 자리 — 막힌 곳은 빨갛게, 되는 곳은 파랗게 */}
                      {drag && drag.at === i && (
                        <span className={`absolute -top-px right-0 left-0 h-0.5 rounded ${drag.refused ? 'bg-destructive' : 'bg-primary'}`} />
                      )}
                      {drag && drag.at === i + 1 && (
                        <span className={`absolute right-0 -bottom-px left-0 h-0.5 rounded ${drag.refused ? 'bg-destructive' : 'bg-primary'}`} />
                      )}
                      <div
                        className={`flex w-full items-center gap-1 rounded-md px-1 py-1 text-sm ${
                          node.id === selectedId ? 'bg-accent' : 'hover:bg-accent/60'
                        } ${broken ? 'text-destructive' : ''}`}
                      >
                        <GripVertical className="text-muted-foreground/40 group-hover:text-muted-foreground size-3.5 shrink-0 cursor-grab" aria-hidden />
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedId(node.id)
                            setEditing(true)
                          }}
                          className="flex min-w-0 flex-1 items-center gap-1 text-left"
                          title={`${spec?.label ?? node.op} — 눌러서 고칩니다`}
                        >
                          <span className="text-muted-foreground w-4 shrink-0 text-[10px]">{i + 1}</span>
                          {Icon && <Icon className="text-muted-foreground size-3.5 shrink-0" aria-hidden />}
                          <span className="truncate">{node.label || spec?.label || node.op}</span>
                          <span className="text-muted-foreground ml-auto truncate font-mono text-[10px] group-hover:hidden">{node.id}</span>
                        </button>
                        {/* 손을 올렸을 때만 — 늘 보이면 목록이 단추 밭이 된다 */}
                        <span className="ml-auto hidden shrink-0 gap-0.5 group-hover:flex">
                          <button
                            type="button"
                            className="hover:bg-background rounded p-1"
                            aria-label={`${node.id} 고치기`}
                            title="고치기"
                            onClick={() => {
                              setSelectedId(node.id)
                              setEditing(true)
                            }}
                          >
                            <Pencil className="size-3.5" />
                          </button>
                          <button
                            type="button"
                            className="hover:bg-destructive/10 text-destructive rounded p-1"
                            aria-label={`${node.id} 지우기`}
                            title="지우기"
                            onClick={() => removeNode(node.id)}
                          >
                            <Trash2 className="size-3.5" />
                          </button>
                        </span>
                      </div>
                    </li>
                  )
                })}
                {/* 맨 끝에 놓기 */}
                <li
                  aria-hidden
                  className="relative h-3"
                  onDragOver={(event) => {
                    if (!drag) return
                    event.preventDefault()
                    const to = nodes.length
                    const refused = drag.allowed.has(to) ? null : dropProblem(nodes, drag.from, to)
                    event.dataTransfer.dropEffect = refused ? 'none' : 'move'
                    setDrag({ ...drag, at: to, refused })
                  }}
                  onDrop={(event) => {
                    event.preventDefault()
                    dropNode(nodes.length)
                  }}
                >
                  {drag?.at === nodes.length && (
                    <span className={`absolute top-0 right-0 left-0 h-0.5 rounded ${drag.refused ? 'bg-destructive' : 'bg-primary'}`} />
                  )}
                </li>
              </ol>
            )}
            {drag?.refused ? (
              <p className="text-destructive mt-1 text-xs">{drag.refused}</p>
            ) : (
              nodes.length > 1 && <p className="text-muted-foreground mt-1 text-xs">끌어서 순서를 바꿉니다. 쓰는 피처는 쓰이는 피처보다 앞설 수 없습니다.</p>
            )}
            {value.result && value.result !== nodes[nodes.length - 1]?.id && <p className="text-muted-foreground mt-2 text-xs">결과 피처: {value.result}</p>}
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
                    ? '면을 누르면 그 면이 이 피처의 평면이 됩니다.'
                    : '뚫을 면을 누르세요. 다시 누르면 뺍니다. 끝나면 피처를 다시 열어 확인하세요.'
                : pickMode === 'edge'
                  ? `엣지를 눌러 고릅니다 (${(selected?.edges as { near?: number[][] })?.near?.length ?? 0} 개). 다시 누르면 뺍니다.`
                  : pickMode === 'measure'
                    ? '측정 중 — 3D 에서 점 · 선 · 면을 누르세요. 값은 오른쪽 창에 나옵니다.'
                    : '끌어서 돌리고, 굴려서 확대합니다. 왼쪽 피처를 누르면 고칩니다.'}
              {edgePicking && pickMode === 'edge' && (
                <button type="button" className="ml-2 underline" onClick={() => setEditing(true)}>
                  피처 열기
                </button>
              )}
            </p>
            {mesh ? (
              <Suspense fallback={<Skeleton className={`${viewerHeight} w-full`} />}>
                <PickViewer
                  mesh={mesh}
                  mode={pickMode}
                  highlightEdgesNear={isNear(selected?.edges) ? (selected!.edges as { near: number[][] }).near : undefined}
                  onPickFace={onFacePicked}
                  onPickEdge={toggleEdge}
                  onMeasure={(pick) => setMeasures((m) => (m.length >= 3 ? [pick] : [...m, pick]))}
                  measureKinds={{ point: measureKinds.has('point'), edge: measureKinds.has('edge'), face: measureKinds.has('face') }}
                  measureMarks={pickMode === 'measure' || kept.length > 0 ? measureMarks(measures, kept) : undefined}
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
                {!summary.is_sketch && ` · 부피 ${summary.volume.toLocaleString()} mm³`} · 면 {summary.face_count} · 피처 {summary.nodes.length}
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
                  {OP_BY_NAME[selected.op]?.label ?? selected.op} <span className="text-muted-foreground font-mono text-xs">{selected.id}</span>
                </DialogTitle>
                <DialogDescription>{OP_BY_NAME[selected.op]?.help}</DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                {selected.op === 'sketch' && <SketchCanvas shapes={(selected.shapes as SketchShape[]) ?? []} onChange={(shapes) => updateNode({ ...selected, shapes })} />}
                <NodeForm node={selected} nodes={nodes} onChange={updateNode} onPickFaces={pickFacesFor} />
                {edgePicking && <p className="text-muted-foreground text-xs">엣지는 3D 에서 고릅니다 — 이 창을 닫고 3D 의 엣지를 누르세요. 고른 것은 남습니다.</p>}
              </div>
              <DialogFooter className="sm:justify-between">
                <div className="flex gap-1">
                  {/* 못 옮기는 방향은 아예 눌리지 않게 하고, 왜인지 말풍선에 적는다. */}
                  <Button size="sm" variant="ghost" disabled={!!moveRefusal(selected.id, -1)} title={moveRefusal(selected.id, -1) ?? '앞으로'} onClick={() => moveNode(selected.id, -1)}>
                    ↑ 앞으로
                  </Button>
                  <Button size="sm" variant="ghost" disabled={!!moveRefusal(selected.id, 1)} title={moveRefusal(selected.id, 1) ?? '뒤로'} onClick={() => moveNode(selected.id, 1)}>
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
