/**
 * DOE 설계점 형상 보기 — 만든 형상을 **하나씩 · 겹쳐서 · 나란히** 본다.
 *
 * 점이 수백이라 한꺼번에 다 그리지 않는다: 메시는 **고른 점만** 서버에서 받아 오고(받은 것은
 * 들고 있는다), 한 번에 화면에 올리는 것은 `MAX_SHOWN` 개까지다 — 브라우저의 WebGL 문맥은
 * 열 몇 개가 한계이고, 겹쳐 보기도 넷을 넘으면 무엇이 무엇인지 안 보인다.
 */

import { ChevronLeft, ChevronRight } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { doeApi } from '@/modules/doe/api'
import type { DoePoint, DoeStudy, PointMesh } from '@/modules/doe/api'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'
import type { MeshData } from '@/shared/viewer/PickViewer'

const PickViewer = lazy(() => import('@/shared/viewer/PickViewer'))

export type GalleryMode = 'single' | 'overlay' | 'grid'
/** 한 번에 올리는 점의 수 — 겹쳐 보기 · 나란히 둘 다. */
export const MAX_SHOWN = 4
/** 겹쳐 볼 때 점마다 다른 색. 나란히에서는 테두리 색으로도 쓴다. */
const POINT_COLORS = [0x3b82f6, 0xf97316, 0x10b981, 0xa855f7]
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
  onFocus,
  picked,
  onPicked,
}: {
  study: DoeStudy
  /** 하나씩 볼 때의 점(번호). 표에서 줄을 누르면 바뀐다. */
  focus: number | null
  onFocus: (number: number) => void
  /** 겹쳐 · 나란히 볼 점들(번호). 표의 체크가 고른다. */
  picked: number[]
  onPicked: (next: number[]) => void
}) {
  const [mode, setMode] = useState<GalleryMode>('single')
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
  const shown = mode === 'single' ? (focus === null ? [] : [focus]) : picked.slice(0, MAX_SHOWN)
  useEffect(() => {
    for (const number of shown) if (ready.includes(number)) void load(number)
  }, [shown, ready, load])

  function step(delta: number) {
    if (ready.length === 0) return
    const at = focus === null ? -1 : ready.indexOf(focus)
    const next = ready[(at + delta + ready.length) % ready.length]
    onFocus(next)
  }

  const colorOf = (number: number) => POINT_COLORS[picked.indexOf(number) % POINT_COLORS.length]
  const paramsLine = (number: number) => {
    const point = study.points.find((one) => one.number === number)
    return point ? Object.entries(point.params).map(([k, v]) => `${k} ${v}`).join(' · ') : ''
  }

  const overlay = useMemo(() => {
    const items = shown.filter((n) => meshes[n]).map((n) => ({ label: pointLabel(n), mesh: meshes[n].mesh }))
    return items.length > 0 ? mergeMeshes(items) : null
  }, [shown, meshes])
  const overlayColors = useMemo(() => Object.fromEntries(shown.map((n) => [pointLabel(n), colorOf(n)])), [shown, picked]) // eslint-disable-line react-hooks/exhaustive-deps

  const viewerHeight = mode === 'grid' ? 'h-[260px]' : 'h-[420px]'

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
              onClick={() => setMode(one.value)}
              aria-pressed={mode === one.value}
              className={`rounded-md border px-2 py-1 text-xs ${mode === one.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}
            >
              {one.label}
            </button>
          ))}
        </div>
        {mode === 'single' ? (
          <>
            <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => step(-1)} disabled={ready.length === 0} aria-label="이전 점">
              <ChevronLeft className="size-3.5" />
            </Button>
            <span className="font-mono text-xs">{focus === null ? '—' : pointLabel(focus)}</span>
            <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => step(1)} disabled={ready.length === 0} aria-label="다음 점">
              <ChevronRight className="size-3.5" />
            </Button>
            <span className="text-muted-foreground text-xs">{focus !== null && paramsLine(focus)}</span>
            <span className="text-muted-foreground ml-auto text-xs">표에서 줄을 누르거나 ◀ ▶ 로 넘깁니다. 카메라는 그대로라 견주기 쉽습니다.</span>
          </>
        ) : (
          <span className="text-muted-foreground text-xs">
            표의 체크로 고릅니다 — 한 번에 <b>{MAX_SHOWN}</b> 개까지 ({picked.length} 고름
            {picked.length > MAX_SHOWN && `, 앞 ${MAX_SHOWN} 개만 보임`}).
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
          <Empty height={viewerHeight} text="표에서 나란히 볼 점을 체크하세요." />
        ) : (
          <div className={`grid gap-2 ${shown.length > 1 ? 'md:grid-cols-2' : ''}`}>
            {shown.map((n) => (
              <div key={n} className="space-y-1">
                <p className="flex items-center gap-1.5 text-xs">
                  <span className="size-2.5 rounded-full" style={{ background: cssColor(colorOf(n)) }} aria-hidden />
                  <span className="font-mono">{pointLabel(n)}</span>
                  <span className="text-muted-foreground">{paramsLine(n)}</span>
                </p>
                {failed[n] ? (
                  <Empty height={viewerHeight} text={failed[n]} />
                ) : meshes[n] ? (
                  <Suspense fallback={<Skeleton className={`${viewerHeight} w-full`} />}>
                    <PickViewer mesh={meshes[n].mesh} mode="none" className={`${viewerHeight} w-full rounded-md border`} />
                  </Suspense>
                ) : (
                  <Skeleton className={`${viewerHeight} w-full`} />
                )}
              </div>
            ))}
          </div>
        ))}
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
