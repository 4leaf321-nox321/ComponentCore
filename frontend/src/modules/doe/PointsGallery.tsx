/**
 * DOE 설계점 형상 보기 — 만든 형상을 **하나씩 · 겹쳐서 · 나란히** 본다.
 *
 * 점이 수백이라 한꺼번에 다 그리지 않는다: 메시는 **고른 점만** 서버에서 받아 오고(받은 것은
 * 들고 있는다), 한 번에 화면에 올리는 수에 상한이 있다 — 겹쳐 보기는 뷰어 하나라 색으로 가를
 * 수 있는 만큼(`MAX_OVERLAY`), 나란히는 한 WebGL 문맥에 칸을 잘라 그리므로(`GridViewer`)
 * 그리는 양이 한계(`MAX_GRID`). 나란히는 카메라가 하나라 돌리면 모두 같이 돈다.
 *
 * 격자는 정사각형 칸으로 1x1 → 2x1 → 2x2 → 3x2 → 3x3 → 4x3 → 4x4 까지 열을 늘리고, 그 뒤는
 * 4열로 세로만 는다(`gridColumns`). 하나씩 볼 때의 ◀ ▶ 는 표 위에 따로 둔다(`PointsNav`).
 */

import { ChevronLeft, ChevronRight } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { doeApi } from '@/modules/doe/api'
import type { DoePoint, DoeStudy, PointMesh } from '@/modules/doe/api'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'
import type { MeshData } from '@/shared/viewer/PickViewer'

const PickViewer = lazy(() => import('@/shared/viewer/PickViewer'))
const GridViewer = lazy(() => import('@/shared/viewer/GridViewer').then((m) => ({ default: m.GridViewer })))

export type GalleryMode = 'single' | 'overlay' | 'grid'
/** 겹쳐 볼 때 한 번에 올리는 점의 수 — 뷰어 하나라 색으로 가를 수 있는 만큼. */
export const MAX_OVERLAY = 12
/** 나란히 볼 때 — 한 문맥에 칸을 잘라 그리므로 그리는 양이 한계다. 4x6 까지. */
export const MAX_GRID = 24

/** 격자의 열 수 — 정사각형에 가깝게 늘리다가 넷에서 멈춘다: 1 · 2 · 2 · 2 · 3 · 3 · 3 · 3 · 3 · 4 … */
export function gridColumns(count: number): number {
  return Math.max(1, Math.min(4, Math.ceil(Math.sqrt(count))))
}
/** 점마다 다른 색 — 겹쳐 보기의 면 색이자 나란히의 표시 색. 열두 개면 서로 가려진다. */
const POINT_COLORS = [0x3b82f6, 0xf97316, 0x10b981, 0xa855f7, 0xef4444, 0x14b8a6, 0xeab308, 0xec4899, 0x6366f1, 0x84cc16, 0x0ea5e9, 0x78716c]
const cssColor = (color: number) => `#${color.toString(16).padStart(6, '0')}`

export const pointLabel = (number: number) => `p${String(number).padStart(4, '0')}`

/** 메시 여럿을 하나로 — 면 · 엣지에 어느 점인지(`part`) 를 붙이고 번호를 이어 준다. */
export function mergeMeshes(items: { label: string; mesh: MeshData }[]): MeshData {
  const faces: MeshData['faces'] = []
  const edges: MeshData['edges'] = []
  let min = [Infinity, Infinity, Infinity]
  let max = [-Infinity, -Infinity, -Infinity]
  for (const { label, mesh } of items) {
    for (const face of mesh.faces) faces.push({ ...face, index: faces.length, part: label })
    for (const edge of mesh.edges) edges.push({ ...edge, index: edges.length, part: label })
    min = min.map((v, i) => Math.min(v, mesh.bbox.min[i]))
    max = max.map((v, i) => Math.max(v, mesh.bbox.max[i]))
  }
  return { bbox: { min, max }, faces, edges }
}

export function PointsGallery({
  study,
  focus,
  picked,
  onPicked,
  mode,
  onMode,
}: {
  study: DoeStudy
  /** 하나씩 볼 때의 점(번호). 표에서 줄을 누르거나 `PointsNav` 가 바꾼다. */
  focus: number | null
  /** 겹쳐 · 나란히 볼 점들(번호). 표의 체크가 고른다. */
  picked: number[]
  onPicked: (next: number[]) => void
  /** 보기 방식 — 표가 체크를 보일지 말지도 이것이 정한다. */
  mode: GalleryMode
  onMode: (next: GalleryMode) => void
}) {
  const [meshes, setMeshes] = useState<Record<number, PointMesh>>({})
  const [loading, setLoading] = useState<Set<number>>(new Set())
  const [failed, setFailed] = useState<Record<number, string>>({})
  const inflight = useRef<Set<number>>(new Set())

  const ready = useMemo(() => study.points.filter((one) => one.status === 'ok').map((one) => one.number), [study.points])

  const load = useCallback(
    async (number: number) => {
      if (meshes[number] || inflight.current.has(number)) return
      inflight.current.add(number)
      setLoading((now) => new Set(now).add(number))
      try {
        const got = await doeApi.pointMesh(study.id, number)
        setMeshes((now) => ({ ...now, [number]: got }))
      } catch (caught) {
        setFailed((now) => ({ ...now, [number]: caught instanceof Error ? caught.message : '못 받았습니다' }))
      } finally {
        inflight.current.delete(number)
        setLoading((now) => {
          const next = new Set(now)
          next.delete(number)
          return next
        })
      }
    },
    [meshes, study.id],
  )

  // 보여야 할 점만 받아 온다 — 모드에 따라 하나, 또는 고른 것들(상한까지).
  const limit = mode === 'grid' ? MAX_GRID : MAX_OVERLAY
  const shown = mode === 'single' ? (focus === null ? [] : [focus]) : picked.slice(0, limit)
  useEffect(() => {
    for (const number of shown) if (ready.includes(number)) void load(number)
  }, [shown, ready, load])

  const colorOf = (number: number) => POINT_COLORS[Math.max(0, picked.indexOf(number)) % POINT_COLORS.length]
  const paramsLine = (number: number) => {
    const point = study.points.find((one) => one.number === number)
    return point ? Object.entries(point.params).map(([k, v]) => `${k} ${v}`).join(' · ') : ''
  }

  const overlay = useMemo(() => {
    const items = shown.filter((n) => meshes[n]).map((n) => ({ label: pointLabel(n), mesh: meshes[n].mesh }))
    return items.length > 0 ? mergeMeshes(items) : null
  }, [shown, meshes])
  const overlayColors = useMemo(() => Object.fromEntries(shown.map((n) => [pointLabel(n), colorOf(n)])), [shown, picked]) // eslint-disable-line react-hooks/exhaustive-deps

  const viewerHeight = 'h-[520px]'
  const gridItems = useMemo(
    () =>
      shown
        .filter((n) => meshes[n] && !failed[n])
        .map((n) => ({
          key: pointLabel(n),
          label: (
            <span className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-full" style={{ background: cssColor(colorOf(n)) }} aria-hidden />
              <span className="font-mono">{pointLabel(n)}</span>
              <span className="text-muted-foreground">{paramsLine(n)}</span>
            </span>
          ),
          mesh: meshes[n].mesh,
        })),
    [shown, meshes, failed], // eslint-disable-line react-hooks/exhaustive-deps
  )

  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium">형상 보기</span>
        <div className="flex gap-1">
          {(
            [
              { value: 'single', label: '하나씩' },
              { value: 'overlay', label: '겹쳐 보기' },
              { value: 'grid', label: '나란히' },
            ] as const
          ).map((one) => (
            <button
              key={one.value}
              type="button"
              onClick={() => onMode(one.value)}
              aria-pressed={mode === one.value}
              className={`rounded-md border px-2 py-1 text-xs ${mode === one.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}
            >
              {one.label}
            </button>
          ))}
        </div>
        {mode === 'single' ? (
          <span className="text-muted-foreground text-xs">오른쪽 표에서 줄을 누르거나 ◀ ▶ 로 넘깁니다. 카메라는 그대로라 견주기 쉽습니다.</span>
        ) : (
          <span className="text-muted-foreground text-xs">
            오른쪽 표의 체크로 고릅니다 — 한 번에 <b>{limit}</b> 개까지 ({picked.length} 고름
            {picked.length > limit && `, 앞 ${limit} 개만 보임`}).{mode === 'grid' && ' 하나를 돌리면 모두 같이 돕니다.'}
            {picked.length > 0 && (
              <button type="button" className="ml-1 underline" onClick={() => onPicked([])}>
                모두 해제
              </button>
            )}
          </span>
        )}
      </div>

      {mode !== 'single' && shown.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {shown.map((n) => (
            <li key={n} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-full" style={{ background: cssColor(colorOf(n)) }} aria-hidden />
              <span className="font-mono">{pointLabel(n)}</span>
              <span className="text-muted-foreground">{paramsLine(n)}</span>
              {loading.has(n) && <span className="text-muted-foreground">받는 중…</span>}
              {failed[n] && <span className="text-destructive">{failed[n]}</span>}
            </li>
          ))}
        </ul>
      )}

      {mode === 'single' &&
        (focus === null ? (
          <Empty height={viewerHeight} text={ready.length === 0 ? '만들어진 형상이 아직 없습니다.' : '표에서 점을 누르세요.'} />
        ) : failed[focus] ? (
          <Empty height={viewerHeight} text={failed[focus]} />
        ) : meshes[focus] ? (
          <Suspense fallback={<Skeleton className={`${viewerHeight} w-full`} />}>
            <PickViewer mesh={meshes[focus].mesh} mode="none" className={`${viewerHeight} w-full rounded-md border`} />
          </Suspense>
        ) : (
          <Skeleton className={`${viewerHeight} w-full`} />
        ))}

      {mode === 'overlay' &&
        (shown.length === 0 ? (
          <Empty height={viewerHeight} text="표에서 견줄 점을 체크하세요 — 같은 자리에 겹쳐 그려 차이가 보입니다." />
        ) : overlay ? (
          <Suspense fallback={<Skeleton className={`${viewerHeight} w-full`} />}>
            <PickViewer mesh={overlay} mode="none" partColors={overlayColors} className={`${viewerHeight} w-full rounded-md border`} />
          </Suspense>
        ) : (
          <Skeleton className={`${viewerHeight} w-full`} />
        ))}

      {mode === 'grid' &&
        (shown.length === 0 ? (
          <Empty height={viewerHeight} text="오른쪽 표에서 나란히 볼 점을 체크하세요." />
        ) : gridItems.length === 0 ? (
          <Skeleton className={`${viewerHeight} w-full`} />
        ) : (
          <div className="max-h-[75vh] overflow-auto">
            <Suspense fallback={<Skeleton className={`${viewerHeight} w-full`} />}>
              <GridViewer items={gridItems} columns={gridColumns(shown.length)} />
            </Suspense>
            {gridItems.length < shown.length && <p className="text-muted-foreground mt-1 text-xs">{shown.length - gridItems.length} 개는 아직 받는 중이거나 실패했습니다.</p>}
          </div>
        ))}

    </div>
  )
}

/** 하나씩 볼 때의 ◀ ▶ — 표 위에 둔다. 만들어진 점만 돈다(실패한 점은 건너뛴다). */
export function PointsNav({ study, focus, onFocus }: { study: DoeStudy; focus: number | null; onFocus: (n: number) => void }) {
  const ready = study.points.filter((one) => one.status === 'ok').map((one) => one.number)
  const point = study.points.find((one) => one.number === focus)
  function step(delta: number) {
    if (ready.length === 0) return
    const at = focus === null ? -1 : ready.indexOf(focus)
    onFocus(ready[(at + delta + ready.length) % ready.length])
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => step(-1)} disabled={ready.length === 0} aria-label="이전 점">
        <ChevronLeft className="size-3.5" />
      </Button>
      <span className="font-mono text-xs">{focus === null ? '—' : pointLabel(focus)}</span>
      <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => step(1)} disabled={ready.length === 0} aria-label="다음 점">
        <ChevronRight className="size-3.5" />
      </Button>
      {ready.length > 0 && (
        <span className="text-muted-foreground ml-auto text-xs">
          {focus === null ? 0 : ready.indexOf(focus) + 1} / {ready.length}
        </span>
      )}
      {point && <span className="text-muted-foreground w-full text-xs">{Object.entries(point.params).map(([k, v]) => `${k} ${v}`).join(' · ')}</span>}
    </div>
  )
}

function Empty({ height, text }: { height: string; text: string }) {
  return <div className={`text-muted-foreground flex ${height} items-center justify-center rounded-md border border-dashed text-sm`}>{text}</div>
}

/** 표의 줄 하나 — 누르면 하나씩 보기의 점, 체크면 겹쳐 · 나란히의 점. */
export function pointRowProps(point: DoePoint, focus: number | null, picked: number[], onFocus: (n: number) => void, onPicked: (next: number[]) => void) {
  const viewable = point.status === 'ok'
  const isPicked = picked.includes(point.number)
  return {
    viewable,
    isFocus: focus === point.number,
    isPicked,
    toggle: () => onPicked(isPicked ? picked.filter((n) => n !== point.number) : [...picked, point.number]),
    focus: () => viewable && onFocus(point.number),
  }
}
